import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import (
    device_tokens,
    events,
    health,
    notifications,
    persons,
    regions,
    subscriptions,
)
from app.config import get_settings
from app.logging_utils import setup_secret_redaction
from app.scheduler import ingest_loop

logging.basicConfig(level=logging.INFO)
setup_secret_redaction()  # httpx 등 로그에 API 키가 노출되지 않게 마스킹


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 수집 스케줄러를 백그라운드로 띄우고, 종료 시 정리한다."""
    task: asyncio.Task | None = None
    if get_settings().scheduler_enabled:
        task = asyncio.create_task(ingest_loop())
    yield
    if task is not None:
        task.cancel()


app = FastAPI(
    title="시켜줘, 명예소방관 API",
    description="공공데이터 기반 개인 맞춤형 이상상황 알림 플랫폼 — Phase 1 뼈대",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(persons.router)
app.include_router(regions.router)
app.include_router(subscriptions.router)
app.include_router(events.router)
app.include_router(notifications.router)
app.include_router(device_tokens.router)
