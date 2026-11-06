from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text, select, func
from app.common.config import settings
from app.common.domain import DomainError
from app.common.messaging import Bus
from app.common.storage import Sessions, Repository, Outbox


def create_app(name: str, router, seed=lambda repo: None, handler=lambda repo, event: None, tick=lambda repo: None):
    bus = Bus(handler, tick)

    @asynccontextmanager
    async def lifespan(app):
        with Sessions.begin() as session:
            seed(Repository(session))
        await bus.start()
        yield
        await bus.stop()

    app = FastAPI(title=f'ПР7 · {name}', version='1.0.0', lifespan=lifespan,
                  description='Учебная система китайского языка. Демонстрационные внешние адаптеры. Авторизация: Bearer-токен из User Service; служебные вызовы: X-Service-Token и X-User-Id.')
    app.include_router(router, prefix='/api/v1')

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status, content={'detail': exc.message})

    @app.get('/health', tags=['Infrastructure'])
    def health():
        with Sessions() as session:
            session.execute(text('SELECT 1'))
            pending = session.scalar(select(func.count()).select_from(Outbox).where(Outbox.sent.is_(False)))
        connected = bool(bus.connection and bus.connection.connected.is_set())
        ready = connected or not settings().amqp_url
        return JSONResponse(status_code=200 if ready else 503, content=dict(service=name, status='ok' if ready else 'degraded', database='ok', broker='connected' if connected else 'offline', pending_events=pending))

    return app
