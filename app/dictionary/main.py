from uuid import UUID
from fastapi import APIRouter, Depends, Query
from app.common.application import create_app
from app.common.auth import actor, Actor
from app.common.domain import page, require, new_id
from app.common.storage import repository, Repository
from app.dictionary.models import WordData, WordCommand
from app.dictionary import service

router = APIRouter(tags=['Словарь'])


@router.get('/words')
def search(q: str = Query(default='', max_length=100), hsk_level: int | None = Query(default=None, ge=1, le=6), offset: int = Query(default=0, ge=0), count: int = Query(default=20, ge=1, le=100), who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    words = [service.view(repo, who, w['id']) for w in repo.all('word') if (hsk_level is None or w['hsk_level'] == hsk_level) and (not q or q.casefold() in (w['hanzi'] + ' ' + w['pinyin'] + ' ' + w['translation']).casefold())]
    return page(words, offset, count)


@router.get('/words/{id}')
def word(id: UUID, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return service.view(repo, who, str(id))


@router.post('/words/{id}/commands')
async def command(id: UUID, data: WordCommand, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return await service.command(repo, who, str(id), data)


@router.post('/words', status_code=201)
def create(data: WordData, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    require(who.role == 'admin', 403, 'Требуется роль admin')
    require(not any(w['hanzi'] == data.hanzi for w in repo.all('word')), 409, 'Слово уже есть')
    id = new_id()
    return repo.put('word', id, dict(id=id, **data.model_dump()))


app = create_app('Словарь', router, service.seed, service.handle_event)
