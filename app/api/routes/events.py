from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event
from app.schemas.event import EventRead
from app.services.ingest import run_ingestion_cycle

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/ingest")
def ingest_events(db: Session = Depends(get_db)) -> dict:
    """
    기상특보/지진/홍수특보 소스를 한 번 폴링해서 저장하고, 매칭되는 구독에
    대해 위험도를 평가한다 (project-spec.md 8절 파이프라인 참고).
    API 키가 없는 소스는 자동으로 mock 데이터를 쓴다.
    운영에서는 Cloud Scheduler가 이 엔드포인트를 주기 호출하게 될 예정 (Phase 3).
    """
    return run_ingestion_cycle(db)


@router.get("", response_model=list[EventRead])
def list_events(limit: int = 50, db: Session = Depends(get_db)):
    stmt = select(Event).order_by(Event.occurred_at.desc()).limit(limit)
    return list(db.scalars(stmt))
