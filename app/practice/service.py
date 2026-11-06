from app.common.learning import LearningService, task


def tasks(level):
    return [task('practice', level, 1, 'Переведите на китайский: Привет.', ['你好']), task('practice', level, 2, 'Переведите на китайский: Спасибо.', ['谢谢']), task('practice', level, 3, 'Переведите на русский: 我学习汉语。', ['Я изучаю китайский язык', 'Я учу китайский язык'])]


service = LearningService('practice', tasks, {'build_sequence', 'start_session', 'finish_session', 'request_audio', 'start_audio', 'play_audio', 'finish_audio', 'start_translation', 'translate', 'send_ai_request', 'finish_translation'})
