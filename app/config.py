"""
앱 전역 설정. .env 파일에서 값을 읽어온다.
project-spec.md 11절(기술 스택) 참고.
"""
from functools import lru_cache

from pydantic import Field
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
    openai_base_url: str = "https://api.openai.com/v1"  # OpenAI 호환이면 교체 가능 (Ollama 등)
    openai_model: str = "gpt-4o-mini"  # 문구 생성용 — 저렴·빠름. 필요 시 .env 로 교체
    anthropic_api_key: str | None = None

    # LLM 폴백 프로바이더 (유료 quota 소진 시 자동 전환 — 선택사항)
    # OpenAI 호환 API 면 무엇이든 가능: Gemini(OpenAI 호환 엔드포인트), Groq, OpenRouter, Ollama 등
    llm_fallback_base_url: str | None = None
    llm_fallback_api_key: str | None = None
    llm_fallback_model: str | None = None

    # 푸시 알림 (Phase 2 - 7절 알림 채널 전략). FCM HTTP v1 방식.
    # 레거시 서버키(fcm_server_key)는 2024.6 구글이 폐기 → 서비스계정 JSON + OAuth2 Bearer 로 전환.
    # 둘 다 설정돼 있어야 실제 발송, 아니면 no-op(mock) 로 동작한다(app/services/push.py).
    fcm_project_id: str | None = None  # Firebase 프로젝트 ID (v1 엔드포인트 경로에 들어감). env: FCM_PROJECT_ID
    # 서비스계정 JSON 경로 (secrets/ 아래 권장, gitignore됨). google-auth 관례 이름을 그대로 씀.
    fcm_credentials_file: str | None = Field(default=None, validation_alias="GOOGLE_APPLICATION_CREDENTIALS")

    # 주기 수집 스케줄러 (호출량 예산: docs/dev-learning-notes.md 2026-07-20 항목)
    scheduler_enabled: bool = True  # 테스트에선 conftest 가 0 으로 끔
    ingest_interval_minutes: int = 10  # 10분 = 하루 144사이클, 가장 빡빡한 재난문자(1,000/일)도 14.4%
    ingest_min_gap_minutes: int = 3  # 수동 /events/ingest 연타 가드 — 이 간격 내 재호출은 스킵

    # 홍수통제소 분당 호출 상한. 실제 한도 1,000/분의 60% — 관측소를 여러 개 순회할 때
    # 순간적으로 한도를 넘겨 키가 차단(초과 3회)되지 않도록 호출 속도에 상한을 건다.
    hrfco_max_requests_per_minute: int = 600


@lru_cache
def get_settings() -> Settings:
    return Settings()
