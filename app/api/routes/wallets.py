from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.api.deps import SessionDependency, get_current_active_user
from app.core.config import get_settings
from app.models.user import User
from app.schemas.wallet import FundingRequest, FundingResponse
from app.services.ledger import (
    AssetNotFoundError,
    IdempotencyConflictError,
    InsufficientTreasuryBalanceError,
    TreasuryNotInitializedError,
    post_sandbox_funding,
)

router = APIRouter(prefix="/wallets", tags=["Wallets"])
settings = get_settings()

CurrentUserDependency = Annotated[User, Depends(get_current_active_user)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


@router.post(
    "/fund",
    response_model=FundingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def fund_sandbox_wallet(
    payload: FundingRequest,
    response: Response,
    idempotency_key: IdempotencyKey,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> FundingResponse:
    if settings.ENVIRONMENT != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sandbox funding is available only in development.",
        )

    try:
        result = await post_sandbox_funding(
            session,
            user_id=current_user.id,
            asset_code=payload.asset_code,
            amount=payload.amount,
            idempotency_key=idempotency_key,
        )
    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested asset was not found.",
        ) from exc
    except TreasuryNotInitializedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox treasury is not initialized.",
        ) from exc
    except InsufficientTreasuryBalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox treasury has insufficient balance.",
        ) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used with different data.",
        ) from exc

    if result.replayed:
        response.status_code = status.HTTP_200_OK

    return FundingResponse(
        transaction_id=result.transaction.id,
        reference=result.transaction.reference,
        asset_code=result.asset.code,
        amount=payload.amount,
        replayed=result.replayed,
    )
