from fastapi import APIRouter, Depends
from app.common.auth import Actor, actor
from app.common.storage import repository, Repository
from app.common.application import create_app
from app.user.models import Register, Login, UserPatch
from app.user import service

router = APIRouter(tags=['Пользователь'])


@router.post('/users', status_code=201)
def register(data: Register, repo: Repository = Depends(repository)):
    return service.register(repo, data)


@router.post('/sessions', status_code=201)
def login(data: Login, repo: Repository = Depends(repository)):
    return service.login(repo, data)


@router.get('/users/me')
def profile(who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return service.profile(repo, who)


@router.patch('/users/me')
async def update(data: UserPatch, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return await service.update(repo, who, data)


app = create_app('Пользователь', router, service.seed, service.handle_event)
