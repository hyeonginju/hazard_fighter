"""
라우트 공용 의존성 — JWT 인증.

FastAPI 의존성 주입: 라우트가 `user: User = Depends(get_current_user)` 한 줄만 받으면
Authorization 헤더 파싱 → 서명/만료 검증 → DB 사용자 조회까지 끝난다.
기존 user_email 쿼리/바디 파라미터(임시 방식)를 이걸로 대체 (2026-07-23).
"""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import InvalidTokenError, decode_token


def get_current_user(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> User:
    """`Authorization: Bearer <JWT>` 헤더에서 인증된 사용자를 꺼낸다. 실패는 전부 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    try:
        user_id = decode_token(authorization.removeprefix("Bearer "))
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="로그인이 만료됐거나 잘못된 토큰입니다.")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="존재하지 않는 사용자입니다.")
    return user
