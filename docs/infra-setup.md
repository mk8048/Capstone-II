# 인프라 셋업

PostgreSQL, MinIO, NATS JetStream을 제공하는 VM 인프라와 각 서버가 접근하는 방법을 정리한 문서입니다. 서버별 실행 방법은 각 README를 따르고, 이 문서는 공통 포트·터널·사전 데이터만 다룹니다.

---

## 1. 역할

| 구성 요소 | 포트 | 역할 |
|-----------|------|------|
| PostgreSQL | `5432` | main-server 이벤트/객체/LLM 분석 저장 |
| MinIO API | `9000` | vision-server 탐지 프레임 저장, llm-server/dashboard 이미지 조회 |
| MinIO Console | `9001` | bucket/object 확인용 웹 콘솔 |
| NATS JetStream | `4222` | Vision/LLM/Main/Dashboard 이벤트 메시징 |
| NATS Monitor | `8222` | NATS 상태 확인용 HTTP monitor |

---

## 2. 워크플로우

```text
Windows Vision PC
  └─ vision-server ─┬─ NATS 4222
                    └─ MinIO 9000

Windows LLM PC
  └─ llm-server ────┬─ NATS 4222
                    ├─ MinIO 9000
                    └─ Ollama 11434 (local)

Linux PC
  ├─ main-server ───┬─ PostgreSQL 5432
  │                 └─ NATS 4222
  └─ dashboard ─────┬─ NATS 4222
                    ├─ MinIO 9000
                    └─ main-server 8000

VM
  ├─ PostgreSQL
  ├─ MinIO
  └─ NATS JetStream
```

Linux PC와 두 Windows PC(vision / llm)는 VM의 포트를 SSH 터널 또는 직접 IP로 접근합니다. 현재 실행 스크립트는 기본적으로 `localhost` 터널 방식을 사용합니다.

---

## 3. 구성 / 주요 파일

```text
capstone-ii/
├── docker-compose.yml          # PostgreSQL + MinIO + NATS
├── .env.example                # VM 인프라 환경변수 템플릿
├── infra/
│   ├── postgres/init.sql       # DB 테이블 + cam01 seed
│   ├── postgres/data/          # PostgreSQL data volume
│   ├── minio/data/             # MinIO data volume
│   └── nats/data/              # NATS JetStream data volume
├── scripts/
│   ├── main_start.sh           # Linux PC main-server + dashboard 실행
│   └── main_stop.sh            # Linux PC main-server + dashboard + tunnel 종료
```

---

## 4. 사전 준비

### 4.1 VM

VM에는 Docker와 Docker Compose가 필요합니다. 프로젝트 루트에서 다음 파일을 준비합니다.

```bash
cp .env.example .env
```

`.env`의 비밀번호는 실제 값으로 변경합니다.

```env
POSTGRES_USER=capstone2
POSTGRES_PASSWORD=<password>
POSTGRES_DB=capstone2

MINIO_ROOT_USER=minio_admin
MINIO_ROOT_PASSWORD=<password>
```

인프라 실행:

```bash
docker compose up -d
```

상태 확인:

```bash
docker compose ps
```

### 4.2 SSH 키

각 Windows PC(vision / llm)와 Linux PC에서 VM에 접근할 SSH 키가 필요합니다.

Windows PC의 실행 스크립트 기본값:

```powershell
C:\projects\.ssh\keypairsw.pem
```

Linux PC는 `~/.ssh/config`에 `capstone-vm` alias를 두는 방식을 사용합니다.

### 4.3 Linux PC SSH config 예시

```sshconfig
Host capstone-vm
    HostName <VM_IP>
    User ubuntu
    IdentityFile ~/.ssh/keypairsw.pem
    LocalForward 5432 localhost:5432
    LocalForward 9000 localhost:9000
    LocalForward 9001 localhost:9001
    LocalForward 4222 localhost:4222
    LocalForward 8222 localhost:8222
```

터널 실행:

```bash
ssh -fN capstone-vm
```

### 4.4 Windows PC 터널 (vision / llm 공통)

`vision-server/vision_start.ps1`(Vision PC)와 `llm-server/llm_start.ps1`(LLM PC)는 각자의 PC에서 NATS/MinIO 포트가 없으면 아래 형태의 터널을 자동으로 엽니다.

```powershell
ssh -fN `
  -L 4222:localhost:4222 `
  -L 9000:localhost:9000 `
  ubuntu@<VM_IP> `
  -i C:\projects\.ssh\keypairsw.pem
```

---

## 5. 환경 변수

