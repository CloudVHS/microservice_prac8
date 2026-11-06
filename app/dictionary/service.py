from app.common.domain import require, fixed_id, new_id
from app.common.adapters import audio_preview
from app.common import client

WORDS = [
    ('你好', 'nǐ hǎo', 'привет', 1, '你好！我叫安德烈。'),
    ('谢谢', 'xièxie', 'спасибо', 1, '谢谢你的帮助。'),
    ('学习', 'xuéxí', 'учиться', 1, '我学习汉语。'),
    ('朋友', 'péngyou', 'друг', 2, '他是我的朋友。'),
    ('旅游', 'lǚyóu', 'путешествовать', 3, '我喜欢旅游。'),
    ('经验', 'jīngyàn', 'опыт', 4, '他有很多经验。'),
    ('效率', 'xiàolǜ', 'эффективность', 5, '我们提高效率。'),
    ('潜力', 'qiánlì', 'потенциал', 6, '这个项目有潜力。'),
]


def seed(repo):
    for hanzi, pinyin, translation, level, example in WORDS:
        id = fixed_id('word/' + hanzi)
        if not repo.get('word', id, required=False):
            repo.put('word', id, dict(id=id, hanzi=hanzi, pinyin=pinyin, translation=translation, hsk_level=level, example=example))


def view(repo, who, id):
    word = repo.get('word', id)
    word['learned'] = repo.get('learned', who.id + ':' + id, required=False) is not None
    return word


async def command(repo, who, id, data):
    word = view(repo, who, id)
    if data.action == 'listen':
        return audio_preview(word['hanzi'])
    if data.action == 'open_canvas':
        return dict(word_id=id, hanzi=word['hanzi'], example=word['example'], canvas={'width': 600, 'height': 400, 'background': 'rice-grid', 'strokes': []}, event='dictionary.canvas.opened')
    if data.action == 'select_level':
        return await client.request('user', 'PATCH', '/api/v1/users/me', who.id, {'hsk_level': word['hsk_level']})
    if not word['learned']:
        repo.put('learned', who.id + ':' + id, dict(user_id=who.id, word_id=id))
        repo.emit('learning.word.learned', dict(user_id=who.id, word_id=id, hsk_level=word['hsk_level']))
    return view(repo, who, id)


def handle_event(repo, event):
    d = event['data']
    repo.put('learned', d['user_id'] + ':' + d['word_id'], dict(user_id=d['user_id'], word_id=d['word_id']))
