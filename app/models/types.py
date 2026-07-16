"""
다이얼렉트 호환 컬럼 타입.

운영 DB는 PostgreSQL이지만(11절 기술 스택), DB 서버 없이도 테스트를 돌릴 수 있도록
Postgres에서는 네이티브 타입을, 그 외(SQLite 등)에서는 표준 타입을 쓰도록 variant를 건다.

- UUID     : Postgres 네이티브 UUID / 그 외 CHAR(32)  → sqlalchemy.Uuid가 알아서 처리
- JSONB    : Postgres JSONB / 그 외 JSON
- text[]   : Postgres ARRAY(String) / 그 외 JSON 리스트
"""
from sqlalchemy import JSON, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# UUID 컬럼은 각 모델에서 Uuid(as_uuid=True)로 직접 선언한다 (인스턴스 공유 방지).
UuidType = Uuid  # re-export, 가독성용

# JSONB on Postgres, JSON elsewhere
JsonVariant = JSON().with_variant(JSONB, "postgresql")

# text[] on Postgres, JSON list elsewhere
StringArrayVariant = JSON().with_variant(ARRAY(String), "postgresql")
