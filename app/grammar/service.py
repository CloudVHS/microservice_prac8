from app.common.learning import LearningService, task


def tasks(level):
    return [task('grammar', level, 1, 'Переведите: Я изучаю китайский язык.', ['我学习汉语', '我学汉语']), task('grammar', level, 2, 'Вставьте отрицание: 我___是老师。', ['不']), task('grammar', level, 3, 'Составьте вопрос: 你是学生___？', ['吗'])]


service = LearningService('grammar', tasks,
    {'build_sequence', 'start_session', 'finish_session', 'send_ai_request', 'generate_grammar', 'view_rules'},
    rules=['Порядок слов: подлежащее + сказуемое + дополнение.', '不 ставится перед глаголом для отрицания.', '吗 в конце предложения превращает утверждение в общий вопрос.'])
