from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.api.deps import SessionDependency, get_current_active_user
from app.models.user import User
from app.schemas.order import OrderCreateRequest, OrderResponse
from app.services.orders import (
    InsufficientAvailableBalanceError,
    OrderAssetNotFoundError,
    OrderIdempotencyConflictError,
    create_order_reservation,
)

router = APIRouter(prefix="/orders", tags=["Orders"])

CurrentUserDependency = Annotated[User, Depends(get_current_active_user)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreateRequest,
    response: Response,
    idempotency_key: IdempotencyKey,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> OrderResponse:
    try:
        result = await create_order_reservation(
            session,
            user_id=current_user.id,
            base_asset_code=payload.base_asset_code,
            quote_asset_code=payload.quote_asset_code,
            side=payload.side,
            price=payload.price,
            quantity=payload.quantity,
            idempotency_key=idempotency_key,
        )
    except OrderAssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested asset was not found.",
        ) from exc
    except InsufficientAvailableBalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Insufficient available balance for this order.",
        ) from exc
    except OrderIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used with different order data.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    if result.replayed:
        response.status_code = status.HTTP_200_OK

    return OrderResponse(
        id=result.order.id,
        base_asset_code=result.base_asset.code,
        quote_asset_code=result.quote_asset.code,
        side=result.order.side,
        status=result.order.status,
        price=result.order.price,
        quantity=result.order.quantity,
        remaining_quantity=result.order.remaining_quantity,
        reserved_asset_code=result.reserve_asset.code,
        reserved_amount=result.order.reserved_amount,
        reservation_transaction_id=result.order.reservation_transaction_id,
        replayed=result.replayed,
    )
