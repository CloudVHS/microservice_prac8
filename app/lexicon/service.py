from app.common.learning import LearningService, task
from app.common.domain import now


def tasks(level):
    return [task('lexicon', level, 1, 'Переведите 你好', ['привет', 'здравствуйте']), task('lexicon', level, 2, 'Переведите 谢谢', ['спасибо']), task('lexicon', level, 3, 'Переведите 学习', ['учиться', 'изучать'])]


service = LearningService('lexicon', tasks, {'build_sequence', 'start_session', 'finish_session', 'view_lexicon'})


def handle_event(repo, event):
    data = event['data']
    uid = data['user_id']
    value = repo.get('progress', uid, required=False) or dict(user_id=uid, completed_sessions=0, learned_words=0, best_score=0, hsk_level=1, goal='hsk', history=[])
    if event['event_type'] == 'user.profile.changed':
        value.update(hsk_level=data['hsk_level'], goal=data['goal'])
    elif event['event_type'] == 'learning.session.completed':
        value['completed_sessions'] += 1
        value['best_score'] = max(value['best_score'], data['score'])
        value['history'].append(dict(session_id=data['session_id'], context=data['context'], score=data['score'], completed_at=event['occurred_at']))
    elif event['event_type'] == 'learning.word.learned':
        value['learned_words'] += 1
    value['updated_at'] = now()
    repo.put('progress', uid, value)
