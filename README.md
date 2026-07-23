# 시켜줘, 명예소방관

공공데이터 기반 개인 맞춤형 이상상황 알림 플랫폼 — peterju.cloud 사이드 프로젝트 #3 (FDE 지원용).
전체 기획/근거는 [`docs/project-spec.md`](docs/project-spec.md) 참고. 이 저장소는 그중 **Phase 1: 데이터 파이프라인 & 백엔드 뼈대**를 구현한다.

## 지금 뭐가 되어 있나

**Phase 1 완료 + Phase 2 일부 — 실데이터로 개인 맞춤 알림 생성까지 검증됨 (2026-07-17~19):**

- FastAPI 백엔드 + PostgreSQL 스키마 (spec 9절 MVP 범위: users/persons/regions/subscriptions/events/notifications/risk_matrix/river_gauges 등 12개 테이블) — 실제 Postgres(Docker)에 생성 검증
- **실제 공공 API 4개 연동 검증 완료** (기상특보/지진/홍수통제소/긴급재난문자) — 키 없으면 자동 mock
- **특보→지역 매칭**: 통보문 상세(`getWthrWrnMsg`)의 `t6` 스냅샷을 파싱해 특보별 시군구 추출. 이벤트 중복 방지(dedupe) 포함
- 위험도 판단 로직 Layer 1 (spec 4절 규칙 매트릭스) — 실데이터로 "전남 광양 폭염주의보 + 고령 구독자 → HIGH 알림" 생성 확인
- **구독 소급 평가(backfill)**: 구독을 나중에 만들어도 이미 발효 중인 특보를 즉시 평가해 알림 생성. 지역명 정규화('광양시'→'광양') 포함
- **LLM 알림 문구 생성 + 3단계 폴백 체인**: 유료(OpenAI) → 무료(Gemini, `.env`의 `LLM_FALLBACK_*`) → 템플릿. quota 소진(429) 감지 시 해당 프로바이더 15분 쿨다운. 두 프로바이더 모두 실연동 검증됨
- **주기 자동 수집 스케줄러 (2026-07-20)**: 서버 기동 시 10분 주기 자동 ingest (asyncio, `app/scheduler.py`). 중복 실행 가드로 수동 `/events/ingest` 연타·겹침에도 공공 API 낭비 호출 없음. 주기는 API 호출량 예산 분석 기반(`docs/dev-learning-notes.md` 2026-07-20 항목), `.env`로 조정 가능
- **Layer 2 LLM 위험도 보조 판단 (2026-07-20)**: 규칙 매트릭스 밖 케이스를 LLM이 판단(`app/services/risk_ai.py`) → `ai_risk_logs` 감사 기록 → MEDIUM/HIGH만 `risk_source=ai` 알림 생성. LLM 실패 시 판단 보류(임의 판정 금지), 프로필 캐시로 호출 절약
- **로그 시크릿 마스킹 (2026-07-20)**: httpx 요청 로그에 노출되던 API 키를 루트 로거 필터로 자동 치환(`app/logging_utils.py`)
- **긴급재난문자 연동 (2026-07-22)**: safetydata `DSSP-IF-00247` 클라이언트(`app/ingestion/safety_disaster.py`). `crtDt` 날짜 필터 + 오름차순이라 마지막 페이지=최신을 잡는 2-call 방식, `DST_SE_NM` 비재해(기타·교통통제) denylist, 다지역 분리. **Option A(공식 방송 취급)**: 당국이 이미 방송한 경보라 위험엔진 재판정 없이 `risk_source=broadcast`/MEDIUM으로 알림, 문구는 `MSG_CN` 원문 기반 개인화. 오늘치 실데이터 90건(폭염/호우/산사태/화재/붕괴/홍수) 정규화 검증
- **FCM 웹푸시 발송 (2026-07-22)**: 생성/발송을 분리한 dispatch 단계(`app/services/dispatch.py`) — 알림을 `sent_at=NULL`로 쌓고, ingest 사이클 끝에서 미발송분만 모아 FCM HTTP v1(서비스계정 OAuth2, `app/services/push.py`)로 발송 후 `sent_at` 기록. `sent_at`이 멱등 가드라 중복발송 방지·실패 자동 재시도, 죽은 토큰(404) 자동 정리. 서비스계정 JSON이 없으면 no-op(mock)으로 degrade. `POST /device-tokens`로 기기 토큰 등록(멱등)
- **웹 PWA 구독 화면 (2026-07-22)**: `app/static/` 순수 HTML+JS를 FastAPI가 직접 서빙(`GET /app`) — 빌드 도구 없이 uvicorn 하나로 백엔드+프론트. **단일 폼**(이메일+보호 대상+지역)에 CTA 하나 — 알림 권한+FCM 토큰 발급이 관문(실패 시 등록 안 됨). 지역은 표준 행정구역 17개 시도 계단식 드롭다운(districts.js). FCM 서비스워커는 `.env`의 `FCM_WEB_*` 값을 주입해 동적 생성, 포그라운드 수신 핸들러 포함. 설정이 없으면 알림만 비활성(graceful)
- **이름 기반 지역 매칭 (2026-07-22)**: 사용자의 행정구역명(경주시)과 기상청 예보구역명(경주남부)의 간극을 `crud.regions_match`로 해소 — 시도 표준화(부산광역시↔부산, 전북특별자치도↔전북자치도) + '전체'(시도 단위 특보) + 시군구 접두어 비교. 실기기로 "경주시 구독 ← 경주 4개 구역 특보" 매칭 실증
- **FCM 실기기 발송 검증 (2026-07-22)**: cloudflared HTTPS 터널 → 모바일 크롬 토큰 발급 → 실발송(FCM v1, 200) → 백그라운드 수신 확인. 과정에서 웹푸시 함정 2개(권한 요청 전 await로 user activation 소진, 포그라운드 메시지 무표시) 수정
- **알림 dedupe (2026-07-23)**: 예보구역 분할(경주 폭염 → 남부/서부/동부/중북부 4건)로 특보 하나에 푸시가 구역 수만큼 가던 문제 해결 — 같은 보호 대상에게 같은 통보문 시그니처(source·종류·등급·발표시각)의 알림은 1건만 생성. 기상특보 한정(재난문자는 내용이 제각각이라 미적용), Layer 2 LLM 평가 앞에서 차단해 LLM 호출도 절약
- **소셜 로그인 + JWT 인증 (2026-07-23)**: `user_email` 임시 방식 전면 제거 → 구글+카카오 서버사이드 OAuth(`/auth/*`) + 30일 HS256 JWT + `get_current_user` 의존성. 이메일·비밀번호 미수집 — 식별은 (프로바이더, 회원번호) 쌍. 화면도 분리: `/login`(소셜 버튼 + "지난번 로그인" 배지) / `/app`(구독 설정+현황). **계정당 보호 대상 상한 3명**(users.person_limit — 남용 방지 실질 방어선, 초과 시 409, 추후 유료 쿠폰이 올리는 구조)
- 기본 REST API: 인물/지역/구독 CRUD(멱등), 이벤트 조회, 수동 ingest 트리거, 알림 조회, 기기 토큰 등록
- Docker Compose (Postgres + app), Alembic 마이그레이션, 테스트 122개(전부 DB 서버·외부 API 없이 돎)

