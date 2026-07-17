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
)


def pytest_configure(config):
    for var in _API_KEY_VARS:
        os.environ[var] = ""
    # get_settings 는 lru_cache 라 이미 읽힌 설정이 있으면 비워준다
    get_settings.cache_clear()
