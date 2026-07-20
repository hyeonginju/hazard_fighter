# 시켜줘, 명예소방관

공공데이터 기반 개인 맞춤형 이상상황 알림 플랫폼 — peterju.cloud 사이드 프로젝트 #3 (FDE 지원용).
전체 기획/근거는 [`docs/project-spec.md`](docs/project-spec.md) 참고. 이 저장소는 그중 **Phase 1: 데이터 파이프라인 & 백엔드 뼈대**를 구현한다.

## 지금 뭐가 되어 있나

**Phase 1 완료 + Phase 2 일부 — 실데이터로 개인 맞춤 알림 생성까지 검증됨 (2026-07-17~19):**

- FastAPI 백엔드 + PostgreSQL 스키마 (spec 9절 MVP 범위: users/persons/regions/subscriptions/events/notifications/risk_matrix/river_gauges 등 12개 테이블) — 실제 Postgres(Docker)에 생성 검증
- **실제 공공 API 3개 연동 검증 완료** (기상특보/지진/홍수통제소) — 키 없으면 자동 mock
- **특보→지역 매칭**: 통보문 상세(`getWthrWrnMsg`)의 `t6` 스냅샷을 파싱해 특보별 시군구 추출. 이벤트 중복 방지(dedupe) 포함
- 위험도 판단 로직 Layer 1 (spec 4절 규칙 매트릭스) — 실데이터로 "전남 광양 폭염주의보 + 고령 구독자 → HIGH 알림" 생성 확인
- **구독 소급 평가(backfill)**: 구독을 나중에 만들어도 이미 발효 중인 특보를 즉시 평가해 알림 생성. 지역명 정규화('광양시'→'광양') 포함
- **LLM 알림 문구 생성 + 3단계 폴백 체인**: 유료(OpenAI) → 무료(Gemini, `.env`의 `LLM_FALLBACK_*`) → 템플릿. quota 소진(429) 감지 시 해당 프로바이더 15분 쿨다운. 두 프로바이더 모두 실연동 검증됨
- 기본 REST API: 인물/지역/구독 CRUD(멱등), 이벤트 조회, 수동 ingest 트리거, 알림 조회
- Docker Compose (Postgres + app), Alembic 마이그레이션, 테스트 33개(전부 DB 서버·외부 API 없이 돎)

아직 없는 것 (다음): Layer 2 LLM 위험도 보조 판단(`ai_risk_logs`), 주기 실행(스케줄러), 실제 FCM 푸시 발송, 웹 프론트(PWA), JWT 인증.

개발 과정·기술 결정의 상세 기록은 [`docs/dev-learning-notes.md`](docs/dev-learning-notes.md) 참고.

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

**테스트는 DB 서버(Docker/Postgres)·외부 API 없이 전부 돈다.** 모델이 다이얼렉트 호환 타입(`app/models/types.py`: UUID/JSONB/ARRAY → SQLite 호환 variant)이라 통합 테스트는 in-memory SQLite로 실제 DB 왕복까지 검증하고, `tests/conftest.py`가 API 키를 비워 테스트는 항상 mock 을 쓴다:
- `test_risk_matrix.py` — Layer1 규칙 매트릭스 로직
- `test_ingestion.py` — API 키 없을 때 mock fallback
- `test_pipeline_e2e.py` — 사용자/인물/지역/구독 생성 → ingest → events → 위험도 평가 → notifications 생성까지 전체 흐름
- `test_warning_msg_parser.py` — 통보문 t6 파싱(실응답 케이스), 이벤트 dedupe
- `test_subscription_backfill.py` — 구독 소급 평가, 지역명 정규화, 구독 멱등성
- `test_message_generation.py` — LLM 폴백 체인(quota 소진 시 무료 전환·쿨다운·템플릿 폴백)
- `test_health.py` — 헬스체크

운영 DDL은 Postgres를 타겟으로 하고(JSONB/네이티브 UUID 유지), 아래 Docker 절차로 실제 Postgres에 적용해 최종 확인한다.

## API 키 발급 현황

