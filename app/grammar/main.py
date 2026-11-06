from app.common.application import create_app
from app.common.learning import learning_router
from app.grammar.service import service

app = create_app('Грамматика', learning_router(service))
