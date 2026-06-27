from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import SessionDependency, get_current_active_user
from app.models.asset import Asset
from app.models.user import User
from app.schemas.order import OrderCreateRequest, OrderResponse
from app.services import orders as order_service
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


def build_order_response(
    *,
    order: object,
    base_asset: Asset,
    quote_asset: Asset,
    reserve_asset: Asset,
    replayed: bool,
) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        base_asset_code=base_asset.code,
        quote_asset_code=quote_asset.code,
        side=order.side,
        status=order.status,
        price=order.price,
        quantity=order.quantity,
        remaining_quantity=order.remaining_quantity,
        reserved_asset_code=reserve_asset.code,
        reserved_amount=order.reserved_amount,
        reservation_transaction_id=order.reservation_transaction_id,
        replayed=replayed,
    )


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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if result.replayed:
        response.status_code = status.HTTP_200_OK

    return build_order_response(
        order=result.order,
        base_asset=result.base_asset,
        quote_asset=result.quote_asset,
        reserve_asset=result.reserve_asset,
        replayed=result.replayed,
    )


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> OrderResponse:
    try:
        result = await order_service.cancel_order_reservation(
            session,
            user_id=current_user.id,
            order_id=order_id,
        )
    except order_service.OrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order was not found.",
        ) from exc
    except (
        order_service.OrderNotCancelableError,
        order_service.OrderReservationStateError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order cannot be canceled in its current state.",
        ) from exc

    base_asset = await session.scalar(
        select(Asset).where(Asset.id == result.order.base_asset_id)
    )
    quote_asset = await session.scalar(
        select(Asset).where(Asset.id == result.order.quote_asset_id)
    )
    if base_asset is None or quote_asset is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order assets are unavailable.",
        )

    return build_order_response(
        order=result.order,
        base_asset=base_asset,
        quote_asset=quote_asset,
        reserve_asset=result.reserve_asset,
        replayed=result.replayed,
    )
