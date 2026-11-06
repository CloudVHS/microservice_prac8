# tests/unit/test_user_service.py
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.user import service
from app.user.models import Login, Register, UserPatch


class FakeRepo:
    """Локальная замена Repository: хранение в словаре, события в списке."""

    def __init__(self):
        self.items: dict[tuple[str, str], dict] = {}
        self.events: list[tuple[str, dict]] = []

    def all(self, kind):
        return [v for (k, _), v in self.items.items() if k == kind]

    def get(self, kind, item_id, required=True):
        item = self.items.get((kind, str(item_id)))
        if item is None and required:
            raise KeyError(item_id)
        return item

    def put(self, kind, item_id, item):
        self.items[(kind, str(item_id))] = item

    def emit(self, event_type, data):
        self.events.append((event_type, data))


class FakePaymentClient:
    """Заменяет межсервисный HTTP-клиент: запоминает вызовы."""

    def __init__(self):
        self.calls = []

    async def request(self, target, method, path, user_id, body=None):
        self.calls.append((target, method, path, user_id, body))
        if method == 'GET':
            return {'payment_id': 'pay-1', 'type': 'premium'}
        return {'status': 'ok'}


@pytest.fixture()
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture()
def payment(monkeypatch) -> FakePaymentClient:
    fake = FakePaymentClient()
    monkeypatch.setattr(service, 'client', fake)
    return fake


def registration(email='User@Example.com', name='Студент'):
    return Register(email=email, password='password123', display_name=name)


def actor_for(user: dict):
    return SimpleNamespace(id=user['id'], role=user['role'])


def http_status(exc: Exception):
    for name in ('status_code', 'status', 'code'):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            return value
    return exc.args[0] if exc.args else None


def register_user(repo, **kwargs) -> dict:
    return service.register(repo, registration(**kwargs))


def run(coro):
    return asyncio.run(coro)


def test_register_returns_public_profile(repo):
    user = register_user(repo)
    assert 'password_hash' not in user
    assert user['hsk_level'] == 1
    assert user['goal'] == 'hsk'
    assert user['premium'] is False
    assert user['role'] == 'user'


def test_register_normalizes_email_and_hashes_password(repo):
    user = register_user(repo, email='User@Example.com')
    stored = repo.get('user', user['id'])
    assert stored['email'] == 'user@example.com'
    assert stored['password_hash'] != 'password123'


def test_register_emits_profile_changed_event(repo):
    user = register_user(repo)
    assert repo.events == [('user.profile.changed',
                            {'user_id': user['id'], 'hsk_level': 1, 'goal': 'hsk'})]


def test_register_duplicate_email_conflict(repo):
    register_user(repo, email='dup@example.com')
    with pytest.raises(Exception) as err:
        register_user(repo, email='DUP@example.com')
    assert http_status(err.value) == 409
    assert len(repo.all('user')) == 1


def test_login_success_returns_bearer_token(repo):
    register_user(repo, email='a@example.com')
    session = service.login(repo, Login(email='A@example.com', password='password123'))
    assert session['token_type'] == 'bearer'
    assert session['access_token']
    assert session['expires_in'] > 0


def test_login_wrong_password(repo):
    register_user(repo, email='a@example.com')
    with pytest.raises(Exception) as err:
        service.login(repo, Login(email='a@example.com', password='wrong-password'))
    assert http_status(err.value) == 401


def test_login_unknown_email(repo):
    with pytest.raises(Exception) as err:
        service.login(repo, Login(email='nobody@example.com', password='password123'))
    assert http_status(err.value) == 401


def test_profile_hides_password_hash(repo):
    user = register_user(repo)
    profile = service.profile(repo, actor_for(user))
    assert profile['id'] == user['id']
    assert 'password_hash' not in profile


def test_profile_revokes_expired_premium(repo):
    user = register_user(repo)
    stored = repo.get('user', user['id'])
    stored['premium'] = True
    stored['premium_until'] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert service.profile(repo, actor_for(user))['premium'] is False


def test_profile_keeps_active_premium(repo):
    user = register_user(repo)
    stored = repo.get('user', user['id'])
    stored['premium'] = True
    stored['premium_until'] = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    assert service.profile(repo, actor_for(user))['premium'] is True


def test_update_profile_fields_and_event(repo):
    user = register_user(repo)
    repo.events.clear()
    result = run(service.update(repo, actor_for(user),
                                UserPatch(hsk_level=4, goal='work')))
    assert result['hsk_level'] == 4
    assert result['goal'] == 'work'
    assert repo.events == [('user.profile.changed',
                            {'user_id': user['id'], 'hsk_level': 4, 'goal': 'work'})]


