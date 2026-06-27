from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import SessionDependency, get_current_active_user
from app.models.asset import Asset
from app.models.enums import WalletOwnerType
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.balances import WalletBalanceResponse, WalletBalancesResponse

router = APIRouter(prefix="/wallets", tags=["Wallets"])
CurrentUserDependency = Annotated[User, Depends(get_current_active_user)]


@router.get("", response_model=WalletBalancesResponse)
async def list_wallet_balances(
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> WalletBalancesResponse:
    rows = (
        await session.execute(
            select(Wallet, Asset)
            .join(Asset, Wallet.asset_id == Asset.id)
            .where(
                Wallet.owner_type == WalletOwnerType.USER,
                Wallet.user_id == current_user.id,
            )
            .order_by(Asset.code)
        )
    ).all()

    balances = [
        WalletBalanceResponse(
            asset_code=asset.code,
            available_balance=wallet.available_balance,
            locked_balance=wallet.locked_balance,
            total_balance=wallet.available_balance + wallet.locked_balance,
        )
        for wallet, asset in rows
    ]
    return WalletBalancesResponse(balances=balances)
