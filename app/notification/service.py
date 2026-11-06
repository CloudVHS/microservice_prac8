from datetime import datetime, timezone
from app.common.adapters import push
from app.common.auth import owner
from app.common.domain import new_id, now, require


def create(repo, uid, title, text, source='user'):
    value = dict(id=new_id(), user_id=uid, title=title, text=text, source=source, status='created', is_read=False, scheduled_at=None, delivery=None, created_at=now())
    repo.put('notification', value['id'], value)
    return value


def send(repo, value):
    permission = repo.get('permission', value['user_id'], required=False)
    require(permission and permission['allowed'], 403, 'Пользователь не разрешил уведомления')
    if value['status'] != 'sent':
        value.update(status='sent', delivery=push(value))
        repo.put('notification', value['id'], value)
    return value


def command(repo, who, id, data):
    value = repo.get('notification', id)
    owner(value, who)
    if data.action == 'delete':
        repo.delete('notification', id)
        return dict(id=id, status='deleted')
    if data.action == 'schedule':
        require(value['status'] in ['created', 'scheduled'], 409, 'Отправленное уведомление нельзя запланировать')
        require(data.scheduled_at and data.scheduled_at > datetime.now(timezone.utc), 422, 'Нужно будущее время с часовым поясом')
        value.update(status='scheduled', scheduled_at=data.scheduled_at.astimezone(timezone.utc).isoformat())
    elif data.action == 'send':
        return send(repo, value)
    elif data.action == 'read':
        value['is_read'] = True
    return repo.put('notification', id, value)


def handle_event(repo, event):
    kind, data = event['event_type'], event['data']
    messages = {
        'user.profile.changed': ('Профиль обновлен', 'Учебный уровень и цель сохранены.'),
        'payment.subscription.activated': ('Premium активирован', 'Оплата подтверждена. Premium-доступ предоставлен.'),
        'payment.subscription.expired': ('Подписка истекла', 'Продлите подписку для доступа к Premium.'),
        'payment.failed': ('Оплата отклонена', 'Можно создать новую попытку оплаты.'),
        'learning.session.completed': ('Занятие завершено', f'Результат: {data.get("score", 0)}%.'),
    }
    if kind not in messages:
        return
    value = create(repo, data['user_id'], *messages[kind], source=kind)
    permission = repo.get('permission', data['user_id'], required=False)
    if permission and permission['allowed']:
        send(repo, value)


def tick(repo):
    for value in repo.all('notification'):
        if value['status'] == 'scheduled' and datetime.fromisoformat(value['scheduled_at']) <= datetime.now(timezone.utc):
            permission = repo.get('permission', value['user_id'], required=False)
            if permission and permission['allowed']:
                send(repo, value)
