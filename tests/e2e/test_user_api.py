# tests/e2e/test_user_api.py
import os
import time
from uuid import uuid4

import pytest
import requests

BASE_URL = os.getenv('USER_SERVICE_URL', 'http://localhost:8001')
API = f'{BASE_URL}/api/v1'
PASSWORD = 'password123'


@pytest.fixture(scope='session', autouse=True)
def service_is_ready():
    """Ждём готовности контейнера: GET /health проверяет БД и брокер."""
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if requests.get(f'{BASE_URL}/health', timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    pytest.fail('User service не запустился за 60 секунд')


def new_email() -> str:
    return f'e2e-{uuid4().hex[:12]}@example.com'


def register(email=None, password=PASSWORD, name='E2E User'):
    return requests.post(f'{API}/users', json={
        'email': email or new_email(), 'password': password, 'display_name': name})


def login(email, password=PASSWORD):
    return requests.post(f'{API}/sessions', json={'email': email, 'password': password})


@pytest.fixture()
def credentials():
    email = new_email()
    assert register(email).status_code == 201
    return email


@pytest.fixture()
def auth(credentials) -> dict:
    token = login(credentials).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_health():
    response = requests.get(f'{BASE_URL}/health')
    assert response.status_code == 200


def test_register_success():
    email = new_email()
    response = register(email, name='Иван')
    assert response.status_code == 201
    body = response.json()
    assert body['email'] == email
    assert body['display_name'] == 'Иван'
    assert body['hsk_level'] == 1
    assert body['goal'] == 'hsk'
    assert body['premium'] is False
    assert 'password' not in body and 'password_hash' not in body


def test_register_duplicate_email(credentials):
    assert register(credentials).status_code == 409


@pytest.mark.parametrize('payload', [
    {'email': 'not-an-email', 'password': PASSWORD, 'display_name': 'x'},
    {'email': 'a@example.com', 'password': 'short', 'display_name': 'x'},
    {'email': 'a@example.com', 'password': PASSWORD, 'display_name': ''},
    {'email': 'a@example.com'},
])
def test_register_validation_error(payload):
    assert requests.post(f'{API}/users', json=payload).status_code == 422


def test_login_success(credentials):
    response = login(credentials)
    assert response.status_code == 201
    body = response.json()
    assert body['token_type'] == 'bearer'
    assert body['access_token']


def test_login_wrong_password(credentials):
    assert login(credentials, 'wrong-password').status_code == 401


def test_login_unknown_user():
    assert login(new_email()).status_code == 401


def test_profile_requires_token():
    assert requests.get(f'{API}/users/me').status_code in (401, 403)


def test_profile_with_invalid_token():
    headers = {'Authorization': 'Bearer invalid.token'}
    assert requests.get(f'{API}/users/me', headers=headers).status_code in (401, 403)


def test_profile_success(credentials, auth):
    response = requests.get(f'{API}/users/me', headers=auth)
    assert response.status_code == 200
    assert response.json()['email'] == credentials


def test_patch_profile_persists(auth):
    response = requests.patch(f'{API}/users/me', headers=auth,
                              json={'hsk_level': 3, 'goal': 'tourism'})
    assert response.status_code == 200
    assert response.json()['hsk_level'] == 3
    profile = requests.get(f'{API}/users/me', headers=auth).json()
    assert profile['hsk_level'] == 3
    assert profile['goal'] == 'tourism'


@pytest.mark.parametrize('payload', [
    {}, {'hsk_level': 0}, {'hsk_level': 7}, {'hsk_level': '3'},
    {'goal': 'fun'}, {'display_name': None},
])
def test_patch_validation_error(auth, payload):
    response = requests.patch(f'{API}/users/me', headers=auth, json=payload)
    assert response.status_code == 422


def test_regular_user_cannot_grant_rights(auth):
    profile = requests.get(f'{API}/users/me', headers=auth).json()
    response = requests.patch(f'{API}/users/me', headers=auth, json={
        'action': 'grant_rights', 'target_user_id': profile['id'], 'role': 'admin'})
    assert response.status_code == 403
    assert requests.get(f'{API}/users/me', headers=auth).json()['role'] == 'user'


@pytest.mark.skipif(not os.getenv('DEMO_ADMIN_PASSWORD'),
                    reason='не задан пароль демонстрационного администратора')
def test_admin_can_grant_rights(credentials):
    admin = login('admin@pr7.local', os.environ['DEMO_ADMIN_PASSWORD'])
    assert admin.status_code == 201
    headers = {'Authorization': f"Bearer {admin.json()['access_token']}"}
    user_id = requests.get(
        f'{API}/users/me',
        headers={'Authorization': f"Bearer {login(credentials).json()['access_token']}"},
    ).json()['id']
    response = requests.patch(f'{API}/users/me', headers=headers, json={
        'action': 'grant_rights', 'target_user_id': user_id, 'role': 'admin'})
    assert response.status_code == 200
    assert response.json()['role'] == 'admin'
