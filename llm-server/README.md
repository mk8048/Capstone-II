# llm-server

Vision 탐지 이벤트를 구독해 **MinIO에서 해당 프레임을 가져와 LLaVA로 분석**하고, 영어 한 문장 요약을 NATS로 발행하는 서버. NATS-driven · stateless. Windows + GPU(Ollama/LLaVA) 환경 기준.

---

## 1. 역할

| 책임 | 입력 / 출력 |
|------|------|
| `cs.vision.control.detected` 구독 | Vision 탐지 이벤트 (JetStream durable pull) |
| `data.image_key`로 MinIO 프레임 fetch | JPEG bytes |
| LLaVA(Ollama)로 이미지 분석 | 영어 한 문장 요약 |
| `cs.llm.control.update` 발행 | 동일 `event_id` + `data.summary` |

- **stateless** — 자체 DB 없음. 받은 이벤트를 분석해 발행만 한다.
- Vision이 만든 `event_id`를 그대로 유지해, main-server/Dashboard가 같은 이벤트로 연결한다.
- 요약 규칙: 영어, 자연스러운 한 문장, JSON/목록/마크다운 없이 보이는 사실만 기술.

---

## 2. 워크플로우

```
cs.vision.control.detected  (JetStream stream: CAPSTONE_EVENTS)
        │  durable pull consumer: llm-server-vision
        ▼
[nats_subscriber] ── data.image_key ──▶ [minio_client] ──▶ MinIO  events/<event_id>/thumb.jpg
        │                                                          │ JPEG bytes
        │                                                          ▼
        │                                                   [llm_client] ──▶ Ollama / LLaVA
        │                                                          │ 영어 한 문장
        ▼                                                          │
[nats_publisher] ◀───────────────────────────────────────────────┘
        │  js.publish
        ▼
cs.llm.control.update  ──▶ Main Server (llm_analysis 저장) ──▶ Dashboard (요약 표시)
```

처리 실패(이미지 없음 / 추론 실패 / 필드 누락)는 **로그만 남기고 메시지를 ack(skip)** 한다(MVP). 별도 에러 payload는 발행하지 않는다.

---

## 3. 구성 / 주요 파일

```
llm-server/
├── README.md             # 본 문서
├── llm_start.ps1         # launcher (SSH 터널 + Ollama 기동/정리 + 중복 실행 가드)
├── main.py               # 엔트리포인트: NATS 연결 + 구독 루프 + graceful shutdown
├── config.py             # python-dotenv 기반 설정 로드
├── nats_subscriber.py    # JetStream durable pull consumer + 이벤트 처리 + payload 조립
├── nats_publisher.py     # cs.llm.control.update 발행 (js.publish)
├── minio_client.py       # image_key → JPEG bytes fetch
├── llm_client.py         # Ollama/LLaVA 호출 + 응답 정리(clean_summary)
├── app.py                # (선택) 수동 디버그용 POST /analyze 엔드포인트
├── requirements.txt      # nats-py + minio + python-dotenv + requests
├── .env.example          # 환경변수 템플릿
└── tests/                # 단위 테스트 (payload 검증 / 요약 정리)
```

`app.py`(FastAPI `/analyze`)는 로컬 이미지로 분석을 수동 확인하는 디버그 용도이며, 운영 흐름은 `main.py`(NATS-driven)이다. `app.py`를 쓰려면 `fastapi`/`uvicorn`을 별도 설치한다.

---

## 4. 사전 준비

### 4.1 하드웨어
- NVIDIA GPU (LLaVA 추론용. CPU는 추론이 매우 느려 권장하지 않음)

### 4.2 Ollama + 모델
```powershell
# Ollama 설치 후
ollama pull llava:7b
```
`llm_start.ps1`은 Ollama가 안 떠 있으면 `ollama serve`를 띄우지만, **설치와 모델 pull은 자동으로 하지 않는다.**

### 4.3 Python 의존성
```powershell
cd llm-server
pip install -r requirements.txt
# (선택) 격리하려면: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
```

### 4.4 인프라 (VM) 접속
NATS(4222) / MinIO(9000)는 VM에 있고 SSH 터널로 접근한다. 공통 인프라 준비는 [docs/infra-setup.md](../docs/infra-setup.md) 참조.

핵심 전제:
- **main-server가 먼저 떠 있어야** JetStream stream `CAPSTONE_EVENTS`가 존재한다(main-server가 stream 소유). 없으면 llm-server는 stream이 생길 때까지 3초마다 재시도한다.
- 구독은 main-server와 겹치지 않는 별도 durable consumer 이름(`llm-server-vision`)을 쓴다.

### 4.5 .env 생성
```powershell
copy .env.example .env
# .env 열어 MINIO_SECRET_KEY를 실제 값으로 변경
```

---

