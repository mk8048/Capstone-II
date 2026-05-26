# vision-server

카메라 영상에서 사람을 탐지해 **NATS 이벤트 발행 + MinIO 프레임 저장 + MediaMTX 실시간 스트림**을 수행하는 서버. Windows + GPU(YOLO CUDA) 환경 기준.

---

## 1. 역할

| 책임 | 출력 |
|------|------|
| 카메라/비디오 입력 읽기 | 실시간 frame |
| YOLO 객체 탐지 (person only) | bbox, confidence |
| 탐지 프레임을 MinIO에 업로드 | `events/<event_id>/thumb.jpg` (원본, 무가공) |
| `cs.vision.control.detected` NATS 발행 | event payload (`image_key` 포함) |
| MediaMTX에 RTSP 푸시 (원본 + bbox 오버레이 2채널) | `rtsp://localhost:8554/cam01`, `.../cam01_ai` |

main-server는 NATS 메시지만 수신한다. **vision-server는 main-server의 주소를 모른다** (단방향, 느슨한 결합).

---

## 2. 워크플로우

```
[Webcam]
   │
   ▼
[VideoSource] ──▶ [PersonDetector (YOLO + CUDA)]
   │                      │
   │            (사람 탐지 시 · EVENT_COOLDOWN_SECONDS 적용)
   │                      ├──▶ [FrameUploader] ──▶ MinIO  events/<event_id>/thumb.jpg
   │                      └──▶ [NatsPublisher] ──▶ cs.vision.control.detected ──▶ Main Server / LLM Server
   │
   └──(매 프레임)──▶ [ffmpeg × 2] ─┬─▶ rtsp://…/cam01      (원본, 박스 없음)
                                   └─▶ rtsp://…/cam01_ai   (bbox 오버레이)
                                            │
                                            ▼
                                      [MediaMTX :8554] ──▶ WebRTC :8889 ──▶ Dashboard
```

두 파이프라인(**이벤트**: NATS/MinIO, **스트림**: RTSP/MediaMTX)은 독립적이다. 한쪽이 실패해도 다른 쪽은 계속 동작한다.
스트림은 두 채널을 동시에 발행한다 — `cam01`(원본)과 `cam01_ai`(탐지 박스 오버레이). Dashboard에서 둘을 토글로 전환한다.

---

## 3. 구성 / 주요 파일

```
vision-server/
├── README.md                  # 본 문서
├── vision_start.ps1           # 통합 launcher (SSH 터널 + MediaMTX + Vision, 중복 실행 가드)
├── mediamtx.yml               # MediaMTX 설정
├── prototype.py               # 단일 이미지 실험 스크립트 (참고용)
├── requirements.txt           # CUDA PyTorch(cu128) + ultralytics + nats-py + minio + ...
├── .env.example               # 환경변수 템플릿 (시크릿은 placeholder)
└── app/
    ├── main.py                # async 루프 오케스트레이션 (탐지·업로드·발행·스트림)
    ├── config.py              # python-dotenv 기반 설정 로드
    ├── video_source.py        # cv2.VideoCapture (Windows DSHOW 백엔드)
    ├── detector.py            # YOLO + person-only 필터
    ├── storage.py             # MinIO in-memory JPEG 업로드
    ├── event_builder.py       # NATS payload 조립 + KST timestamp + event_id 생성
    ├── publisher.py           # JetStream 발행 (persistent connection)
    └── stream_publisher.py    # ffmpeg subprocess + draw_overlay()
```

---

## 4. 사전 준비

### 4.1 하드웨어
- NVIDIA GPU (CUDA 지원, 검증 환경: RTX 3070)
- USB 웹캠 / RTSP 카메라 / 비디오 파일

### 4.2 OS · 도구
- Windows 10/11 (cv2 DSHOW 백엔드 기준)
- Python 3.12 (3.13은 일부 wheel 미지원 가능)
- winget

