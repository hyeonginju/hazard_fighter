import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    auth,
    device_tokens,
    events,
    health,
    notifications,
    persons,
    regions,
    subscriptions,
    web,
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


_docs = get_settings().docs_enabled

app = FastAPI(
    title="시켜줘, 명예소방관 API",
    description="공공데이터 기반 개인 맞춤형 이상상황 알림 플랫폼 — Phase 1 뼈대",
    version="0.1.0",
    lifespan=lifespan,
    # 프로덕션(DOCS_ENABLED=0)에선 셋 다 없앤다. openapi_url 을 같이 끄지 않으면
    # /docs 만 404 가 되고 스키마는 그대로 열려 있어 막은 의미가 없다.
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(persons.router)
app.include_router(regions.router)
app.include_router(subscriptions.router)
app.include_router(events.router)
app.include_router(notifications.router)
app.include_router(device_tokens.router)
app.include_router(web.router)

# 웹 PWA 정적 파일 (css/js/manifest/아이콘). 화면 자체는 GET /app 이 서빙한다.
app.mount("/static", StaticFiles(directory=web.STATIC_DIR), name="static")
