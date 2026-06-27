from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import OrderSide, OrderStatus


class OrderCreateRequest(BaseModel):
    base_asset_code: str = Field(
        min_length=2,
        max_length=16,
        pattern="^[A-Za-z0-9]+$",
    )
    quote_asset_code: str = Field(
        min_length=2,
        max_length=16,
        pattern="^[A-Za-z0-9]+$",
    )
    side: OrderSide
    price: Decimal = Field(
        gt=Decimal("0"),
        max_digits=38,
        decimal_places=18,
    )
    quantity: Decimal = Field(
        gt=Decimal("0"),
        max_digits=38,
        decimal_places=18,
    )


class OrderResponse(BaseModel):
    id: UUID
    base_asset_code: str
    quote_asset_code: str
    side: OrderSide
    status: OrderStatus
    price: Decimal
    quantity: Decimal
    remaining_quantity: Decimal
    reserved_asset_code: str
    reserved_amount: Decimal
    reservation_transaction_id: UUID
    replayed: bool
