from typing import Literal
from pydantic import Field
from app.common.domain import Model


class WordData(Model):
    hanzi: str = Field(min_length=1, max_length=40)
    pinyin: str = Field(min_length=1, max_length=100)
    translation: str = Field(min_length=1, max_length=200)
    hsk_level: int = Field(ge=1, le=6, strict=True)
    example: str = Field(min_length=1, max_length=500)


class WordCommand(Model):
    action: Literal['listen', 'select_level', 'open_canvas', 'mark_learned']
