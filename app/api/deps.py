from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.user import User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)

CredentialsDependency = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_active_user(
    credentials: CredentialsDependency,
    session: SessionDependency,
) -> User:
    if credentials is None:
        raise authentication_error()

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = UUID(str(payload.get("sub")))
    except (jwt.InvalidTokenError, TypeError, ValueError) as exc:
        raise authentication_error() from exc

    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise authentication_error()

    return user
