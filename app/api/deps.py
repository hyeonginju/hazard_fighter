"""
라우트 공용 의존성 — 사용자 JWT 인증 + 수집 엔드포인트 토큰.

FastAPI 의존성 주입: 라우트가 `user: User = Depends(get_current_user)` 한 줄만 받으면
Authorization 헤더 파싱 → 서명/만료 검증 → DB 사용자 조회까지 끝난다.
기존 user_email 쿼리/바디 파라미터(임시 방식)를 이걸로 대체 (2026-07-23).
"""
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
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


def require_ingest_token(x_ingest_token: str | None = Header(default=None)) -> None:
    """수집 엔드포인트(POST /events/ingest) 보호 — 외부 스케줄러만 호출할 수 있게.

    왜 필요한가 (2026-07-27, 배포 준비 중 발견):
    이 엔드포인트는 지금까지 무인증이었다. 로컬에서는 "내가 실수로 연타하는 것"만
    문제여서 시간 가드로 충분했지만, 공개 배포되면 위협이 바뀐다 — 주소를 아는 누구나
    우리 수집을 트리거할 수 있고 그건 공공 API 쿼터와 LLM 비용을 남이 태울 수 있다는 뜻이다.
    시간 가드는 낭비를 줄이지만 인증이 아니다.

    왜 앱 레벨 공유 시크릿인가:
    Cloud Run 의 IAM 인증은 서비스 단위 전체 적용(all-or-nothing)이라, 같은 서비스가
    공개 페이지(/login·/app)도 서빙하는 구조에서는 쓸 수 없다. 그래서 이 엔드포인트만
    헤더 토큰으로 막는다. (웹 서비스와 수집 잡을 별도 Cloud Run 서비스로 쪼개면
    플랫폼 인증을 쓸 수 있지만, 인프라가 늘어나므로 지금은 택하지 않았다.)

    토큰 미설정 시 열어두지 않고 503 으로 막는다(fail-closed) — "설정을 잊으면 열려 있는"
    보호는 없는 것보다 위험하다. 로컬 개발에서 자동 수집은 스케줄러가 서비스 함수를
    직접 호출하므로 토큰 없이도 계속 돈다. 막히는 건 HTTP 수동 트리거뿐이다.
    """
    expected = get_settings().ingest_token
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="수집 엔드포인트 토큰(INGEST_TOKEN)이 설정되지 않았습니다.",
        )
    # compare_digest: 문자 비교 시간차로 토큰을 한 글자씩 알아내는 타이밍 공격 방지.
    # bytes 로 넘기는 이유: str 끼리 비교하면 non-ASCII 입력에 TypeError 가 나서
    # 401 이어야 할 요청이 500 이 된다 (테스트로 실제로 걸린 함정).
    if not x_ingest_token or not secrets.compare_digest(
        x_ingest_token.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="수집 토큰이 올바르지 않습니다.")