| 소스 | 상태 | 비고 |
|---|---|---|
| 기상특보 조회서비스 (data.go.kr 15000415) | ✅ 발급 완료 | `.env`의 `KMA_WARNING_API_KEY` |
| 지진정보 조회서비스 (data.go.kr 15000420) | ✅ 발급 완료 | `.env`의 `KMA_EARTHQUAKE_API_KEY` |
| 홍수통제소 표준수문DB (hrfco.go.kr) | ✅ 발급 완료 | `.env`의 `HRFCO_API_KEY`. data.go.kr 계정과 별개로 hrfco.go.kr에서 직접 발급. 인증키 신청 시 "사이트 URL(IP)"을 요구하는데, 개발 중인 컴퓨터 공인 IP나 보유 도메인(peterju.cloud)을 넣으면 됨. 배포 후 아웃바운드 IP가 바뀌면 재등록 필요 가능 (spec 12절 Open Question #8) |
| 긴급재난문자 (safetydata.go.kr) | ✅ 발급 완료 (2026-07-19) | `.env`의 `SAFETYDATA_API_KEY`. ingestion 클라이언트는 미구현(Phase 5 항목) — `debug_fetch.py`로 실응답 확인 후 구현 예정 |
| LLM 유료 — 알림 문구 생성 | ✅ 발급·충전 완료 (OpenAI) | `.env`의 `OPENAI_API_KEY`. 선불 크레딧 필요(없으면 insufficient_quota → 자동으로 폴백 체인 작동) |
| LLM 무료 폴백 (Gemini) | ✅ 발급 완료 | `.env`의 `LLM_FALLBACK_*` 3종. aistudio.google.com/apikey 에서 무료 발급. 모델명은 `gemini-flash-lite-latest` 같은 "latest" 별칭 권장 — 구버전 모델명은 무료 티어가 닫히면 `limit: 0` 429 가 남 |
| Firebase Cloud Messaging — 웹푸시 (Phase 2) | ⏳ 미발급 | 레거시 `FCM_SERVER_KEY`는 2024.7 폐기됨. 서비스 계정 JSON 방식 사용: Firebase 콘솔 → 프로젝트 설정 → 서비스 계정 → 비공개 키 생성 → `secrets/firebase-service-account.json`. `.env`는 `GOOGLE_APPLICATION_CREDENTIALS`(파일 경로) + `FCM_PROJECT_ID` |

키가 없는 소스는 `app/ingestion/*.py`의 `fetch()`가 자동으로 mock 데이터를 반환하므로, 키 발급을 기다리지 않고도 API/DB/위험도 로직을 계속 개발·테스트할 수 있다.

## 환경변수 & 시크릿 관리

- **`.env`** — 실제 키를 담는 파일. `.gitignore`로 무시되어 커밋되지 않는다.
- **`.env.example`** — 커밋되는 템플릿. 변수명만 있고 값은 비어 있어야 한다. 최초 세팅은 `cp .env.example .env` 후 값 채우기.
- **`secrets/`** — Firebase 서비스 계정 JSON 등 시크릿 파일 폴더. `.gitignore`로 무시된다.
- 커밋 전에 `git status`로 `.env`나 `secrets/`가 스테이징에 안 걸렸는지 확인할 것.

### 시크릿 히스토리 정리 (완료)

초기 개발 중 `.env.example`에 실제 키(KMA/HRFCO)가 잠깐 커밋된 적이 있었으나, 원격에 push되기 전 `git filter-repo --replace-text`로 히스토리 전체에서 스크럽 완료. 로컬 전용이었고 외부 노출 없었으므로 키 재발급은 불필요. 앞으로 GitHub(private) 연결 후 push해도 안전하다.

## 실제 API 연동 상태 (2026-07-17~19 검증 완료)

세 소스 모두 실제 응답 기준으로 연동 완료. `POST /events/ingest` → 특보-지역 매칭 → 위험도 평가 → 알림 생성(LLM 문구)까지 실데이터로 end-to-end 검증됐다. 실 응답 샘플은 `debug_responses/`(gitignore됨), 재확인은 `python scripts/debug_fetch.py`.

| 소스 | 상태 | 남은 것 |
|---|---|---|
| 기상특보 | ✅ 지역 매칭까지 동작 | 통보문 상세(`getWthrWrnMsg`) `t6` 스냅샷 파싱으로 시군구 추출. 남은 것: 지역명 표기 정규화 고도화(행정구역 코드 기반) |
| 지진 | ✅ 동작 | 필수 파라미터 fromTmFc/toTmFc + 최대 3일 제한 반영됨. 국내 지진 발생 시 필드 재확인, 국외 지진 필터 검토 |
| 홍수통제소 | ✅ 동작 | `api.hrfco.go.kr` 수위 임계치 판정 방식. 모니터링 관측소가 청주 2곳 하드코딩 → 구독 지역 기반 동적 선정(river_gauges 테이블 활용)은 Phase 2 |
| LLM (알림 문구) | ✅ 폴백 체인까지 동작 | OpenAI·Gemini 모두 실연동 검증. 남은 것: Layer 2 위험도 보조 판단에 재사용 |

## 왜 초기 마이그레이션이 `create_all`/`drop_all` 방식인가

로컬에 Postgres를 바로 못 띄우는 환경(이 스캐폴딩을 만든 세션)에서 작성하다 보니 `alembic revision --autogenerate`를 실제 DB에 돌려볼 수 없었다. 그래서 `migrations/versions/0001_initial_schema.py`는 `Base.metadata.create_all()`을 직접 호출하는 방식으로 작성했고, DDL은 `create_mock_engine`으로 Postgres 다이얼렉트 기준 컴파일까지 확인했다 (`alembic history`/`heads`로 구조도 확인 완료). 앞으로 스키마를 바꿀 때는 이 파일을 직접 고치지 말고, 로컬 Postgres를 띄운 뒤 `alembic revision --autogenerate -m "설명"`으로 새 리비전을 만들면 된다.

## 다음 순서 (project-spec.md 10절 로드맵 기준)

1. ~~실제 API 응답 확인·매핑~~ ✅ / ~~실제 Postgres 검증~~ ✅ (07-17) / ~~알림 문구 LLM + 폴백 체인~~ ✅ (07-19)
2. **Layer 2 LLM 위험도 보조 판단** — 규칙 매트릭스가 못 잡는(None) 케이스를 LLM으로 판단, `ai_risk_logs`에 기록. 문구 생성과 같은 폴백 체인 재사용
3. **주기 실행** — 지금은 수동 `POST /events/ingest` → 스케줄러로 10분 주기 자동 수집
4. FCM 웹푸시 실제 발송(서비스 계정 JSON 방식), 웹(PWA) 구독 관리 화면, JWT 인증
