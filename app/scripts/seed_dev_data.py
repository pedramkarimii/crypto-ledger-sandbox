from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.models.asset import Asset
from app.models.enums import WalletOwnerType
from app.models.wallet import Wallet
from app.services.ledger import TREASURY_ACCOUNT

DEVELOPMENT_ASSETS = (
    ("USDT", "Tether USD", 6, Decimal("1000000")),
    ("BTC", "Bitcoin", 8, Decimal("1000")),
)


async def main() -> None:
    settings = get_settings()
    if settings.ENVIRONMENT != "development":
        raise RuntimeError("Development seed is disabled outside development.")

    created = []

    async with AsyncSessionFactory() as session:
        for code, name, precision, treasury_amount in DEVELOPMENT_ASSETS:
            asset = await session.scalar(select(Asset).where(Asset.code == code))
            if asset is None:
                asset = Asset(
                    code=code,
                    name=name,
                    precision=precision,
                )
                session.add(asset)
                await session.flush()
                created.append(f"{code} asset")

            treasury_wallet = await session.scalar(
                select(Wallet).where(
                    Wallet.owner_type == WalletOwnerType.SYSTEM,
                    Wallet.system_account == TREASURY_ACCOUNT,
                    Wallet.asset_id == asset.id,
                )
            )
            if treasury_wallet is None:
                treasury_wallet = Wallet(
                    asset_id=asset.id,
                    owner_type=WalletOwnerType.SYSTEM,
                    system_account=TREASURY_ACCOUNT,
                    available_balance=treasury_amount,
                    locked_balance=Decimal("0"),
                )
                session.add(treasury_wallet)
                created.append(f"{code} treasury")

        await session.commit()

    if created:
        print(f"Development seed created: {', '.join(created)}.")
    else:
        print("Development assets and treasuries already exist.")
