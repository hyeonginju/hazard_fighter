"""
웹 PWA 서빙 라우트 (project-spec.md 7절 — 웹 우선 + 웹푸시).

정적 파일(app/static/)로 만든 구독 화면을 FastAPI 가 직접 서빙한다.
별도 프론트 서버(Node/React) 없이 uvicorn 하나로 백엔드+프론트가 다 돌게 하는 MVP 구성.

동적으로 만드는 것 두 가지:
- GET /firebase-config: .env 의 Firebase 웹 설정을 프론트에 JSON 으로 내려준다.
  설정이 비어 있으면 enabled=false — 프론트는 알림 기능만 끄고 나머지(구독 관리)는 동작한다.
- GET /firebase-messaging-sw.js: FCM 백그라운드 수신용 서비스워커를 "코드 생성"해 서빙한다.
  서비스워커는 페이지와 별개 파일이라 /firebase-config 를 fetch 해 초기화하기 어렵다
  (이벤트 리스너를 스크립트 첫 실행에서 동기로 등록해야 해서). 그래서 서버가 설정값을
  박아 넣은 JS 를 만들어 준다. 또 서비스워커의 제어 범위(scope)는 "파일이 서빙된 경로
  이하"라서, 루트 경로(/firebase-messaging-sw.js)에서 서빙해야 /app 페이지를 제어할 수 있다.
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.config import get_settings

router = APIRouter(tags=["web"])

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

# 서비스워커 템플릿. compat 빌드를 쓰는 이유: 서비스워커에는 ES 모듈 import 대신
# importScripts 가 표준적이고, Firebase 공식 문서의 SW 예제도 compat 방식이다.
_SW_TEMPLATE = """\
/* 자동 생성됨 — app/api/routes/web.py 가 .env 의 Firebase 웹 설정을 넣어 서빙한다. */
importScripts("https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js");

firebase.initializeApp({config});

const messaging = firebase.messaging();

// notification 페이로드는 브라우저가 자동 표시하므로, 여기는 data-only 메시지 대비용.
messaging.onBackgroundMessage((payload) => {{
  const n = payload.notification || payload.data || {{}};
  self.registration.showNotification(n.title || "명예소방관 안전 알림", {{
    body: n.body || "",
    icon: "/static/icon.svg",
  }});
}});
"""


def _firebase_web_config(settings) -> dict:
    """프론트(Firebase JS SDK)가 기대하는 키 이름으로 변환."""
    return {
        "apiKey": settings.fcm_web_api_key,
        "authDomain": f"{settings.fcm_project_id}.firebaseapp.com",
        "projectId": settings.fcm_project_id,
        "messagingSenderId": settings.fcm_web_messaging_sender_id,
        "appId": settings.fcm_web_app_id,
    }


@router.get("/app", include_in_schema=False)
def serve_app():
    """PWA 구독 화면."""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/firebase-config")
def firebase_config():
    """프론트가 FCM 초기화에 쓸 공개 설정. 미설정이면 enabled=false 로 알림 기능만 비활성."""
    settings = get_settings()
    if not settings.fcm_web_enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "config": _firebase_web_config(settings),
        "vapidKey": settings.fcm_vapid_key,
    }


@router.get("/firebase-messaging-sw.js", include_in_schema=False)
def firebase_messaging_sw():
    """FCM 백그라운드 수신 서비스워커 (설정 주입해 동적 생성)."""
    settings = get_settings()
    if not settings.fcm_web_enabled:
        # 설정 없이는 유효한 SW 를 만들 수 없다. 프론트는 enabled=false 면 등록 자체를 안 한다.
        raise HTTPException(status_code=404, detail="Firebase 웹 설정이 없습니다 (.env 참고)")
    body = _SW_TEMPLATE.format(config=json.dumps(_firebase_web_config(settings), ensure_ascii=False))
    return Response(content=body, media_type="application/javascript")
