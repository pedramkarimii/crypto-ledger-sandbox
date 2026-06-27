from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    BalanceBucket,
    LedgerEntryType,
    LedgerTransactionStatus,
    LedgerTransactionType,
    enum_type,
)


class LedgerTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ledger_transactions"

    reference: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
    )
    transaction_type: Mapped[LedgerTransactionType] = mapped_column(
        enum_type(LedgerTransactionType, "ledger_transaction_type"),
        nullable=False,
    )
    status: Mapped[LedgerTransactionStatus] = mapped_column(
        enum_type(LedgerTransactionStatus, "ledger_transaction_status"),
        nullable=False,
        default=LedgerTransactionStatus.POSTED,
        server_default=LedgerTransactionStatus.POSTED.value,
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class LedgerEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "sequence",
            name="transaction_sequence",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    wallet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        enum_type(LedgerEntryType, "ledger_entry_type"),
        nullable=False,
    )
    balance_bucket: Mapped[BalanceBucket] = mapped_column(
        enum_type(BalanceBucket, "balance_bucket"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
