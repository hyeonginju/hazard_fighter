"""수집 실행 이력 테이블 — 중복 실행 가드를 프로세스 메모리에서 DB로

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-27

가드 상태가 모듈 전역 변수였는데, 인스턴스가 2개 이상이면 서로의 실행을 모르므로
가드가 무력해진다(= 공공 API 호출량이 인스턴스 수만큼 배가). 클라우드 배포·외부
스케줄러 전환의 전제조건으로 상태를 DB로 옮긴다. 겸해서 실행 이력이 남는다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events_ingested", sa.Integer(), nullable=True),
        sa.Column("duplicates_skipped", sa.Integer(), nullable=True),
        sa.Column("notifications_created", sa.Integer(), nullable=True),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # 가드가 매 사이클마다 MAX(started_at) 을 읽으므로 인덱스
    op.create_index("ix_ingest_runs_started_at", "ingest_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_ingest_runs_started_at", table_name="ingest_runs")
    op.drop_table("ingest_runs")
