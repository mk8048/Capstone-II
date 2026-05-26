# main-server

NATS JetStream으로 들어오는 Vision/LLM 이벤트를 PostgreSQL에 저장하고 Dashboard용 REST API를 제공하는 FastAPI 서버. Linux PC에서 dashboard와 함께 실행하는 기준입니다.

---

## 1. 역할

| 책임 | 내용 |
|------|------|
| Vision 이벤트 수신 | `cs.vision.control.detected` durable pull consumer |
| LLM 결과 수신 | `cs.llm.control.update` durable pull consumer |
| DB 저장 | `detection_events`, `detected_objects`, `llm_analysis` |
| REST API 제공 | `/health`, `/events`, `/events/{event_id}` |
| DLQ 처리 | validation/DB 오류를 `cs.main.dead_letter`로 보관 |

main-server는 이미지 바이너리를 직접 저장하지 않습니다. Vision Server가 MinIO에 저장한 `image_key`만 DB에 보관합니다.

---

## 2. 워크플로우

```text
cs.vision.control.detected
        │
        ▼
[vision_subscriber]
        ├─ payload validation
        ├─ cameras FK 확인
        ├─ detection_events insert
        └─ detected_objects insert

cs.llm.control.update
        │
        ▼
[llm_subscriber]
        ├─ payload validation
        ├─ llm_analysis insert
        └─ detection_events.status = analyzed

FastAPI
  ├─ GET /health
  ├─ GET /events
  └─ GET /events/{event_id}
        │
        ▼
Dashboard
```

NATS 메시지는 JetStream durable pull consumer로 처리합니다. 처리 성공 시 `ack`, 재시도 가능한 DB 오류는 `nak`, 반복 실패나 validation 오류는 DLQ로 보냅니다.

---

## 3. 구성 / 주요 파일

```text
main-server/
├── README.md
├── requirements.txt
└── app/
    ├── main.py                    # FastAPI app + lifespan + subscriber task
    ├── config.py                  # pydantic-settings 기반 환경변수
    ├── db.py                      # SQLAlchemy async engine/session
    ├── models.py                  # DB model mapping
    ├── schemas.py                 # NATS payload + API response schema
    ├── logging.py                 # loguru 설정
    ├── api/
    │   ├── health.py              # GET /health
    │   └── events.py              # GET /events, /events/{event_id}
    ├── services/
    │   └── event_service.py       # DB 저장/조회 로직
    └── subscribers/
        ├── nats_client.py         # stream/consumer 준비 + DLQ publish
        ├── vision_subscriber.py   # Vision 이벤트 처리
        └── llm_subscriber.py      # LLM 이벤트 처리
```

Linux PC 통합 실행 스크립트:

```text
scripts/main_start.sh
scripts/main_stop.sh
```

---

## 4. 사전 준비

### 4.1 환경

- Linux PC
- Python 3.x
- VM 인프라 접근 가능
  - PostgreSQL `5432`
  - NATS `4222`

공통 인프라와 SSH 터널은 [docs/infra-setup.md](../docs/infra-setup.md)를 참조합니다.

### 4.2 venv + 의존성

```bash
cd main-server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.3 `.env` 생성

```bash
cd main-server
cat > .env <<'EOF'
MAIN_SERVER_PORT=8000
DATABASE_URL=postgresql+asyncpg://capstone2:<password>@localhost:5432/capstone2
NATS_URL=nats://localhost:4222
EOF
```

`DATABASE_URL`의 비밀번호는 VM PostgreSQL 비밀번호와 일치해야 합니다.

---

## 5. 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MAIN_SERVER_PORT` | `8000` | FastAPI 실행 포트 |
| `DATABASE_URL` | (필수) | PostgreSQL async SQLAlchemy URL |
| `NATS_URL` | (필수) | NATS endpoint |
| `NATS_STREAM` | `CAPSTONE_EVENTS` | Vision/LLM live event stream |
| `NATS_DLQ_STREAM` | `CAPSTONE_DLQ` | dead letter stream |
| `NATS_DLQ_SUBJECT` | `cs.main.dead_letter` | DLQ subject |
| `NATS_VISION_SUBJECT` | `cs.vision.control.detected` | Vision 이벤트 subject |
| `NATS_LLM_SUBJECT` | `cs.llm.control.update` | LLM 결과 subject |
| `NATS_VISION_CONSUMER` | `main-server-vision` | Vision durable consumer |
| `NATS_LLM_CONSUMER` | `main-server-llm` | LLM durable consumer |
| `NATS_MAX_DELIVER` | `5` | 최대 재전달 횟수 |
| `NATS_ACK_WAIT_SECONDS` | `30` | ack wait |
| `NATS_NAK_DELAY_SECONDS` | `10` | nak 재시도 delay |
| `NATS_FETCH_BATCH` | `10` | pull fetch batch |
| `NATS_FETCH_TIMEOUT_SECONDS` | `1` | pull fetch timeout |

