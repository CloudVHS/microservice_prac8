"""Shared mechanics; each bounded context supplies its own tasks and commands."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import Field
from app.common import client
from app.common.auth import Actor, actor, owner
from app.common.adapters import grade, audio_preview
from app.common.domain import Model, require, new_id, fixed_id, now
from app.common.storage import Repository, repository


class StartSession(Model):
    topic: str = Field(default='basic', min_length=1, max_length=100)


class Answer(Model):
    task_id: UUID
    text: str = Field(min_length=1, max_length=2000)


class SessionCommand(Model):
    action: Literal['build_sequence', 'start_session', 'finish_session', 'view_lexicon', 'view_rules', 'send_ai_request', 'generate_grammar', 'request_audio', 'start_audio', 'play_audio', 'finish_audio', 'start_translation', 'translate', 'finish_translation']
    answers: list[Answer] | None = Field(default=None, min_length=1, max_length=20)


def task(context, level, index, prompt, answers):
    return dict(id=fixed_id(f'{context}/{level}/{index}'), prompt=prompt, accepted_answers=answers, hsk_level=level)


class LearningService:
    def __init__(self, context, tasks, commands, rules=None):
        self.context, self.task_factory, self.commands = context, tasks, commands
        self.rules = rules or []

    def expose(self, session):
        return {**session, 'tasks': [{k: v for k, v in t.items() if k != 'accepted_answers'} for t in session['tasks']]}

    async def catalog(self, repo, who):
        profile = await client.request('user', 'GET', '/api/v1/users/me', who.id)
        tasks = self.task_factory(profile['hsk_level'])
        return dict(context=self.context, hsk_level=profile['hsk_level'], goal=profile['goal'], tasks=[{k: v for k, v in t.items() if k != 'accepted_answers'} for t in tasks], progress=repo.get('progress', who.id, required=False) or dict(completed_sessions=0, learned_words=0, best_score=0))

    async def create(self, repo, who, data):
        profile = await client.request('user', 'GET', '/api/v1/users/me', who.id)
        # Nested service function call: router -> create -> profile HTTP -> task builder -> repository.
        tasks = self.task_factory(profile['hsk_level'])
        value = dict(id=new_id(), user_id=who.id, context=self.context, topic=data.topic, hsk_level=profile['hsk_level'], goal=profile['goal'], status='created', tasks=tasks, created_at=now(), completed_at=None, assessment=None, audio_state='none', translation_state='none', ai_requested=False, generated_rules=None)
        repo.put('session', value['id'], value)
        repo.emit(f'{self.context}.sequence.built', dict(user_id=who.id, session_id=value['id']))
        return self.expose(value)

    def get(self, repo, who, id):
        value = repo.get('session', id)
        owner(value, who)
        return value

    def assess(self, session, data):
        require(data.answers is not None, 422, 'Нужны answers для каждого задания')
        answers = {str(x.task_id): x.text for x in data.answers}
        require(len(answers) == len(data.answers), 422, 'Повторяющийся task_id')
        require(set(answers) == {t['id'] for t in session['tasks']}, 422, 'Ответы должны точно соответствовать заданиям сессии')
        return grade(session['tasks'], answers)

    def command(self, repo, who, id, data):
        require(data.action in self.commands, 422, 'Команда не относится к этому сервису')
        value = self.get(repo, who, id)
        action = data.action
        if action == 'finish_session' and value['status'] == 'completed':
            return self.expose(value)
        if action == 'build_sequence':
            require(value['status'] == 'created', 409, 'Последовательность уже используется')
            return self.expose(value)
        if action == 'start_session':
            require(value['status'] == 'created', 409, 'Сессия уже начата')
            value['status'] = 'active'
        else:
            require(value['status'] == 'active', 409, 'Требуется активная сессия')
            if action == 'view_lexicon':
                return dict(session_id=id, tasks=self.expose(value)['tasks'])
            elif action == 'view_rules':
                return dict(session_id=id, rules=self.rules)
            elif action == 'send_ai_request':
                value['assessment'] = self.assess(value, data)
                value['ai_requested'] = True
            elif action == 'generate_grammar':
                require(value['ai_requested'], 409, 'Сначала отправьте AI-запрос с ответами')
                value['generated_rules'] = dict(adapter='local-grammar-template', rules=self.rules, feedback='Повторите правила для ошибочных ответов' if not value['assessment']['passed'] else 'Все условия перехода выполнены')
            elif action == 'request_audio':
                value['audio_state'] = 'requested'
            elif action == 'start_audio':
                require(value['audio_state'] == 'requested', 409, 'Сначала запросите аудио')
                value['audio_state'] = 'started'
            elif action == 'play_audio':
                require(value['audio_state'] in ['started', 'played'], 409, 'Сначала начните аудиоупражнение')
                value['audio_state'] = 'played'
                repo.put('session', id, value)
                return audio_preview('你好，谢谢')
            elif action == 'finish_audio':
                require(value['audio_state'] == 'played', 409, 'Сначала воспроизведите аудио')
                value['audio_state'] = 'completed'
            elif action == 'start_translation':
                require(value['translation_state'] == 'none', 409, 'Упражнение перевода уже начато')
                value['translation_state'] = 'started'
            elif action == 'translate':
                require(value['translation_state'] in ['started', 'submitted'], 409, 'Сначала начните перевод')
                # Store actual learner answers; local adapter checks them on send_ai_request.
                self.assess(value, data)
                value['translation_answers'] = [x.model_dump(mode='json') for x in data.answers]
                value['translation_state'] = 'submitted'
            elif action == 'finish_translation':
                require(value['translation_state'] == 'submitted' and value['assessment'] and value['assessment']['passed'], 409, 'Сначала отправьте перевод на проверку и наберите 70%')
                value['translation_state'] = 'completed'
            elif action == 'finish_session':
                if self.context == 'lexicon':
                    value['assessment'] = self.assess(value, data)
                require(value['assessment'] and value['assessment']['passed'], 409, 'Для завершения нужно не менее 70%')
                if self.context == 'practice':
                    require(value['audio_state'] == 'completed' and value['translation_state'] == 'completed', 409, 'Завершите аудио и перевод')
                value.update(status='completed', completed_at=now())
                repo.emit('learning.session.completed', dict(user_id=who.id, session_id=id, context=self.context, score=value['assessment']['score'], hsk_level=value['hsk_level']))
        if self.context == 'practice' and action == 'send_ai_request':
            require(value['translation_state'] == 'submitted', 409, 'Сначала отправьте перевод')
            require([x.model_dump(mode='json') for x in data.answers] == value['translation_answers'], 422, 'Проверяться должны отправленные ответы перевода')
        repo.put('session', id, value)
        repo.emit(f'{self.context}.{action}', dict(user_id=who.id, session_id=id))
        return self.expose(value)


def learning_router(service):
    router = APIRouter(tags=[service.context])

    @router.get('/tasks')
    async def tasks(who: Actor = Depends(actor), repo: Repository = Depends(repository)):
        return await service.catalog(repo, who)

    @router.post('/sessions', status_code=201)
    async def create(data: StartSession, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
        return await service.create(repo, who, data)

    @router.get('/sessions/{id}')
    def get(id: UUID, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
        return service.expose(service.get(repo, who, str(id)))

    @router.post('/sessions/{id}/commands')
    def command(id: UUID, data: SessionCommand, who: Actor = Depends(actor), repo: Repository = Depends(repository)):
        return service.command(repo, who, str(id), data)

    return router
