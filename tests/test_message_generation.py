"""
알림 문구 생성 테스트 — LLM 프로바이더 폴백 체인 검증.
실제 LLM 호출은 하지 않는다 (monkeypatch 로 httpx.post 를 대체).

검증하는 경로:
- 키 없음 → 템플릿
- 정상 응답 → LLM 문구 사용 (+프롬프트에 인물 특성 포함)
- 에러/빈 응답 → 템플릿 fallback
- 유료 quota 소진(429) → 무료 폴백 프로바이더로 전환 + 쿨다운 동작
"""
from types import SimpleNamespace

import httpx
import pytest

from app.config import get_settings
from app.services import message as message_mod
from app.services.message import generate_notification_message, template_message


@pytest.fixture(autouse=True)
def clear_cooldowns():
    """쿨다운 상태는 모듈 전역이라 테스트 간 격리 필요."""
    message_mod._cooldowns.clear()
    yield
    message_mod._cooldowns.clear()


@pytest.fixture()
def sample_event_person():
    region = SimpleNamespace(sido="전라남도", sigungu="광양")
    event = SimpleNamespace(event_type="폭염특보", severity="주의보", region=region)
    person = SimpleNamespace(label="어머니", age_group="고령")
    return event, person


@pytest.fixture()
def with_fake_api_key(monkeypatch):
    """테스트 동안만 가짜 유료 키를 설정."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    get_settings.cache_clear()
    yield
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()


@pytest.fixture()
def with_fallback_provider(monkeypatch):
    """무료 폴백 프로바이더(Gemini 무료 티어 흉내)까지 설정."""
    monkeypatch.setenv("LLM_FALLBACK_BASE_URL", "https://free.example.com/v1")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "free-test-key")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "free-model")
    get_settings.cache_clear()
    yield
    for var in ("LLM_FALLBACK_BASE_URL", "LLM_FALLBACK_API_KEY", "LLM_FALLBACK_MODEL"):
        monkeypatch.setenv(var, "")
    get_settings.cache_clear()


def _ok_response(url: str, text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": text}}]},
        request=httpx.Request("POST", url),
    )


def _error_response(url: str, status: int) -> httpx.Response:
    return httpx.Response(status, json={"error": "x"}, request=httpx.Request("POST", url))


def test_template_without_key(sample_event_person):
    # conftest 가 키를 비워두므로 기본 경로는 템플릿
    event, person = sample_event_person
    msg = generate_notification_message(event, person, "HIGH")
    assert msg == template_message(event, person)
    assert "폭염특보" in msg and "어머니" in msg


def test_llm_used_when_key_present(sample_event_person, with_fake_api_key, monkeypatch):
    event, person = sample_event_person
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _ok_response(url, "광양에 폭염주의보가 발효 중이에요. 어머니님, 낮 시간 외출을 피하고 물을 자주 드세요.")

    monkeypatch.setattr(message_mod.httpx, "post", fake_post)

    msg = generate_notification_message(event, person, "HIGH", {"보행보조필요"})

    assert "낮 시간 외출" in msg  # LLM 응답이 사용됨
    prompt_text = str(captured["json"]["messages"])
    assert "고령" in prompt_text and "보행보조필요" in prompt_text and "광양" in prompt_text


def test_fallback_on_api_error(sample_event_person, with_fake_api_key, monkeypatch):
    event, person = sample_event_person

    def fake_post(url, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(message_mod.httpx, "post", fake_post)

    msg = generate_notification_message(event, person, "HIGH")
    assert msg == template_message(event, person)  # 죽지 않고 템플릿으로


def test_fallback_on_empty_response(sample_event_person, with_fake_api_key, monkeypatch):
    event, person = sample_event_person
    monkeypatch.setattr(message_mod.httpx, "post", lambda url, **kw: _ok_response(url, "  "))

    msg = generate_notification_message(event, person, "HIGH")
    assert msg == template_message(event, person)


def test_quota_exhausted_fails_over_to_free_provider(
    sample_event_person, with_fake_api_key, with_fallback_provider, monkeypatch
):
    """핵심 시나리오: 유료 429(quota 소진) → 무료 프로바이더가 문구 생성."""
    event, person = sample_event_person
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if "api.openai.com" in url:
            return _error_response(url, 429)  # 유료: quota 소진
        return _ok_response(url, "무료 모델이 생성한 맞춤 문구입니다.")

    monkeypatch.setattr(message_mod.httpx, "post", fake_post)

    msg = generate_notification_message(event, person, "HIGH")

    assert msg == "무료 모델이 생성한 맞춤 문구입니다."
    assert len(calls) == 2  # 유료 시도 → 무료 성공
    assert "api.openai.com" in calls[0] and "free.example.com" in calls[1]


def test_cooldown_skips_dead_provider_on_next_call(
    sample_event_person, with_fake_api_key, with_fallback_provider, monkeypatch
):
    """쿨다운: quota 소진이 감지된 유료 프로바이더는 다음 알림부터 시도 자체를 안 한다."""
    event, person = sample_event_person
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if "api.openai.com" in url:
            return _error_response(url, 429)
        return _ok_response(url, "무료 모델 문구.")

    monkeypatch.setattr(message_mod.httpx, "post", fake_post)

    generate_notification_message(event, person, "HIGH")  # 1번째: 유료 실패 → 쿨다운 설정
    generate_notification_message(event, person, "HIGH")  # 2번째: 유료 스킵해야 함

    openai_calls = [u for u in calls if "api.openai.com" in u]
    assert len(openai_calls) == 1  # 두 번째 호출에선 유료를 건드리지 않음
    assert len(calls) == 3  # 유료1 + 무료2


def test_both_providers_down_falls_back_to_template(
    sample_event_person, with_fake_api_key, with_fallback_provider, monkeypatch
):
    event, person = sample_event_person
    monkeypatch.setattr(message_mod.httpx, "post", lambda url, **kw: _error_response(url, 429))

    msg = generate_notification_message(event, person, "HIGH")
    assert msg == template_message(event, person)
