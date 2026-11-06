from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class DomainError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def require(condition, status: int, message: str):
    if not condition:
        raise DomainError(status, message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


def fixed_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, 'pr7/' + value))


def uuid_value(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise DomainError(422, 'Ожидается UUID')


Offset = Annotated[int, Field(ge=0)]
Count = Annotated[int, Field(ge=1, le=100)]


def page(items: list, offset: int, count: int) -> dict:
    return dict(items=items[offset:offset + count], total=len(items), offset=offset, count=count)
