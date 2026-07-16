"""initial schema — MVP 데이터 모델 (project-spec.md 9절)

Revision ID: 0001
Revises:
Create Date: 2026-07-17

이 첫 마이그레이션은 app.models의 Base.metadata를 그대로 create_all/drop_all 하는 방식으로
작성했다 (일반적인 개별 op.create_table 나열 대신). 로컬 Postgres가 없는 환경에서
`alembic revision --autogenerate`를 돌릴 수 없어서, 모델과 100% 일치를 보장하는 이 방법을
택했다 — DDL은 create_mock_engine으로 postgres 다이얼렉트 기준 컴파일까지 확인했다.

이후 스키마를 바꿀 때는 이 마이그레이션을 손대지 말고, docker-compose로 로컬 Postgres를
띄운 뒤 `alembic revision --autogenerate -m "설명"`으로 다음 리비전을 새로 생성할 것.
"""
from typing import Sequence, Union

from alembic import op

from app.database import Base
from app.models import *  # noqa: F401,F403 -- Base.metadata에 전부 등록시키기 위해 필요

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
