"""
로그 시크릿 마스킹.

문제 (2026-07-20 발견): httpx 가 INFO 레벨로 요청 URL 전체를 찍는데, 공공 API 는
serviceKey 를 쿼리스트링에, 홍수통제소는 아예 URL 경로에 키를 넣는 방식이라
로그에 실제 API 키가 그대로 노출된다. 로컬에선 무해하지만 배포 후 로그 수집
시스템(CloudWatch 등)에 키가 쌓이면 유출 경로가 된다.

해결: 로그를 끄는 대신(요청 로그는 디버깅에 유용) 루트 로거 핸들러에 필터를 달아,
설정에 있는 시크릿 값이 메시지에 보이면 ***REDACTED*** 로 치환한다.
새 시크릿이 설정에 추가되면 자동으로 마스킹 대상에 포함된다.
"""
import logging

from app.config import get_settings

REDACTED = "***REDACTED***"


class SecretRedactionFilter(logging.Filter):
    """로그 메시지에서 알려진 시크릿 값을 치환하는 필터."""

    def __init__(self, secrets: list[str]):
        super().__init__()
        # 빈 값/짧은 값 제외 (짧은 문자열은 오탐으로 엉뚱한 단어까지 가릴 수 있음)
        self._secrets = [s for s in secrets if s and len(s) >= 8]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for secret in self._secrets:
            if secret in redacted:
                redacted = redacted.replace(secret, REDACTED)
        if redacted != message:
            record.msg = redacted
            record.args = None  # 이미 포맷된 문자열이므로 인자 재적용 방지
        return True  # 로그 자체는 통과 (내용만 수정)


def _collect_secrets() -> list[str]:
    s = get_settings()
    return [
        s.kma_warning_api_key or "",
        s.kma_earthquake_api_key or "",
        s.hrfco_api_key or "",
        s.safetydata_api_key or "",
        s.openai_api_key or "",
        s.anthropic_api_key or "",
        s.llm_fallback_api_key or "",
        s.jwt_secret or "",
        s.google_client_secret or "",
        s.kakao_client_secret or "",
    ]


def setup_secret_redaction() -> None:
    """루트 로거의 모든 핸들러에 마스킹 필터를 단다.

    httpx 등 서드파티 로거는 별도 핸들러 없이 루트로 전파(propagate)되므로,
    루트 핸들러에서 필터링하면 전부 커버된다.
    """
    redaction_filter = SecretRedactionFilter(_collect_secrets())
    for handler in logging.getLogger().handlers:
        handler.addFilter(redaction_filter)
