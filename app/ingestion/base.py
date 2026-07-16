"""
데이터 소스별 ingestion 클라이언트가 공통으로 따르는 인터페이스.
project-spec.md 6절(데이터 소스), 8절(시스템 아키텍처 — Ingestion Layer) 참고.

API 키가 없으면 fetch()는 자동으로 mock 데이터를 반환한다 — 키가 아직 없어도
DB 스키마·위험도 판단 로직·API 엔드포인트를 지금 바로 개발/테스트할 수 있게 하기 위함.
키가 생기면 .env에 값만 채우면 실제 호출로 자동 전환된다 (_fetch_live 참고).
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NormalizedEvent(BaseModel):
    """모든 소스가 이 공통 스키마로 정규화된 뒤 events 테이블에 적재된다."""

    source: str  # enums.EventSource 값
    event_type: str  # enums.EventType 값
    severity: str | None = None  # enums.Severity 값 (지진은 magnitude를 대신 씀)
    magnitude: float | None = None  # 지진 전용, 규모
    region_sido: str | None = None
    region_sigungu: str | None = None
    station_code: str | None = None  # 홍수통제소 관측소 코드 (홍수특보 전용)
    occurred_at: datetime
    raw_payload: dict[str, Any]


class BaseIngestionClient(ABC):
    source: str

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def fetch(self) -> list[NormalizedEvent]:
        if not self.api_key:
            return self._fetch_mock()
        return self._fetch_live()

    @abstractmethod
    def _fetch_mock(self) -> list[NormalizedEvent]:
        """API 키 없이도 개발할 수 있도록 하는 고정 mock 응답."""
        raise NotImplementedError

    @abstractmethod
    def _fetch_live(self) -> list[NormalizedEvent]:
        """실제 API 호출. 키 발급 후 첫 실행에서 실제 응답 필드명을 확인하고 다듬어야 한다."""
        raise NotImplementedError
