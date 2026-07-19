"""
알림 문구 생성 테스트 — LLM 사용/미사용/실패 세 경로 모두 검증.
실제 OpenAI 호출은 하지 않는다 (monkeypatch 로 httpx.post 를 대체).
"""
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.services import message as message_mod
from app.services.message import generate_notification_message, template_message


@pytest.fixture()
def sample_event_person():
    region = SimpleNamespace(sido="전라남도", sigungu="광양")
    event = SimpleNamespace(event_type="폭염특보", severity="주의보", region=region)
    person = SimpleNamespace(label="어머니", age_group="고령")
    return event, person


@pytest.fixture()
def with_fake_api_key(monkeypatch):
    """테스트 동안만 가짜 키를 설정 (conftest 가 비워둔 상태를 복원하며 종료)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    get_settings.cache_clear()
    yield
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()


def test_template_without_key(sample_event_person):
    # conftest 가 키를 비워두므로 기본 경로는 템플릿
    event, person = sample_event_person
    msg = generate_notification_message(event, person, "HIGH")
    assert msg == template_message(event, person)
    assert "폭염특보" in msg and "어머니" in msg


def test_llm_used_when_key_present(sample_event_person, with_fake_api_key, monkeypatch):
    event, person = sample_event_person

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "광양에 폭염주의보가 발효 중이에요. 어머니님, 낮 시간 외출을 피하고 물을 자주 드세요."}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResponse()

    monkeypatch.setattr(message_mod.httpx, "post", fake_post)

    msg = generate_notification_message(event, person, "HIGH", {"보행보조필요"})

    assert "낮 시간 외출" in msg  # LLM 응답이 사용됨
    # 프롬프트에 인물 특성이 실제로 들어갔는지
    prompt_text = str(captured["json"]["messages"])
    assert "고령" in prompt_text and "보행보조필요" in prompt_text and "광양" in prompt_text


def test_fallback_on_api_error(sample_event_person, with_fake_api_key, monkeypatch):
    event, person = sample_event_person

    def fake_post(url, **kwargs):
        raise RuntimeError("openai down")

    monkeypatch.setattr(message_mod.httpx, "post", fake_post)

    msg = generate_notification_message(event, person, "HIGH")
    assert msg == template_message(event, person)  # 죽지 않고 템플릿으로


def test_fallback_on_empty_response(sample_event_person, with_fake_api_key, monkeypatch):
    event, person = sample_event_person

    class EmptyResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "  "}}]}

    monkeypatch.setattr(message_mod.httpx, "post", lambda url, **kw: EmptyResponse())

    msg = generate_notification_message(event, person, "HIGH")
    assert msg == template_message(event, person)
