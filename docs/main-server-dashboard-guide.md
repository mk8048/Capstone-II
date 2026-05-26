# Main Server + Dashboard 운영 가이드

본 문서는 main-server와 dashboard를 같이 운영할 때 참조하는 안내서다.
설계 SoT는 [`docs/main-server-design.md`](./main-server-design.md), Vision Server 통합은 [`docs/vision-server-integration.md`](./vision-server-integration.md) 참조.

---

## 1. 개요 / 역할

| 컴포넌트 | 책임 | 포트 |
|---------|------|------|
| **main-server** | NATS 이벤트 수신 → PostgreSQL 저장 → REST API 제공 | 8000 |
| **dashboard** | NATS 직접 구독 (실시간) + main-server API 호출 (과거) + MediaMTX iframe (영상) | 5001 |

### 전체 데이터 흐름

```
Vision Server (Windows + GPU)
   │
   ├─► MediaMTX (RTSP publish, 같은 PC) ─► dashboard <iframe>           [영상]
   ├─► MinIO (image_key 업로드)
   └─► NATS publish ─► main-server (FastAPI)
                          │
                          ├─► PostgreSQL (detection_events, detected_objects, llm_analysis)
                          └─► REST API (/events) ─► dashboard            [메시지 영역 갱신]
                                                      ▲
                                                      └── NATS direct sub (실시간 push)
```

---

## 2. 코드 구조

### main-server ([main-server/](../main-server/))

```
main-server/
  app/
    main.py              # FastAPI + lifespan (NATS connect, subscriber tasks)
    config.py            # .env 로딩 (pydantic-settings)
    db.py                # async SQLAlchemy engine
    models.py            # Camera, DetectionEvent, DetectedObject, LLMAnalysis
    schemas.py           # Pydantic v2 (NATS payload + API response)
    logging.py           # loguru
    api/
      health.py          # GET /health
      events.py          # GET /events, GET /events/{event_id}
    services/event_service.py
    subscribers/
      nats_client.py     # JetStream durable consumer
      vision_subscriber.py
      llm_subscriber.py
  tests/                 # pytest 18 + PG fixture 3 (skipped without tunnel)
  requirements.txt
  .env                   # gitignore. 직접 작성 (예시 §5 참조)
  .venv/                 # pyenv 3.12.13 기반
```

### dashboard ([dashboard/](../dashboard/))

```
dashboard/
  dashboard_app.py       # Flask + NATS 구독 thread + API 폴링
  send_nats_test.py      # NATS 테스트용 publish 스크립트
  requirements.txt       # flask, nats-py
  .venv/                 # pyenv 3.12.13 기반
  WORK_SUMMARY.md
```

**주요 동작:**
- 시작 시 `GET /events?limit=20` → 과거 이벤트 채움 (`fetch_initial_events()`)
- 백그라운드 thread에서 NATS 직접 구독 (`cs.vision.control.detected`, `cs.llm.control.update`)
- `event_id` 기준 중복 체크 (NATS/API 양쪽에서 같은 이벤트 들어와도 한 번만 표시)
- JS polling 3초마다 `GET /messages` → 메시지 영역 + NATS 상태 갱신 (iframe은 안 건드림)

---

## 3. 실행 준비 조건

### 3-0. 담당자에게 미리 받아둘 것

main-server 담당자에게 직접 받아야 하는 항목. **저장소(repo)에는 보안상 들어있지 않으므로 별도로 전달받아야 한다.**

| 항목 | 용도 | 사용 위치 |
|------|------|----------|
| **`keypairsw.pem`** (SSH 키 파일) | VM 접속 (Postgres / NATS / MinIO 터널) | §3-5 |
| **DB 비밀번호** | `main-server/.env`의 `DATABASE_URL`에 삽입 | §3-6 |
| (참고) VM 공인 IP | `~/.ssh/config`의 `HostName` 갱신 시 | §3-5 |

