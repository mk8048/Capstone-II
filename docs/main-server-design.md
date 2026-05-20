# Main Server Design

본 문서는 main-server MVP 설계 문서다.
구현은 이 문서를 기준으로 진행한다. 변경 필요 시 본 문서를 먼저 수정한 뒤 구현에 반영한다.

---

## 1. 목표

main-server의 1차 목표는 **NATS JetStream으로 들어오는 Vision/LLM 이벤트를 PostgreSQL에 안정적으로 저장하고, Dashboard가 조회할 최소 REST API를 제공하는 것**이다.

MVP 성공 기준:

- `GET /health` 응답 가능
- `cs.vision.control.detected` 메시지를 durable consumer로 수신
- Vision 이벤트를 `detection_events`, `detected_objects`에 저장
- `cs.llm.control.update` 메시지를 durable consumer로 수신
- LLM 분석 결과를 `llm_analysis`에 저장하고 이벤트 상태를 갱신
- `GET /events`로 최신 이벤트 목록 조회
- `GET /events/{event_id}`로 이벤트 상세 조회
- 서버 종료 시 NATS와 DB 연결을 정상 정리

---

## 2. 기술 스택

합의된 기본 스택:

- Web framework: **FastAPI**
- ASGI server: **uvicorn**
- DB access: **SQLAlchemy 2.0 async + asyncpg**
- NATS client: **nats-py**
- NATS mode: **JetStream durable pull consumer**
- Settings: **pydantic-settings**
- Logging: **loguru**
- Migration: **Alembic 미도입**

MVP에서 제외:

- main-server의 MinIO client
- MinIO presigned URL API
- REST 기반 이벤트 생성 API
- `/cameras` API

MinIO 관련 판단:

- Vision/LLM/Dashboard 흐름에서 이미지는 `image_key`로만 참조한다.
- main-server MVP는 `image_key`를 DB에 저장하고 API 응답에 포함하는 역할만 한다.
- Dashboard가 실제 이미지 URL을 요구하는 시점에 presigned URL API를 추가한다.

---

## 3. 폴더 구조

```text
main-server/
  README.md
  requirements.txt
  app/
    __init__.py
    main.py
    config.py
    db.py
    models.py
    schemas.py
    logging.py
    api/
      __init__.py
      health.py
      events.py
    services/
      __init__.py
      event_service.py
    subscribers/
      __init__.py
      nats_client.py
      vision_subscriber.py
      llm_subscriber.py
```

모듈 책임:

- `main.py`: FastAPI 앱 생성, lifespan에서 DB/NATS lifecycle 관리
- `config.py`: `.env` 기반 설정 로딩
- `db.py`: async SQLAlchemy engine/session factory
- `models.py`: 기존 PostgreSQL 테이블 매핑
- `schemas.py`: NATS payload 검증 schema + API response schema
- `logging.py`: loguru 설정
- `api/health.py`: `/health`
- `api/events.py`: `/events`, `/events/{event_id}`
- `services/event_service.py`: 이벤트 저장/조회 비즈니스 로직
- `subscribers/nats_client.py`: JetStream 연결, stream/consumer 준비, DLQ publish helper
- `subscribers/vision_subscriber.py`: Vision 이벤트 처리 loop
- `subscribers/llm_subscriber.py`: LLM 이벤트 처리 loop

---

## 4. REST API

### `GET /health`

Process alive 확인용 API.

응답 예:

```json
{
  "status": "ok"
}
```

DB/NATS deep health check는 MVP 범위에서 제외한다.

### `GET /events`

최신 이벤트 목록 조회.

Query parameters:

- `limit`: default `20`, max `100`
- `camera_id`: optional
- `status`: optional
- `risk_level`: optional

정렬:

- `detection_events.occurred_at DESC`

응답에는 이벤트 기본 정보와 최신 LLM 분석 1건을 포함한다.
`risk_level` 필터는 최신 LLM 분석 기준으로 적용한다.

### `GET /events/{event_id}`

이벤트 상세 조회.

포함 정보:

- 이벤트 기본 정보
- `detected_objects` 전체
- 최신 `llm_analysis` 1건

