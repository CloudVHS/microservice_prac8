from datetime import datetime, timedelta, timezone
from app.common.auth import owner, internal
from app.common.domain import require, now, new_id
from app.common import client

PLANS = {'premium_month': {'title': 'Premium на 30 дней', 'amount': '299.00', 'currency': 'RUB', 'days': 30}}


async def create(repo, who, data, key):
    require(bool(who.id), 422, 'Не задан пользователь')
    if key:
        old = repo.get('idempotency', who.id + ':' + key, required=False)
        if old:
            require(old['plan_code'] == data.plan_code, 409, 'Ключ уже использован для другого запроса')
            return repo.get('payment', old['payment_id']), False
    await client.request('user', 'GET', '/api/v1/users/me', who.id)
    plan = PLANS[data.plan_code]
    payment = dict(id=new_id(), user_id=who.id, plan_code=data.plan_code, amount=plan['amount'], currency=plan['currency'], status='pending', provider_transaction_id=None, adapter='local-demo-acquiring', created_at=now())
    repo.put('payment', payment['id'], payment)
    if key:
        repo.put('idempotency', who.id + ':' + key, dict(payment_id=payment['id'], plan_code=data.plan_code))
    repo.emit('payment.created', dict(user_id=who.id, payment_id=payment['id']))
    return payment, True


def subscription(repo, who):
    value = repo.get('subscription', who.id)
    owner(value, who)
    return value


def command(repo, who, id, data):
    payment = repo.get('payment', id)
    if data.action in ['confirm', 'fail', 'expire_subscription']:
        internal(who)
    else:
        owner(payment, who)
    if data.action == 'confirm':
        require(bool(data.provider_transaction_id), 422, 'Нужен provider_transaction_id')
        if payment['status'] == 'confirmed':
            require(payment['provider_transaction_id'] == data.provider_transaction_id, 409, 'Платеж подтвержден другой транзакцией')
            return payment
        require(payment['status'] == 'pending', 409, 'Подтвердить можно только ожидающий платеж')
        require(not any(p['provider_transaction_id'] == data.provider_transaction_id for p in repo.all('payment')), 409, 'Транзакция уже использована')
        payment.update(status='confirmed', provider_transaction_id=data.provider_transaction_id)
        previous = repo.get('subscription', payment['user_id'], required=False)
        start = datetime.now(timezone.utc)
        if previous and previous['status'] == 'active':
            start = max(start, datetime.fromisoformat(previous['expires_at']))
        value = dict(id=new_id(), user_id=payment['user_id'], payment_id=id, plan_code=payment['plan_code'], status='active', auto_renew=True, expires_at=(start + timedelta(days=30)).isoformat())
        repo.put('subscription', value['user_id'], value)
        repo.emit('payment.subscription.activated', dict(user_id=value['user_id'], subscription_id=value['id'], payment_id=id, expires_at=value['expires_at']))
    elif data.action == 'fail':
        require(payment['status'] == 'pending', 409, 'Платеж уже обработан')
        payment['status'] = 'failed'
        repo.emit('payment.failed', dict(user_id=payment['user_id'], payment_id=id))
    else:
        value = repo.get('subscription', payment['user_id'])
        require(value['payment_id'] == id, 409, 'Этот платеж не соответствует текущей подписке')
        if data.action == 'cancel_subscription':
            value['auto_renew'] = False
            # Already-paid access is valid until expires_at.
        else:
            require(datetime.fromisoformat(value['expires_at']) <= datetime.now(timezone.utc), 409, 'Срок подписки еще не истек')
            expire(repo, value)
        repo.put('subscription', value['user_id'], value)
        return value
    return repo.put('payment', id, payment)


def expire(repo, value):
    if value['status'] == 'active':
        value.update(status='expired', auto_renew=False)
        repo.put('subscription', value['user_id'], value)
        repo.emit('payment.subscription.expired', dict(user_id=value['user_id'], subscription_id=value['id']))


def tick(repo):
    for value in repo.all('subscription'):
        if value['status'] == 'active' and datetime.fromisoformat(value['expires_at']) <= datetime.now(timezone.utc):
            expire(repo, value)
