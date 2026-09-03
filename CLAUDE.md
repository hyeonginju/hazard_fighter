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

## 현재 상태 (2026-07-30 기준)

Phase 1 완료 + Phase 2 대부분 완료. **실기기까지 end-to-end 실증됨** (2026-07-22): 공공 API 실데이터 → 이름 기반 지역 매칭 → 위험도 판단(규칙+LLM) → LLM 개인화 문구 → FCM v1 실발송 → 모바일 크롬 백그라운드 수신. 테스트 147개 통과.

**프로덕션 점검 + 조용한 실패 수정 (2026-07-30):** 배포 3일 뒤 점검에서 **겉보기 지표는 정상인데(5xx 0건, 웜 0.3초, 수집 401회 전부 200) 알림만 이틀째 안 나가던 상태**를 발견 — 기기 토큰 0개·미발송 8건. 원인 ① 죽은 토큰(FCM 404)은 자동 정리하는데 재등록 경로가 구독 폼뿐 + localStorage 캐시가 죽은 토큰을 붙들어 **스스로 복구 불가** ② `ingest`·`dispatch` 에 로그가 없어 무음(스케줄러를 앱 밖으로 빼면서 결과 dict 를 보던 사람이 사라짐). 수정: 사이클 요약 INFO + 사람이 알아야 할 상황만 WARNING(**정상일 때 조용한 것까지 테스트로 고정**), `/app` 열 때마다 FCM 토큰을 서버와 동기화(멱등 POST, 권한 요청은 하지 않음), 화면에 기기 등록 배지(`#push-status`). 밀린 8건은 `sent_at` 을 찍어 발송 제외(삭제 아님 — 되돌릴 수 있고 기록도 남김). 자세한 건 학습노트 3-26·Part 4 07-30.

**푸시 복구 실증 + 태그 해상도 한계 발견 (2026-08-01):** 폰에서 `/app` 을 열자 토큰이 서버와 동기화되고 배지가 떠 07-30 수정이 실제로 작동함을 확인. 보호 대상(여자친구·경기도 안양) 추가 후 실발송 성공. 이때 나이대를 영유아/아동으로 잘못 등록해 "통학" 문구가 나왔고, 성인으로 고치니 **위험도도 HIGH→MEDIUM 으로 함께 이동**(규칙 매트릭스가 나이대를 실제로 쓴다는 실증). 그런데도 통근 문구가 안 나와 파고드니 **태그 enum 값 `실외근무/통학통근 중` 이 통학·통근을 한 문자열에 묶고 있어 LLM 이 구분할 근거가 없었다** — 태그 텍스트만 바꾸자 즉시 해결. 프롬프트가 아니라 분류 체계가 천장이었다. 자세한 건 학습노트 Part 4 08-01.

**⏸️ 수집 스케줄러 일시중지 (2026-08-23):** Neon 무료 한도(100 CU-시간)를 23일 만에 80% 소진했다는 경고를 받고 **Cloud Scheduler `hazard-ingest` 를 `pause` 했다.** 원인은 트래픽이 아니라 **10분 주기 크론이 Neon 의 5분 유휴 타임아웃보다 짧아 scale to zero 가 무력화된 것**(가동률 약 55% → 3.5 CU-시간/일, 실측 80.2÷23=3.49 로 계산 일치). 게다가 아래 1번 장애로 8일째 신규 이벤트 0건이라 **아무것도 수집하지 못하면서 DB 만 깨우고 있었다.** Cloud Run 과 Neon 은 **그대로 살려뒀다** — 포트폴리오 목적이라 `hazard.peterju.cloud` 가 열리는 것 자체가 산출물이고, 방문 시에만 깨어나므로 소비가 미미하다. 재개는 `gcloud scheduler jobs resume hazard-ingest --location=asia-southeast1 --project=hazard-fighter` 한 줄(주기 설정 `*/10` 은 보존됨). **단, 재개 전에 아래 0번(소스 차단)과 1번(신선도 필터)을 먼저 처리할 것** — 안 그러면 소비만 다시 시작되고 미발송 169건이 쏟아진다. 자세한 건 학습노트 3-27·Part 4 08-23.