> 키 파일은 가능하면 USB나 보안 채널로 전달받는다. 비밀번호도 채팅/이메일 평문보다는 1Password/비밀번호 관리자 사용 권장.

### 3-1. 시스템 의존성

- Ubuntu (Linux native — WSL도 가능)
- Python build deps (pyenv로 3.12 컴파일에 필요):
  ```bash
  sudo apt install -y make build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev \
    libncurses-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev curl git
  ```

### 3-2. Python 환경 (pyenv 권장)

시스템 Python이 3.14+이거나 의존성 호환 이슈가 있어 별도 3.12 설치.

```bash
# pyenv 설치
curl https://pyenv.run | bash

# ~/.bashrc에 추가
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"

# 3.12.13 설치 (3~5분 컴파일)
pyenv install 3.12.13
```

### 3-3. .venv + 의존성 설치 (main-server)

```bash
cd main-server
pyenv local 3.12.13              # .python-version 생성
python -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 3-4. .venv + 의존성 설치 (dashboard)

```bash
cd dashboard
pyenv local 3.12.13
python -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 3-5. SSH 키 + 터널 셋업 (VM Postgres/NATS/MinIO 접근용)

```bash
# 1. 키 파일 권한
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cp /path/to/keypairsw.pem ~/.ssh/
chmod 400 ~/.ssh/keypairsw.pem

# 2. ~/.ssh/config 추가 (LocalForward 8000은 제외 — 로컬 main-server와 충돌)
cat >> ~/.ssh/config << 'EOF'

Host capstone-vm
    HostName 210.109.82.57
    User ubuntu
    IdentityFile ~/.ssh/keypairsw.pem
    IdentitiesOnly yes
    ServerAliveInterval 60
    ServerAliveCountMax 3

    LocalForward 5432 localhost:5432
    LocalForward 9000 localhost:9000
    LocalForward 9001 localhost:9001
    LocalForward 4222 localhost:4222
    LocalForward 8222 localhost:8222
EOF
chmod 600 ~/.ssh/config
```

상세는 [`docs/onboarding.md §6~7`](./onboarding.md) 참조.

### 3-6. main-server `.env` 작성

[`main-server/.env`](../main-server/.env) (gitignore. 직접 작성):

```env
MAIN_SERVER_PORT=8000
DATABASE_URL=postgresql+asyncpg://capstone2:<password>@localhost:5432/capstone2
NATS_URL=nats://localhost:4222
```

> `<password>`는 main-server 담당자에게 받은 값.

### 3-7. (선택) dashboard 환경 변수

dashboard는 env가 없어도 default로 동작. 변경하려면 shell에서:

```bash
export NATS_URL=nats://127.0.0.1:4222
export MEDIA_URL=http://<vision-pc-ip>:8889/cam01/   # MediaMTX WebRTC player
export MAIN_SERVER_URL=http://127.0.0.1:8000
```

---

## 4. 실행 방법

### 4-1. SSH 터널 띄우기

```bash
ssh -fN capstone-vm
```

확인:
```bash
ss -tlnp | grep -E ':(5432|4222)\s'
# 둘 다 listen 보여야 함
```

### 4-2. main-server + dashboard 시작 (한 번에)

```bash
./scripts/main_start.sh
```

동작:
1. 기존 프로세스 정리
2. SSH 터널 확인 (없으면 warning만)
3. main-server 시작 → `/health` 200 응답 대기 (최대 15초)
4. dashboard 시작
5. PID + 로그 경로 출력

출력 예:
```
[start] services started:
  main-server: http://127.0.0.1:8000  (PID xxxxx)
  dashboard:   http://127.0.0.1:5001  (PID xxxxx)
```

### 4-3. 종료

```bash
./scripts/main_stop.sh
```

SSH 터널은 별도:
```bash
pkill -f "ssh -fN capstone-vm"
```

### 4-4. 로그 확인

