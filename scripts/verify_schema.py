"""마이그레이션 결과가 현재 모델과 일치하는지 대조한다.

왜 필요한가 (2026-07-27): 모델이 진실이고 마이그레이션은 그 진실에 도달하는 경로다.
경로를 다 밟았는데 다른 곳에 도착하면 "로컬에선 되는데 배포에선 안 되는" 문제가 된다.
실제로 이 스크립트가 created_at 의 nullable 불일치 7건을 잡았다.

사용법 (빈 DB 에 `alembic upgrade head` 를 돌린 뒤):
    DATABASE_URL="postgresql://..." python scripts/verify_schema.py

종료 코드: 일치 0, 불일치 1.
"""
import sys

from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.database import Base
from app.models import *  # noqa: F401,F403 — Base.metadata 에 전부 등록


def main() -> int:
    engine = create_engine(get_settings().database_url)
    inspector = inspect(engine)

    db_tables = set(inspector.get_table_names()) - {"alembic_version"}
    model_tables = set(Base.metadata.tables)
    problems = 0

    print(f"DB 테이블 {len(db_tables)}개 / 모델 {len(model_tables)}개")
    for label, diff in (("DB 에만 있음", db_tables - model_tables), ("모델에만 있음", model_tables - db_tables)):
        if diff:
            problems += len(diff)
            print(f"  {label}: {sorted(diff)}")

    for name in sorted(db_tables & model_tables):
        db_cols = {c["name"]: c for c in inspector.get_columns(name)}
        model_cols = {c.name: c for c in Base.metadata.tables[name].columns}
        only_db, only_model = set(db_cols) - set(model_cols), set(model_cols) - set(db_cols)
        if only_db or only_model:
            problems += 1
            print(f"  [{name}] DB 에만: {sorted(only_db)} / 모델에만: {sorted(only_model)}")
            continue
        for col, model_col in model_cols.items():
            if db_cols[col]["nullable"] != model_col.nullable:
                problems += 1
                print(f"  [{name}.{col}] nullable 불일치 — DB={db_cols[col]['nullable']} 모델={model_col.nullable}")

    print("결과:", "일치 ✅" if problems == 0 else f"불일치 {problems}건 ❌")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
