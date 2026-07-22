"""
pytest 전역 설정.

테스트는 .env 에 실제 API 키가 있어도 항상 mock 모드로 돌아야 한다
(외부 API 호출 = 느리고, 비결정적이고, 네트워크 의존).
환경변수는 .env 파일보다 우선하므로(pydantic-settings), 키를 빈 값으로 덮어써서
BaseIngestionClient.fetch() 가 _fetch_mock() 으로 빠지게 만든다.

이 파일은 2026-07-17 에 추가 — .env 에 실제 키를 채우자 테스트가 실제 API 를
호출하려다 실패하는 "테스트 격리 버그"를 발견하고 고친 것.
"""
import os

from app.config import get_settings

_API_KEY_VARS = (
    "KMA_WARNING_API_KEY",
    "KMA_EARTHQUAKE_API_KEY",
    "HRFCO_API_KEY",
    "SAFETYDATA_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LLM_FALLBACK_BASE_URL",
    "LLM_FALLBACK_API_KEY",
    "LLM_FALLBACK_MODEL",
    # FCM 도 비워 발송을 mock(no-op)으로 — 테스트는 실제 서비스계정·네트워크 없이 돌아야 한다
    "FCM_PROJECT_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
    # Firebase 웹 클라이언트 설정도 비움 — /firebase-config 가 enabled=false 인 상태가 기본
    "FCM_WEB_API_KEY",
    "FCM_WEB_APP_ID",
    "FCM_WEB_MESSAGING_SENDER_ID",
    "FCM_VAPID_KEY",
)


def pytest_configure(config):
    for var in _API_KEY_VARS:
        os.environ[var] = ""
    # 테스트 중엔 백그라운드 수집 스케줄러를 끈다 (외부 호출·타이밍 비결정성 방지)
    os.environ["SCHEDULER_ENABLED"] = "0"
    # get_settings 는 lru_cache 라 이미 읽힌 설정이 있으면 비워준다
    get_settings.cache_clear()
