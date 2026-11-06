from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import Field
from app.common.application import create_app
from app.common.auth import actor, Actor
from app.common.domain import Model, fixed_id, page, require
from app.common.storage import repository, Repository

router = APIRouter(tags=['Справочник'])


class UniversityPatch(Model):
    name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)


def seed(repo):
    id = fixed_id('university/demo')
    if not repo.get('university', id, required=False):
        repo.put('university', id, dict(id=id, name='Демонстрационный университет', city='Пекин', description='Учебная запись справочника; сведения не являются рекомендацией для поступления.', demo=True))
    id = fixed_id('exam/demo')
    if not repo.get('exam', id, required=False):
        repo.put('exam', id, dict(id=id, name='HSK — учебный пример', date='2027-06-01', hsk_level=3, city='Москва', demo=True, note='Вымышленная дата для проверки API. Не расписание реального экзамена.'))


@router.get('/exams')
def exams(hsk_level: int | None = Query(default=None, ge=1, le=6), offset: int = Query(default=0, ge=0), count: int = Query(default=20, ge=1, le=100), who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return page([x for x in repo.all('exam') if hsk_level is None or x['hsk_level'] == hsk_level], offset, count)


@router.get('/universities')
def universities(q: str = Query(default='', max_length=100), offset: int = Query(default=0, ge=0), count: int = Query(default=20, ge=1, le=100), who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    return page([x for x in repo.all('university') if q.casefold() in (x['name'] + x['city']).casefold()], offset, count)


@router.patch('/universities/{id}')
def update(id: UUID, data: UniversityPatch, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
    require(who.role == 'admin', 403, 'Требуется роль admin')
    value = repo.get('university', str(id))
    value.update(data.model_dump())
    repo.emit('reference.university.changed', {'university_id': str(id)})
    return repo.put('university', str(id), value)


@router.get('/templates/{name}')
def download(name: Literal['application-letter'], who: Actor = Depends(actor)):
    text = 'Образец учебного письма\n尊敬的老师：\n您好！我想申请贵校的汉语课程。\n谢谢！\n此致\n敬礼\n[Имя студента]\n'
    return Response(text.encode('utf-8'), media_type='text/plain; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="application-letter.txt"'})


app = create_app('Справочник', router, seed)
