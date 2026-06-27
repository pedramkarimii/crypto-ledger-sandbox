from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.auth import router as auth_router
from app.api.routes.me import router as me_router
from app.core.config import get_settings
from app.db.session import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.2.0",
    description=(
        "A production-style crypto trading sandbox. "
        "It does not connect to real exchanges or handle real funds."
    ),
    lifespan=lifespan,
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(me_router, prefix="/api/v1")


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    return {"message": "Crypto Ledger Sandbox API", "docs": "/docs"}


@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "service": settings.PROJECT_NAME,
    }


@app.get("/health/ready", tags=["System"])
async def readiness() -> dict[str, str]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return {"status": "ready", "database": "connected"}
