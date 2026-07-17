# 시켜줘, 명예소방관

공공데이터 기반 개인 맞춤형 이상상황 알림 플랫폼 — peterju.cloud 사이드 프로젝트 #3 (FDE 지원용).
전체 기획/근거는 [`docs/project-spec.md`](docs/project-spec.md) 참고. 이 저장소는 그중 **Phase 1: 데이터 파이프라인 & 백엔드 뼈대**를 구현한다.

## 지금 뭐가 되어 있나

- FastAPI 백엔드 + PostgreSQL 스키마 (spec 9절 MVP 범위: users/persons/regions/subscriptions/events/notifications/risk_matrix/river_gauges 등 12개 테이블)
- 위험도 판단 로직 Layer 1 (spec 4절 규칙 매트릭스) — `app/risk/matrix.py`, 테스트로 검증됨
- 3개 데이터 소스 ingestion 클라이언트 (기상특보/지진/홍수통제소) — API 키 없으면 자동으로 mock 데이터 사용
- 기본 REST API: 인물/지역/구독 CRUD, 이벤트 조회, 수동 ingest 트리거, 알림 조회
- Docker Compose (Postgres + app), Alembic 마이그레이션 뼈대

아직 없는 것 (다음 Phase): 실제 API 키 연동 검증, Layer 2 LLM 판단, 실제 FCM 푸시 발송, 웹 프론트, JWT 인증.

## 로컬 실행

```bash
cp .env.example .env
# .env에 발급받은 키 채우기 (아래 "API 키 발급 현황" 참고)

docker compose up -d db
pip install -r requirements-dev.txt
alembic upgrade head

uvicorn app.main:app --reload
```

- API 문서: http://localhost:8000/docs
- 헬스체크: `curl http://localhost:8000/health`

### 전체를 Docker로 띄우고 싶으면

```bash
docker compose up --build
```

### 테스트

```bash
pytest
```

**테스트는 DB 서버(Docker/Postgres) 없이 전부 돈다.** 모델이 다이얼렉트 호환 타입(`app/models/types.py`: UUID/JSONB/ARRAY → SQLite 호환 variant)이라, 통합 테스트는 in-memory SQLite로 실제 DB 왕복까지 검증한다:
- `test_risk_matrix.py` — Layer1 규칙 매트릭스 로직
- `test_ingestion.py` — API 키 없을 때 mock fallback
- `test_pipeline_e2e.py` — 사용자/인물/지역/구독 생성 → ingest → events → 위험도 평가 → notifications 생성까지 전체 흐름
- `test_health.py` — 헬스체크

운영 DDL은 Postgres를 타겟으로 하고(JSONB/네이티브 UUID 유지), 아래 Docker 절차로 실제 Postgres에 적용해 최종 확인한다.

## API 키 발급 현황

