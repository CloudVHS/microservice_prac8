from datetime import datetime, timezone
from app.common.auth import hash_password, check_password, sign_token
from app.common.config import settings
from app.common.domain import require, now, new_id, fixed_id
from app.common import client


def public(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != 'password_hash'}


def register(repo, data, role='user'):
    email = data.email.lower()
    require(not any(u['email'] == email for u in repo.all('user')), 409, 'Email уже зарегистрирован')
    user = dict(id=new_id(), email=email, password_hash=hash_password(data.password), display_name=data.display_name, role=role, hsk_level=1, goal='hsk', premium=False, premium_until=None, subscription_id=None, created_at=now())
    repo.put('user', user['id'], user)
    repo.emit('user.profile.changed', {'user_id': user['id'], 'hsk_level': 1, 'goal': 'hsk'})
    return public(user)


def login(repo, data):
    users = [u for u in repo.all('user') if u['email'] == data.email.lower()]
    require(bool(users) and check_password(data.password, users[0]['password_hash']), 401, 'Неверный email или пароль')
    return dict(access_token=sign_token(users[0]), token_type='bearer', expires_in=settings().token_ttl_seconds)


def profile(repo, who):
    require(bool(who.id), 422, 'Нужен X-User-Id для служебного запроса')
    user = repo.get('user', who.id)
    if user['premium_until'] and datetime.fromisoformat(user['premium_until']) <= datetime.now(timezone.utc):
        user['premium'] = False
    return public(user)


async def update(repo, who, data):
    user = repo.get('user', who.id)
    if data.action == 'grant_rights':
        require(user['role'] == 'admin' and who.role == 'admin', 403, 'Права выдает администратор')
        target = repo.get('user', str(data.target_user_id))
        target['role'] = data.role
        repo.put('user', target['id'], target)
        repo.emit('user.rights.granted', {'user_id': target['id'], 'role': target['role']})
        return public(target)
    if data.action == 'subscribe':
        return await client.request('payment', 'POST', '/api/v1/payments', who.id, {'plan_code': 'premium_month'})
    if data.action == 'cancel_subscription':
        subscription = await client.request('payment', 'GET', '/api/v1/subscriptions/me', who.id)
        return await client.request('payment', 'POST', f'/api/v1/payments/{subscription["payment_id"]}/commands', who.id, {'action': 'cancel_subscription'})
    changed = False
    for key in ['display_name', 'hsk_level', 'goal']:
        value = getattr(data, key)
        if value is not None and user[key] != value:
            user[key] = value
            changed = True
    repo.put('user', user['id'], user)
    if changed:
        repo.emit('user.profile.changed', {'user_id': user['id'], 'hsk_level': user['hsk_level'], 'goal': user['goal']})
    return public(user)


def seed(repo):
    from app.user.models import Register
    if not any(u['email'] == 'admin@pr7.local' for u in repo.all('user')):
        register(repo, Register(email='admin@pr7.local', password=settings().demo_admin_password, display_name='Администратор'), role='admin')


def handle_event(repo, event):
    data, kind = event['data'], event['event_type']
    user = repo.get('user', data['user_id'], required=False)
    if not user:
        return
    if kind == 'payment.subscription.activated':
        # Ignore delayed older activation after a later subscription has been applied.
        if not user['premium_until'] or data['expires_at'] >= user['premium_until']:
            user.update(premium=True, premium_until=data['expires_at'], subscription_id=data['subscription_id'])
    elif kind == 'payment.subscription.expired' and user['subscription_id'] == data['subscription_id']:
        user['premium'] = False
    repo.put('user', user['id'], user)
