"""initial schema — MVP 데이터 모델 (project-spec.md 9절)

Revision ID: 0001
Revises:
Create Date: 2026-07-17

원래 이 마이그레이션은 `Base.metadata.create_all()` 한 줄이었다. 로컬 Postgres 가 없어
autogenerate 를 못 돌리는 상황에서 "모델과 100% 일치"를 보장하려고 택한 방법이었는데,
**시간이 지나면 깨지는 선택이었다** (2026-07-27, Neon 에 처음 적용하다 발견):

create_all 은 "이 리비전 시점의 스키마"가 아니라 **"지금 모델 전체"** 를 만든다. 그래서
0002(users 컬럼 추가)·0003(ingest_runs) 이 생긴 뒤에는 새 DB 에서 0001 이 이미 그 컬럼까지
다 만들어버리고, 이어서 0002 가 "column auth_provider already exists" 로 죽는다.
기존 DB(로컬)는 리비전을 순서대로 밟아왔으니 아무 문제가 없어서 반년 가까이 드러나지 않았다.
= **마이그레이션은 현재 상태를 참조하면 안 되고, 그 시점의 스냅샷으로 고정돼야 한다.**

그래서 이 파일을 0001 당시 스키마(테이블 12개, users 는 email 필수·소셜 컬럼 없음)로
명시적으로 다시 썼다. 0001→0002→0003 을 빈 DB 에 순서대로 적용하면 현재 모델과 같아지는지
검증했다(테이블·컬럼 대조).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 사용자·보호 대상 ---
    # 이 시점의 users 는 이메일 기반(임시 방식). 소셜 로그인 컬럼은 0002 에서 추가된다.
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "persons",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("age_group", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "person_tags",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("person_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "tag", name="uq_person_tag"),
    )

    # --- 지역·구독 ---
    op.create_table(
        "regions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sido", sa.String(length=20), nullable=False),
        sa.Column("sigungu", sa.String(length=30), nullable=False),
        sa.Column("region_code", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sido", "sigungu", name="uq_region_sido_sigungu"),
    )
    op.create_index("ix_regions_region_code", "regions", ["region_code"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("person_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("region_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "region_id", name="uq_subscription_person_region"),
    )

    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("fcm_token", sa.String(length=512), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fcm_token", name="uq_device_token_fcm_token"),
    )

    # --- 이벤트·위험도·알림 ---
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("region_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("news_refs", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "risk_matrix",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("trigger_type", sa.String(length=20), nullable=False),
        sa.Column("trigger_value", sa.String(length=30), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("subscription_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.Column("risk_source", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_risk_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("subscription_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- 홍수 관측소 (지역 매핑) ---
    op.create_table(
        "river_gauges",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("station_code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("lng", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("station_code"),
    )

    op.create_table(
        "gauge_region_map",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("river_gauge_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("region_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["river_gauge_id"], ["river_gauges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # FK 역순으로 삭제
    op.drop_table("gauge_region_map")
    op.drop_table("river_gauges")
    op.drop_table("ai_risk_logs")
    op.drop_table("notifications")
    op.drop_table("risk_matrix")
    op.drop_table("events")
    op.drop_table("device_tokens")
    op.drop_table("subscriptions")
    op.drop_index("ix_regions_region_code", table_name="regions")
    op.drop_table("regions")
    op.drop_table("person_tags")
    op.drop_table("persons")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
