"""Health-check and readiness endpoints.

GET /health      — lightweight liveness probe (no DB/Redis touch)
GET /health/ready — readiness probe (checks DB + Redis connectivity)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
async def readiness():
    errors: dict[str, str] = {}

    # Check DB
    try:
        from aiblock.core.db import get_session
        from sqlalchemy import text
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        errors["database"] = str(exc)

    # Check Redis
    try:
        from aiblock.core.cache import get_redis
        await get_redis().ping()
    except Exception as exc:
        errors["redis"] = str(exc)

    if errors:
        return JSONResponse(status_code=503, content={"status": "degraded", "errors": errors})

    return {"status": "ready"}
