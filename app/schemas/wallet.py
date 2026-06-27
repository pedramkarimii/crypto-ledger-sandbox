from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class FundingRequest(BaseModel):
    asset_code: str = Field(
        min_length=2,
        max_length=16,
        pattern="^[A-Za-z0-9]+$",
    )
    amount: Decimal = Field(
        gt=Decimal("0"),
        max_digits=38,
        decimal_places=18,
    )


class FundingResponse(BaseModel):
    transaction_id: UUID
    reference: str
    asset_code: str
    amount: Decimal
    replayed: bool
