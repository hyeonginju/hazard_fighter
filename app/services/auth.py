"""
JWT 발급/검증 — 소셜 로그인 성공 후 우리 서비스의 "출입증"을 만든다.

왜 우리 토큰을 따로 발급하나: 구글/카카오의 토큰은 "그 프로바이더에게" 나를 증명하는 것이고,
수명도 짧다. 로그인 순간에만 프로바이더로 신원을 확인하고, 이후의 API 호출은
우리가 서명한 JWT(30일)로 인증한다 — 프로바이더 장애·정책과 API 인증이 분리된다.

만료 30일 근거: 이 서비스는 구독 설정할 때 말고는 방문할 일이 거의 없고,
푸시 발송은 JWT 와 무관하게 동작하므로 만료의 비용이 "가끔 재로그인" 뿐이다.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings
from app.models import User


class InvalidTokenError(Exception):
    """서명 불일치·만료·형식 오류 — 라우트/의존성에서 401 로 변환."""


def issue_token(user: User) -> str:
    """로그인 성공한 사용자에게 30일짜리 접근 토큰을 발급한다."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),  # 토큰의 주인 (표준 클레임)
        "provider": user.auth_provider,  # 어떤 방법으로 로그인했는지 (화면 표시용)
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expires_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> uuid.UUID:
    """토큰을 검증하고 사용자 id 를 돌려준다. 위조·만료면 InvalidTokenError."""
    settings = get_settings()
    if not settings.jwt_secret:
        raise InvalidTokenError("서버에 JWT_SECRET 이 설정되지 않았습니다.")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as e:
        raise InvalidTokenError(str(e)) from e
