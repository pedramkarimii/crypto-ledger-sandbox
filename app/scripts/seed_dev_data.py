from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.models.asset import Asset
from app.models.enums import WalletOwnerType
from app.models.wallet import Wallet
from app.services.ledger import TREASURY_ACCOUNT


async def main() -> None:
    settings = get_settings()
    if settings.ENVIRONMENT != "development":
        raise RuntimeError("Development seed is disabled outside development.")

    async with AsyncSessionFactory() as session:
        asset = await session.scalar(select(Asset).where(Asset.code == "USDT"))
        if asset is None:
            asset = Asset(
                code="USDT",
                name="Tether USD",
                precision=6,
            )
            session.add(asset)
            await session.flush()

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
                available_balance=Decimal("1000000"),
                locked_balance=Decimal("0"),
            )
            session.add(treasury_wallet)
            await session.commit()
            print("Development USDT treasury created with 1000000.000000 balance.")
            return

        await session.commit()
        print("Development USDT treasury already exists.")