이벤트가 없으면 `404`를 반환한다.

---

## 5. NATS / JetStream 설계

단순 NATS subscriber가 아니라 **JetStream durable pull consumer**를 사용한다.

이유:

- main-server가 재시작되거나 잠시 중단되어도 이벤트 유실을 줄이기 위함
- ack/nak/retry/DLQ 처리가 필요하기 때문

### Live Event Stream

Stream name:

```text
CAPSTONE_EVENTS
```

Subjects:

```text
cs.vision.control.detected
cs.llm.control.update
```

Stream 생성 정책:

- main-server startup에서 `add_stream` 호출 (create-if-missing).
- 이미 존재하면 config를 수정하지 않는다.
- `add_stream` 실패 또는 설정 불일치는 warning 로그만 남기고 계속 진행한다.
- live stream을 자동 update하는 것은 위험하므로 수동 운영 대응으로 둔다.

### Consumers

Vision consumer:

```text
durable name: main-server-vision
subject: cs.vision.control.detected
ack policy: explicit
deliver policy: all
max deliver: 5
ack wait: 30s
```

LLM consumer:

```text
durable name: main-server-llm
subject: cs.llm.control.update
ack policy: explicit
deliver policy: all
max deliver: 5
ack wait: 30s
```

구현 방식:

- subscriber별 background task 1개
- pull consumer 방식
- batch fetch loop
- 정상 처리 시 `ack()`
- 재시도 가능한 실패는 `nak(delay=...)`
- 영구 실패 또는 max deliver 도달 시 DLQ publish 후 `ack()`

---

## 6. Message 처리 정책

### Vision Message

Subject:

```text
cs.vision.control.detected
```

처리 순서:

1. JSON parse
2. Pydantic schema validation
3. `camera_id` 존재 확인
4. `detection_events` insert
5. `detected_objects` bulk insert
6. commit
7. `ack()`

정책:

- `event_id`는 Vision이 생성한 값을 그대로 사용한다.
- 중복 `event_id`는 `ON CONFLICT DO NOTHING`으로 처리한다.
- 이벤트는 immutable snapshot으로 본다.
- 중복 이벤트가 오면 객체도 재삽입하지 않는다.
- 미등록 `camera_id`는 자동 upsert하지 않는다.
- 미등록 `camera_id`: `nak(delay=10s)`로 재시도, max deliver 5회 도달 시 DLQ로 보낸다.

### LLM Message

Subject:

```text
cs.llm.control.update
```

처리 순서:

1. JSON parse
2. Pydantic schema validation
3. `llm_analysis` insert (parent pre-check 없음)
4. FK violation 발생 시 transaction rollback + `nak(delay=10s)`
5. 정상 insert 시 `detection_events.status='analyzed'` update
6. commit
7. `ack()`

정책:

- `llm_analysis`는 매번 insert한다.
- 동일 이벤트에 대한 재분석 결과는 누적 저장한다.
- 부모 `event_id`가 없으면 FK violation을 catch하여 `nak(delay=10s)` 재시도, max deliver 5회 도달 시 DLQ로 보낸다.
- parent pre-check를 두지 않는 이유: race condition 방지 + 쿼리 1회 절약.

---

## 7. DLQ 설계

DLQ는 live event stream과 분리한다.

Stream:

```text
CAPSTONE_DLQ
```

Subject:

```text
cs.main.dead_letter
```

분리 이유:

- live event와 DLQ의 보존 정책을 다르게 가져갈 수 있음
- live stream 정리와 DLQ 정리를 분리할 수 있음
- 장애 분석용 메시지를 더 오래 보존하기 쉬움

DLQ payload 예:

```json
{
  "source_subject": "cs.llm.control.update",
  "reason": "parent_event_not_found",
  "deliveries": 5,
  "failed_at": "2026-05-14T12:00:00+09:00",
  "payload": {}
}
```

DLQ로 보내는 대표 상황:

- JSON parse 실패
- schema validation 실패
- 미등록 `camera_id` retry 초과
- LLM parent event 없음 retry 초과
- 처리 불가능한 DB 오류

---

## 8. DB 처리 정책

`infra/postgres/init.sql`을 source of truth로 둔다.

