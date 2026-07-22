from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.engine import get_business_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    try:
        yield
    finally:
        if get_business_engine.cache_info().currsize:
            await get_business_engine().dispose()
            get_business_engine.cache_clear()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": settings.app_name, "docs": "/docs"}
