from app.common.application import create_app
from app.common.learning import learning_router
from app.lexicon.service import service, handle_event

app = create_app('Лексика', learning_router(service), handler=handle_event)
