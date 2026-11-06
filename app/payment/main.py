from uuid import UUID
from fastapi import APIRouter, Depends, Header, Response
from app.common.application import create_app
from app.common.auth import Actor, actor, owner
from app.common.storage import Repository, repository
from app.payment.models import CreatePayment, PaymentCommand
from app.payment import service

router = APIRouter(tags=['Оплата'])


@router.post('/payments', status_code=201)
async def create(data: CreatePayment, response: Response, idempotency_key: str | None = Header(default=None, min_length=1, max_length=100), who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    value, created = await service.create(repo, who, data, idempotency_key)
    response.status_code = 201 if created else 200
    return value


@router.get('/payments/{id}')
def get(id: UUID, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    value = repo.get('payment', str(id))
    owner(value, who)
    return value


@router.post('/payments/{id}/commands')
def command(id: UUID, data: PaymentCommand, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return service.command(repo, who, str(id), data)


@router.get('/subscriptions/me')
def subscription(who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return service.subscription(repo, who)


app = create_app('Оплата', router, tick=service.tick)