아직 없는 것 (다음): named tunnel 고정 주소(`hazard.peterju.cloud`)+모바일 실검증 — 구글·카카오 실로그인은 데스크톱에서 검증 완료(07-23), 네임서버도 Cloudflare 이전 완료. 이후 인앱 브라우저 감지, 쿠폰/결제(BM 연습).

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
- `test_safety_disaster.py` — 긴급재난문자 지역 파싱(시도-only/시+구 복합/동 단위/쉼표 중복), 비재해 denylist 필터, broadcast 알림 생성
- `test_subscription_backfill.py` — 구독 소급 평가, 지역명 정규화, 구독 멱등성
- `test_message_generation.py` — LLM 폴백 체인(quota 소진 시 무료 전환·쿨다운·템플릿 폴백)
- `test_risk_ai.py` — Layer 2 판단(알림 생성·LOW 필터·판단 보류·캐시·형식 위반 처리)
- `test_scheduler_guard.py` — 수집 중복 실행 가드
- `test_hrfco_throttle.py` — 홍수통제소 분당 호출 상한 레이트 리미터(시계·sleep 주입)
- `test_push_dispatch.py` — 생성/발송 분리 dispatch(멱등 sent_at·재시도·죽은 토큰 정리·mock degrade)
- `test_region_match.py` — 이름 기반 지역 매칭(시도 표준화·'전체'·접두어, 행정구역명↔예보구역명)
- `test_dedupe.py` — 알림 dedupe(분할 구역 1건 합치기·새 통보문 재알림·재난문자 미적용·backfill 경로)
- `test_web_app.py` — PWA 화면 서빙(/app·/login), firebase-config·동적 서비스워커(설정 유무에 따른 degrade)
- `test_auth.py` — JWT 발급/위조/만료, 보호 라우트 401, 보호 대상 상한 409, 구글/카카오 콜백 흐름(httpx 모킹), 사용자 간 데이터 격리
- `test_user_accounts.py` — 소셜 사용자 (프로바이더, 회원번호) 식별, person_limit 상한
- `test_log_redaction.py` — 로그 시크릿 마스킹
- `test_health.py` — 헬스체크

