"""Each process owns a separate database; no cross-service SQL access."""
import copy
from pathlib import Path
from sqlalchemy import JSON, Boolean, Column, Integer, String, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.common.config import settings
from app.common.domain import DomainError, new_id, now


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = 'records'
    kind = Column(String(60), primary_key=True)
    id = Column(String(120), primary_key=True)
    payload = Column(JSON, nullable=False)


class Outbox(Base):
    __tablename__ = 'outbox'
    sequence = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(36), unique=True, nullable=False)
    routing_key = Column(String(120), nullable=False)
    payload = Column(JSON, nullable=False)
    sent = Column(Boolean, default=False, nullable=False)


class Inbox(Base):
    __tablename__ = 'inbox'
    event_id = Column(String(36), primary_key=True)


def make_engine(url: str):
    if url.startswith('sqlite:///'):
        filename = url.removeprefix('sqlite:///')
        if filename != ':memory:':
            Path(filename).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {})
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def pragmas(connection, _):
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA foreign_keys=ON')
    return engine


engine = make_engine(settings().database_url)
Sessions = sessionmaker(engine, expire_on_commit=False)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, kind: str, id: str, required: bool = True) -> dict | None:
        row = self.session.get(Record, (kind, str(id)))
        if row is None:
            if required:
                raise DomainError(404, f'{kind}: объект не найден')
            return None
        return copy.deepcopy(row.payload)

    def all(self, kind: str) -> list[dict]:
        return [copy.deepcopy(x.payload) for x in self.session.scalars(select(Record).where(Record.kind == kind).order_by(Record.id))]

    def put(self, kind: str, id: str, payload: dict) -> dict:
        row = self.session.get(Record, (kind, str(id)))
        if row is None:
            self.session.add(Record(kind=kind, id=str(id), payload=copy.deepcopy(payload)))
        else:
            row.payload = copy.deepcopy(payload)
        self.session.flush()
        return payload

    def delete(self, kind: str, id: str):
        self.get(kind, id)
        self.session.delete(self.session.get(Record, (kind, str(id))))

    def emit(self, routing_key: str, data: dict):
        id = new_id()
        body = dict(event_id=id, event_type=routing_key, source=settings().service_name, occurred_at=now(), data=data)
        self.session.add(Outbox(event_id=id, routing_key=routing_key, payload=body))


def repository():
    with Sessions.begin() as session:
        yield Repository(session)