SQLAlchemy 모델은 기존 테이블을 매핑만 한다.
MVP에서 `create_all()`은 사용하지 않는다.

### Vision 저장

트랜잭션 단위:

- `cameras` 존재 확인
- `detection_events` insert
- insert가 실제로 된 경우에만 `detected_objects` bulk insert
- commit

중복 처리:

```sql
ON CONFLICT (event_id) DO NOTHING
```

### LLM 저장

트랜잭션 단위:

- `llm_analysis` insert (parent pre-check 없음)
- FK violation 발생 시 rollback → 호출자(subscriber)가 `nak(delay=10s)`로 재시도
- 정상 insert 시 `detection_events.status='analyzed'` update
- commit

이 패턴의 이유:

- pre-check + insert 사이의 race condition 제거
- 정상 경로에서 쿼리 1회 절약

### DB Pool

권장 설정:

```text
pool_size=5
max_overflow=10
pool_pre_ping=True
```

---

## 9. Migration 정책

MVP에서는 Alembic을 도입하지 않는다.

스키마 변경 시:

- `infra/postgres/init.sql` 수정
- `docs/db-schema.md` 수정

기존 dev DB 반영:

- MVP 단계에서는 docker volume을 삭제하고 재생성한다.

운영/시연 DB 유지가 필요해지는 시점:

- Alembic 도입을 검토한다.

---

## 10. Logging / Shutdown

### Logging

라이브러리:

```text
loguru
```

MVP 로그 형식:

- JSON logging은 강제하지 않는다.
- 사람이 읽기 쉬운 key=value 형태로 시작한다.

가능한 로그 필드:

- `event_id`
- `camera_id`
- `subject`
- `deliveries`
- `reason`

### Shutdown

FastAPI lifespan shutdown에서 순서대로 처리한다.

1. subscriber task cancel 요청
2. 진행 중 메시지 처리 완료 대기
3. NATS drain/close
4. SQLAlchemy engine dispose

---

## 11. 환경 변수

로컬 개발은 SSH tunnel 기준으로 `localhost`를 사용한다.
Docker compose network 내부 실행 시 host는 `postgres`, `nats`로 바뀔 수 있다.

```env
MAIN_SERVER_PORT=8000
DATABASE_URL=postgresql+asyncpg://capstone2:<password>@localhost:5432/capstone2
NATS_URL=nats://localhost:4222

NATS_STREAM=CAPSTONE_EVENTS
NATS_DLQ_STREAM=CAPSTONE_DLQ
NATS_VISION_CONSUMER=main-server-vision
NATS_LLM_CONSUMER=main-server-llm
NATS_MAX_DELIVER=5
NATS_ACK_WAIT_SECONDS=30
```

main-server MVP에서는 MinIO 환경 변수를 사용하지 않는다.

---

## 12. 합의 완료된 항목

- Framework: FastAPI
- ASGI server: uvicorn
- DB: SQLAlchemy 2.0 async + asyncpg
- NATS client: nats-py
- NATS mode: JetStream durable pull consumer
- Settings: pydantic-settings
- Logging: loguru
- Alembic: MVP 미도입
- `event_id`: Vision이 생성
- `image_key`: `events/<event_id>/thumb.jpg` 예시 패턴 사용
- 중복 `event_id`: `ON CONFLICT DO NOTHING`
- `llm_analysis`: 재분석 누적 insert
- MinIO presigned URL: MVP 제외
- DB pool: `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`
- LLM parent event 없음: retry 후 DLQ

---

## 13. 핵심 정책 요약 (2026-05-14)

본문에 명시된 운영 정책 중 구현 시 자주 참조될 항목.

| # | 항목 | 결정 |
|---|------|------|
| 1 | DLQ stream | 별도 stream `CAPSTONE_DLQ` 사용 (§7) |
| 2 | 미등록 camera NAK delay | `nak(delay=10s)`, max deliver 5회 (§6 Vision) |
| 3 | LLM parent 없음 처리 | FK violation catch 방식 (§6 LLM, §8 LLM 저장) |
| 4 | Stream 생성 정책 | create-if-missing only, 불일치는 warning log (§5) |
