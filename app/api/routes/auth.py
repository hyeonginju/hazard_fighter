"""
소셜 로그인 (구글·카카오) — 서버사이드 OAuth 2.0 인가 코드 흐름.

흐름: GET /auth/{provider}/login → 동의 화면 → GET /auth/{provider}/callback?code=...
  → 서버가 code 를 프로바이더 토큰 엔드포인트에서 교환해 회원번호·닉네임 획득
  → (provider, 회원번호)로 사용자 get-or-create → 우리 JWT 발급
  → /app#token=... 으로 리다이렉트 (fragment 는 서버 로그·히스토리에 안 남는다)

이메일은 요청하지 않는다 — 사용자 식별은 프로바이더 회원번호로 충분하고,
카카오는 이메일 수집에 비즈 앱 전환이 필요하기 때문. 닉네임만 화면 표시용으로 받는다.

구글 id_token 서명을 JWKS 로 재검증하지 않는 이유: 토큰을 브라우저 경유가 아니라
서버↔구글 TLS 직통(토큰 엔드포인트)으로 받으므로 발신자가 구글임이 채널로 보장된다.
대신 aud(우리 client_id)·iss 는 반드시 확인한다.
카카오는 id_token 대신 access_token 으로 /v2/user/me 를 조회한다 (OIDC 활성화 불필요).
"""
import logging
import secrets

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud
from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services.auth import issue_token

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    """로그인한 사용자의 화면 표시용 정보 (닉네임·로그인 방법·보호 대상 상한)."""
    return {
        "nickname": user.nickname,
        "provider": user.auth_provider,
        "person_limit": user.person_limit,
    }

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_STATE_COOKIE = "oauth_state"


def _redirect_uri(request: Request) -> str:
    return str(request.url_for("google_callback"))


@router.get("/google/login")
def google_login(request: Request):
    settings = get_settings()
    if not settings.google_oauth_enabled:
        raise HTTPException(status_code=503, detail="서버에 구글 로그인 설정이 없습니다 (.env 의 GOOGLE_CLIENT_* / JWT_SECRET).")

    # state: CSRF 방어 — 우리가 보낸 로그인 요청의 응답인지 콜백에서 대조한다
    state = secrets.token_urlsafe(16)
    params = httpx.QueryParams(
        client_id=settings.google_client_id,
        redirect_uri=_redirect_uri(request),
        response_type="code",
        scope="openid profile",  # 이메일 미수집
        state=state,
    )
    response = RedirectResponse(f"{_GOOGLE_AUTH_URL}?{params}")
    response.set_cookie(_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return response


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error or not code:
        # 사용자가 동의 화면에서 취소한 경우 등 — 로그인 화면으로 돌려보낸다
        return RedirectResponse("/login#login_error=cancelled")
    if not state or state != request.cookies.get(_STATE_COOKIE):
        raise HTTPException(status_code=400, detail="state 불일치 — 로그인을 처음부터 다시 시도해 주세요.")

    settings = get_settings()
    token_response = httpx.post(
        _GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": _redirect_uri(request),
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if token_response.status_code != 200:
        # 에러 응답에는 토큰이 없고 원인 코드만 있어 로그에 남겨도 안전하다
        logger.warning("구글 토큰 교환 실패 (%s): %s", token_response.status_code, token_response.text)
        raise HTTPException(status_code=502, detail="구글 토큰 교환에 실패했습니다.")

    # 서명 재검증 없이 디코드(위 모듈 docstring 참고) — 단 aud/iss 는 직접 확인.
    # (PyJWT 는 verify_signature=False 면 aud/iss 검증도 같이 꺼버리므로 수동으로)
    claims = jwt.decode(token_response.json()["id_token"], options={"verify_signature": False})
    if claims.get("aud") != settings.google_client_id or claims.get("iss") not in (
        "accounts.google.com",
        "https://accounts.google.com",
    ):
        raise HTTPException(status_code=502, detail="구글 id_token 검증에 실패했습니다.")

    user = crud.get_or_create_social_user(db, "google", claims["sub"], claims.get("name"))
    return _login_success(user, "google")


def _login_success(user, provider: str) -> RedirectResponse:
    token = issue_token(user)
    response = RedirectResponse(f"/app#token={token}&provider={provider}")
    response.delete_cookie(_STATE_COOKIE)
    return response


# --- 카카오 -------------------------------------------------------------------

_KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
_KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_KAKAO_USER_URL = "https://kapi.kakao.com/v2/user/me"


@router.get("/kakao/login")
def kakao_login(request: Request):
    settings = get_settings()
    if not settings.kakao_oauth_enabled:
        raise HTTPException(status_code=503, detail="서버에 카카오 로그인 설정이 없습니다 (.env 의 KAKAO_REST_API_KEY / JWT_SECRET).")

    state = secrets.token_urlsafe(16)
    params = httpx.QueryParams(
        client_id=settings.kakao_rest_api_key,
        redirect_uri=str(request.url_for("kakao_callback")),
        response_type="code",
        state=state,
        # scope 미지정 = 콘솔에 설정한 기본 동의항목(닉네임)만 — 이메일은 요청하지 않는다
    )
    response = RedirectResponse(f"{_KAKAO_AUTH_URL}?{params}")
    response.set_cookie(_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return response


@router.get("/kakao/callback")
def kakao_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error or not code:
        return RedirectResponse("/login#login_error=cancelled")
    if not state or state != request.cookies.get(_STATE_COOKIE):
        raise HTTPException(status_code=400, detail="state 불일치 — 로그인을 처음부터 다시 시도해 주세요.")

    settings = get_settings()
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.kakao_rest_api_key,
        "redirect_uri": str(request.url_for("kakao_callback")),
        "code": code,
    }
    if settings.kakao_client_secret:
        data["client_secret"] = settings.kakao_client_secret
    token_response = httpx.post(_KAKAO_TOKEN_URL, data=data, timeout=10)
    if token_response.status_code != 200:
        # 에러 응답에는 토큰이 없고 원인 코드(KOE___)만 있어 로그에 남겨도 안전하다
        logger.warning("카카오 토큰 교환 실패 (%s): %s", token_response.status_code, token_response.text)
        raise HTTPException(status_code=502, detail="카카오 토큰 교환에 실패했습니다.")

    # 카카오 회원번호(id)와 닉네임 조회 — access_token 도 서버↔카카오 TLS 직통으로 받은 것
    me = httpx.get(
        _KAKAO_USER_URL,
        headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
        timeout=10,
    )
    if me.status_code != 200:
        raise HTTPException(status_code=502, detail="카카오 사용자 조회에 실패했습니다.")
    profile = me.json()
    nickname = (profile.get("properties") or {}).get("nickname")

    user = crud.get_or_create_social_user(db, "kakao", str(profile["id"]), nickname)
    return _login_success(user, "kakao")
