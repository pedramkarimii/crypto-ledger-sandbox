from sqlalchemy import Boolean, CheckConstraint, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("code = upper(code)", name="code_uppercase"),
        CheckConstraint("precision >= 0 AND precision <= 18", name="precision_range"),
    )

    code: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    precision: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
