from datetime import datetime
from typing import Literal
from pydantic import Field, AwareDatetime
from app.common.domain import Model


class Permission(Model):
    allowed: bool = Field(strict=True)


class CreateNotification(Model):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=1000)


class NotificationCommand(Model):
    action: Literal['schedule', 'send', 'read', 'delete']
    scheduled_at: AwareDatetime | None = None
