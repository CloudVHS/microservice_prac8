from app.common.application import create_app
from app.common.learning import learning_router
from app.practice.service import service

app = create_app('Практика', learning_router(service))