---

## 6. 실행

### 6.1 dashboard와 함께 실행 (권장)

프로젝트 루트에서 실행합니다.

```bash
./scripts/main_start.sh
```

`main_start.sh`가 하는 일:

1. 기존 main-server/dashboard 프로세스 종료
2. `ssh -fN capstone-vm`으로 터널 확인/기동
3. main-server를 `127.0.0.1:8000`에 백그라운드 실행
4. `/health` 응답 대기
5. `dashboard/.env`를 source한 뒤 dashboard를 `127.0.0.1:5001`에 실행
6. 로그를 `logs/main-server.log`, `logs/dashboard.log`에 저장

종료:

```bash
./scripts/main_stop.sh
```

### 6.2 main-server 단독 실행

```bash
cd main-server
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## 7. 동작 확인 / 예상 결과

### 7.1 health check

```bash
curl http://127.0.0.1:8000/health
```

정상 응답:

```json
{"status":"ok"}
```

### 7.2 이벤트 목록

```bash
curl "http://127.0.0.1:8000/events?limit=5"
```

응답에는 최신 `detection_events`와 최신 LLM risk 정보가 포함됩니다.

### 7.3 이벤트 상세

```bash
curl "http://127.0.0.1:8000/events/<event_id>"
```

응답에는 탐지 이벤트, 객체 목록, 최신 LLM 분석 1건이 포함됩니다.

### 7.4 정상 로그 패턴

```text
main-server starting port=8000
stream created name=CAPSTONE_EVENTS ...
consumer created stream=CAPSTONE_EVENTS durable=main-server-vision
consumer created stream=CAPSTONE_EVENTS durable=main-server-llm
vision subscriber bound consumer=main-server-vision
llm subscriber bound consumer=main-server-llm
vision saved event_id=... camera_id=cam01 inserted=True
llm saved event_id=... risk_level=None
```

이미 stream/consumer가 존재하면 create 로그 대신 existing/conflict warning이 나올 수 있습니다. 이미 준비된 인프라에서는 정상입니다.

### 7.5 테스트

```bash
cd main-server
source .venv/bin/activate
python -m pytest
```

PostgreSQL 터널이 없으면 DB 통합 테스트 일부가 skip될 수 있습니다. VM 터널이 살아 있으면 PostgreSQL 연동 테스트까지 실행됩니다.

---

## 8. 문제 해결

| 증상 | 원인 / 조치 |
|------|------------|
| 시작 시 DB 연결 실패 | PostgreSQL 터널(5432), `DATABASE_URL`, 비밀번호 확인 |
| 시작 시 NATS 연결 실패 | NATS 터널(4222), `NATS_URL`, NATS 컨테이너 확인 |
| Vision 이벤트가 저장되지 않음 | payload schema 오류 또는 `cameras.camera_id` 미등록 |
| Vision 이벤트가 DLQ로 감 | `CAMERA_ID` row 누락 가능. `cameras` 테이블에 row 추가 |
| LLM 결과가 DLQ로 감 | 부모 `detection_events`가 아직 없거나 payload schema 오류 |
| `/events`가 비어 있음 | Vision Server가 아직 이벤트를 발행하지 않았거나 consumer가 처리 실패 |
| dashboard 과거 이벤트가 안 뜸 | main-server `/events` 응답, `MAIN_SERVER_URL` 확인 |

DLQ subject:

```text
cs.main.dead_letter
```

DLQ에는 원본 payload, 실패 이유, delivery count가 함께 저장됩니다.

---

## 9. 참고 문서

- NATS 메시지 계약: [docs/nats-schema.md](../docs/nats-schema.md)
- DB 스키마: [docs/db-schema.md](../docs/db-schema.md)
- 인프라(VM/SSH 터널/포트) 셋업: [docs/infra-setup.md](../docs/infra-setup.md)
- Dashboard: [dashboard/README.md](../dashboard/README.md)
