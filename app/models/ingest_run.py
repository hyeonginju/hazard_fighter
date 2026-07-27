"""
ingest_runs: 수집 사이클 실행 이력 — 중복 실행 가드의 상태 저장소.

왜 테이블인가 (2026-07-27, 클라우드 배포 준비):
가드 상태를 프로세스 메모리(모듈 전역 변수)에 두면 인스턴스가 2개 이상일 때 서로의
실행을 모른다. 인스턴스 A 가 "방금 수집했다"고 기억해도 B 는 모르므로 가드가 무력해지고,
그건 곧 공공 API 호출량이 인스턴스 수만큼 배가된다는 뜻이다 (특히 긴급재난문자는
하루 1,000건 한도). 외부 스케줄러로 전환하고 인스턴스를 늘리려면 가드 상태가
"모든 인스턴스가 함께 보는 곳"에 있어야 한다.

겸해서 실행 이력이 남는다 — 언제 몇 건이 들어왔고 어떤 소스가 실패했는지 로그를
grep 하지 않고 조회할 수 있다. finished_at 이 NULL 로 남은 행은 도중에 죽은 사이클이다.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import JsonVariant


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 가드가 매번 읽는 컬럼이라 인덱스 — MAX(started_at) 조회용
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events_ingested: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicates_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notifications_created: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[dict | None] = mapped_column(JsonVariant, nullable=True)  # 소스별 에러 (없으면 NULL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
