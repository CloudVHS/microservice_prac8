from uuid import UUID
from fastapi import APIRouter, Depends, Query
from app.common.application import create_app
from app.common.auth import actor, Actor
from app.common.domain import page
from app.common.storage import repository, Repository
from app.notification.models import Permission, CreateNotification, NotificationCommand
from app.notification import service

router = APIRouter(tags=['Уведомление'])


@router.post('/notification-permissions')
def permission(data: Permission, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return repo.put('permission', who.id, dict(user_id=who.id, allowed=data.allowed))


@router.post('/notifications', status_code=201)
def create(data: CreateNotification, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return service.create(repo, who.id, data.title, data.text)


@router.get('/notifications')
def list_notifications(is_read: bool | None = None, offset: int = Query(default=0, ge=0), count: int = Query(default=20, ge=1, le=100), who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    items = [x for x in repo.all('notification') if x['user_id'] == who.id and (is_read is None or x['is_read'] == is_read)]
    return page(items, offset, count)


@router.post('/notifications/{id}/commands')
def command(id: UUID, data: NotificationCommand, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return service.command(repo, who, str(id), data)


app = create_app('Уведомление', router, handler=service.handle_event, tick=service.tick)
