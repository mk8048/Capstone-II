# dashboard

실시간 카메라 영상과 탐지 이벤트(+LLM 요약+탐지 프레임)를 한 화면에 보여주는 Flask 웹 대시보드. main-server와 같은 Linux PC에서 실행.

---

## 1. 역할

| 책임 | 내용 |
|------|------|
| NATS 실시간 구독 | `cs.vision.control.detected` + `cs.llm.control.update`를 `event_id` 기준으로 한 카드에 병합 |
| 과거 이벤트 로드 | 시작 시 main-server `GET /events`로 최근 이벤트 채움 |
| 실시간 영상 표시 | MediaMTX WebRTC 스트림을 iframe으로 표시 (원본 / AI 토글) |
| 탐지 프레임 표시 | MinIO에 저장된 `image_key`를 자체 프록시로 받아 카드에 렌더 (+ bbox 오버레이) |

탐지 카드는 Vision 메시지로 먼저 뜨고(객체/confidence/이미지), 잠시 뒤 도착하는 LLM 메시지가 **같은 카드에 요약을 채운다**.

---

## 2. 워크플로우

```
브라우저 ◀── 3초 polling ── /messages ◀── 메모리(event_id별 병합)
                                              ▲
                  ┌───────────────────────────┤
   cs.vision.control.detected  ───────────────┤  (NATS live 구독)
   cs.llm.control.update       ───────────────┘
                                              ▲
   시작 시 main-server GET /events ───────────┘  (과거 이벤트 초기 로드)

[카메라 영상]  iframe ◀── MediaMTX WebRTC :8889  (원본 cam01 / AI cam01_ai 토글)
[탐지 이미지]  <img src="/image/events/<id>/thumb.jpg"> ──▶ 자체 프록시 ──▶ MinIO get_object
```

- **이미지 프록시**: 브라우저는 MinIO에 직접 붙지 않고 대시보드의 `GET /image/<image_key>`를 호출 → 서버가 MinIO에서 받아 `image/jpeg`로 스트리밍.
- **영상 토글**: `MEDIA_URL`(원본, `…/cam01/`)에서 경로만 바꿔 AI URL(`…/cam01_ai/`)을 파생. 버튼으로 iframe 전환.

---

## 3. 구성 / 주요 파일

```
dashboard/
├── README.md            # 본 문서
├── dashboard_app.py     # Flask 앱 (NATS 구독 + /events 로드 + /image 프록시 + 단일 HTML 템플릿)
├── send_nats_test.py    # 테스트용 NATS 메시지 발행 스크립트
├── requirements.txt     # flask + nats-py + minio
└── .env.example         # 환경변수 템플릿 (MINIO_SECRET_KEY 중심)
```

주요 라우트:
- `GET /` — 대시보드 페이지
- `GET /messages` — 현재 이벤트 목록(JSON, 프론트가 3초마다 polling)
- `GET /image/<path:image_key>` — MinIO 프레임 프록시
- `POST /set-media-url` — MediaMTX URL 변경

---

## 4. 사전 준비

### 4.1 환경
- Linux PC (main-server와 동일 호스트)
- Python 3.x

### 4.2 의존성
```bash
cd dashboard
pip install -r requirements.txt   # flask, nats-py, minio
```

### 4.3 인프라 접속
- NATS(4222) / MinIO(9000)에 접근 가능해야 한다 (SSH 터널). 공통 셋업은 [docs/infra-setup.md](../docs/infra-setup.md) 참조.
- 영상은 Vision PC의 MediaMTX(WebRTC 8889)에서 받는다 → `MEDIA_URL`에 **Vision PC의 LAN/공인 IP**를 넣는다 (대시보드 폼에서 입력/저장 가능).

### 4.4 .env 생성
```bash
cp .env.example .env
# MINIO_SECRET_KEY 입력 (이미지 프록시에 필요)
```
대시보드는 `.env`를 자동 로드하지 않는다. `scripts/main_start.sh`가 실행 전 `dashboard/.env`를 source 한다. 단독 실행 시에는 환경변수를 직접 export 한다.

