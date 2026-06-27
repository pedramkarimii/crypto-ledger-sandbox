from decimal import Decimal

from pydantic import BaseModel


class WalletBalanceResponse(BaseModel):
    asset_code: str
    available_balance: Decimal
    locked_balance: Decimal
    total_balance: Decimal


class WalletBalancesResponse(BaseModel):
    balances: list[WalletBalanceResponse]