def test_update_same_values_does_not_emit_event(repo):
    user = register_user(repo)
    repo.events.clear()
    run(service.update(repo, actor_for(user), UserPatch(hsk_level=1, goal='hsk')))
    assert repo.events == []


def test_update_display_name_only_emits_event_once(repo):
    user = register_user(repo)
    repo.events.clear()
    result = run(service.update(repo, actor_for(user), UserPatch(display_name='Новое имя')))
    assert result['display_name'] == 'Новое имя'
    assert len(repo.events) == 1


def test_grant_rights_forbidden_for_regular_user(repo):
    user = register_user(repo, email='u1@example.com')
    other = register_user(repo, email='u2@example.com')
    patch = UserPatch(action='grant_rights', target_user_id=other['id'], role='admin')
    with pytest.raises(Exception) as err:
        run(service.update(repo, actor_for(user), patch))
    assert http_status(err.value) == 403
    assert repo.get('user', other['id'])['role'] == 'user'


def test_grant_rights_by_admin(repo):
    admin = service.register(repo, registration(email='root@example.com'), role='admin')
    other = register_user(repo, email='u2@example.com')
    repo.events.clear()
    patch = UserPatch(action='grant_rights', target_user_id=other['id'], role='admin')
    result = run(service.update(repo, actor_for(admin), patch))
    assert result['role'] == 'admin'
    assert repo.events == [('user.rights.granted',
                            {'user_id': other['id'], 'role': 'admin'})]


def test_subscribe_calls_payment_service(repo, payment):
    user = register_user(repo)
    run(service.update(repo, actor_for(user), UserPatch(action='subscribe')))
    assert payment.calls == [('payment', 'POST', '/api/v1/payments', user['id'],
                              {'plan_code': 'premium_month'})]


def test_cancel_subscription_calls_payment_service(repo, payment):
    user = register_user(repo)
    run(service.update(repo, actor_for(user), UserPatch(action='cancel_subscription')))
    assert [c[1] for c in payment.calls] == ['GET', 'POST']
    assert payment.calls[1][2] == '/api/v1/payments/pay-1/commands'
    assert payment.calls[1][4] == {'action': 'cancel_subscription'}


def event(kind, user_id, **data):
    return {'event_type': kind, 'data': {'user_id': user_id, **data}}


def test_event_subscription_activated_grants_premium(repo):
    user = register_user(repo)
    until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    service.handle_event(repo, event('payment.subscription.activated', user['id'],
                                     expires_at=until, subscription_id='s1'))
    stored = repo.get('user', user['id'])
    assert stored['premium'] is True
    assert stored['premium_until'] == until
    assert stored['subscription_id'] == 's1'


def test_event_older_activation_is_ignored(repo):
    user = register_user(repo)
    now = datetime.now(timezone.utc)
    late = (now + timedelta(days=60)).isoformat()
    early = (now + timedelta(days=30)).isoformat()
    service.handle_event(repo, event('payment.subscription.activated', user['id'],
                                     expires_at=late, subscription_id='new'))
    service.handle_event(repo, event('payment.subscription.activated', user['id'],
                                     expires_at=early, subscription_id='old'))
    assert repo.get('user', user['id'])['premium_until'] == late
    assert repo.get('user', user['id'])['subscription_id'] == 'new'


def test_event_expired_revokes_premium(repo):
    user = register_user(repo)
    until = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    service.handle_event(repo, event('payment.subscription.activated', user['id'],
                                     expires_at=until, subscription_id='s1'))
    service.handle_event(repo, event('payment.subscription.expired', user['id'],
                                     subscription_id='s1'))
    assert repo.get('user', user['id'])['premium'] is False


def test_event_expired_of_foreign_subscription_is_ignored(repo):
    user = register_user(repo)
    until = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    service.handle_event(repo, event('payment.subscription.activated', user['id'],
                                     expires_at=until, subscription_id='current'))
    service.handle_event(repo, event('payment.subscription.expired', user['id'],
                                     subscription_id='stale'))
    assert repo.get('user', user['id'])['premium'] is True


def test_event_for_unknown_user_is_ignored(repo):
    service.handle_event(repo, event('payment.subscription.expired',
                                     '00000000-0000-0000-0000-000000000000',
                                     subscription_id='s1'))
    assert repo.all('user') == []


def test_seed_creates_single_admin(repo):
    service.seed(repo)
    service.seed(repo)
    admins = [u for u in repo.all('user') if u['email'] == 'admin@pr7.local']
    assert len(admins) == 1
    assert admins[0]['role'] == 'admin'