**🛑 수집 중단 — 고치지 않기로 한 결정 (2026-08-28):** 아래 1번의 원인은 규명됐고, **회복하지 않기로 정했다.** 미해결 과제가 아니라 내린 판단이다 — 다음에 이 파일을 읽는 사람이 반사적으로 달려들지 않도록 구분해 적는다. 근거: ① 실사용자 0명이라 13일 중단 동안 아무 불편이 없었다 ② 밀린 169건은 이미 상한 데이터다 ③ **차단은 남의 방화벽이라 고치는 게 아니라 우회하는 일**이고, Job 분리로 IP 를 매번 다시 뽑아도 측정 성공률 1/3 기준 사이클당 70~80% 가 천장이며 상대가 조이면 다시 내려간다. 포트폴리오 목적에는 **작동하는 크론보다 규명 기록이 더 값나간다**(학습노트 Part 4 08-28 세 번째 항목). **재개하고 싶어지면 아래 조건을 먼저 볼 것.**

**⚠️ 재개 전 반드시 처리할 것 (장전된 총):** 미발송 **169건**(전부 긴급재난문자, 8/2~8/15, 08-23 로그 기준)이 그대로 있다. 스케줄러를 재개했을 때 기기 토큰이 살아 있으면 **8월 초 재난문자 169건이 한꺼번에 쏟아진다.** 07-30 에 밀린 8건을 `sent_at` 만 찍어 발송에서 제외한(삭제 아님) 것과 같은 처리를 먼저 하거나, 알림 신선도 필터(아래 1번)를 먼저 넣을 것.

**참고 — 2026-08-17 점검에서 발견한 상태:**
1. **수집 전면 중단 — 원인 규명 완료(2026-08-28), 회복 설계 미착수.** 공공 API 서버가 **Cloud Run 의 egress IP 를 IP 단위로 차단**하고 있다. 실험으로 배제한 것: 키 만료·코드(로컬에서 4/4 성공), egress 고장·한국행 경로(같은 리전에서 naver·google 은 붙음), **지리 기반 차단 → 서울 리전 이전(서울에서도 똑같이 실패 — 이전은 답이 아니다)**. IP 6개 병렬 측정에서 2개만 통과했고 같은 `/24` 안에서 갈렸다(`.18` 막힘 / `.61` 통과). 기상청·재난문자는 IP별로 완전히 동일하게 움직여 같은 상위 보안 장비를 공유하는 것으로 보이고, hrfco 는 6개 전부 실패하는 더 넓은 별도 차단(07-27 판단 확인). 8일 연속 100% 실패였던 건 **인스턴스가 7일 반 동안 안 바뀌어(10분 크론이 계속 깨움) 나쁜 IP 에 갇혔기 때문.** 우리 호출량(하루 864회, 한도 내)이 차단을 불렀다는 증거는 없다 — 표본 6개 중 4개가 이미 막혀 있었으니 풀 자체가 오염된 것에 가깝다. **고정 IP(Cloud NAT)는 피할 것** — 월 30~45달러인데다 그 IP 가 차단되면 다시 뽑을 수도 없다. 자세한 건 학습노트 Part 4 08-28.
2. **기기 토큰 다시 0개 + 미발송 169건**(전부 긴급재난문자, 8/2~8/15). 07-30 복구 경로는 `/app` **방문이 있어야** 작동하는 기회형이라, 16일 미방문 동안 수정 이전 상태로 돌아갔다. 토큰이 살아나면 169건이 한꺼번에 쏟아지므로 **신선도 필터를 먼저 넣거나 밀린 건을 정리한 뒤** 복구할 것.
3. **로그는 정확히 남았는데 아무도 안 읽었다** — WARNING 4줄이 매 사이클 16일간 기록됐다. 관측성의 다음 단계는 **도달**(로그 기반 측정항목 + 알림 정책 → 이메일).

