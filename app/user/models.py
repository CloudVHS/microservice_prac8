from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.common.domain import Model


class Register(Model):
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=200)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class Login(Model):
    email: str
    password: str


class UserPatch(Model):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    hsk_level: int | None = Field(default=None, ge=1, le=6, strict=True)
    goal: Literal['tourism', 'study', 'work', 'hsk'] | None = None
    action: Literal['grant_rights', 'subscribe', 'cancel_subscription'] | None = None
    target_user_id: UUID | None = None
    role: Literal['user', 'admin'] | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set or any(getattr(self, k) is None for k in self.model_fields_set):
            raise ValueError('Укажите непустые изменяемые поля')
        if self.action == 'grant_rights':
            if not self.target_user_id or not self.role:
                raise ValueError('Для выдачи прав нужны target_user_id и role')
        elif self.target_user_id or self.role:
            raise ValueError('Права изменяются только командой grant_rights')
        return self