```bash
# 실시간 양쪽 같이
tail -F logs/main-server.log logs/dashboard.log

# main-server만
tail -F logs/main-server.log

# 특정 이벤트 grep
tail -F logs/main-server.log | grep "vision saved\|DLQ\|ERROR"
```

---

## 5. 확인 / 검증

### 5-1. 헬스체크

```bash
curl http://127.0.0.1:8000/health
# → {"status":"ok"}
```

### 5-2. API 동작

```bash
# 최신 이벤트 5건
curl 'http://127.0.0.1:8000/events?limit=5' | jq

# 특정 이벤트 상세
curl http://127.0.0.1:8000/events/evt_xxx | jq
```

### 5-3. dashboard 페이지

브라우저로 http://127.0.0.1:5001 접속.

확인 포인트:
- 상단 "NATS 상태: **connected**"
- "최근 N건 / 최대 100건" 카운트가 3초마다 자동 갱신
- "(updated HH:MM:SS)" 시각이 3초마다 갱신 (polling 동작 증거)
- 우측 영상 영역에 MediaMTX iframe (Vision Server가 publish 중이면 영상 보임)

### 5-4. NATS 직접 publish 테스트

```bash
cd dashboard
.venv/bin/python send_nats_test.py
# → published event_id=evt_dashboard_test_001
```

main-server 로그에:
```
vision saved event_id=evt_dashboard_test_001 camera_id=cam01 inserted=True
```

### 5-5. pytest (main-server)

```bash
cd main-server
.venv/bin/python -m pytest
# → 18 passed, 3 skipped  (SSH 터널 없으면 PG fixture skip)
# → 21 passed             (SSH 터널 + PG 접근 가능 시)
```

---

## 6. 주요 엔드포인트

### main-server (port 8000)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 프로세스 alive 확인 |
| GET | `/events?limit=N&camera_id=&status=&risk_level=` | 최신 이벤트 목록 |
| GET | `/events/{event_id}` | 이벤트 상세 (objects + 최신 LLM 분석) |

### dashboard (port 5001)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 메인 페이지 (영상 + 메시지) |
| GET | `/messages` | JSON: 현재 messages + NATS 상태 (JS polling용) |
| POST | `/set-media-url` | MediaMTX URL 변경 (form submit) |

---

## 7. NATS Subjects

| Subject | 발행자 | 수신자 |
|---------|--------|--------|
| `cs.vision.control.detected` | Vision Server | main-server (durable `main-server-vision`), dashboard (direct sub) |
| `cs.llm.control.update` | LLM Server | main-server (durable `main-server-llm`), dashboard (direct sub) |
| `cs.main.dead_letter` | main-server (DLQ) | (관리/디버그용) |

상세는 [`docs/nats-schema.md`](./nats-schema.md).

---

## 8. 빠른 참조 치트시트

```bash
# 시작
ssh -fN capstone-vm
./scripts/main_start.sh

# 중지
./scripts/main_stop.sh
pkill -f "ssh -fN capstone-vm"

# 상태 확인
curl http://127.0.0.1:8000/health
ss -tlnp | grep -E ':(5432|4222|8000|5001)\s'

# 로그
tail -F logs/main-server.log logs/dashboard.log

# 테스트 메시지 발행
cd dashboard && .venv/bin/python send_nats_test.py

# pytest
cd main-server && .venv/bin/python -m pytest
```

---

## 9. 관련 문서

| 문서 | 내용 |
|------|------|
| [main-server-design.md](./main-server-design.md) | main-server 설계 SoT |
| [vision-server-integration.md](./vision-server-integration.md) | Vision Server 통합 가이드 |
| [nats-schema.md](./nats-schema.md) | NATS 메시지 명세 |
| [db-schema.md](./db-schema.md) | DB 스키마 |
| [onboarding.md](./onboarding.md) | 팀원 환경 셋업 (WSL 기반) |

---

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-20 | 초안 작성 (main-server MVP + dashboard hybrid 통합 + scripts 자동화 + MediaMTX iframe + JS polling 완료 시점 기준) |
