from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event
from app.schemas.event import EventRead
from app.services.ingest import run_ingestion_cycle_guarded

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/ingest")
def ingest_events(db: Session = Depends(get_db)) -> dict:
    """
    기상특보/지진/홍수특보 소스를 한 번 폴링해서 저장하고, 매칭되는 구독에
    대해 위험도를 평가한다 (project-spec.md 8절 파이프라인 참고).
    API 키가 없는 소스는 자동으로 mock 데이터를 쓴다.

    평상시엔 내장 스케줄러(app/scheduler.py)가 10분마다 자동 실행하므로 수동 호출은
    디버깅용. 중복 실행 가드가 있어 최근 수집(기본 3분) 직후 재호출은 스킵된다
    ("skipped": true 응답) — 공공 API 호출량 낭비 방지.
    """
    return run_ingestion_cycle_guarded(db)


@router.get("", response_model=list[EventRead])
def list_events(limit: int = 50, db: Session = Depends(get_db)):
    stmt = select(Event).order_by(Event.occurred_at.desc()).limit(limit)
    return list(db.scalars(stmt))