### 4.3 외부 바이너리
```powershell
winget install -e --id Gyan.FFmpeg
winget install -e --id bluenviron.mediamtx
```
설치 후 새 PowerShell 세션에서 `ffmpeg` / `mediamtx`가 PATH에 잡힌다.

### 4.4 인프라 (VM) 접속
NATS(4222) / MinIO(9000)는 VM에 있고 SSH 터널로 접근한다. SSH 키, MinIO 비밀번호, bucket·camera 사전 등록 등 공통 인프라 준비는 [docs/infra-setup.md](../docs/infra-setup.md) 참조.

핵심 전제:
- MinIO bucket `capstone2` 사전 생성 (없으면 첫 업로드 시 `NoSuchBucket`)
- Postgres `cameras` 테이블에 `CAMERA_ID` row 등록 (미등록 시 main-server가 NAK 후 DLQ)

### 4.5 venv + 의존성
```powershell
cd vision-server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
`requirements.txt`는 CUDA PyTorch wheel(cu128 index)을 포함한다(첫 설치 ~3GB).

### 4.6 .env 생성
```powershell
copy .env.example .env
# .env 열어 MINIO_SECRET_KEY를 실제 값으로 변경
```

---

## 5. 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NATS_URL` | `nats://localhost:4222` | NATS JetStream endpoint (SSH 터널) |
| `NATS_SUBJECT` | `cs.vision.control.detected` | 발행 subject |
| `CAMERA_ID` | `cam01` | `cameras` 테이블 등록 ID |
| `VIDEO_SOURCE` | `0` | 웹캠 index / 파일 경로 / RTSP URL |
| `MODEL_PATH` | `yolov8n.pt` | Ultralytics 자동 다운로드 |
| `CONF_THRESHOLD` | `0.5` | YOLO confidence 최소값 |
| `DEVICE` | `cuda` | `cpu`로 override 가능 |
| `EVENT_COOLDOWN_SECONDS` | `3` | 연속 이벤트 발행 최소 간격 |
| `MINIO_ENDPOINT` | `localhost:9000` | SSH 터널 endpoint |
| `MINIO_ACCESS_KEY` | `minio_admin` | |
| `MINIO_SECRET_KEY` | (필수) | MinIO 비밀번호 |
| `MINIO_BUCKET` | `capstone2` | 사전 생성 필요 |
| `MINIO_SECURE` | `false` | dev/내부망 |
| `STREAM_ENABLED` | `true` | MediaMTX 푸시 활성화 |
| `MEDIAMTX_RTSP_URL` | `rtsp://127.0.0.1:8554/cam01` | 원본 스트림 (박스 없음) |
| `MEDIAMTX_RTSP_URL_AI` | `rtsp://127.0.0.1:8554/cam01_ai` | AI 스트림 (bbox 오버레이) |
| `STREAM_FPS` | `30` | ffmpeg 입력 rate |
| `STREAM_WIDTH` | `0` | 0 = 첫 frame 실측, 양수 = 강제 resize |
| `STREAM_HEIGHT` | `0` | 동일 |
| `STREAM_BITRATE` | `2500k` | libx264 target |
| `STREAM_OVERLAY` | `true` | AI 스트림에 bbox/confidence 라벨 표시 |
| `FFMPEG_PATH` | `ffmpeg` | PATH에 있으면 그대로 / launcher가 절대경로 override |
| `FFMPEG_LOG_PATH` | (빈 값) | 비면 stderr=DEVNULL. 경로 지정 시 원본은 그 파일, AI는 `*.ai.log` |

---

## 6. 실행

### 6.1 통합 실행 (권장)
```powershell
cd vision-server
.\vision_start.ps1
```
`vision_start.ps1`이 하는 일:
1. 이미 실행 중인 Vision 인스턴스가 있으면 중복 실행 차단
2. SSH 터널(NATS 4222 / MinIO 9000) 확인 후 없으면 자동 기동
3. ffmpeg / mediamtx 경로 자동 resolve
4. 기존 MediaMTX 정리 후 백그라운드 launch (RTSP 8554 listen 대기)
5. LAN IP + Dashboard용 `MEDIA_URL` 출력
6. Vision Server foreground 실행 — **Ctrl+C 시 MediaMTX까지 정리**