**동작하는 것:** 공공 API 4종 연동(기상특보/지진/홍수통제소/긴급재난문자), 특보 t6 파싱 지역 매칭, **이름 기반 지역 매칭**(crud.regions_match — 행정구역명↔예보구역명: 시도 표준화+'전체'+접두어), Layer 1 규칙 매트릭스, Layer 2 LLM 보조 판단(+ai_risk_logs), 긴급재난문자 Option A(risk_source=broadcast), 홍수통제소 분당 호출 상한 스로틀링, FCM 웹푸시 발송(생성/발송 분리 dispatch + v1 서비스계정, 미설정 시 mock — **실기기 검증 완료**), 웹 PWA 구독 화면(GET /app — 단일 폼+알림 게이트, 표준 행정구역 드롭다운 districts.js, 동적 서비스워커, 포그라운드 수신 핸들러), 구독 소급 평가, **알림 dedupe**(2026-07-23 — 예보구역 분할로 특보 하나에 푸시 N건 가던 문제: 같은 보호 대상에게 같은 통보문 시그니처(source·종류·등급·발표시각)면 1건만, 기상특보 한정, LLM 평가 앞에서 차단), LLM 문구 생성+3단계 폴백 체인, 10분 주기 스케줄러+중복 가드, 로그 시크릿 마스킹.

**인증 (2026-07-23 전환 완료):** 구글+카카오 소셜 로그인(서버사이드 code 흐름, `app/api/routes/auth.py`) + 30일 HS256 JWT(`app/services/auth.py`) + `get_current_user` 의존성(`app/api/deps.py`) — `user_email` 파라미터 전면 제거. 이메일·비밀번호 미수집, 식별은 users.(auth_provider, provider_user_id) 쌍 유니크. 계정당 보호 대상 상한 users.person_limit(기본 3, 초과 409 — 추후 유료 쿠폰이 올리는 구조). 화면: `/login`(소셜 버튼+지난 로그인 배지) → 콜백이 `/app#token=` fragment 로 JWT 전달 → localStorage 저장. 콘솔 실설정 전엔 로그인 라우트가 503 안내.

**인앱 브라우저 안내 (2026-07-27):** 카톡 등 앱 안 브라우저는 구글 OAuth 가 차단되고(`disallowed_useragent`) 웹푸시도 막힐 수 있어, `app/static/inapp.js` 가 UA 패턴으로 감지해 `/login`·`/app` 상단 배너로 안내(카카오톡·라인은 기본 브라우저 전환 버튼, 그 외는 주소 복사). 오탐이 미탐보다 비싸다는 기준으로 규칙을 좁게 잡음 — 네이버 웨일(UA 에 `NAVER` 포함)이 대표 오탐 위험이라 패턴은 `NAVER(inapp`. UA 규칙표는 node 로 실행해 테스트(node 없으면 skip). **실제 카카오톡 인앱에서 배너·전환 버튼 실확인 완료(07-27 배포 후).**

**클라우드 배포 준비 완료 (2026-07-27, Cloud Run + Cloud Scheduler 방향):** 주기 실행을 앱 밖으로 빼는 구조로 간다 — 배포 시 `SCHEDULER_ENABLED=0` + Cloud Scheduler 가 10분마다 `POST /events/ingest` 호출. 근거는 학습노트 3-25(호출량 예산이 인스턴스 수에 곱해지는 문제). 준비된 것: ① `X-Ingest-Token` 인증(`app/api/deps.py:require_ingest_token`, 미설정 시 503 fail-closed) ② 가드 상태를 `ingest_runs` 테이블로(Alembic 0003) ③ Dockerfile(python 3.12, `$PORT`, `--proxy-headers --forwarded-allow-ips=*`) ④ `FCM_CREDENTIALS_JSON` 환경변수 경로 ⑤ 로딩 표시. 마이그레이션은 컨테이너 기동에 넣지 않았으니 **배포 시 1회 별도 실행** 필요.

**클라우드 자원 관계 (중요 — 이름이 비슷한 프로젝트가 여러 개다):** Firebase 프로젝트 = GCP 프로젝트라서 07-22 FCM 설정 시점에 이미 만들어져 있었다(새로 만들 필요 없음). **자원이 두 프로젝트에 흩어져 있다** — 검증은 `gcloud projects list` 의 PROJECT_NUMBER 와 자원 ID 접두 번호(OAuth client_id, FCM appId/messagingSenderId) 대조:

