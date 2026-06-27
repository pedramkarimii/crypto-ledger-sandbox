from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WalletOwnerType, enum_type


class Wallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_id", name="user_asset"),
        UniqueConstraint(
            "system_account",
            "asset_id",
            name="system_account_asset",
        ),
        CheckConstraint(
            "((owner_type = 'user' AND user_id IS NOT NULL "
            "AND system_account IS NULL) OR "
            "(owner_type = 'system' AND user_id IS NULL "
            "AND system_account IS NOT NULL))",
            name="valid_owner",
        ),
        CheckConstraint(
            "available_balance >= 0",
            name="available_balance_non_negative",
        ),
        CheckConstraint(
            "locked_balance >= 0",
            name="locked_balance_non_negative",
        ),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    owner_type: Mapped[WalletOwnerType] = mapped_column(
        enum_type(WalletOwnerType, "wallet_owner_type"),
        nullable=False,
    )
    system_account: Mapped[str | None] = mapped_column(String(32), nullable=True)
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    locked_balance: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
