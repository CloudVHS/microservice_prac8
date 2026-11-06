from typing import Literal
from pydantic import Field
from app.common.domain import Model


class CreatePayment(Model):
    plan_code: Literal['premium_month'] = 'premium_month'


class PaymentCommand(Model):
    action: Literal['confirm', 'fail', 'cancel_subscription', 'expire_subscription']
    provider_transaction_id: str | None = Field(default=None, min_length=1, max_length=100)
