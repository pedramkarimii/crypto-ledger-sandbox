from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
CurrentUserDependency = Annotated[User, Depends(get_current_active_user)]


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: CurrentUserDependency,
) -> User:
    return current_user