## 5. 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NATS_URL` | `nats://localhost:4222` | NATS endpoint (SSH 터널) |
| `NATS_STREAM` | `CAPSTONE_EVENTS` | 구독할 JetStream stream (main-server 소유) |
| `NATS_VISION_SUBJECT` | `cs.vision.control.detected` | 구독 subject |
| `NATS_LLM_SUBJECT` | `cs.llm.control.update` | 발행 subject |
| `NATS_VISION_CONSUMER` | `llm-server-vision` | durable consumer 이름 (main-server와 달라야 함) |
| `NATS_FETCH_BATCH` | `1` | pull fetch 배치 크기 |
| `NATS_FETCH_TIMEOUT_SECONDS` | `5` | pull fetch 타임아웃 |
| `MINIO_ENDPOINT` | `localhost:9000` | SSH 터널 endpoint |
| `MINIO_ACCESS_KEY` | `minio_admin` | |
| `MINIO_SECRET_KEY` | (필수) | MinIO 비밀번호 |
| `MINIO_BUCKET` | `capstone2` | Vision이 프레임을 올리는 bucket |
| `MINIO_SECURE` | `false` | dev/내부망 |
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Ollama generate API (원격 GPU 박스로 변경 가능) |
| `LLM_MODEL_NAME` | `llava:7b` | 분석 모델 |

---

## 6. 실행

### 6.1 통합 실행 (권장)
```powershell
cd llm-server
.\llm_start.ps1
```
`llm_start.ps1`이 하는 일:
1. 이미 실행 중인 인스턴스가 있으면 중복 실행 차단
2. SSH 터널(NATS 4222 / MinIO 9000) 확인 후 없으면 자동 기동
3. Ollama(11434) 확인 — 안 떠 있으면 `ollama serve` 기동(이 경우 종료 시 함께 정리)
4. LLM Server foreground 실행 — Ctrl+C로 종료

실행 정책에 막히면:
```powershell
powershell -ExecutionPolicy Bypass -File .\llm_start.ps1
```

### 6.2 수동 실행
```powershell
cd llm-server
python -u main.py
```

### 6.3 디버그 엔드포인트 (선택)
```powershell
pip install fastapi uvicorn
uvicorn app:app --port 8100
# POST /analyze  body: { "image_path": "test.jpg", "event_id": "evt_x", "camera_id": "cam01" }
```

---

## 7. 동작 확인 / 예상 결과

### 7.1 정상 콘솔 로그
```
[start] Ollama already up (11434)
[llm] starting model=llava:7b ollama=http://localhost:11434/api/generate minio=localhost:9000
[llm] nats connected url=nats://localhost:4222 publish=cs.llm.control.update
[llm] subscribed stream=CAPSTONE_EVENTS consumer=llm-server-vision subject=cs.vision.control.detected
[llm] published event_id=evt_xxxxxxxx inference=4.82s total=4.85s summary='...'
```
이벤트당 `inference=`(LLaVA 추론 시간)과 `total=`(MinIO fetch 포함 전체 처리 시간)이 로그에 남는다.

### 7.2 e2e 확인
1. Vision Server가 탐지 이벤트를 발행한다.
2. llm-server가 `[llm] published ...` 로그를 남긴다 (동일 `event_id`).
3. main-server에 `llm_analysis` row가 저장된다.
4. Dashboard 해당 이벤트 카드에 요약이 표시된다.

---

## 8. 문제 해결

| 증상 | 원인 / 조치 |
|------|------------|
| `pull_subscribe failed (stream not ready?)` 반복 | main-server 미기동 → stream(`CAPSTONE_EVENTS`) 부재. main-server 먼저 실행 |
| 이벤트를 main-server와 나눠 가져감/누락 | durable 이름이 main-server와 겹침 → `NATS_VISION_CONSUMER`를 고유값으로 |
| `[start] Ollama not reachable on 11434` | Ollama 미기동 → `ollama serve` (그리고 `ollama pull llava:7b`) |
| 추론 실패 / 타임아웃 로그 후 skip | 모델 미설치 또는 GPU 메모리 부족. 모델 pull / GPU 확인 |
| 요약은 오는데 Dashboard에 안 보임 | `event_id`가 Vision 이벤트와 다름 → 동일 ID 유지 확인 |
| 처리 지연이 누적됨(backlog) | 평균 추론시간 > Vision `EVENT_COOLDOWN_SECONDS`. 쿨다운을 추론시간보다 길게 조정 |
| 첫 추론만 유독 느림 | 모델 cold start(VRAM 로드). 이후 추론은 정상 |

---

## 9. 참고 문서

- NATS 메시지 계약: [docs/nats-schema.md](../docs/nats-schema.md)
- DB 스키마: [docs/db-schema.md](../docs/db-schema.md)
- 인프라(VM/SSH 터널/포트/bucket) 셋업: [docs/infra-setup.md](../docs/infra-setup.md)
