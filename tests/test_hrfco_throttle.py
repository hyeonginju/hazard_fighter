"""
홍수통제소 호출 스로틀링 테스트.
배경: 실제 API 한도가 분당 1,000건이고 초과 3회면 키가 차단된다(학습노트 2026-07-20).
관측소를 여러 개 순회할 때 호출 속도가 상한을 넘지 않아야 한다.

_RateLimiter 는 clock/sleep 을 주입받으므로 실제 대기 없이 결정론적으로 검증한다.
"""
import pytest

from app.ingestion.hrfco_flood import HrfcoFloodClient, _RateLimiter


class _FakeClock:
    """가짜 단조시계 + sleep. sleep 하면 시간이 그만큼 흐르고 호출량을 기록한다."""

    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


# --- 레이트리미터 단위 검증 --------------------------------------------------

def test_rate_limiter_enforces_min_interval():
    clock = _FakeClock()
    # 600/분 → 콜당 최소 간격 0.1초
    limiter = _RateLimiter(600, monotonic=clock.monotonic, sleep=clock.sleep)

    limiter.wait()  # 첫 호출: 대기 없음
    limiter.wait()  # 즉시 두 번째: 0.1초 대기
    limiter.wait()  # 즉시 세 번째: 또 0.1초 대기

    assert clock.sleeps == [pytest.approx(0.1), pytest.approx(0.1)]


def test_rate_limiter_no_wait_when_calls_naturally_spaced():
    clock = _FakeClock()
    limiter = _RateLimiter(600, monotonic=clock.monotonic, sleep=clock.sleep)

    limiter.wait()
    clock.t = 5.0  # 5초 경과 — 간격이 이미 충분하면 대기하지 않아야
    limiter.wait()

    assert clock.sleeps == []


def test_rate_limiter_caps_rate_under_limit():
    """실제 한도 1,000/분 아래로 눌리는지: 60초 동안 허용되는 호출 수 ≤ 상한."""
    clock = _FakeClock()
    limiter = _RateLimiter(600, monotonic=clock.monotonic, sleep=clock.sleep)

    for _ in range(600):
        limiter.wait()

    # 599번의 0.1초 대기 = 59.9초. 60초 창 안에서 601번째는 아직 허용 안 됨 → 상한 준수.
    assert clock.t == pytest.approx(59.9)


def test_rate_limiter_rejects_non_positive():
    with pytest.raises(ValueError):
        _RateLimiter(0)


# --- 클라이언트가 매 outbound 호출을 게이트하는지 ----------------------------

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _SpyLimiter:
    def __init__(self):
        self.waits = 0

    def wait(self) -> None:
        self.waits += 1


def test_client_gates_every_live_call(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, timeout=None):
        calls["n"] += 1
        if url.endswith("info.json"):
            return _FakeResp({"content": [
                {"wlobscd": "1004616", "attwl": "3.3", "wrnwl": "5.6",
                 "addr": "충청북도 청주시 상당구"},
                {"wlobscd": "3010605", "attwl": "1.4", "wrnwl": "2.1",
                 "addr": "충청북도 청주시 서원구"},
            ]})
        # 수위 조회: 경보 임계치를 넘는 값 하나
        return _FakeResp({"content": [{"wlobscd": url, "ymdhm": "202607221610", "wl": "9.9"}]})

    monkeypatch.setattr("app.ingestion.hrfco_flood.httpx.get", fake_get)

    client = HrfcoFloodClient(api_key="TEST")
    spy = _SpyLimiter()
    client._limiter = spy

    client.fetch()

    # 목록 1콜 + 관측소 2개 수위 2콜 = 3콜, 각 콜 앞에 wait() 가 한 번씩.
    assert calls["n"] == 3
    assert spy.waits == 3
