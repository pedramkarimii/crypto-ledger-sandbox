from enum import StrEnum

from sqlalchemy import Enum as SQLAlchemyEnum


def enum_type(enum_class: type[StrEnum], name: str) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
    )


class WalletOwnerType(StrEnum):
    USER = "user"
    SYSTEM = "system"


class LedgerTransactionType(StrEnum):
    FUNDING = "funding"
    ORDER_RESERVE = "order_reserve"
    ORDER_RELEASE = "order_release"
    TRADE = "trade"


class LedgerTransactionStatus(StrEnum):
    POSTED = "posted"
    REVERSED = "reversed"


class LedgerEntryType(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class BalanceBucket(StrEnum):
    AVAILABLE = "available"
    LOCKED = "locked"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    OPEN = "open"
    CANCELED = "canceled"
    FILLED = "filled"
