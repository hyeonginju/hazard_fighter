# 시켜줘, 명예소방관 — 개발 학습 노트

> 이 프로젝트를 만들면서 쓴 기술들이 **무엇이고, 왜 골랐고, 이 프로젝트에서 어떻게 쓰였는지**를 입문자 관점에서 정리한 문서다.
> FDE(Forward Deployed Engineer) 전직 준비용으로, 나중에 이 문서를 보고 공부하고, 기록을 되짚고, 블로그를 쓰기 위해 계속 업데이트한다.

---

## 0. 이 문서 사용법

이 문서는 두 부분이 합쳐진 하이브리드 형식이다.

- **Part 1~3 (학습 가이드)** — 주제별로 정리. "이 개념이 뭔지" 모를 때 찾아보는 사전처럼 쓴다.
- **Part 4 (개발 일지)** — 시간순 기록. "그때 왜 그렇게 했더라"를 되짚거나 블로그 초안으로 쓴다.
- **Part 5~7** — 다음 할 일, 용어 사전, 블로그 소재.

각 주제는 아래 3단 구조로 쓴다:

- 💡 **개념** — 배경지식 없이도 이해할 수 있게 쉬운 설명
- 🔧 **이 프로젝트에서** — 우리가 실제로 내린 결정과 이유, 코드 위치
- 🎤 **면접 한마디** — FDE 면접에서 이 기술을 물어보면 한 문장으로 답할 버전

