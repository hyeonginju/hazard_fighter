# CLAUDE.md — 프로젝트 인수인계 & 작업 규칙

이 파일은 Claude Code가 세션 시작 시 자동으로 읽는 프로젝트 컨텍스트다.
"시켜줘, 명예소방관" — 공공데이터 기반 개인 맞춤형 이상상황 알림 백엔드 (peterju.cloud 사이드 프로젝트 #3, FDE 전직 준비용).

> **개발 배경·기술 결정의 상세 기록은 반드시 [`docs/dev-learning-notes.md`](docs/dev-learning-notes.md)를 먼저 읽을 것.**
> 그 문서에 "왜 이렇게 했는지"(판단 보류 원칙, 호출량 예산, 폴백 체인 등)가 다 담겨 있다.
> 전체 기획은 [`docs/project-spec.md`](docs/project-spec.md), 사용법은 [`README.md`](README.md).

## 사용자 프로필 (중요)

- 사용자(형인)는 **백엔드/DB 거의 입문 수준**이다. 개념을 짚어주며 진행하고, 터미널 명령은 주석 없이(zsh가 `#` 뒤를 인자로 먹는 사고가 있었음) 한 줄씩 제시할 것.
- 목적이 FDE 전직이라, **"기술을 왜/어떻게 썼는지"가 코드만큼 중요**하다. 작업할 때마다 결정의 근거를 설명하고 학습 노트에 남긴다.
- 응답은 한국어. 커밋 메시지도 한국어.

## 현재 상태 (2026-07-27 기준)

Phase 1 완료 + Phase 2 대부분 완료. **실기기까지 end-to-end 실증됨** (2026-07-22): 공공 API 실데이터 → 이름 기반 지역 매칭 → 위험도 판단(규칙+LLM) → LLM 개인화 문구 → FCM v1 실발송 → 모바일 크롬 백그라운드 수신. 테스트 138개 통과.

**동작하는 것:** 공공 API 4종 연동(기상특보/지진/홍수통제소/긴급재난문자), 특보 t6 파싱 지역 매칭, **이름 기반 지역 매칭**(crud.regions_match — 행정구역명↔예보구역명: 시도 표준화+'전체'+접두어), Layer 1 규칙 매트릭스, Layer 2 LLM 보조 판단(+ai_risk_logs), 긴급재난문자 Option A(risk_source=broadcast), 홍수통제소 분당 호출 상한 스로틀링, FCM 웹푸시 발송(생성/발송 분리 dispatch + v1 서비스계정, 미설정 시 mock — **실기기 검증 완료**), 웹 PWA 구독 화면(GET /app — 단일 폼+알림 게이트, 표준 행정구역 드롭다운 districts.js, 동적 서비스워커, 포그라운드 수신 핸들러), 구독 소급 평가, **알림 dedupe**(2026-07-23 — 예보구역 분할로 특보 하나에 푸시 N건 가던 문제: 같은 보호 대상에게 같은 통보문 시그니처(source·종류·등급·발표시각)면 1건만, 기상특보 한정, LLM 평가 앞에서 차단), LLM 문구 생성+3단계 폴백 체인, 10분 주기 스케줄러+중복 가드, 로그 시크릿 마스킹.

**인증 (2026-07-23 전환 완료):** 구글+카카오 소셜 로그인(서버사이드 code 흐름, `app/api/routes/auth.py`) + 30일 HS256 JWT(`app/services/auth.py`) + `get_current_user` 의존성(`app/api/deps.py`) — `user_email` 파라미터 전면 제거. 이메일·비밀번호 미수집, 식별은 users.(auth_provider, provider_user_id) 쌍 유니크. 계정당 보호 대상 상한 users.person_limit(기본 3, 초과 409 — 추후 유료 쿠폰이 올리는 구조). 화면: `/login`(소셜 버튼+지난 로그인 배지) → 콜백이 `/app#token=` fragment 로 JWT 전달 → localStorage 저장. 콘솔 실설정 전엔 로그인 라우트가 503 안내.

**인앱 브라우저 안내 (2026-07-27):** 카톡 등 앱 안 브라우저는 구글 OAuth 가 차단되고(`disallowed_useragent`) 웹푸시도 막힐 수 있어, `app/static/inapp.js` 가 UA 패턴으로 감지해 `/login`·`/app` 상단 배너로 안내(카카오톡·라인은 기본 브라우저 전환 버튼, 그 외는 주소 복사). 오탐이 미탐보다 비싸다는 기준으로 규칙을 좁게 잡음 — 네이버 웨일(UA 에 `NAVER` 포함)이 대표 오탐 위험이라 패턴은 `NAVER(inapp`. UA 규칙표는 node 로 실행해 테스트(node 없으면 skip). 실제 카톡 인앱 확인은 상시 가동 후.

**클라우드 배포 준비 완료 (2026-07-27, Cloud Run + Cloud Scheduler 방향):** 주기 실행을 앱 밖으로 빼는 구조로 간다 — 배포 시 `SCHEDULER_ENABLED=0` + Cloud Scheduler 가 10분마다 `POST /events/ingest` 호출. 근거는 학습노트 3-25(호출량 예산이 인스턴스 수에 곱해지는 문제). 준비된 것: ① `X-Ingest-Token` 인증(`app/api/deps.py:require_ingest_token`, 미설정 시 503 fail-closed) ② 가드 상태를 `ingest_runs` 테이블로(Alembic 0003) ③ Dockerfile(python 3.12, `$PORT`, `--proxy-headers --forwarded-allow-ips=*`) ④ `FCM_CREDENTIALS_JSON` 환경변수 경로 ⑤ 로딩 표시. 마이그레이션은 컨테이너 기동에 넣지 않았으니 **배포 시 1회 별도 실행** 필요.

**클라우드 자원 관계 (중요 — 중복 생성 방지):** **GCP 프로젝트 `hazard-fighter` 하나에 다 들어 있다** — Firebase(FCM) 설정·서비스계정, 구글 OAuth 클라이언트. Firebase 프로젝트 = GCP 프로젝트라서 07-22 FCM 설정 시점에 이미 만들어져 있었다(새로 만들 필요 없음). **Cloud Run 도 같은 프로젝트에 배포한다** (프로젝트가 IAM·결제·로그의 경계). 단 Spark 플랜엔 결제 계정이 없어 Cloud Run 용 **결제 연결은 필요**. DB 는 **Neon**(무료 티어, AWS 싱가포르 = Cloud Run 도 `asia-southeast1` 로 맞춘다 — 앱↔DB 거리가 사용자↔앱 거리보다 중요) — 앱은 pooled 접속, alembic 은 direct 접속.

**다음 할 일 (우선순위):**
1. **클라우드 실배포 진행** — `hazard-fighter` 프로젝트에 결제 연결 + gcloud 설치·인증(형인이 직접) → API 활성화 → Neon 에 마이그레이션 → Cloud Run 배포(`asia-southeast1`, `SCHEDULER_ENABLED=0`) → Cloud Scheduler 등록 → DNS 를 터널에서 Cloud Run 으로 → 콜드/웜 응답시간 측정(`curl -w "%{time_total}"`).
2. 쿠폰/결제(person_limit 확장 BM 연습 — 구조는 준비됨).
3. (선택) 홍수 관측소 동적 선정, 재난문자 폴링 주기 분리, webpush 옵션(아이콘·클릭 URL) 세분화.

**hazard.peterju.cloud 운영 방법 (07-23 구축):** 네임서버는 가비아→Cloudflare 이전됨(포트폴리오 Firebase A레코드는 프록시 OFF 유지 필수). named tunnel `hazard-fighter`(`~/.cloudflared/config.yml`) 가 hazard.peterju.cloud→localhost:8000 연결. 서비스 켜기: ① `uvicorn app.main:app --port 8000 --proxy-headers` (**--proxy-headers 필수** — 없으면 OAuth 리다이렉트가 http 로 생성돼 콘솔 등록값과 불일치) ② `cloudflared tunnel run hazard-fighter`. 구글/카카오 콘솔엔 localhost 와 hazard.peterju.cloud 콜백이 둘 다 등록돼 있음.

**소셜 로그인 실검증 완료(07-23):** 구글·카카오 실계정 로그인 데스크톱 검증됨. 콘솔 함정 기록 — 카카오 개편 콘솔은 Redirect URI 가 "카카오 로그인" 메뉴가 아니라 **앱 키(REST API 키)별 설정**에 있고, Client Secret 이 기본 활성이라 .env 에 KAKAO_CLIENT_SECRET 필수(없으면 KOE010).

**모바일 테스트 방법:** `https://hazard.peterju.cloud` 고정 주소 사용 (named tunnel — 위 운영 방법 참고, quick tunnel 은 이제 불필요). iPhone 은 Safari "홈 화면에 추가" 필요.

**긴급재난문자 관련 후속(선택):** 재난문자 전용 폴링 주기 분리(현재는 전 소스 공통 10분 — 재난문자는 2-call/사이클이라 288회/일), `전남광주통합특별시` 같은 비표준 시도명·시도-only(`전체`) 매칭 개선, DST_SE_NM 별 위험도 세분화.

## 아키텍처 한눈에

```
app/ingestion/*     공공 API 클라이언트 (BaseIngestionClient 상속, 키 없으면 mock)
app/services/
  ingest.py         파이프라인 오케스트레이션 (run_ingestion_cycle_guarded 진입점, 끝에서 dispatch 호출)
  llm.py            LLM 폴백 체인 (chat()) — 문구 생성·위험도 판단이 공유
  message.py        알림 문구 생성 (실패 시 템플릿 fallback)
  risk_ai.py        Layer 2 LLM 위험도 판단 (실패 시 판단 보류)
  dispatch.py       생성/발송 분리 — 미발송(sent_at=NULL) 알림을 모아 FCM 발송·sent_at 기록
  push.py           FCM HTTP v1 발송 클라이언트 (서비스계정 OAuth2, 미설정 시 no-op/mock)
app/risk/matrix.py  Layer 1 결정론적 규칙 매트릭스
app/static/*        웹 PWA 구독 화면 (순수 HTML+JS, GET /app 으로 서빙 — 빌드 도구 없음)
app/api/routes/web.py  /app·/firebase-config·동적 서비스워커(/firebase-messaging-sw.js) 서빙
app/scheduler.py    10분 주기 백그라운드 수집 루프 (lifespan에서 기동)
app/models/*        SQLAlchemy 모델 12개 (types.py = 다이얼렉트 호환 타입)
app/logging_utils.py 로그 시크릿 마스킹 필터
```

데이터 흐름: 수집 → events 저장(dedupe) → 구독 매칭 → Layer1 규칙(없으면 Layer2 LLM) → notifications 생성 → dispatch(미발송분 FCM 발송, sent_at 기록).

## 이 프로젝트의 반복 패턴 (새 코드도 이 원칙 따를 것)

- **낭비 호출 차단** — "상태를 기억해서 불필요한 외부 호출을 막는다"가 반복 모티프: 스케줄러 중복 가드, LLM 쿨다운(429 시 15분), Layer 2 판단 캐시, 이벤트 dedupe. 새 외부 호출을 추가하면 호출량 예산(학습노트 2026-07-20)을 먼저 따져볼 것.
- **graceful degradation** — LLM 등 외부 의존은 실패해도 서비스가 돌아가야 한다. LLM 실패 시: 문구는 템플릿 fallback, 위험도는 판단 보류(임의 판정 금지).
- **소스별 에러 격리** — 한 데이터 소스가 죽어도 나머지는 처리하고, 응답 `errors`에 소스별로 기록.
- **멱등성** — 같은 요청 반복해도 안전하게 (get-or-create, dedupe).
- **LLM 출력은 항상 검증** — 형식 강제 + 파싱 실패 시 버림.

## 작업 규칙

### 테스트
- `pytest` (프로젝트 루트, venv 활성화 상태). **DB 서버·외부 API 없이 전부 돈다** — 모델이 다이얼렉트 호환 타입이라 in-memory SQLite로, `tests/conftest.py`가 API 키를 비워 mock 강제, 스케줄러도 끔.
- 새 기능엔 테스트를 반드시 추가. 모듈 전역 상태(쿨다운·캐시·가드 시각)를 쓰면 autouse fixture로 테스트 간 격리할 것.
- 커밋/PR 전 `pytest` 통과 확인.

### 시크릿 위생 (엄격히)
- 실제 키는 `.env`에만 (gitignore됨). `.env.example`엔 **절대 실제 값 금지**, 빈 템플릿만.
- `secrets/`, `debug_responses/`도 gitignore됨.
- 커밋 전 `git ls-files | grep -E '^\.env$|^secrets/'` 로 시크릿 추적 여부 확인 (아무것도 안 나와야 정상).
- 로그에 키 노출 주의 — `logging_utils.py` 마스킹 필터가 있지만 새 시크릿은 `_collect_secrets()`에 추가.

### 커밋
- 한국어 메시지, "무엇을 왜"가 드러나게. 예: "스케줄러: 10분 주기 자동 수집 + 중복 실행 가드, 호출량 예산 반영".
- 원격: `origin` = GitHub private repo (`hyeonginju/hazard_fighter`). 히스토리는 git filter-repo로 시크릿 스크럽 완료 상태.

### 문서화 (분업 규칙)
- **코딩은 Claude Code, 문서 산출물(docx/pptx)은 Cowork**에서 진행한다. 한 번에 한 쪽에서만 편집(동시 편집 충돌 방지).
- 매 작업 후 `docs/dev-learning-notes.md`의 **Part 4 개발 일지**에 항목 추가(날짜는 `TZ=Asia/Seoul date`로 확인 — 샌드박스 시계 신뢰 금지). 새 기술 주제는 Part 3에 "개념→이 프로젝트에서→면접 한마디" 3단으로.
- `README.md`의 "지금 뭐가 되어 있나"·테스트 목록·"다음 순서"도 함께 갱신.
- docx 변환은 Cowork에서: `pandoc docs/dev-learning-notes.md -f gfm -t docx --toc --toc-depth=2 -V lang=ko -o docs/dev-learning-notes.docx`.

## 로컬 실행

```bash
cd ~/Desktop/dev/projects/hazard_fighter
source .venv/bin/activate          # 새 터미널마다 필요 (프롬프트에 (.venv))
docker compose up -d db            # Docker Desktop 실행 상태여야 함
alembic upgrade head
uvicorn app.main:app --reload      # http://localhost:8000/docs
```

- Python은 **3.12**로 venv 생성 (3.9는 프로젝트 문법·psycopg2 빌드 문제).
- 실제 API 응답 탐색: `python scripts/debug_fetch.py` → `debug_responses/`.
- DB 직접 조회: `docker compose exec db psql -U hazard -d hazard_fighter -c "..."`.
- LLM 실기기 데모: `python scripts/demo_layer2.py`.

## 알려진 함정 (이번 개발에서 실제로 겪음)

- 새 터미널은 `cd` + `source .venv/bin/activate` 먼저. 안 하면 `command not found: alembic`.
- 터미널에 명령 붙여넣을 때 **주석(`# ...`) 포함 금지** — zsh가 인자로 먹어 엉뚱한 폴더/venv 생성됨.
- 기상특보 `getWthrWrnList`는 관서 단위라 지역 매칭 불가 → `getWthrWrnMsg`의 `t6` 스냅샷을 파싱해야 함.
- 지진 API는 `fromTmFc/toTmFc` 필수 + 최대 조회 3일.
- Gemini 무료 모델명은 `gemini-flash-lite-latest` 같은 "latest" 별칭 사용 (구버전명은 `limit: 0` 429).
- 시간 언급 시 `TZ=Asia/Seoul date`로 한국 시간 확인할 것.
- 웹푸시 권한 요청(`Notification.requestPermission`)은 버튼 클릭 직후 **첫 번째 await**여야 함 — fetch 등을 먼저 하면 user activation 소진으로 모바일 크롬이 팝업 없이 조용히 거부.
- FCM 발송 성공(200) ≠ 사용자 눈에 표시됨 — 탭이 포그라운드면 메시지가 페이지로 와서 onMessage 핸들러 없이는 조용히 버려짐. 실기기에서 실제로 겪은 함정.
- **uvicorn `--proxy-headers` 만으로는 부족** — 신뢰 목록(기본 `127.0.0.1`)에서 온 `X-Forwarded-*` 만 반영한다. cloudflared 터널은 localhost 에서 붙어 통했지만 컨테이너/클라우드는 프록시 IP 가 달라 OAuth 리다이렉트가 http 로 생성된다. Dockerfile 은 `--forwarded-allow-ips=*` 를 함께 준다.
- **`secrets.compare_digest` 는 비ASCII str 에 TypeError** — 헤더는 latin-1 로 디코드되므로 401 이어야 할 요청이 500 이 된다. 항상 `.encode()` 해서 bytes 로 비교.
- **로컬에서 `POST /events/ingest` 호출 시 `X-Ingest-Token` 헤더 필요** (`.env` 의 `INGEST_TOKEN`). 미설정이면 503 — 자동 수집(스케줄러)은 함수 직접 호출이라 영향 없음.
- **시간 창을 가진 로직의 테스트에 절대 시각을 박으면 안 됨** — `test_dedupe.py`가 발표시각을 `2026-07-22`로 고정해 뒀다가, `backfill_subscription`의 "최근 48시간" 창을 벗어난 07-27에 깨졌다. 실행 시각 기준 상대값(`now - 12h`)으로 쓸 것.
- 실데이터 지역명은 행정구역명이 아니라 기상청 예보구역명(부산·경주남부·달성남부 등) — 지역 관련 코드는 `crud.regions_match` 매칭 규칙을 거칠 것.