| 소스 | 상태 | 비고 |
|---|---|---|
| 기상특보 조회서비스 (data.go.kr 15000415) | ✅ 발급 완료 | `.env`의 `KMA_WARNING_API_KEY` |
| 지진정보 조회서비스 (data.go.kr 15000420) | ✅ 발급 완료 | `.env`의 `KMA_EARTHQUAKE_API_KEY` |
| 홍수통제소 표준수문DB (hrfco.go.kr) | ✅ 발급 완료 | `.env`의 `HRFCO_API_KEY`. data.go.kr 계정과 별개로 hrfco.go.kr에서 직접 발급. 인증키 신청 시 "사이트 URL(IP)"을 요구하는데, 개발 중인 컴퓨터 공인 IP나 보유 도메인(peterju.cloud)을 넣으면 됨. 배포 후 아웃바운드 IP가 바뀌면 재등록 필요 가능 (spec 12절 Open Question #8) |
| 긴급재난문자 (safetydata.go.kr) | ⏳ 진행 중 | `.env`의 `SAFETYDATA_API_KEY`. Phase 5 확장 항목이라 급하진 않음 |
| LLM — 알림 문구 생성 (Phase 2) | ✅ 발급 완료 (OpenAI) | `.env`의 `OPENAI_API_KEY`. Anthropic 키(`ANTHROPIC_API_KEY`)로 대체 가능 — 둘 중 하나만 있으면 됨 |
| Firebase Cloud Messaging — 웹푸시 (Phase 2) | ⏳ 미발급 | 레거시 `FCM_SERVER_KEY`는 2024.7 폐기됨. 서비스 계정 JSON 방식 사용: Firebase 콘솔 → 프로젝트 설정 → 서비스 계정 → 비공개 키 생성 → `secrets/firebase-service-account.json`. `.env`는 `GOOGLE_APPLICATION_CREDENTIALS`(파일 경로) + `FCM_PROJECT_ID` |

키가 없는 소스는 `app/ingestion/*.py`의 `fetch()`가 자동으로 mock 데이터를 반환하므로, 키 발급을 기다리지 않고도 API/DB/위험도 로직을 계속 개발·테스트할 수 있다.

## 환경변수 & 시크릿 관리

- **`.env`** — 실제 키를 담는 파일. `.gitignore`로 무시되어 커밋되지 않는다.
- **`.env.example`** — 커밋되는 템플릿. 변수명만 있고 값은 비어 있어야 한다. 최초 세팅은 `cp .env.example .env` 후 값 채우기.
- **`secrets/`** — Firebase 서비스 계정 JSON 등 시크릿 파일 폴더. `.gitignore`로 무시된다.
- 커밋 전에 `git status`로 `.env`나 `secrets/`가 스테이징에 안 걸렸는지 확인할 것.

### 시크릿 히스토리 정리 (완료)

초기 개발 중 `.env.example`에 실제 키(KMA/HRFCO)가 잠깐 커밋된 적이 있었으나, 원격에 push되기 전 `git filter-repo --replace-text`로 히스토리 전체에서 스크럽 완료. 로컬 전용이었고 외부 노출 없었으므로 키 재발급은 불필요. 앞으로 GitHub(private) 연결 후 push해도 안전하다.

## 실제 API 연동 상태 (2026-07-17 검증 완료)

세 소스 모두 실제 응답 기준으로 `_fetch_live()`를 수정했고, `POST /events/ingest`가 실 데이터로 end-to-end 성공했다 (`events_ingested: 8, errors: {}`). 실 응답 샘플은 `debug_responses/`(gitignore됨), 재확인은 `python scripts/debug_fetch.py`.

| 소스 | 상태 | 남은 것 |
|---|---|---|
| 기상특보 | ✅ 동작 | `getWthrWrnList`는 관서 단위라 region 매칭 불가. 시군구는 통보문 상세(`getWthrWrnMsg`, `t6` 필드) 파싱 필요 → **알림 생성으로 이어지려면 이게 다음 핵심 작업** |
| 지진 | ✅ 동작 | 필수 파라미터 fromTmFc/toTmFc + 최대 3일 제한 반영됨. 국내 지진 발생 시 필드 재확인, 국외 지진 필터 검토 |
| 홍수통제소 | ✅ 동작 | `api.hrfco.go.kr` 수위 임계치 판정 방식. 모니터링 관측소가 청주 2곳 하드코딩 → 구독 지역 기반 동적 선정(river_gauges 테이블 활용)은 Phase 2 |

## 왜 초기 마이그레이션이 `create_all`/`drop_all` 방식인가

로컬에 Postgres를 바로 못 띄우는 환경(이 스캐폴딩을 만든 세션)에서 작성하다 보니 `alembic revision --autogenerate`를 실제 DB에 돌려볼 수 없었다. 그래서 `migrations/versions/0001_initial_schema.py`는 `Base.metadata.create_all()`을 직접 호출하는 방식으로 작성했고, DDL은 `create_mock_engine`으로 Postgres 다이얼렉트 기준 컴파일까지 확인했다 (`alembic history`/`heads`로 구조도 확인 완료). 앞으로 스키마를 바꿀 때는 이 파일을 직접 고치지 말고, 로컬 Postgres를 띄운 뒤 `alembic revision --autogenerate -m "설명"`으로 새 리비전을 만들면 된다.

## 다음 순서 (project-spec.md 10절 로드맵 기준)

1. 3개 소스(기상특보/지진/홍수통제소) 키 모두 발급 완료 → `POST /events/ingest`로 실제 응답 확인하고 `_fetch_live()` 필드 매핑 다듬기
2. `docker compose up -d db && alembic upgrade head`로 실제 Postgres에 스키마 생성 검증 (스캐폴딩 세션에서는 환경 제약으로 못 해봄)
3. Phase 2 착수: Layer 2 LLM 판단(`ai_risk_logs`), 알림 문구 실제 LLM 생성(OpenAI 키 준비됨), 웹(PWA) 구독 관리 화면, FCM 웹푸시 연동(서비스 계정 JSON 방식)
