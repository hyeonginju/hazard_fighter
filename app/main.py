from fastapi import FastAPI

from app.api.routes import events, health, notifications, persons, regions, subscriptions

app = FastAPI(
    title="시켜줘, 명예소방관 API",
    description="공공데이터 기반 개인 맞춤형 이상상황 알림 플랫폼 — Phase 1 뼈대",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(persons.router)
app.include_router(regions.router)
app.include_router(subscriptions.router)
app.include_router(events.router)
app.include_router(notifications.router)