### 5.1 VM `.env`

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `POSTGRES_USER` | `capstone2` | PostgreSQL 사용자 |
| `POSTGRES_PASSWORD` | 변경 필요 | PostgreSQL 비밀번호 |
| `POSTGRES_DB` | `capstone2` | PostgreSQL DB 이름 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 외부 포트 |
| `MINIO_ROOT_USER` | `minio_admin` | MinIO access key |
| `MINIO_ROOT_PASSWORD` | 변경 필요 | MinIO secret key |
| `MINIO_API_PORT` | `9000` | MinIO API 포트 |
| `MINIO_CONSOLE_PORT` | `9001` | MinIO Console 포트 |
| `NATS_PORT` | `4222` | NATS client 포트 |
| `NATS_MONITOR_PORT` | `8222` | NATS monitor 포트 |

### 5.2 서버별 공통 연결값

| 서버 | 변수 | 값 |
|------|------|----|
| main-server | `DATABASE_URL` | `postgresql+asyncpg://capstone2:<password>@localhost:5432/capstone2` |
| main-server | `NATS_URL` | `nats://localhost:4222` |
| dashboard | `NATS_URL` | `nats://127.0.0.1:4222` |
| dashboard | `MINIO_ENDPOINT` | `localhost:9000` |
| vision-server | `NATS_URL` | `nats://localhost:4222` |
| vision-server | `MINIO_ENDPOINT` | `localhost:9000` |
| llm-server | `NATS_URL` | `nats://localhost:4222` |
| llm-server | `MINIO_ENDPOINT` | `localhost:9000` |

---

## 6. 실행

### 6.1 VM 인프라 실행

```bash
docker compose up -d
```

### 6.2 Linux PC 터널 실행

```bash
ssh -fN capstone-vm
```

포트 확인:

```bash
nc -zv localhost 5432
nc -zv localhost 9000
nc -zv localhost 4222
```

### 6.3 Windows PC 터널 확인 (vision / llm 각 PC)

```powershell
Test-NetConnection 127.0.0.1 -Port 4222 -InformationLevel Quiet
Test-NetConnection 127.0.0.1 -Port 9000 -InformationLevel Quiet
```

---

## 7. 동작 확인 / 예상 결과

### 7.1 PostgreSQL

```bash
psql -h localhost -p 5432 -U capstone2 -d capstone2 -c "\dt"
```

기본 테이블:

```text
cameras
detection_events
detected_objects
llm_analysis
```

초기 seed:

```sql
SELECT camera_id, name, location FROM cameras;
```

`cam01` row가 있어야 Vision 이벤트가 main-server에 정상 저장됩니다.

### 7.2 MinIO

Console:

```text
http://localhost:9001
```

bucket:

```text
capstone2
```

Vision Server가 동작하면 아래 object가 누적됩니다.

```text
events/<event_id>/thumb.jpg
```

### 7.3 NATS JetStream

main-server가 시작되면 아래 stream이 준비됩니다.

| Stream | Subjects |
|--------|----------|
| `CAPSTONE_EVENTS` | `cs.vision.control.detected`, `cs.llm.control.update` |
| `CAPSTONE_DLQ` | `cs.main.dead_letter` |

주요 durable consumer:

| Consumer | Subject | 사용 |
|----------|---------|------|
| `main-server-vision` | `cs.vision.control.detected` | Vision 이벤트 DB 저장 |
| `main-server-llm` | `cs.llm.control.update` | LLM 분석 DB 저장 |
| `llm-server-vision` | `cs.vision.control.detected` | LLM Server 이미지 분석 |

---

## 8. 문제 해결

| 증상 | 원인 / 조치 |
|------|------------|
| `localhost:4222` 연결 실패 | SSH 터널 미기동 또는 NATS 컨테이너 미실행 |
| `localhost:9000` 연결 실패 | SSH 터널 미기동 또는 MinIO 컨테이너 미실행 |
| main-server가 시작 중 DB 연결 실패 | `DATABASE_URL`, PostgreSQL 터널, DB 비밀번호 확인 |
| Vision 이벤트가 DLQ로 감 | `cameras` 테이블에 `CAMERA_ID` row가 없음 |
| MinIO 이미지가 404 | bucket 이름, `image_key`, `MINIO_SECRET_KEY` 확인 |
| Windows에서 터널 포트가 이미 사용 중 | 기존 SSH 프로세스 또는 로컬 서비스가 같은 포트를 점유 중 |
| Dashboard 이미지 프록시 실패 | Linux PC에도 MinIO `9000` 터널이 필요함 |

---

## 9. 참고 문서

- NATS 메시지 계약: [nats-schema.md](nats-schema.md)
- DB 스키마: [db-schema.md](db-schema.md)
- Vision Server: [../vision-server/README.md](../vision-server/README.md)
- LLM Server: [../llm-server/README.md](../llm-server/README.md)
- Main Server: [../main-server/README.md](../main-server/README.md)
- Dashboard: [../dashboard/README.md](../dashboard/README.md)