운영 DDL은 Postgres를 타겟으로 하고(JSONB/네이티브 UUID 유지), 아래 Docker 절차로 실제 Postgres에 적용해 최종 확인한다.

## API 키 발급 현황

| 소스 | 상태 | 비고 |
|---|---|---|
| 기상특보 조회서비스 (data.go.kr 15000415) | ✅ 발급 완료 | `.env`의 `KMA_WARNING_API_KEY` |
| 지진정보 조회서비스 (data.go.kr 15000420) | ✅ 발급 완료 | `.env`의 `KMA_EARTHQUAKE_API_KEY` |
| 홍수통제소 표준수문DB (hrfco.go.kr) | ✅ 발급 완료 | `.env`의 `HRFCO_API_KEY`. data.go.kr 계정과 별개로 hrfco.go.kr에서 직접 발급. 인증키 신청 시 "사이트 URL(IP)"을 요구하는데, 개발 중인 컴퓨터 공인 IP나 보유 도메인(peterju.cloud)을 넣으면 됨. 배포 후 아웃바운드 IP가 바뀌면 재등록 필요 가능 (spec 12절 Open Question #8) |
| 긴급재난문자 (safetydata.go.kr) | ✅ 발급·연동 완료 (2026-07-22) | `.env`의 `SAFETYDATA_API_KEY`. `DSSP-IF-00247`, 클라이언트 `app/ingestion/safety_disaster.py` 구현·실데이터 검증 완료. **일일 한도 1,000건**이라 2-call/사이클(288회/일)로 설계 — 폴링 주기 10분 이상 유지 필수 |
| LLM 유료 — 알림 문구 생성 | ✅ 발급·충전 완료 (OpenAI) | `.env`의 `OPENAI_API_KEY`. 선불 크레딧 필요(없으면 insufficient_quota → 자동으로 폴백 체인 작동) |
| LLM 무료 폴백 (Gemini) | ✅ 발급 완료 | `.env`의 `LLM_FALLBACK_*` 3종. aistudio.google.com/apikey 에서 무료 발급. 모델명은 `gemini-flash-lite-latest` 같은 "latest" 별칭 권장 — 구버전 모델명은 무료 티어가 닫히면 `limit: 0` 429 가 남 |
| Firebase Cloud Messaging — 웹푸시 | ✅ 실기기 발송 검증 완료 (2026-07-22) | 레거시 `FCM_SERVER_KEY`는 2024.7 폐기됨. 서비스 계정 JSON 방식: Firebase 콘솔 → 프로젝트 설정 → 서비스 계정 → 비공개 키 생성 → `secrets/firebase-service-account.json`. `.env`는 `GOOGLE_APPLICATION_CREDENTIALS`(파일 경로) + `FCM_PROJECT_ID`. **발송 파이프라인(`push.py`/`dispatch.py`)은 구현·테스트 완료** — 자격증명이 없으면 mock으로 degrade하므로, JSON만 넣으면 실발송 전환 |

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
| 홍수통제소 | ✅ 동작 | `api.hrfco.go.kr` 수위 임계치 판정 방식. 모니터링 관측소가 청주 2곳 하드코딩 → 구독 지역 기반 동적 선정(river_gauges 테이블 활용)은 Phase 2. 분당 호출 상한 스로틀링 적용(동적 선정 시 분당 1,000 한도 방어) |
| LLM (문구 생성 + Layer 2 판단) | ✅ 폴백 체인까지 동작 | OpenAI·Gemini 실연동 검증. 범용 체인(app/services/llm.py)을 문구 생성·위험도 판단이 공유 |

## 왜 초기 마이그레이션이 `create_all`/`drop_all` 방식인가

로컬에 Postgres를 바로 못 띄우는 환경(이 스캐폴딩을 만든 세션)에서 작성하다 보니 `alembic revision --autogenerate`를 실제 DB에 돌려볼 수 없었다. 그래서 `migrations/versions/0001_initial_schema.py`는 `Base.metadata.create_all()`을 직접 호출하는 방식으로 작성했고, DDL은 `create_mock_engine`으로 Postgres 다이얼렉트 기준 컴파일까지 확인했다 (`alembic history`/`heads`로 구조도 확인 완료). 앞으로 스키마를 바꿀 때는 이 파일을 직접 고치지 말고, 로컬 Postgres를 띄운 뒤 `alembic revision --autogenerate -m "설명"`으로 새 리비전을 만들면 된다.

## 다음 순서 (project-spec.md 10절 로드맵 기준)

1. ~~실제 API 응답 확인·매핑~~ ✅ / ~~실제 Postgres 검증~~ ✅ (07-17) / ~~알림 문구 LLM + 폴백 체인~~ ✅ (07-19)
2. ~~주기 실행(스케줄러)~~ ✅ (07-20, 내장 asyncio + 가드)
3. ~~Layer 2 LLM 위험도 보조 판단~~ ✅ (07-20 — 2계층 하이브리드 완성)
4. ~~긴급재난문자 클라이언트~~ ✅ (07-22 — Option A 공식 방송 취급, DST_SE denylist, 실데이터 검증)
5. ~~홍수통제소 스로틀링~~ ✅ (07-22 — 분당 호출 상한 레이트 리미터, 동적 선정 전 안전장치)
6. ~~FCM 웹푸시 발송~~ ✅ (07-22 — 생성/발송 분리 dispatch + v1 서비스계정, 미설정 시 mock)
7. ~~웹(PWA) 구독 관리 화면~~ ✅ (07-22 — 단일 폼+알림 게이트, 행정구역 드롭다운+이름 기반 매칭)
8. ~~FCM 실기기 발송 검증~~ ✅ (07-22 — HTTPS 터널로 모바일 토큰 발급→실발송→백그라운드 수신 실증)
9. ~~알림 dedupe~~ ✅ (07-23 — (보호 대상, 통보문 시그니처)당 1건, 기상특보 한정)
10. ~~JWT 인증~~ ✅ (07-23 — 구글+카카오 소셜 로그인 + 30일 JWT, 보호 대상 상한 3명)
11. 소셜 로그인 실검증(콘솔 설정) + peterju.cloud 배포, 인앱 브라우저 감지, 쿠폰/결제(BM 연습)
