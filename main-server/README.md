# main-server

NATS JetStream으로 들어오는 Vision/LLM 이벤트를 PostgreSQL에 저장하고 Dashboard용 REST API를 제공하는 서비스.

설계: [docs/main-server-design.md](../docs/main-server-design.md)

## 실행

사전 조건: docker-compose 인프라가 떠 있어야 한다 (Postgres/MinIO/NATS).
SSH 터널 또는 docker network 내부에서 접근 가능해야 한다.

```bash
cd main-server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` 예시 (프로젝트 루트의 `.env` 또는 main-server 디렉토리 기준):

```env
MAIN_SERVER_PORT=8000
DATABASE_URL=postgresql+asyncpg://capstone2:<password>@localhost:5432/capstone2
NATS_URL=nats://localhost:4222
```

실행:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API

- `GET /health` — 프로세스 alive 확인
- `GET /events?limit=20&camera_id=&status=&risk_level=` — 최신 이벤트 목록
- `GET /events/{event_id}` — 이벤트 상세 (objects + 최신 LLM 분석 포함)

## NATS

- 구독: `cs.vision.control.detected`, `cs.llm.control.update` (JetStream durable pull consumer)
- DLQ: `cs.main.dead_letter` (별도 stream `CAPSTONE_DLQ`)

자세한 처리 정책은 [docs/main-server-design.md](../docs/main-server-design.md) 참조.
