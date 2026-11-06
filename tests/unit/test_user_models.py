# tests/unit/test_user_models.py
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.user.models import Login, Register, UserPatch


def make_register(**changes) -> dict:
    data = {'email': 'student@example.com', 'password': 'password123',
            'display_name': 'Студент'}
    data.update(changes)
    return data


def test_register_valid():
    user = Register(**make_register())
    assert user.email == 'student@example.com'
    assert user.display_name == 'Студент'


@pytest.mark.parametrize('email', ['', 'plain', 'a@b', '@example.com',
                                   'a b@example.com', 'a@@example.com'])
def test_register_invalid_email(email):
    with pytest.raises(ValidationError):
        Register(**make_register(email=email))


@pytest.mark.parametrize('password', ['', '1234567', 'x' * 129])
def test_register_invalid_password_length(password):
    with pytest.raises(ValidationError):
        Register(**make_register(password=password))


@pytest.mark.parametrize('password', ['12345678', 'x' * 128])
def test_register_password_length_boundaries(password):
    assert Register(**make_register(password=password)).password == password


@pytest.mark.parametrize('name', ['', 'x' * 81])
def test_register_invalid_display_name(name):
    with pytest.raises(ValidationError):
        Register(**make_register(display_name=name))


@pytest.mark.parametrize('field', ['email', 'password', 'display_name'])
def test_register_required_fields(field):
    data = make_register()
    del data[field]
    with pytest.raises(ValidationError):
        Register(**data)


def test_login_requires_both_fields():
    assert Login(email='a@b.c', password='p').password == 'p'
    with pytest.raises(ValidationError):
        Login(email='a@b.c')


@pytest.mark.parametrize('level', [1, 3, 6])
def test_patch_hsk_level_valid(level):
    assert UserPatch(hsk_level=level).hsk_level == level


@pytest.mark.parametrize('level', [0, 7, -1])
def test_patch_hsk_level_out_of_range(level):
    with pytest.raises(ValidationError):
        UserPatch(hsk_level=level)


def test_patch_hsk_level_is_strict():
    with pytest.raises(ValidationError):
        UserPatch(hsk_level='3')


@pytest.mark.parametrize('goal', ['tourism', 'study', 'work', 'hsk'])
def test_patch_goal_valid(goal):
    assert UserPatch(goal=goal).goal == goal


def test_patch_goal_unknown_value():
    with pytest.raises(ValidationError):
        UserPatch(goal='fun')


def test_patch_empty_body_rejected():
    with pytest.raises(ValidationError):
        UserPatch()


def test_patch_explicit_null_rejected():
    with pytest.raises(ValidationError):
        UserPatch(display_name=None)


def test_patch_unknown_action_rejected():
    with pytest.raises(ValidationError):
        UserPatch(action='delete_everything')


@pytest.mark.parametrize('action', ['subscribe', 'cancel_subscription'])
def test_patch_payment_actions_valid(action):
    assert UserPatch(action=action).action == action


def test_patch_grant_rights_valid():
    target = uuid4()
    patch = UserPatch(action='grant_rights', target_user_id=target, role='admin')
    assert patch.target_user_id == target
    assert patch.role == 'admin'


def test_patch_grant_rights_requires_target_and_role():
    with pytest.raises(ValidationError):
        UserPatch(action='grant_rights', role='admin')
    with pytest.raises(ValidationError):
        UserPatch(action='grant_rights', target_user_id=uuid4())


def test_patch_role_without_grant_rights_rejected():
    with pytest.raises(ValidationError):
        UserPatch(role='admin')
    with pytest.raises(ValidationError):
        UserPatch(target_user_id=uuid4(), display_name='Имя')


def test_patch_invalid_role_rejected():
    with pytest.raises(ValidationError):
        UserPatch(action='grant_rights', target_user_id=uuid4(), role='root')


def test_patch_target_must_be_uuid():
    with pytest.raises(ValidationError):
        UserPatch(action='grant_rights', target_user_id='not-uuid', role='user')
