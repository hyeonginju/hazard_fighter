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

## 현재 상태 (2026-07-20 기준)

Phase 1 완료 + Phase 2 대부분 완료. 실데이터로 "공공 API → 지역 매칭 → 위험도 판단(규칙+LLM) → 개인 맞춤 알림 생성"까지 end-to-end 검증됨. 테스트 57개 통과.

**동작하는 것:** 공공 API 4종 연동(기상특보/지진/홍수통제소/긴급재난문자), 특보 t6 파싱 지역 매칭, Layer 1 규칙 매트릭스, Layer 2 LLM 보조 판단(+ai_risk_logs), 긴급재난문자 Option A(공식 방송 취급, risk_source=broadcast), 구독 소급 평가, LLM 문구 생성+3단계 폴백 체인, 10분 주기 스케줄러+중복 가드, 로그 시크릿 마스킹.

**다음 할 일 (우선순위):**
1. **홍수통제소 호출 스로틀링** — 관측소 동적 선정 도입 시 분당 1,000건 초과하면 키 차단(3회 위반). 순차 호출/스로틀 필요.
2. FCM 웹푸시 발송(서비스 계정 JSON), 웹 PWA 구독 화면, JWT 인증.

**긴급재난문자 관련 후속(선택):** 재난문자 전용 폴링 주기 분리(현재는 전 소스 공통 10분 — 재난문자는 2-call/사이클이라 288회/일), `전남광주통합특별시` 같은 비표준 시도명·시도-only(`전체`) 매칭 개선, DST_SE_NM 별 위험도 세분화.

## 아키텍처 한눈에

```
app/ingestion/*     공공 API 클라이언트 (BaseIngestionClient 상속, 키 없으면 mock)
app/services/
  ingest.py         파이프라인 오케스트레이션 (run_ingestion_cycle_guarded 진입점)
  llm.py            LLM 폴백 체인 (chat()) — 문구 생성·위험도 판단이 공유
  message.py        알림 문구 생성 (실패 시 템플릿 fallback)
  risk_ai.py        Layer 2 LLM 위험도 판단 (실패 시 판단 보류)
app/risk/matrix.py  Layer 1 결정론적 규칙 매트릭스
app/scheduler.py    10분 주기 백그라운드 수집 루프 (lifespan에서 기동)
app/models/*        SQLAlchemy 모델 12개 (types.py = 다이얼렉트 호환 타입)
app/logging_utils.py 로그 시크릿 마스킹 필터
```

데이터 흐름: 수집 → events 저장(dedupe) → 구독 매칭 → Layer1 규칙(없으면 Layer2 LLM) → notifications 생성.

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
