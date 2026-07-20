"""
로그 시크릿 마스킹 필터 테스트.
배경(2026-07-20): httpx 요청 로그에 serviceKey 가 URL 그대로 노출되던 문제.
"""
import logging

from app.logging_utils import REDACTED, SecretRedactionFilter


def _make_record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="httpx", level=logging.INFO, pathname=__file__, lineno=1,
        msg=message, args=None, exc_info=None,
    )


def test_secret_in_url_is_redacted():
    secret = "df46f9d78b84c64c9d172ed7d90b5c16TEST"
    f = SecretRedactionFilter([secret])
    record = _make_record(
        f"HTTP Request: GET http://apis.data.go.kr/x?serviceKey={secret}&pageNo=1"
    )
    assert f.filter(record) is True  # 로그 자체는 통과
    assert secret not in record.getMessage()
    assert REDACTED in record.getMessage()
    assert "pageNo=1" in record.getMessage()  # 나머지 내용은 보존


def test_secret_in_path_is_redacted():
    # 홍수통제소처럼 키가 URL 경로에 들어가는 경우
    secret = "BDD2FFE9-TEST-48AC-A263-989D1606F956"
    f = SecretRedactionFilter([secret])
    record = _make_record(f"GET https://api.hrfco.go.kr/{secret}/waterlevel/info.json")
    f.filter(record)
    assert secret not in record.getMessage()
    assert "waterlevel/info.json" in record.getMessage()


def test_multiple_secrets_and_formatted_args():
    s1, s2 = "secret-value-11111", "secret-value-22222"
    f = SecretRedactionFilter([s1, s2])
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="k1=%s k2=%s", args=(s1, s2), exc_info=None,
    )
    f.filter(record)
    msg = record.getMessage()
    assert s1 not in msg and s2 not in msg
    assert msg.count(REDACTED) == 2


def test_empty_and_short_secrets_ignored():
    # 빈 값/너무 짧은 값은 오탐 방지를 위해 마스킹 대상에서 제외
    f = SecretRedactionFilter(["", "abc"])
    record = _make_record("abc 는 평범한 단어라 가려지면 안 된다")
    f.filter(record)
    assert "abc" in record.getMessage()


def test_message_without_secret_untouched():
    f = SecretRedactionFilter(["some-secret-key-123"])
    original = "수집 완료: events=3 notifications=1"
    record = _make_record(original)
    f.filter(record)
    assert record.getMessage() == original
