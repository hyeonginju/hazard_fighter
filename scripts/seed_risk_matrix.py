"""
app/risk/matrix.py의 RISK_MATRIX를 risk_matrix 테이블에 미러링한다.
감사/추후 관리 UI용 — evaluate_risk()는 지금 이 테이블을 읽지 않는다 (matrix.py 상단 설명 참고).

실행: python -m scripts.seed_risk_matrix
"""
from app.database import SessionLocal
from app.models import RiskMatrixRule
from app.risk.matrix import RISK_MATRIX


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(RiskMatrixRule).count()
        if existing > 0:
            print(f"risk_matrix에 이미 {existing}개 행이 있어서 스킵합니다. (초기화하려면 테이블을 비우고 재실행)")
            return

        for rule in RISK_MATRIX:
            db.add(
                RiskMatrixRule(
                    event_type=rule["event_type"],
                    severity=rule["severity"],
                    trigger_type=rule["trigger_type"],
                    trigger_value=rule["trigger_value"],
                    risk_level=rule["risk_level"],
                )
            )
        db.commit()
        print(f"risk_matrix에 {len(RISK_MATRIX)}개 행을 저장했습니다.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