실행 정책에 막히면:
```powershell
powershell -ExecutionPolicy Bypass -File .\vision_start.ps1
```

### 6.2 수동 실행 (디버깅)
```powershell
# 터미널 1: MediaMTX
cd vision-server; mediamtx

# 터미널 2: Vision Server
cd vision-server; .venv\Scripts\Activate.ps1; python -m app.main
```

---

## 7. 동작 확인 / 예상 결과

### 7.1 정상 콘솔 로그
```
[start] SSH tunnel already up (NATS 4222 / MinIO 9000)
[start] MediaMTX ready (RTSP 8554)
[start] Vision PC LAN IP: <ip>
[start] MEDIA_URL: http://<ip>:8889/cam01/
[vision] starting camera_id=cam01 source=0 device=cuda
[vision] nats connected url=nats://localhost:4222 subject=cs.vision.control.detected
[vision] minio target endpoint=localhost:9000 bucket=capstone2
[vision] stream enabled raw=rtsp://127.0.0.1:8554/cam01 ai=rtsp://127.0.0.1:8554/cam01_ai overlay=True
[stream] ffmpeg started size=640x480 fps=30 bitrate=2500k rtsp=rtsp://127.0.0.1:8554/cam01
[stream] ffmpeg started size=640x480 fps=30 bitrate=2500k rtsp=rtsp://127.0.0.1:8554/cam01_ai
[vision] event published event_id=evt_xxxxxxxx objects=N max_conf=0.XX
```
스트림 활성화 시 `[stream] ffmpeg started`가 **2줄**(cam01 + cam01_ai) 나오면 정상이다.

### 7.2 스트림 확인
```powershell
curl -sI http://127.0.0.1:8889/cam01/      # HTTP 200 (원본)
curl -sI http://127.0.0.1:8889/cam01_ai/   # HTTP 200 (AI)
```
또는 브라우저에서 `http://127.0.0.1:8889/cam01/` 직접 열기 → 실시간 영상.

### 7.3 이벤트 / 저장 확인
- main-server `GET /events`에 발행한 `event_id`가 나타난다.
- MinIO `capstone2` bucket에 `events/<event_id>/thumb.jpg`가 누적된다.

---

## 8. 문제 해결

| 증상 | 원인 / 조치 |
|------|------------|
| 카메라가 안 열림 / `MF_E_HW_MFT_FAILED_START_STREAMING` | Windows MSMF 이슈. 코드가 DSHOW 백엔드를 강제하므로 대개 회피됨. 다른 앱이 카메라 점유 중인지 확인 |
| 첫 업로드 시 `NoSuchBucket` | MinIO에 `capstone2` bucket 미생성 → 사전 생성 |
| 이벤트가 main-server에 안 보이고 DLQ로 감 | `cameras` 테이블에 `CAMERA_ID` 미등록 → row 추가 |
| `[stream]`/`ffmpeg started` 로그가 없음 | `STREAM_ENABLED=false`이거나 ffmpeg 미설치 → 설치 + env 확인 |
| Dashboard iframe에 영상 안 뜸 | MediaMTX URL은 **trailing slash 필수** (`/cam01/`). `/cam01`은 302 redirect라 iframe이 안 따라감 |
| GPU 미사용 / 느림 | `DEVICE=cuda` 확인, CUDA 드라이버/torch wheel(cu128) 설치 확인 |
| NATS/MinIO 연결 실패 | SSH 터널(4222/9000) 미기동 → launcher 재실행 또는 [docs/infra-setup.md](../docs/infra-setup.md) 확인 |

---

## 9. 참고 문서

- NATS 메시지 계약: [docs/nats-schema.md](../docs/nats-schema.md)
- DB 스키마: [docs/db-schema.md](../docs/db-schema.md)
- 인프라(VM/SSH 터널/포트/bucket/camera) 셋업: [docs/infra-setup.md](../docs/infra-setup.md)