---

## 5. 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NATS_URL` | `nats://127.0.0.1:4222` | NATS endpoint |
| `MAIN_SERVER_URL` | `http://127.0.0.1:8000` | 과거 이벤트 로드용 main-server |
| `MEDIA_URL` | `http://127.0.0.1:8889/cam01/` | MediaMTX 원본 스트림 (AI는 `cam01_ai`로 자동 파생). **trailing slash 필수** |
| `MINIO_ENDPOINT` | `localhost:9000` | 이미지 프록시용 |
| `MINIO_ACCESS_KEY` | `minio_admin` | |
| `MINIO_SECRET_KEY` | (필수) | MinIO 비밀번호 |
| `MINIO_BUCKET` | `capstone2` | Vision이 프레임을 올리는 bucket |
| `MINIO_SECURE` | `false` | dev/내부망 |
| `CAMERA_LOCATIONS` | `{"cam01": "Lab Entrance"}` | (선택) 카메라 ID→위치 라벨 JSON |

---

## 6. 실행

### 6.1 main-server와 함께 (권장)
```bash
./scripts/main_start.sh     # main-server + dashboard 동시 기동
```

### 6.2 단독 실행
```bash
cd dashboard
export MINIO_SECRET_KEY='<MinIO 비밀번호>'
export MEDIA_URL='http://<vision-pc-ip>:8889/cam01/'
python dashboard_app.py     # http://127.0.0.1:5001
```

### 6.3 테스트 메시지 발행 (프로젝트 루트에서)
```bash
python dashboard/send_nats_test.py   # cs.vision.control.detected 샘플 발행
```

---

## 7. 동작 확인 / 예상 결과

브라우저에서 `http://127.0.0.1:5001` 접속:
- 상단에 `NATS: connected` 표시.
- **영상 불러오기** 버튼 → 카메라 영상 표시. 영상 우하단 **원본/AI 토글**로 박스 없는 영상 ↔ bbox 오버레이 영상 전환.
- 탐지 발생 시 오른쪽에 카드 생성:
  - 라이브 이벤트: 객체/confidence/bbox + thumb.jpg(+오버레이) + (잠시 뒤) LLM 요약
  - 과거 이벤트(`/events` 로드): 이미지 + 메타데이터 (객체 배열 없어 bbox 오버레이는 없음 — 정상)
- 이미지 프록시 단독 확인:
  ```bash
  curl -I "http://127.0.0.1:5001/image/events/<event_id>/thumb.jpg"   # 200 + image/jpeg
  ```

---

## 8. 문제 해결

| 증상 | 원인 / 조치 |
|------|------------|
| 영상이 안 뜸 | `MEDIA_URL`은 **trailing slash 필수**(`/cam01/`). Vision PC IP·포트(8889) 도달성 확인 |
| 토글했는데 AI 영상이 없음 | Vision이 `cam01_ai`를 발행 중인지 확인 (`STREAM_ENABLED=true`, ffmpeg 2채널) |
| 이미지 자리에 "탐지 이미지 미수신" | payload에 `image_key`가 없거나, 프록시가 MinIO를 못 받음 → 아래 프록시 오류 참고 |
| `/image/...` 503 | `minio` 패키지 미설치 → `pip install -r requirements.txt` |
| `/image/...` 404 | `MINIO_SECRET_KEY` 미설정 / bucket·key 불일치 |
| `NATS: disconnected` | NATS 터널(4222) 미연결 → 터널 확인 |
| 과거 이벤트가 안 채워짐 | main-server(`/events`) 미기동 또는 `MAIN_SERVER_URL` 오류 |

---

## 9. 참고 문서

- NATS 메시지 계약: [docs/nats-schema.md](../docs/nats-schema.md)
- DB 스키마: [docs/db-schema.md](../docs/db-schema.md)
- 인프라(VM/SSH 터널/포트) 셋업: [docs/infra-setup.md](../docs/infra-setup.md)