| 자원 | 프로젝트 | 번호 |
|---|---|---|
| FCM(서버·웹), Cloud Run 배포 대상 | `hazard-fighter` | 608692423557 |
| **구글 OAuth 클라이언트** (리다이렉트 URI 추가는 여기서!) | `hazard-fighter-503307` (표시명 "hazard fighter") | 480606898875 |
| Gemini API 키 (LLM 폴백) 추정 위치 | `gen-lang-client-*` (AI Studio 자동 생성) | — **삭제 금지** |

기능상 문제는 없다(OAuth 는 client_id/secret 로 동작). `hazard-fighter` 에 결제 연결 완료(Firebase 결제 계정) + run/artifactregistry/cloudbuild/cloudscheduler API 활성화 완료. DB 는 **Neon**(무료 티어, AWS 싱가포르 = Cloud Run 도 `asia-southeast1` 로 맞춘다 — 앱↔DB 거리가 사용자↔앱 거리보다 중요) — 앱은 pooled 접속, alembic 은 direct 접속.

**클라우드 실배포 완료 + 모바일 실검증 (2026-07-27):** Cloud Run + Cloud Scheduler + Neon + 도메인 매핑까지 전부 가동 — 맥이 꺼져도 돈다. 실측: 웜 0.3초, 배포 직후 첫 요청 0.32초(startup probe 사전 기동), 실데이터 133건 수집·dedupe·DB 가드 프로덕션 검증. **Neon DB 는 새로 시작(로컬 데이터 미이관)** — 폰에서 옛 JWT 401→자동 로그아웃 → 재로그인 → 구독 → **backfill 알림 푸시 수신** → **카톡 인앱 배너 실확인**까지 5단계 전부 통과.

**다음 할 일 (우선순위 — 08-17 점검의 장애 두 건이 맨 앞):**
0. ~~수집 회복~~ — **보류 결정(2026-08-28).** 위 🛑 항목 참고. 다시 하고 싶어지면 방향은 ① 주기 늘리기(30분 이상 — Neon 유휴 타임아웃·Cloud Run 인스턴스 수명 양쪽을 넘긴다) ② Cloud Run Job 분리(매 실행이 새 컨테이너 = 새 IP 추첨)다. **리전 이전과 고정 IP(Cloud NAT)는 하지 말 것** — 전자는 측정으로 배제됐고, 후자는 월 30~45달러인데다 그 IP 가 차단되면 다시 뽑을 수조차 없다.
0-1. **[긴급] 로그 기반 경고 알림** — Cloud Logging 측정항목 + 알림 정책으로 WARNING 을 이메일까지 도달시킨다. 두 번 연속 "로그는 있는데 늦게 발견"이 반복됐다.
0-2. **태그 `실외근무/통학통근 중` 분리** — `실외 통학 중`/`실외 통근 중`/`실외근무`. 위험도 매트릭스 trigger_value 이기도 해서 문구·판정 양쪽 해상도를 동시에 제한한다.
1. **알림 신선도 필터** — 공공 API 가 2023년 9월 재난문자 185건을 돌려준 사이클이 있었고 그게 알림 2건까지 만들었다. cutoff 는 `backfill_subscription`(48h)에만 있고 평상시 경로엔 없다. 저장은 하되 알림은 만들지 않는 창(24h 등)을 두는 방향.
2. **재난문자 페이지 경계 유실** — `safety_disaster.py` 의 "총건수로 마지막 페이지만 읽기"가 total 100 경계를 넘을 때 직전 페이지 뒷부분(최대 99건)을 건너뛴다. 마지막 페이지 + 직전 페이지를 같이 읽으면 끝(dedupe 가 중복 흡수).
3. **hrfco 타임아웃 축소/차단** — 클라우드에서 못 쓰는 소스가 사이클 26.5초의 15초(57%)를 먹고 Cloud Run 무료 CPU 한도의 64% 중 절반가량을 소비한다.
4. **`/` 리다이렉트 + robots.txt** — 도메인만 치면 404(3일간 89건).
5. **쿠폰/결제** (person_limit 확장 BM 연습 — 구조는 준비됨: users.person_limit, 초과 시 409). 쿠폰(결제 없이 완결) → 결제(쿠폰 적용을 호출하는 트리거) 순서로. 국내 PG 실결제는 사업자등록·심사가 필요해 테스트 키까지가 현실적.
6. (선택) 홍수 관측소 동적 선정(+hrfco 해외 IP 차단 대응으로 서울 리전 재검토), 재난문자 폴링 주기 분리, webpush 옵션(아이콘·클릭 URL) 세분화, Artifact Registry 옛 이미지 정리, 예산 알림 설정 확인.

