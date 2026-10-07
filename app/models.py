import datetime as dt
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer, model_validator

# Деньги внутри — Decimal (без ошибок округления float), в JSON — обычное число.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class Payment(str, Enum):
    cash = "cash"
    card = "card"


class TripIn(BaseModel):
    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)

    id: str = Field(min_length=1, max_length=64)
    # AwareDatetime отклоняет время без смещения: без него нельзя определить день поездки.
    start: AwareDatetime
    end: AwareDatetime
    amount: Annotated[Money, Field(gt=0, max_digits=12, decimal_places=2)]
    payment: Payment
    commission: Annotated[Money, Field(ge=0, max_digits=12, decimal_places=2)]

    @model_validator(mode="after")
    def check_consistency(self) -> "TripIn":
        if self.end <= self.start:
            raise ValueError("окончание поездки должно быть позже начала")
        if self.commission > self.amount:
            raise ValueError("комиссия не может быть больше суммы поездки")
        return self


class Trip(TripIn):
    # День поездки: дата начала в её собственном часовом поясе.
    local_date: dt.date


class PaymentTotals(BaseModel):
    trips: int
    revenue: Money


class Summary(BaseModel):
    date: dt.date
    trips: int
    revenue: Money
    commission: Money
    net: Money
    cash: PaymentTotals
    card: PaymentTotals
