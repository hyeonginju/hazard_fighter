"""
FCM HTTP v1 웹푸시 발송.
project-spec.md 7절(알림 채널 전략 — 웹 우선 + 웹푸시) 참고.

왜 v1인가: 구글이 레거시 서버키(FCM_SERVER_KEY) 방식을 2024.6 폐기했다. 지금은
서비스계정 JSON 으로 OAuth2 액세스 토큰을 발급받아 Bearer 로 붙이는 v1 API 만 동작한다:
    POST https://fcm.googleapis.com/v1/projects/{project_id}/messages:send

graceful degradation: 프로젝트ID·서비스계정 파일이 설정돼 있지 않으면 실제 발송 대신
no-op(mock) 로 동작한다 — ingestion 클라이언트가 키 없으면 _fetch_mock 을 쓰는 것과 같은
패턴. 덕분에 FCM 자격증명이 아직 없어도 등록·dispatch 파이프라인 전체를 개발/테스트할 수 있고,
secrets/ 에 JSON 만 넣으면 실발송으로 자동 전환된다.

google-auth/requests 는 실제 발송 경로에서만 필요하므로 지연 import 한다 —
미설정(mock) 환경에서는 이 패키지들이 없어도 앱이 뜬다.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings

_FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]


@dataclass
class PushResult:
    """한 토큰에 대한 발송 결과. dispatch 가 이걸 보고 sent_at 기록·죽은 토큰 정리를 판단한다."""

    ok: bool
    status: str  # "sent" | "mock" | "invalid_token" | "error"
    detail: str = ""


class FcmClient:
    def __init__(self, project_id: str | None, credentials_file: str | None):
        self.project_id = project_id
        self.credentials_file = credentials_file
        self._credentials = None  # google-auth Credentials (지연 생성·자동 갱신)

    @property
    def enabled(self) -> bool:
        return bool(self.project_id and self.credentials_file)

    def _access_token(self) -> str:
        """서비스계정으로 OAuth2 액세스 토큰을 얻는다. google-auth 가 만료 시 자동 갱신한다."""
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        if self._credentials is None:
            self._credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file, scopes=_SCOPES
            )
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return self._credentials.token

    def send(self, fcm_token: str, title: str, body: str) -> PushResult:
        """단일 기기 토큰으로 알림 1건 발송. 예외를 던지지 않고 PushResult 로 결과를 알린다
        (한 토큰 실패가 dispatch 루프 전체를 멈추지 않도록)."""
        if not self.enabled:
            return PushResult(ok=True, status="mock", detail="FCM 미설정 — 발송 생략")

        url = _FCM_ENDPOINT.format(project_id=self.project_id)
        payload = {"message": {"token": fcm_token, "notification": {"title": title, "body": body}}}
        try:
            token = self._access_token()
            response = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except Exception as e:  # noqa: BLE001 — 네트워크·자격증명 오류를 결과로 변환
            return PushResult(ok=False, status="error", detail=f"{type(e).__name__}: {e}")

        if response.status_code == 200:
            return PushResult(ok=True, status="sent")
        # 404 UNREGISTERED/NOT_FOUND = 토큰이 죽음(앱 삭제·구독 해제) → dispatch 가 이 토큰을 지운다.
        # 그 외(400 요청 오류, 401 인증, 5xx 등)는 transient 로 보고 sent_at 을 남겨 다음 사이클에 재시도.
        if response.status_code == 404:
            return PushResult(ok=False, status="invalid_token", detail=response.text[:200])
        return PushResult(ok=False, status="error", detail=f"HTTP {response.status_code}: {response.text[:200]}")


def get_fcm_client() -> FcmClient:
    settings = get_settings()
    return FcmClient(settings.fcm_project_id, settings.fcm_credentials_file)