**hazard.peterju.cloud 운영 (07-27부터 클라우드 상시 가동):** **Cloud Run 서비스 `hazard-fighter`(asia-southeast1, GCP 프로젝트 `hazard-fighter`)가 서빙한다 — 맥과 무관하게 24시간 돈다.** Cloudflare DNS: `hazard` CNAME → `ghs.googlehosted.com`(DNS only, 도메인 매핑 + 자동 인증서). DB 는 Neon(싱가포르), 수집은 Cloud Scheduler `hazard-ingest`(asia-southeast1, 10분 주기, `X-Ingest-Token` 헤더) — **2026-08-23 부터 `PAUSED`**(위 ⏸️ 항목 참고, 재개 전 조건 있음). 프로덕션은 `DOCS_ENABLED=0`(API 문서·스키마 비공개, 2026-08-28부터). 배포 갱신: `gcloud run deploy hazard-fighter --source . --region asia-southeast1`(환경변수는 기존 리비전에서 승계). 환경변수 일괄 갱신은 `.env`→YAML 스크립트(학습노트 07-27 참고). 스키마 변경 시 배포 전에 Neon direct 주소로 `alembic upgrade head` 1회. **hrfco(홍수통제소)는 해외 IP 차단으로 클라우드에서 타임아웃** — 수용 결정(학습노트 07-27), 관측소 동적 선정 때 재검토. (구)로컬 터널 운영: named tunnel `hazard-fighter` 설정은 `~/.cloudflared/` 에 남아 있으나 DNS 가 더 이상 터널을 가리키지 않음. 구글/카카오 콘솔엔 localhost 와 hazard.peterju.cloud 콜백이 둘 다 등록돼 있고 **콘솔 수정 없이 그대로 유효**(도메인 유지 덕).

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
- **변환 산출물(`*.docx`·`*.pdf`)은 커밋하지 않는다** (2026-08-23부터 gitignore). 저장소엔 소스(`.md`)만 두고 산출물은 필요할 때 재생성한다 — 산출물이 소스보다 뒤처진 채 커밋되는 걸 막기 위해서다. 로컬 파일은 그대로 있고, 08-23 이전 docx 버전은 히스토리에서 꺼낼 수 있다(`git show <커밋>:docs/dev-learning-notes.docx > 복구.docx`).

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
- **마이그레이션에 `Base.metadata.create_all()` 쓰지 말 것** — 0001 이 그렇게 돼 있어서, 빈 DB 에 `alembic upgrade head` 하면 0001 이 현재 모델 전체를 만들고 0002 가 "컬럼 이미 있음"으로 죽었다(배포 첫 명령에서 발견). 0001 은 명시적 DDL 로 고정됨. 새 리비전은 `alembic revision --autogenerate` 로 만들고, **빈 DB 에 체인을 재생한 뒤 `DATABASE_URL=... python scripts/verify_schema.py` 로 모델과 대조**할 것.
- **uvicorn `--proxy-headers` 만으로는 부족** — 신뢰 목록(기본 `127.0.0.1`)에서 온 `X-Forwarded-*` 만 반영한다. cloudflared 터널은 localhost 에서 붙어 통했지만 컨테이너/클라우드는 프록시 IP 가 달라 OAuth 리다이렉트가 http 로 생성된다. Dockerfile 은 `--forwarded-allow-ips=*` 를 함께 준다.
- **`secrets.compare_digest` 는 비ASCII str 에 TypeError** — 헤더는 latin-1 로 디코드되므로 401 이어야 할 요청이 500 이 된다. 항상 `.encode()` 해서 bytes 로 비교.
- **로컬에서 `POST /events/ingest` 호출 시 `X-Ingest-Token` 헤더 필요** (`.env` 의 `INGEST_TOKEN`). 미설정이면 503 — 자동 수집(스케줄러)은 함수 직접 호출이라 영향 없음.
- **시간 창을 가진 로직의 테스트에 절대 시각을 박으면 안 됨** — `test_dedupe.py`가 발표시각을 `2026-07-22`로 고정해 뒀다가, `backfill_subscription`의 "최근 48시간" 창을 벗어난 07-27에 깨졌다. 실행 시각 기준 상대값(`now - 12h`)으로 쓸 것.
- 실데이터 지역명은 행정구역명이 아니라 기상청 예보구역명(부산·경주남부·달성남부 등) — 지역 관련 코드는 `crud.regions_match` 매칭 규칙을 거칠 것.
- **정리(cleanup) 코드를 쓰면 복구(recovery) 코드를 짝지어 쓸 것** — 죽은 FCM 토큰 삭제는 있었는데 재등록이 사용자 행동 하나에만 걸려 있어서, 한 번 끊긴 뒤 알림이 이틀간 안 갔다(2026-07-30 발견). "무엇이 이걸 다시 만들어주나?"에 답이 없으면 그 정리는 편도 티켓.
- **주기 작업 결과는 로그로 남길 것** — Cloud Scheduler 는 HTTP 응답을 버리므로, 로컬에서 눈으로 보던 결과 dict 가 프로덕션에선 아무 데도 안 남는다. 그리고 정상일 때는 WARNING 이 없어야 한다(경고가 흔하면 아무도 안 읽는다).
- **공공 API 는 날짜 필터를 무시하고 옛 레코드를 줄 수 있다** — `crtDt=오늘` 요청에 2023년 재난문자가 섞여 왔고 알림까지 생성됐다. 상류를 못 막으면 하류(알림 생성)에서 신선도로 걸러야 한다.
- **공개 읽기 엔드포인트도 과금 레버가 된다** — `GET /regions`·`/events` 는 데이터가 비밀이 아니라 열어뒀는데, 그 요청이 **Neon 컴퓨트를 깨운다**. 누가 4분마다 한 번만 찔러도 DB 가 종일 깨어 있다(08-23 에 우리 크론이 무료 한도 80% 를 태운 것과 같은 메커니즘). 08-28 에 둘 다 인증으로 막음. **"읽혀서 잃을 게 있나"만 묻지 말고 "이 요청이 계량기를 돌리나"도 물을 것.**
- **`/docs` 를 끌 땐 `openapi_url` 도 같이 꺼야 한다** — `docs_url` 만 None 으로 두면 사람이 보는 화면만 사라지고 `/openapi.json` 은 그대로 열려 스캐너가 엔드포인트 목록을 계속 읽는다. `DOCS_ENABLED=0` 이 셋을 함께 끈다(로컬 기본값은 켬).
- **`gcloud billing budgets create` 는 결제 계정 통화를 안 맞추면 `INVALID_ARGUMENT`** — 이 계정은 KRW 라서 `--budget-amount=5USD` 가 계속 거부됐고, 에러는 통화 얘기를 한마디도 안 한다. `10000KRW` 로 통과. 결제 계정에 `peters-weather` 도 붙어 있으니 `--filter-projects` 를 꼭 걸 것.
- **인증을 나중에 도입하면 먼저 만든 라우트가 빠진다** — 07-23 에 인증을 전면 도입할 때 `POST /regions` 만 "조회표"라는 이유로 누락돼 무인증 쓰기로 남아 있었다(08-28 저장소 공개 점검에서 발견). `/docs` 가 켜져 있어 이미 발견 가능한 상태였다 — **공개가 위험을 만든 게 아니라 점검이 있던 위험을 보게 했다.** 새 라우트를 추가하면 `grep -n 'get_current_user' app/api/routes/*.py` 로 빠진 문을 확인할 것.
- 프로덕션 상태 점검은 로그(`gcloud logging read '... "수집 사이클"'`)와 DB 집계(`ingest_runs`·`notifications.sent_at is null`·`device_tokens` 행수)를 같이 볼 것 — `/health` 200 은 "알림이 나가고 있다"를 뜻하지 않는다.
