"""users 소셜 로그인 전환 — (auth_provider, provider_user_id) 식별 + person_limit

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23

- auth_provider/provider_user_id: 소셜 로그인 식별자 쌍 (google/kakao 회원번호). 쌍으로 유니크.
- nickname: 화면 표시용 (이메일은 수집하지 않음 — 카카오 이메일은 비즈 앱 필요).
- person_limit: 계정당 보호 대상 상한 (기본 3, 추후 유료 쿠폰이 올림).
- email 은 nullable 로 완화 — 기존 user_email 임시 방식 사용자만 값 유지.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_provider", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("provider_user_id", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("nickname", sa.String(length=100), nullable=True))
    op.add_column(
        "users",
        sa.Column("person_limit", sa.Integer(), nullable=False, server_default="3"),
    )
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=True)
    op.create_unique_constraint(
        "uq_users_provider_identity", "users", ["auth_provider", "provider_user_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_provider_identity", "users", type_="unique")
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("users", "person_limit")
    op.drop_column("users", "nickname")
    op.drop_column("users", "provider_user_id")
    op.drop_column("users", "auth_provider")
