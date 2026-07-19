"""
앱 전역 설정. .env 파일에서 값을 읽어온다.
project-spec.md 11절(기술 스택) 참고.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://hazard:hazard@localhost:5432/hazard_fighter"

    # 공공데이터 API 키 (project-spec.md 6절 데이터 소스 표 참고)
    kma_warning_api_key: str | None = None
    kma_earthquake_api_key: str | None = None
    hrfco_api_key: str | None = None
    safetydata_api_key: str | None = None

    # LLM (Phase 2 - 위험도 판단 로직 4절 Layer 2, 알림 문구 생성용)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"  # 문구 생성용 — 저렴·빠름. 필요 시 .env 로 교체
    anthropic_api_key: str | None = None

    # 푸시 알림 (Phase 2 - 7절 알림 채널 전략)
    fcm_server_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