용어에 익숙하지 않으면 [Part 6. 용어 사전](#part-6-용어-사전)을 먼저 훑어도 좋다.

---

## Part 1. 이 프로젝트가 하는 일 (큰 그림)

한 문장으로: **공공데이터(기상특보·지진·홍수 등)를 계속 수집해서, 사용자가 등록한 "인물"의 특성(나이·건강상태 등)에 맞춰 위험한 상황만 골라 알림을 보내는 백엔드.**

예를 들어 "충북 청주 흥덕구에 사는 고령의 어머니"를 등록해두면, 그 지역에 폭염특보가 뜰 때 시스템이 "고령 + 폭염 = 높은 위험"이라고 판단해서 알림을 만든다. 반면 같은 폭염이라도 건강한 성인에겐 위험도를 낮게 매긴다.

### 데이터가 흐르는 순서 (이게 시스템의 핵심)

```
① 수집(Ingestion)        공공 API에서 재난 데이터를 가져온다
        ↓
② 정규화 → events 저장   소스마다 제각각인 데이터를 공통 형식으로 바꿔 DB에 쌓는다
        ↓
③ 구독 매칭              그 지역을 구독한 사용자/인물을 찾는다
        ↓
④ 위험도 평가(Layer 1)   인물 특성 + 이벤트 종류로 LOW/MEDIUM/HIGH를 매긴다
        ↓
⑤ notifications 생성     위험하다고 판단되면 알림 레코드를 만든다
                        (실제 발송은 Phase 2)
```

이 흐름이 코드에서는 `app/services/ingest.py`의 `run_ingestion_cycle()` 함수 하나에 그대로 담겨 있다. 함수를 읽으면 위 5단계가 순서대로 보인다.

### 왜 이렇게 단계를 나눴나 (레이어드 아키텍처)

각 단계를 별도 파일/폴더로 분리했다. "수집"은 `app/ingestion/`, "위험도 판단"은 `app/risk/`, "DB 모델"은 `app/models/`, "외부에 노출하는 API"는 `app/api/` 하는 식이다.

이렇게 나누는 이유는, 나중에 한 부분을 바꿔도 다른 부분이 안 흔들리게 하기 위해서다. 예를 들어 홍수 데이터 API의 응답 형식이 바뀌어도, 고쳐야 할 곳은 `app/ingestion/hrfco_flood.py` 하나뿐이다. 위험도 판단 로직이나 DB는 건드릴 필요가 없다. 이게 "관심사의 분리(separation of concerns)"라는 개념이고, 규모가 커질수록 유지보수를 살린다.

---

## Part 2. 기술 스택 한눈에 보기

| 기술 | 한 줄 정의 | 왜 이걸 골랐나 | 대안 |
|---|---|---|---|
| **Python** | 프로그래밍 언어 | 데이터/AI 생태계가 강하고 FDE 직무에서 자주 쓰임 | Node.js, Go, Java |
| **FastAPI** | 파이썬 웹 API 프레임워크 | 코드가 간결하고, 자동 문서(/docs)와 타입 검증이 기본 제공 | Flask, Django |
| **PostgreSQL** | 관계형 데이터베이스 | JSONB·배열 등 고급 기능이 강하고 업계 표준급 | MySQL, SQLite |
| **SQLAlchemy** | 파이썬 ORM (DB를 객체로 다루게 해줌) | 파이썬 진영 사실상 표준, 세밀한 제어 가능 | Django ORM, Tortoise |
| **Alembic** | DB 스키마 변경 관리(마이그레이션) 도구 | SQLAlchemy와 짝꿍, 스키마 변경 이력 관리 | Django migrations |
| **Pydantic** | 데이터 검증·직렬화 라이브러리 | FastAPI와 통합, 입력값 자동 검증 | dataclasses, marshmallow |
| **pytest** | 테스트 프레임워크 | 파이썬 표준급, 문법이 간결 | unittest |
| **Docker / Compose** | 앱·DB를 컨테이너로 묶어 실행 | "내 컴퓨터에선 되는데" 문제를 없앰 | 로컬 직접 설치 |
| **httpx** | HTTP 클라이언트 (외부 API 호출용) | 동기/비동기 모두 지원, requests 후속격 | requests, aiohttp |

> 💡 이 표만 외워도 "무슨 스택 썼어요?"에 답할 수 있다. 하지만 FDE 면접에서 중요한 건 **왜/대안 대비 트레이드오프**라서, Part 3에서 하나씩 풀어 쓴다.

---

## Part 3. 개념 + 결정 (주제별 학습 가이드)

### 3-1. 웹 백엔드와 REST API, 그리고 FastAPI

💡 **개념.**
"백엔드"는 사용자 눈에 안 보이는 서버 쪽 프로그램이다. 웹/앱 화면(프론트엔드)이 "이 사용자의 인물 목록 줘"라고 요청하면, 백엔드가 DB에서 꺼내 응답한다. 이 요청/응답을 주고받는 규칙을 정해둔 게 **API**이고, 그중 가장 흔한 방식이 **REST**다. REST는 "주소(URL) + 동사(GET/POST 등)"로 자원을 다룬다. 예: `GET /persons`는 "인물 목록 조회", `POST /persons`는 "인물 새로 생성".

- `GET` = 조회 (읽기)
- `POST` = 생성 (쓰기)
- `PUT`/`PATCH` = 수정, `DELETE` = 삭제

🔧 **이 프로젝트에서.**
FastAPI로 API를 만들었다. 엔드포인트(주소별 처리 함수)는 `app/api/routes/` 폴더에 자원별로 나눠 있다 — `persons.py`, `regions.py`, `subscriptions.py`, `events.py`, `notifications.py`, `health.py`. 예를 들어 `app/api/routes/persons.py`를 보면:

```python
@router.post("", response_model=PersonRead)
def create_person(payload: PersonCreateRequest, db: Session = Depends(get_db)):
    ...
```

- `@router.post("")` → 이 함수는 `POST /persons` 요청을 처리한다는 표시(데코레이터)
- `payload: PersonCreateRequest` → 요청 본문(JSON)을 자동으로 검증해서 파이썬 객체로 준다
- `response_model=PersonRead` → 응답 형태를 정해두면 문서에도 자동 반영되고, 불필요한 필드가 새어나가는 걸 막는다
- `db: Session = Depends(get_db)` → "의존성 주입". 요청이 올 때마다 FastAPI가 DB 세션을 알아서 만들어 넣어준다 (3-6에서 설명)

FastAPI를 고른 결정적 이유는 **자동 문서화**다. 서버를 켜고 `http://localhost:8000/docs`에 들어가면, 내가 만든 모든 API가 눌러볼 수 있는 문서로 나온다. 이건 프론트 개발자나 협업자에게 API를 설명할 때 시간을 크게 줄여준다 — FDE처럼 고객사와 붙어 일하는 직무에서 특히 유용하다.

🎤 **면접 한마디.**
"FastAPI를 쓴 이유는 타입 힌트 기반으로 요청/응답 검증과 OpenAPI 문서가 자동 생성돼, 최소한의 코드로 안전한 API를 빠르게 만들 수 있기 때문입니다."

---

### 3-2. 관계형 데이터베이스와 PostgreSQL

💡 **개념.**
데이터베이스(DB)는 데이터를 저장·조회하는 전용 프로그램이다. "관계형(relational)" DB는 데이터를 **표(table)** 로 저장한다. 엑셀 시트를 떠올리면 된다 — 행(row)은 데이터 하나, 열(column)은 속성.

핵심 개념 3가지:
- **기본키(Primary Key, PK)** — 각 행을 유일하게 구분하는 값. 예: 인물마다 붙는 고유 id.
- **외래키(Foreign Key, FK)** — 다른 표의 행을 가리키는 값. 예: `persons` 표의 각 인물은 `user_id`로 `users` 표의 소유자를 가리킨다. 이걸로 표끼리 "관계"를 맺는다.
- **정규화** — 같은 데이터를 여러 곳에 중복 저장하지 않고 표를 나눠 FK로 잇는 것.

🔧 **이 프로젝트에서.**
PostgreSQL을 골랐다. 표는 총 12개다: `users`, `persons`, `person_tags`, `regions`, `subscriptions`, `device_tokens`, `risk_matrix_rules`, `ai_risk_logs`, `events`, `notifications`, `river_gauges`, `gauge_region_maps`. (`app/models/__init__.py`에 전부 나열돼 있다.)

관계 예시:
- 한 명의 `user`가 여러 `person`을 등록 (1:N)
- 한 `person`은 여러 `person_tag`를 가짐 (예: "고령" + "보행보조필요")
- `subscription`은 어떤 `person`이 어떤 `region`의 알림을 받을지 잇는 연결 표

PostgreSQL을 고른 이유는 **JSONB**와 **배열** 같은 고급 컬럼 타입 때문이다(3-7에서 자세히). 재난 API의 원본 응답을 통째로 보존해야 하는데, 그 형식이 소스마다 다르고 나중에 바뀔 수도 있어서, 정형 컬럼만으로는 부족했다.

🎤 **면접 한마디.**
"원본 API 페이로드처럼 스키마가 유동적인 데이터를 다뤄야 해서, JSONB를 네이티브로 지원하는 PostgreSQL을 골랐습니다. 정형 데이터는 컬럼으로, 비정형 원본은 JSONB로 저장하는 하이브리드 전략을 썼습니다."

---

### 3-3. ORM과 SQLAlchemy — DB를 파이썬 객체로 다루기

💡 **개념.**
원래 DB와 대화하려면 **SQL**이라는 별도 언어를 써야 한다 (`SELECT * FROM persons WHERE user_id = ...`). **ORM(Object-Relational Mapping)** 은 이 SQL을 대신 써주는 통역사다. 파이썬 클래스로 표를 정의하고, 파이썬 객체를 다루듯 코드를 쓰면 ORM이 SQL로 번역해준다.

🔧 **이 프로젝트에서.**
SQLAlchemy로 각 표를 파이썬 클래스로 정의했다. `app/models/event.py`의 `Event` 클래스가 `events` 표에 대응한다:

```python
class Event(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JsonVariant, nullable=False)
    ...
    region: Mapped["Region"] = relationship(back_populates="events")
```

읽는 법:
- `class Event(Base)` → `Base`를 상속하면 SQLAlchemy가 "이건 DB 표"라고 인식
- `mapped_column(...)` → 컬럼 하나. `primary_key=True`면 PK, `ForeignKey("regions.id")`면 FK, `nullable=False`면 필수값
- `default=uuid.uuid4` → 새 행 만들 때 id를 자동 생성
- `relationship(...)` → FK로 이어진 다른 표를 파이썬 속성처럼 접근하게 해줌. `event.region`이라고 쓰면 SQLAlchemy가 알아서 조인해서 지역 객체를 준다

ORM을 쓰면 SQL을 직접 안 짜도 되고, 오타로 인한 실수가 줄고, 파이썬 타입 검사의 도움을 받는다. 대신 복잡한 쿼리는 SQL보다 표현이 어렵거나 성능 튜닝이 필요할 때가 있다 — 이게 ORM의 트레이드오프다.

🎤 **면접 한마디.**
"SQLAlchemy로 표를 파이썬 클래스로 모델링해서, 타입 안정성과 생산성을 얻었습니다. 단순 CRUD는 ORM으로, 복잡한 집계 쿼리는 필요하면 raw SQL로 내려가는 식으로 갈 계획입니다."

---

### 3-4. 모델 vs 스키마 — 왜 두 벌로 나눴나 (Pydantic)

💡 **개념.**
헷갈리기 쉬운 부분. 이 프로젝트엔 데이터 모양을 정의하는 파일이 두 종류다.
- **모델(model)** — `app/models/`. DB 표의 구조. "데이터가 **저장**되는 형태."
- **스키마(schema)** — `app/schemas/`. API로 주고받는 형태. "데이터가 **오가는** 형태."

🔧 **이 프로젝트에서.**
왜 굳이 나눌까? DB에 저장하는 것과 사용자에게 보여주는 것이 항상 같지 않기 때문이다. 예를 들어 비밀번호 해시는 DB엔 있지만 API 응답엔 절대 나가면 안 된다. 반대로 API 입력엔 있지만 DB엔 가공해서 저장하는 값도 있다.

`app/schemas/person.py`를 보면 입력용/출력용이 나뉘어 있다:

```python
class PersonCreate(BaseModel):     # 입력: 사용자가 보내는 것
    label: str
    age_group: str
    tags: list[str] = []

class PersonRead(BaseModel):       # 출력: 사용자에게 돌려주는 것
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    label: str
    age_group: str
    created_at: datetime
    tags: list[str] = []
```

이 스키마들은 **Pydantic**으로 만든다. Pydantic은 들어온 데이터가 형식에 맞는지 자동 검증한다 — 예를 들어 `age_group`에 숫자가 오면 자동으로 에러를 낸다. `from_attributes=True`는 "SQLAlchemy 모델 객체를 이 스키마로 자동 변환해도 된다"는 설정이다.

이렇게 나누면 **DB 구조와 API 계약을 독립적으로 바꿀 수 있다.** DB에 컬럼을 추가해도 API 응답은 그대로 유지할 수 있고, 그 반대도 된다.

🎤 **면접 한마디.**
"DB 모델(SQLAlchemy)과 API 스키마(Pydantic)를 분리해서, 저장 구조와 외부 계약을 독립적으로 진화시킬 수 있게 했습니다. 민감 필드 노출도 스키마 레벨에서 통제됩니다."

---

### 3-5. 마이그레이션과 Alembic — DB 구조를 버전 관리하기

💡 **개념.**
코드는 Git으로 버전 관리한다. 그런데 DB의 **구조(표·컬럼)** 도 시간이 지나면 바뀐다 — 컬럼 추가, 표 신설 등. 이 변경 이력을 코드처럼 관리하는 게 **마이그레이션**이다. 각 변경을 파일로 남겨두면, 어느 컴퓨터에서든 "이 순서대로 실행"만 하면 똑같은 DB 구조를 재현할 수 있다.

🔧 **이 프로젝트에서.**
Alembic으로 관리한다. 첫 마이그레이션은 `migrations/versions/0001_initial_schema.py`다. 명령어 흐름:
- `alembic upgrade head` → 최신 구조까지 DB에 반영
- `alembic revision --autogenerate -m "설명"` → 모델을 바꾼 뒤 변경분을 자동으로 마이그레이션 파일로 뽑기

📝 한 가지 특이점(솔직한 기록): 이 스캐폴딩을 처음 만든 환경에선 로컬에 Postgres를 못 띄웠다. 그래서 `alembic revision --autogenerate`를 실제 DB에 못 돌려봤고, 대신 첫 마이그레이션을 `Base.metadata.create_all()`을 직접 호출하는 방식으로 작성했다. 나중에 실제 Postgres를 띄운 뒤부터는 정석대로 `--autogenerate`로 새 리비전을 만들면 된다. (이 배경은 README "왜 초기 마이그레이션이 create_all 방식인가" 절에도 적혀 있다.)

🎤 **면접 한마디.**
"Alembic으로 스키마 변경을 버전 관리해서, 환경 간 DB 구조를 재현 가능하게 만들었습니다. 스키마 변경이 코드 리뷰와 롤백의 대상이 되는 게 핵심 이점입니다."

---

### 3-6. 세션·트랜잭션·commit — DB에 안전하게 쓰기

💡 **개념.**
DB에 여러 변경을 할 때, "전부 성공 아니면 전부 취소"를 보장해야 할 때가 있다. 예: 인물을 만들고 태그 3개를 다는데, 중간에 실패하면 반쪽짜리 인물이 남으면 안 된다. 이 "전부 아니면 전무" 묶음이 **트랜잭션(transaction)** 이다.
- **세션(session)** — DB와의 대화 창구. 변경사항을 임시로 모아둔다.
- **commit** — 모아둔 변경을 실제로 DB에 확정.
- **flush** — DB에 보내되 아직 확정(commit) 전. 방금 만든 행의 id 같은 걸 미리 얻을 때 쓴다.
- **rollback** — 확정 전 변경을 전부 취소.

🔧 **이 프로젝트에서.**
`app/database.py`에서 세션 공장을 만들고, `get_db()`가 요청마다 세션을 열고 끝나면 닫는다:

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

`flush`와 `commit`의 차이가 실제로 쓰인 예가 `app/crud.py`의 `create_person`이다:

```python
def create_person(db, user, label, age_group, tags):
    person = Person(user_id=user.id, label=label, age_group=age_group)
    db.add(person)
    db.flush()          # ← 아직 확정 전이지만 person.id를 얻으려고 flush
    for tag in tags:
        db.add(PersonTag(person_id=person.id, tag=tag))   # 그 id로 태그 연결
    db.commit()         # ← 인물 + 태그를 한 번에 확정
    db.refresh(person)
    return person
```

여기서 `flush()`로 person.id를 먼저 확보하고, 그 id로 태그들을 붙인 다음, 마지막에 `commit()` 한 번으로 인물과 태그를 함께 확정한다. 중간에 실패하면 인물도 태그도 저장되지 않는다.

🎤 **면접 한마디.**
"연관 데이터를 하나의 트랜잭션으로 묶어 정합성을 보장했습니다. flush로 부모 행의 PK를 얻고, 자식 행을 붙인 뒤 commit으로 원자적으로 확정하는 패턴을 썼습니다."

---

### 3-7. ⭐ 다이얼렉트 호환 타입 — 이 프로젝트의 핵심 트릭

이건 이번 세션에서 실제로 리팩터링한 부분이라 특히 자세히 남긴다. FDE 면접에서 "실전 문제를 어떻게 풀었나" 사례로 쓰기 좋다.

💡 **개념.**
DB마다 지원하는 데이터 타입이 조금씩 다르다. 이 방언 차이를 SQLAlchemy에선 **다이얼렉트(dialect)** 라고 부른다. PostgreSQL엔 있는 특수 타입이 SQLite엔 없다:
- **UUID** — 전 세계에서 겹치지 않는 긴 고유 id (예: `550e8400-e29b-...`). Postgres는 네이티브 지원, SQLite는 없음.
- **JSONB** — JSON을 효율적으로 저장/검색하는 Postgres 전용 타입.
- **ARRAY** — 한 컬럼에 값 여러 개(배열)를 넣는 Postgres 기능.

🔧 **문제 상황.**
운영 DB는 PostgreSQL을 쓰기로 했다. 그런데 **테스트를 돌릴 때마다 Postgres 서버를 띄우는 건 무겁고 느리다.** 테스트는 가볍고 빠른 SQLite(파일/메모리 기반 DB)로 돌리고 싶었다. 문제는, 모델에 Postgres 전용 타입(JSONB, ARRAY)을 그대로 박아두면 SQLite에선 그 타입을 몰라서 테스트가 아예 안 돌아간다.

🔧 **해결.**
"Postgres에선 네이티브 타입, 그 외 DB에선 표준 타입"으로 자동 전환되는 컬럼 타입을 만들었다. `app/models/types.py`:

```python
from sqlalchemy import JSON, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# JSONB on Postgres, JSON elsewhere
JsonVariant = JSON().with_variant(JSONB, "postgresql")

# text[] on Postgres, JSON list elsewhere
StringArrayVariant = JSON().with_variant(ARRAY(String), "postgresql")
```

핵심은 `.with_variant(...)`다. "기본은 표준 JSON을 쓰되, 다이얼렉트가 'postgresql'이면 JSONB로 바꿔라"는 뜻이다. UUID는 SQLAlchemy 2.0의 `Uuid` 타입이 이미 이 전환을 알아서 해준다(Postgres UUID ↔ 그 외 CHAR(32)).

이렇게 하니 **모델 정의는 한 벌인데, 운영에선 Postgres의 성능을, 테스트에선 SQLite의 가벼움을** 둘 다 얻었다. `app/models/event.py`에서 이 타입들을 이렇게 쓴다:

```python
raw_payload: Mapped[dict] = mapped_column(JsonVariant, nullable=False)
news_refs: Mapped[list[str] | None] = mapped_column(StringArrayVariant, nullable=True)
```

이 리팩터 덕분에 DB 서버 없이도 "실제 DB에 저장했다가 다시 읽는" 통합 테스트(3-10)가 가능해졌다.

🎤 **면접 한마디.**
"운영은 PostgreSQL, 테스트는 SQLite로 돌리기 위해 SQLAlchemy의 with_variant로 다이얼렉트별 컬럼 타입을 분기했습니다. 모델 정의는 단일 소스로 유지하면서, 운영 성능과 테스트 속도를 동시에 얻은 결정입니다."

---

### 3-8. 설정과 시크릿 관리 — .env와 pydantic-settings

💡 **개념.**
API 키·DB 비밀번호 같은 **비밀값(시크릿)** 은 코드에 직접 적으면 안 된다. Git에 올라가면 유출되니까. 대신 `.env` 파일에 따로 두고, 프로그램이 실행될 때 읽어온다. `.env`는 `.gitignore`로 Git에서 제외한다.

🔧 **이 프로젝트에서.**
`app/config.py`에서 pydantic-settings로 `.env`를 읽는다:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg2://hazard:hazard@localhost:5432/hazard_fighter"
    kma_warning_api_key: str | None = None
    ...

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- `env_file=".env"` → `.env`에서 값을 읽음
- 키가 없으면 `None`이 기본값 → 키 없이도 프로그램이 죽지 않고 mock 모드로 동작(3-9)
- `@lru_cache` → 설정을 한 번만 읽고 재사용(매번 파일 읽기 방지)

**시크릿 관리 규칙(이번 세션에서 정립):**
- `.env` = 실제 키. `.gitignore`됨 → 커밋 안 됨
- `.env.example` = 빈 템플릿. 커밋됨 → "이런 변수가 필요하다"는 안내용
- `secrets/` = Firebase 서비스 계정 JSON 등. `.gitignore`됨

📝 이번 세션에 실제로 사고가 있었다: 처음에 `.env.example`(=커밋되는 파일)에 실제 키를 적어버렸다. 이걸 발견하고 (1) 실제 값은 `.env`로 옮기고 (2) `.env.example`은 빈 템플릿으로 되돌리고 (3) `secrets/`를 `.gitignore`에 추가하고 (4) 이미 커밋에 박힌 키는 `git filter-repo`로 히스토리에서 스크럽했다. 자세한 건 3-13.

🎤 **면접 한마디.**
"시크릿은 .env로 분리하고 pydantic-settings로 타입 검증과 함께 로드합니다. 커밋되는 .env.example은 값 없는 템플릿으로만 유지해, 실수로 키가 유출되지 않게 했습니다."

---

### 3-9. 외부 API 연동과 mock fallback 패턴

💡 **개념.**
외부 API(여기선 공공데이터 포털)에 의존하는 코드는, 그 API 없이는 개발/테스트가 막히기 쉽다. 키 발급이 며칠 걸리거나, 호출 한도가 있거나, 응답이 느릴 수 있다. 이럴 때 쓰는 게 **mock(가짜 데이터)** 이다 — 실제 API 대신 미리 만들어둔 응답을 돌려준다.

🔧 **이 프로젝트에서.**
`app/ingestion/base.py`에 **추상 클래스**로 공통 규칙을 정했다:

```python
class BaseIngestionClient(ABC):
    def fetch(self) -> list[NormalizedEvent]:
        if not self.api_key:
            return self._fetch_mock()   # 키 없으면 가짜 데이터
        return self._fetch_live()       # 키 있으면 진짜 호출

    @abstractmethod
    def _fetch_mock(self): ...
    @abstractmethod
    def _fetch_live(self): ...
```

- **추상 클래스(ABC)** = "이걸 상속하는 애들은 반드시 `_fetch_mock`과 `_fetch_live`를 구현해야 한다"는 계약. 각 소스(`kma_warnings.py`, `kma_earthquake.py`, `hrfco_flood.py`)가 이걸 상속해 자기 방식으로 구현한다.
- `fetch()`의 스위치 하나로, **키가 있으면 실제, 없으면 mock** 으로 자동 전환. 그래서 키 발급을 기다리는 동안에도 DB·위험도·API를 전부 개발·테스트할 수 있었다.

또 하나 중요한 설계: 소스마다 응답 형식이 다르니, 전부 `NormalizedEvent`라는 **공통 형식**으로 변환한 뒤에 저장한다. 이렇게 하면 뒷단(위험도 판단 등)은 "어느 소스에서 왔는지" 신경 안 써도 된다. 이게 3-1에서 말한 관심사의 분리다.

🎤 **면접 한마디.**
"외부 API 클라이언트를 추상 클래스로 통일하고, 키 유무에 따라 live/mock을 자동 전환하게 했습니다. 덕분에 키 발급 지연과 무관하게 파이프라인 전체를 개발·테스트할 수 있었고, 모든 소스를 공통 스키마로 정규화해 하위 로직을 소스에 독립적으로 유지했습니다."

---

### 3-10. 위험도 판단 로직 — 규칙 매트릭스(Layer 1)와 LLM(Layer 2)

💡 **개념.**
"이 상황이 이 사람에게 얼마나 위험한가"를 판단하는 방법은 크게 둘이다.
- **결정론적 규칙(rule-based)** — "폭염 + 고령 = HIGH"처럼 미리 정한 표(매트릭스)대로 판단. 빠르고, 결과가 항상 같고(예측 가능), 테스트하기 쉽다. 대신 표에 없는 경우는 못 잡는다.
- **LLM 기반** — AI에게 상황을 설명하고 판단을 맡김. 유연하지만 느리고, 비용이 들고, 결과가 매번 달라질 수 있다.

🔧 **이 프로젝트에서.**
두 개를 계층으로 나눴다(spec 4절). **Layer 1은 규칙 매트릭스**로 먼저 판단하고, 규칙에 안 걸리는 애매한 경우만 **Layer 2 LLM**으로 넘긴다(Layer 2는 Phase 2 예정).

Layer 1은 `app/risk/matrix.py`에 있다. 규칙을 파이썬 리스트로 하드코딩했다:

```python
RISK_MATRIX = [
    {"event_type": EventType.HEATWAVE, "severity": None, "trigger_type": "age_group",
     "trigger_value": AgeGroup.SENIOR, "risk_level": RiskLevel.HIGH},
    # 폭염 + 고령 = HIGH
    ...
]
```

판단 함수 `evaluate_risk()`는 이벤트 종류·인물 나이대·태그·특보 등급을 받아서, 매칭되는 규칙 중 **가장 높은 위험도**를 돌려준다. 매칭이 하나도 없으면 `None`을 돌려주는데, 이 `None`이 바로 "Layer 2로 넘겨야 할 케이스"라는 신호다. 지진은 등급 문자열이 아니라 규모(숫자)가 기준이라 `evaluate_earthquake_risk()`로 따로 처리한다(4.0 이상 HIGH 등).

📝 설계 노트: 같은 규칙을 `risk_matrix` **테이블**에도 미러링해두는 코드(`scripts/seed_risk_matrix.py`)가 있지만, 지금 `evaluate_risk()`는 그 테이블을 읽지 않고 코드의 리스트를 쓴다. 테이블 버전은 나중에 "관리자 화면에서 규칙 조정" 같은 확장과 감사(audit)를 위한 사전 포석이다. MVP에선 코드 하드코딩이 정확성·테스트에 유리해서 그렇게 갔다.

🎤 **면접 한마디.**
"위험도 판단을 2계층으로 설계했습니다. 명확한 케이스는 결정론적 규칙 매트릭스로 빠르고 재현 가능하게 처리하고, 규칙이 못 잡는 애매한 케이스만 LLM으로 폴백합니다. 비용·지연·예측가능성의 균형을 맞춘 결정입니다."

---

### 3-11. 테스트 — pytest와 SQLite 인메모리 E2E

💡 **개념.**
테스트는 "코드가 의도대로 도는지"를 자동으로 확인하는 코드다. 한 번 짜두면, 나중에 코드를 고쳤을 때 뭔가 깨졌는지 즉시 알 수 있다. 종류:
- **단위 테스트** — 함수 하나를 콕 집어 검증 (예: `evaluate_risk`가 폭염+고령에 HIGH를 내는지)
- **통합/E2E 테스트** — 여러 부분을 이어서 "전체 흐름"을 검증 (예: 이벤트가 들어와 알림이 생기기까지)

🔧 **이 프로젝트에서.**
pytest로 짰고, 테스트는 `tests/` 폴더에 있다:
- `test_risk_matrix.py` — Layer 1 규칙 로직 (단위)
- `test_ingestion.py` — 키 없을 때 mock으로 잘 빠지는지
- `test_pipeline_e2e.py` — **전체 흐름**: 사용자/인물/지역/구독 생성 → ingest → events 저장 → 위험도 평가 → notifications 생성까지
- `test_health.py` — 헬스체크 엔드포인트

핵심은 **이 테스트가 DB 서버 없이 전부 돈다**는 점이다. 3-7의 다이얼렉트 호환 타입 덕분에, 테스트는 메모리 위의 SQLite로 실제 DB 왕복(저장→조회)까지 검증한다. 예: "충북 청주 흥덕구 + 고령 구독자"에 홍수경보 mock을 넣으면 HIGH 알림이 실제로 DB에 생기는지까지 확인한다. 총 19개 테스트가 통과 상태다.

🎤 **면접 한마디.**
"파이프라인 전체를 SQLite 인메모리로 E2E 검증했습니다. 다이얼렉트 호환 타입 덕에 DB 서버 없이도 실제 저장·조회를 포함한 통합 테스트가 가능해, CI에서 빠르게 돌릴 수 있는 구조입니다."

---

### 3-12. 컨테이너와 Docker — "내 컴퓨터에선 되는데" 없애기

💡 **개념.**
프로그램을 돌리려면 특정 버전의 파이썬, DB, 라이브러리가 필요하다. 사람마다 컴퓨터 환경이 달라서 "내 컴퓨터에선 되는데 네 컴퓨터에선 안 돼" 문제가 생긴다. **Docker**는 앱과 그 실행 환경을 통째로 **컨테이너**라는 상자에 담아, 어디서든 똑같이 돌게 한다. **docker-compose**는 여러 컨테이너(예: 앱 + DB)를 한 번에 정의·실행하는 도구다.

🔧 **이 프로젝트에서.**
`docker-compose.yml`에 두 컨테이너를 정의했다:
- `db` — PostgreSQL 16. 데이터를 `volume`에 저장해 컨테이너를 지워도 데이터가 남게 했고, `healthcheck`로 DB가 진짜 준비됐는지 확인한다.
- `app` — FastAPI 앱. `depends_on`으로 **DB가 건강해진 뒤에** 뜨도록 순서를 잡았다.

`docker compose up -d db` 하나면 팀 누구나 동일한 Postgres를 띄울 수 있다. FDE처럼 여러 환경(내 노트북, 고객사 서버 등)에 배포해야 하는 직무에서 컨테이너는 사실상 필수 소양이다.

🎤 **면접 한마디.**
"앱과 Postgres를 docker-compose로 묶고, healthcheck와 depends_on으로 기동 순서를 보장했습니다. 환경 재현성을 확보해, 온보딩과 배포의 마찰을 줄이는 게 목적이었습니다."

---

### 3-13. Git 시크릿 위생 — 히스토리 스크럽

💡 **개념.**
Git은 파일의 **모든 변경 이력**을 저장한다. 그래서 실수로 비밀 키를 커밋했다가 나중에 지워도, **과거 커밋 히스토리엔 그대로 남는다.** 최신 파일에서 지운다고 끝이 아니다. 히스토리에서 완전히 없애려면 이력을 다시 쓰는(rewrite) 특수 작업이 필요하다.

🔧 **이 프로젝트에서.**
초기에 `.env.example`에 실제 키(기상청·홍수통제소)가 잠깐 커밋된 적이 있었다. 다행히 원격 저장소에 올리기 전이라 유출은 아니었지만, 안전하게 가려고 히스토리에서 지웠다.

`git filter-repo`라는 도구로, 히스토리 전체를 훑어 특정 문자열을 치환했다. 치환 규칙 파일(`.secret-replacements.txt`)에 "실제 키 → `__REMOVED__`"를 적고:

```bash
git filter-repo --replace-text .secret-replacements.txt --force
```

실행 후, 모든 커밋에서 실제 키가 사라지고 `__REMOVED_KMA_KEY__` 같은 마커만 남은 걸 확인했다. 관련 커밋 해시도 새로 만들어졌다(히스토리를 다시 썼으니 당연). 로컬 전용이었어서 키 재발급은 불필요했다.

📝 교훈: 키는 처음부터 `.env`(gitignore됨)에만 넣는다. `.env.example`엔 절대 실제 값 금지. 커밋 전 `git status`로 `.env`/`secrets/`가 안 딸려가는지 확인.

🎤 **면접 한마디.**
"커밋 히스토리에 남은 시크릿을 git filter-repo로 스크럽하고, .env/.env.example/secrets 구조를 정비했습니다. 지운 게 아니라 이력에서 제거해야 한다는 점을 실제로 처리한 경험입니다."

---

## Part 4. 개발 일지 (시간순)

> 블로그 초안으로 쓰기 좋게, "무엇을 왜 했는지" 중심으로 남긴다. 날짜/세션 단위로 계속 추가.

### 2026-07 — Phase 1: 백엔드 뼈대 구축

**기획 문서화.** 먼저 `docs/project-spec.md`에 전체 기획(데이터 소스, 인물 태그 체계, 위험도 판단 로직, 아키텍처, 로드맵)을 정리했다. 코드보다 기획을 먼저 못박은 이유는, MVP 범위를 좁게 유지하고 나중에 "왜 이렇게 했지"를 되짚을 근거를 남기기 위해서다.

**FastAPI + PostgreSQL 스캐폴딩.** 12개 테이블 모델, Layer 1 위험도 로직, 3개 소스 ingestion(mock 지원), 기본 REST API, Docker Compose, Alembic 뼈대를 만들었다. 이 시점의 제약: 로컬에 Postgres를 못 띄우는 환경이라, 마이그레이션은 `create_all` 방식으로 작성하고 DDL은 Postgres 다이얼렉트로 컴파일만 확인했다.

**DB 다이얼렉트 호환 리팩터.** 모델의 Postgres 전용 타입(UUID/JSONB/ARRAY)을 `with_variant`로 분기했다(3-7). 이 덕분에 DB 서버 없이 SQLite 인메모리로 **실제 DB 왕복 E2E 테스트**를 추가할 수 있었다. "충북 청주 흥덕구 + 고령 구독자 + 홍수경보 → HIGH 알림 생성"까지 검증. 테스트 19개 통과.

**API 키 발급.** 기상특보·지진(data.go.kr), 홍수통제소(hrfco.go.kr) 키를 발급받아 `.env`에 넣었다. 긴급재난문자는 Phase 5 항목이라 보류. LLM은 OpenAI 키를 준비(Anthropic 대체 가능). FCM은 레거시 서버 키가 2024.7 폐기돼서, 서비스 계정 JSON 방식으로 전환하기로 확인.

**시크릿 위생 정리.** `.env.example`에 실제 키가 들어가 있던 걸 발견 → `.env`로 이관, 템플릿 복원, `secrets/` gitignore 추가, `git filter-repo`로 히스토리 스크럽(3-8, 3-13).

**문서화.** README를 최신 상태로 갱신하고, 이 학습 노트를 작성하기 시작했다.

### 2026-07-17 — 로컬 실행 환경 구축 + 실제 API 연동 (FDE의 하루)

**로컬 환경 구축에서 배운 것들.** Docker Desktop 설치 → Postgres 컨테이너 기동 → `alembic upgrade head`로 실제 Postgres에 12개 테이블 생성 성공. 과정에서 겪은 실전 문제들:
- 맥 기본 python3가 3.9라 프로젝트 요구(3.10+ 문법)와 안 맞음 → Homebrew로 3.12 설치 후 venv 재생성. psycopg2-binary가 3.9에선 미리빌드 휠이 안 잡혀 pg_config 에러가 났던 것도 같은 뿌리.
- 명령어를 주석(`# ...`)까지 복붙했더니 zsh가 주석으로 안 치고 인자로 받아 `새로`, `맥용으로` 같은 이름의 venv가 생기는 사고. 교훈: 셸에 붙여넣는 명령은 주석 없이.
- 가상환경은 터미널 열 때마다 `source .venv/bin/activate` 필요.

**실제 API 대조 — 추정 코드는 전부 틀렸다.** `_fetch_live()`는 문서 없이 data.go.kr 공통 컨벤션으로 추정해 짠 코드였는데, 첫 실 호출에서 500. `debug_fetch.py`(응답을 파일로 덤프하는 1회성 도구)를 만들어 실 응답을 뜨고, 그걸 근거로 3개 클라이언트를 전부 고쳤다:
- **기상특보**: `items`가 리스트가 아니라 `{"item": [...]}`(data.go.kr 공통 함정). 특보 종류·등급·조치가 별도 필드가 아니라 `title` 문자열("... / 폭염주의보 발표 (*)")에 박혀 있어 정규식 파싱. `stnId`는 시군구가 아니라 발표 관서 코드 → 지역 매칭은 통보문 상세(getWthrWrnMsg, `t6` 필드에 지역 텍스트 확인됨) 연동이 필요 (TODO).
- **지진**: 필수 파라미터 `fromTmFc`/`toTmFc` 누락으로 resultCode=11. 넣었더니 이번엔 "최대 조회 기간 3일" 제한(resultCode=99). 에러 메시지가 다음 스펙을 알려주는 셈 — 실 호출 없이는 알 수 없는 제약들. 발생시각은 `tmEqk`(yyyyMMddHHmmss).
- **홍수통제소**: 코드의 URL이 웹페이지 placeholder였음. 실제 API는 `api.hrfco.go.kr/{키}/waterlevel/info.json`(관측소 1,417개 + 주의/경보 수위 임계치)과 `/waterlevel/list/10M/{코드}/{시작}/{종료}.json`(10분 단위 수위). 전국 4대강 통합 제공 확인 → spec Open Question #6 해결. 홍수 이벤트는 "최신 수위 ≥ 임계치" 자체 판정으로 구현.

**설계 개선 두 가지.**
- ingest를 소스별 try/except로 격리 — 한 소스가 죽어도 나머지는 처리하고, 응답 `errors`에 소스별 에러를 노출. (한 데이터 소스 장애가 전체 파이프라인을 죽이면 안 된다는 기본기.)
- 테스트 격리 버그 발견·수정: `.env`에 실제 키가 생기자 테스트가 실 API를 호출하려다 실패. `tests/conftest.py`에서 키 환경변수를 비워 테스트는 항상 mock을 쓰게 고정. "테스트가 환경에 따라 다르게 도는" 전형적 함정.

**결과.** `POST /events/ingest` → `{"events_ingested": 8, "notifications_created": 0, "errors": {}}`. 실제 공공 API 3개 → 정규화 → Postgres 저장까지 전체 파이프라인이 처음으로 끝까지 돌았다. 알림 0은 특보 이벤트에 region이 아직 없어서(통보문 상세 연동 전)이며 예상된 동작.

### 2026-07-19 — 특보→지역 매칭, 실데이터 알림 생성 성공 🎉

**통보문 상세(getWthrWrnMsg) 연동.** 특보 클라이언트를 발표 이력 목록(getWthrWrnList)에서 통보문 상세 기반으로 전환. 핵심 발견: 최신 통보문의 `t6` 필드가 "이 시점 발효 중인 특보 전체 + 지역" 스냅샷이라, 이거 하나만 파싱하면 현재 상황을 다 얻는다.

**텍스트 파싱의 현실.** 지역이 구조화된 필드가 아니라 자연어에 가까운 텍스트로 온다: `충청남도(보령(도서제외), 보령도서)`, `제주도(제주도산지, 추자도 제외)`, `인천`(하위구역 없음). 괄호 깊이를 추적하는 스플리터(`_split_top_level`)를 직접 짜서 해결 — 중첩 괄호 한정어 제거('보령(도서제외)'→'보령'), '제외' 항목 스킵, 시도 단위는 sigungu='전체'. 실제 응답 케이스를 그대로 테스트로 박아뒀다(test_warning_msg_parser.py).

**이벤트 중복 방지(dedupe).** t6는 스냅샷이라 같은 특보가 매 사이클 반복 유입된다. (소스·종류·등급·지역·발표시각)이 같으면 기존 이벤트를 재사용하고 알림 평가를 건너뛰게 해서 중복 알림을 차단. 응답에 `duplicates_skipped`로 노출.

**끝까지 도는 순간.** 지역 생성 → 구독 생성 → ingest 순서로 실행하니:
`{"events_ingested": 63, "duplicates_skipped": 1, "notifications_created": 1}` →
`"[폭염특보] 전라남도 광양에 이상상황이 감지됐어요. 어머니님 관련 주의가 필요해요"` (HIGH, matrix).
**공공 API → 텍스트 파싱 → 지역 매칭 → 규칙 매트릭스 → 개인 맞춤 알림**까지, 프로젝트의 핵심 가설이 실데이터로 처음 검증됐다.

**과정에서 배운 것.** (1) 422 에러 = 요청 JSON 검증 실패 — placeholder를 실제 UUID로 안 바꾸면 난다. (2) "구독을 먼저, ingest를 나중에" — 알림 평가는 이벤트 생성 시점에만 돌기 때문. 이건 나중에 "구독 생성 시 기존 발효 특보 소급 평가" 기능으로 개선할 만하다(TODO). (3) 개발 중 데이터 리셋은 `docker compose exec db psql`로 직접 DELETE.

### 2026-07-19 — 구독 소급 평가 + 지역명 정규화

**소급 평가(backfill).** 위 (2)의 순서 문제를 바로 해결했다. 평가 로직을 `_notify_subscription_for_event()`(이벤트×구독 한 쌍 평가)로 추출해 ingest 경로와 공유하고, 구독 생성 시 최근 48시간 내 해당 지역 이벤트를 소급 평가하는 `backfill_subscription()`을 추가. 같은 (구독, 이벤트) 쌍 알림은 중복 생성하지 않는다. 검증: 순천 구독을 만들자 ingest 재실행 없이 즉시 폭염 HIGH 알림 생성 확인. **리팩터링 포인트: 같은 로직이 두 경로에서 필요해지면 복붙하지 말고 함수로 추출해 공유한다.**

**지역명 정규화.** 통보문은 '광양', 사용자는 '광양시'라고 쓸 수 있어 region 매칭이 깨질 수 있다. `normalize_sigungu()`로 단일 단어 시/군 접미사를 떼고 저장('광양시'→'광양'). 복합 표기('청주시 흥덕구')는 그대로. 근본 해결은 행정구역 코드 기반 매칭(TODO). **데이터 정합성 교훈: 같은 실체를 가리키는 표기가 여럿일 때는 "저장 시점 정규화"가 매칭 문제를 가장 싸게 막는다.**

### 2026-07-19 — Phase 2 시작: LLM 알림 문구 생성

**설계 원칙: fallback 필수.** 알림은 안전 기능이라 "LLM 장애 = 알림 불발"이면 안 된다. `app/services/message.py`: OpenAI(gpt-4o-mini)로 문구를 생성하되, 키 없음·호출 실패·빈 응답 어느 경우든 즉시 기존 템플릿으로 fallback. 이 구조 덕에 LLM 은 "있으면 좋은 것"이고 없어도 서비스는 완전하다.

**프롬프트 설계.** 시스템 프롬프트에 규칙을 명시: 2~3문장 120자 이내, 첫 문장에 상황+지역, 이어서 인물 특성(나이대·태그) 맞춤 행동 요령 1가지, 과장 금지, 이모지 금지. 이벤트·지역·위험도·인물 정보를 유저 프롬프트로 전달.

**테스트 전략.** 실제 OpenAI 를 호출하지 않고 `monkeypatch` 로 `httpx.post` 를 가짜로 바꿔 세 경로를 검증: 키 없음→템플릿, 정상 응답→LLM 문구 사용(+프롬프트에 인물 특성 포함 확인), 에러/빈 응답→fallback. **외부 API 의존 코드의 테스트는 "호출을 어떻게 속일까"가 핵심.**

**실전에서 겪은 것 두 가지.**
- 중복 구독 500: (person, region) 유니크 제약에 걸려 IntegrityError. `create_subscription` 을 get-or-create 로 바꿔 멱등(idempotent)하게 만들었다. **같은 요청을 두 번 보내도 같은 결과가 나오는 API 가 좋은 API.**
- `insufficient_quota`: OpenAI 는 선불 크레딧이 없으면 호출 거부 → fallback 이 실전에서 첫 작동. curl 로 원인 확인 → 크레딧 충전 → 재시도로 해결. fallback 이 있어서 이 장애 동안에도 알림은 정상 생성됐다.

**결과.** 템플릿: "[폭염특보] ... 주의가 필요해요 (severity=주의보)." →
LLM: "전라남도 순천에 폭염특보가 발효되었습니다. 어머니님은 외출 시 그늘을 찾고, 수분을 충분히 섭취해 주세요."
인물 특성 맞춤 행동 요령이 실데이터로 생성됨. Phase 2 첫 조각 완성.

### 2026-07-19 — LLM 프로바이더 폴백 체인 + 쿨다운

**동기.** 실제로 quota 소진(insufficient_quota)을 겪고 나니 "유료가 죽으면 무료 모델로 자동 전환"이 필요하다는 게 명확해졌다. 단순 if/else 가 아니라 실무 패턴으로 설계:

```
1순위: 유료 (OpenAI gpt-4o-mini)
  ↓ 실패 시
2순위: 무료 폴백 (.env 의 LLM_FALLBACK_* — Gemini 무료 티어 등)
  ↓ 실패 시
최종: 템플릿 문구 (알림은 반드시 나간다)
```

**핵심 설계 3가지.**
- **프로바이더 추상화**: OpenAI 호환 API(chat/completions)라는 공통 규격 덕에, 프로바이더를 (base_url, api_key, model) 세 값으로 일반화. Gemini·Groq·OpenRouter·로컬 Ollama 까지 .env 설정만으로 갈아끼울 수 있다. "고객사 보안 요건상 외부 API 금지 → 로컬 LLM 전환" 같은 FDE 시나리오에 그대로 대응.
- **쿨다운(서킷 브레이커 단순판)**: 401/402/429(키 문제·quota 소진)가 감지된 프로바이더는 15분간 시도 자체를 건너뛴다. 죽은 프로바이더에 매 알림마다 실패 호출을 반복하며 지연을 쌓지 않기 위함. 상태는 프로세스 메모리 — 다중 인스턴스 배포 시 Redis 등으로 옮겨야 한다는 한계도 기록.
- **에러 구분**: quota/인증 오류(지속적 → 쿨다운)와 네트워크 오류(일시적 → 쿨다운 없이 다음 프로바이더만)를 다르게 처리.

**테스트.** httpx.Response 객체를 직접 만들어 429 를 흉내내는 방식으로 4가지 시나리오 검증: 유료 429 → 무료가 문구 생성, 쿨다운 후 다음 알림에선 유료를 건너뜀(호출 횟수로 검증), 전부 실패 → 템플릿, 쿨다운 상태의 테스트 간 격리(autouse fixture).

**면접 한마디.** "LLM 의존 기능에 3단계 폴백 체인을 설계했습니다. 유료 quota 소진 시 무료 프로바이더로 자동 전환하고, 실패한 프로바이더는 쿨다운으로 격리하며, 최종적으로는 LLM 없이도 동작하는 템플릿을 둬서 안전 기능의 가용성을 보장했습니다."

**무료 폴백(Gemini) 실연동에서 배운 것.** aistudio.google.com 에서 무료 키 발급 → 처음 지정한 `gemini-2.0-flash` 는 429 에 `limit: 0` — "다 써서"가 아니라 **그 구세대 모델의 무료 티어 자체가 닫힌 것**. 429 응답을 읽는 법: `limit: 0` 이면 quota 소진이 아니라 할당 자체가 없다는 뜻이다. `GET /models` 로 사용 가능 모델을 조회해 `gemini-flash-lite-latest`("latest" 별칭이라 세대 교체에도 안 깨짐)로 바꿔 해결. 검증 순서도 교훈: 앱에 붙이기 전에 curl 로 (1) 모델 목록 (2) 최소 호출을 먼저 확인하면 디버깅이 빠르다.

### 2026-07-20 — 긴급재난문자 키 발급 + API 호출량 예산 분석

**긴급재난문자(safetydata.go.kr) 실응답 확인.** 키 발급 후 추정 엔드포인트(`/V2/api/DSSP-IF-00247`)가 한 번에 적중 — safetydata 공통 컨벤션(serviceKey, returnType=json) 덕분. 누적 55,276건, 필드: `MSG_CN`(내용), `RCPTN_RGN_NM`(수신 지역), `CRT_DT`(발송 시각), `EMRG_STEP_NM`(긴급 단계), `DST_SE_NM`(재난 구분), `SN`(일련번호 — dedupe 키로 적합). 응답이 오래된 순이라 실서비스엔 날짜 필터 파라미터 확인 필요. 클라이언트 구현은 추후.

**API 호출량 예산 분석.** 각 공공 API의 일일 한도를 확인하고, 10분 주기 폴링(하루 144사이클) 기준으로 예산을 계산했다:

| API | 사이클당 호출 | 일일 호출 | 일일 한도 | 사용률 | 사용자 증가 영향 |
|---|---|---|---|---|---|
| 기상특보 (getWthrWrnMsg) | 1 | 144 | 10,000 | 1.4% | 없음 |
| 지진 (getEqkMsg) | 1 | 144 | 10,000 | 1.4% | 없음 |
| 긴급재난문자 (safetydata) | 1 | 144 | **1,000** | **14.4%** | 없음 |
| 홍수통제소 (목록+수위) | 1+N (N=관측소) | 144×(1+N) | 없음 — 분당 1,000 제한 | — | **있음** (구독 지역↑ → N↑) |
| LLM (문구 생성) | 알림 건수 | 가변 | 크레딧/무료티어 | — | **있음** (알림 ∝ 사용자) |

**아키텍처가 주는 여유.** 수집은 서버가 소스당 1회 폴링하고 사용자에겐 DB에서 팬아웃하므로, **공공 API 호출량은 사용자 수와 무관**하다. 사용자 증가에 비례하는 건 LLM 호출(비용)과 홍수통제소 관측소 수뿐. 폴링 아키텍처의 중요한 장점이고 면접에서 말할 거리.

**병목 식별.** (1) **가장 빨리 소진: 긴급재난문자** — 한도가 1/10이라 폴링을 1분 주기로 당기면 1,440회/일로 초과. 이 소스만은 10분 이상 주기 고정 + 재시도 백오프 필수. (2) **홍수통제소 분당 1,000 제한** — Phase 2에서 관측소 동적 선정 시 병렬 호출하면 순간 초과 위험(3회 위반 시 키 차단). 순차 호출/스로틀링으로 대비. (3) `POST /events/ingest`가 무방비 — 연타하면 그만큼 공공 API를 때리므로, 스케줄러 도입 시 "최근 X분 내 수집했으면 스킵" 가드 필요.

### 2026-07-20 — 스케줄러: 10분 주기 자동 수집 + 중복 실행 가드

**설계가 곧 예산 집행.** 위 호출량 분석이 그대로 설계 근거가 됐다: 주기 10분(재난문자 한도의 14.4%), 수동 호출 가드 3분. 설정은 `.env`로 조정 가능(`INGEST_INTERVAL_MINUTES` 등)하되 기본값에 근거를 주석으로 박아뒀다(`app/config.py`).

**구현 선택: asyncio 백그라운드 태스크 (APScheduler 안 씀).** FastAPI 의 lifespan(서버 시작/종료 훅)에서 `asyncio.create_task`로 무한 루프를 띄우는 최소 구성(`app/scheduler.py`). 단일 프로세스 MVP 에선 라이브러리 하나 덜 쓰는 쪽을 택했고, 다중 인스턴스 배포 시엔 `SCHEDULER_ENABLED=0`으로 끄고 외부 스케줄러(Cloud Scheduler → POST /events/ingest)로 전환하는 퇴로를 문서화해뒀다. 주의점 하나: ingestion 코드가 동기(sync)라 이벤트 루프를 막지 않게 `asyncio.to_thread`로 스레드에서 실행.

**중복 실행 가드.** `run_ingestion_cycle_guarded()` — 마지막 실행 시각(모듈 전역)을 기억해서, 최근 N분 내 재호출이면 공공 API 를 건드리지 않고 `{"skipped": true, "reason": ...}` 반환. 스케줄러와 수동 `/events/ingest`가 같은 가드를 공유하므로 겹쳐도 안전하다. LLM 쿨다운(밤 폴백 체인)과 같은 패턴 — "상태 기억해서 낭비 호출 차단"이 이 프로젝트의 반복 모티프가 됐다.

**루프 생존성.** 사이클 전체가 실패해도(DB 다운 등) 루프는 `try/except`로 살아남아 다음 주기에 자연 재시도. 10분 주기 자체가 완만한 백오프 역할. 소스별 실패는 기존대로 격리·기록된다.

**테스트 격리 추가.** conftest 에 `SCHEDULER_ENABLED=0` — 테스트 중 백그라운드 폴링이 돌면 타이밍 비결정성이 생기니 원천 차단. 가드 로직은 별도 단위 테스트 4개로 검증(`test_scheduler_guard.py`), 스모크로 "서버 기동 → 자동 수집 → 수동 재호출 skipped → 종료 정리"까지 확인.

**면접 한마디.** "폴링 주기를 감으로 정하지 않고, 소스별 API 한도를 조사해 호출량 예산을 계산한 뒤 그 근거로 10분 주기와 중복 실행 가드를 설계했습니다."

### 2026-07-20 — 로그 시크릿 마스킹

**발견.** 스케줄러 실기기 검증 로그를 보다가, httpx 가 요청 URL 전체를 INFO 로 찍으면서 **API 키가 로그에 그대로 노출**되는 걸 발견 — 공공 API 는 serviceKey 를 쿼리스트링에, 홍수통제소는 URL 경로에 키를 넣는 구조라 피할 수 없다. 로컬에선 무해하지만 배포 후 로그 수집 시스템에 키가 쌓이면 유출 경로가 된다. **시크릿 관리는 .env 만으로 끝나지 않는다 — 로그도 유출 채널이다.**

**해결.** 로그를 끄는 대신(요청 로그는 디버깅에 유용) 루트 로거 핸들러에 `SecretRedactionFilter` 를 달아 설정의 모든 시크릿 값을 `***REDACTED***` 로 치환(`app/logging_utils.py`). httpx 같은 서드파티 로거는 루트로 전파되므로 루트 핸들러 필터 하나로 전부 커버된다. 디테일 두 가지: (1) 8자 미만 값은 오탐(평범한 단어까지 가림) 방지를 위해 제외, (2) 새 시크릿이 설정에 추가되면 자동으로 마스킹 대상에 포함.

**면접 한마디.** "시크릿 유출 채널을 저장소(.env/gitignore)뿐 아니라 로그까지 넓혀 봤습니다. 서드파티 라이브러리가 URL 을 로깅하며 키를 노출하는 걸 발견하고, 루트 로거 필터로 알려진 시크릿을 자동 마스킹했습니다."

---

## Part 5. 아직 안 한 것 / 다음 (Phase 2+)

- ~~실제 API 응답 대조~~ ✅ 2026-07-17 완료 (Part 4 일지 참고)
- ~~실제 Postgres 검증~~ ✅ 2026-07-17 완료 — Docker Postgres에 스키마 생성 + 실데이터 저장 확인
- ~~특보 통보문 상세(`getWthrWrnMsg`) 연동~~ ✅ 2026-07-19 완료 — 실데이터 알림 생성까지 검증 (Part 4 일지 참고)
- ~~구독 생성 시 소급 평가~~ ✅ 2026-07-19 완료 — backfill_subscription, 실기기 검증됨
- ~~지역명 정규화(최소 버전)~~ ✅ 2026-07-19 완료 — 시/군 접미사 정규화. 행정구역 코드 기반 근본 해결은 여전히 TODO
- **홍수 관측소 동적 선정.** 지금은 청주 2곳 하드코딩 → 구독 지역 기반으로 river_gauges/gauge_region_maps 테이블 활용.
- ~~알림 문구 LLM 생성~~ ✅ 2026-07-19 완료 — fallback 구조 포함, 실데이터 검증 (Part 4 일지 참고)
- **Layer 2 위험도 보조 판단 (LLM).** 규칙 매트릭스가 못 잡는(None 반환) 케이스를 LLM으로 판단하고 `ai_risk_logs`에 기록. 문구 생성과 같은 fallback 원칙 적용 예정.
- ~~스케줄러 (주기 자동 수집)~~ ✅ 2026-07-20 완료 — 10분 주기 asyncio 루프 + 중복 실행 가드 (Part 4 일지 참고). 소스별 주기 분리는 재난문자 클라이언트 붙일 때 함께.
- **홍수통제소 호출 스로틀링.** 관측소 동적 선정 도입 시 병렬 호출로 분당 1,000건 제한을 순간 초과하면 키 차단(하루 3회) — 순차 호출 또는 초당 제한 필요.
- **긴급재난문자 ingestion 클라이언트.** 실응답 스펙 확인 완료(2026-07-20, DSSP-IF-00247). 날짜 필터 파라미터 확인 → `SN` 기반 dedupe → `RCPTN_RGN_NM` 지역 매칭.
- **웹 프론트(PWA)** 구독 관리 화면.
- **FCM 웹푸시** 실제 발송(서비스 계정 JSON 방식). `app/config.py`의 설정도 `fcm_server_key` → `GOOGLE_APPLICATION_CREDENTIALS`/`FCM_PROJECT_ID`로 맞춰줄 것(현재는 .env만 바뀌고 config는 레거시 필드가 남아 있음 — 작은 정리 항목).
- **JWT 인증.** 지금은 `user_email`로 사용자를 get-or-create하는 임시 방식. 인증 붙으면 인증된 사용자에서 가져오게 교체.

---

## Part 6. 용어 사전

- **백엔드** — 사용자 눈에 안 보이는 서버 쪽 프로그램. 데이터 저장·처리·응답 담당.
- **API** — 프로그램끼리 데이터를 주고받는 약속. REST는 그중 URL+HTTP동사 방식.
- **엔드포인트** — API의 각 주소별 처리 지점 (예: `POST /persons`).
- **ORM** — 파이썬 객체 ↔ DB 표를 자동 변환해주는 도구 (SQLAlchemy).
- **모델** — DB 표 구조 정의 (`app/models/`).
- **스키마** — API 입출력 형태 정의 (`app/schemas/`, Pydantic).
- **PK(기본키)** — 행을 유일하게 구분하는 값.
- **FK(외래키)** — 다른 표의 행을 가리키는 값. 표 간 관계.
- **마이그레이션** — DB 구조 변경 이력을 파일로 관리 (Alembic).
- **세션** — DB와의 대화 창구.
- **트랜잭션** — "전부 성공 아니면 전부 취소" 단위.
- **commit / flush / rollback** — 확정 / 임시반영(id 확보용) / 취소.
- **다이얼렉트(dialect)** — SQLAlchemy가 각 DB의 방언 차이를 다루는 개념.
- **UUID** — 전 세계에서 안 겹치는 긴 고유 id.
- **JSONB** — Postgres의 JSON 저장/검색 전용 타입.
- **mock** — 실제 대신 쓰는 가짜 데이터/동작.
- **추상 클래스(ABC)** — 상속받는 클래스가 특정 메서드를 반드시 구현하게 강제하는 틀.
- **컨테이너 / Docker** — 앱+실행환경을 상자에 담아 어디서나 동일 실행.
- **시크릿** — API 키·비밀번호 등 유출되면 안 되는 값.

---

## Part 7. 블로그 소재 아이디어

이 프로젝트에서 뽑을 만한 글감:

1. **"운영은 Postgres, 테스트는 SQLite" — with_variant로 두 마리 토끼 잡기** (3-7). 실전 문제→해결이 뚜렷해서 가장 반응 좋을 소재.
2. **키 발급을 기다리지 않고 개발하기 — mock fallback 패턴** (3-9). 외부 API 의존 프로젝트의 공통 고민.
3. **위험도를 규칙과 LLM 2계층으로 나눈 이유** (3-10). 비용·지연·예측가능성 트레이드오프 이야기.
4. **실수로 커밋한 API 키, 히스토리에서 지우기 — git filter-repo 실전** (3-13). 짧고 실용적.
5. **모델 vs 스키마, 왜 두 벌로 나눌까** (3-4). 입문자가 자주 헷갈리는 주제라 검색 수요 있음.

---

*마지막 업데이트: 2026-07-20 (로그 마스킹 시점)*
