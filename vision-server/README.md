# vision-server

Camera → YOLO person detection → MinIO upload → NATS publish + MediaMTX live stream.

설계 원본: [docs/main-server-design.md §2](../docs/main-server-design.md), [docs/vision-server-integration.md](../docs/vision-server-integration.md), [docs/nats-schema.md](../docs/nats-schema.md)

---

## 1. 역할

| 책임 | 출력 |
|------|------|
| 카메라/비디오 입력 읽기 | 실시간 frame |
| YOLO 객체 탐지 (person only) | bbox, confidence |
| 탐지 프레임을 MinIO에 업로드 | `events/<event_id>/thumb.jpg` (원본, 무가공) |
| `cs.vision.control.detected` NATS publish | event payload (`image_key` 포함) |
| MediaMTX에 RTSP push (bbox overlay 포함) | `rtsp://localhost:8554/<camera_id>` |

main-server는 NATS 메시지만 수신. **Vision Server는 main-server URL 모름**.

---

## 2. 데이터 흐름

```
[Webcam]
   │
   ▼
[VideoSource] ──▶ [PersonDetector (YOLO+CUDA)]
                       │
                       ├─▶ [FrameUploader] ──▶ MinIO bucket capstone2
                       │                            │
                       ├─▶ [NatsPublisher] ──▶ cs.vision.control.detected
                       │                            │
                       │                            ▼
                       │                       [Main Server DB]
                       │
                       └─▶ [FfmpegRtspPublisher (bbox overlay)]
                                                ▼
                                          [MediaMTX :8554/cam01]
                                                ▼
                                          [Dashboard WebRTC :8889]
```

두 파이프라인(NATS/MinIO, RTSP/MediaMTX)은 독립. 한쪽 실패해도 다른 쪽 계속 동작.

---

## 3. 사전 준비

### 3.1 하드웨어

- NVIDIA GPU (CUDA 지원, 검증된 환경: RTX 3070)
- USB 웹캠 또는 RTSP 카메라 또는 비디오 파일

### 3.2 OS / 도구

- Windows 10/11 (현재 코드는 Windows에 최적화: cv2 DSHOW 백엔드)
- Python 3.12 (pyenv 권장. 3.13은 일부 wheel 미지원 가능)
- winget (Windows 기본 패키지 매니저)

### 3.3 외부 바이너리

```powershell
winget install -e --id Gyan.FFmpeg
winget install -e --id bluenviron.mediamtx
```

설치 후 새 PowerShell 세션을 열면 `ffmpeg` / `mediamtx` 가 PATH에 잡힘.

### 3.4 VM 인프라 (SSH 터널 필요)

main-server 담당자에게 받음 / 확인:
- VM IP, SSH 키 (`keypairsw.pem`)
- MinIO password (= `.env`의 `MINIO_SECRET_KEY`)
- **MinIO bucket `capstone2` 사전 생성 확인** (없으면 첫 frame 업로드 시 `NoSuchBucket` 에러)
- **Postgres `cameras` 테이블에 `<CAMERA_ID>` row 등록 확인** (미등록이면 Main Server가 NAK 5회 후 DLQ로 보냄. 현재 `cam01`은 등록됨)

```powershell
# SSH 터널 — NATS(4222) + MinIO(9000)
ssh -fN -L 4222:localhost:4222 -L 9000:localhost:9000 ubuntu@<VM_IP> -i <pem 경로>
```

확인:
```powershell
Test-NetConnection 127.0.0.1 -Port 4222 -InformationLevel Quiet  # True
Test-NetConnection 127.0.0.1 -Port 9000 -InformationLevel Quiet  # True
```

---

## 4. 셋업

### 4.1 venv + 의존성

```powershell
cd vision-server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt`는 CUDA PyTorch wheel(cu128 index)을 명시. 첫 설치 시 ~3GB.

### 4.2 .env 생성

```powershell
copy .env.example .env
# 편집기로 .env 열어 MINIO_SECRET_KEY를 실제 값으로 바꿈
```

### 4.3 PowerShell 실행 정책 (최초 1회)

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

`start.ps1` 실행 권한 부여. 관리자 권한 불필요.

---

## 5. 실행

### 5.1 한 번에 (권장)

```powershell
cd vision-server
.\start.ps1
```

`start.ps1`은:
1. ffmpeg / mediamtx 경로 자동 resolve
2. 기존 MediaMTX 프로세스 정리
3. MediaMTX 백그라운드 launch (mediamtx.log)
4. RTSP 8554 listen 대기 (최대 5초)
5. Vision Server foreground 실행
6. **Ctrl+C 시 둘 다 cleanup**

### 5.2 수동 (디버깅 시)

```powershell
# 터미널 1: MediaMTX
cd vision-server
mediamtx  # mediamtx.yml 자동 로드

# 터미널 2: Vision Server
cd vision-server
.venv\Scripts\Activate.ps1
python -m app.main
```

### 5.3 종료

`Ctrl+C` 한 번 → Vision Server `KeyboardInterrupt` 잡고 정상 종료 → `start.ps1` finally가 MediaMTX 정리 → 잔여 프로세스 0개.

---

## 6. 동작 확인

### 6.1 콘솔 로그 (정상 패턴)

```
[start] FFMPEG_PATH=...
[start] launching MediaMTX...
[start] MediaMTX ready (RTSP 8554)
[start] starting Vision Server (Ctrl+C to stop both)
[vision] starting camera_id=cam01 source=0 device=cuda
[vision] nats connected url=nats://localhost:4222 ...
[vision] minio target endpoint=localhost:9000 bucket=capstone2
[vision] stream enabled rtsp=rtsp://127.0.0.1:8554/cam01 overlay=True
[stream] ffmpeg started size=640x480 fps=30 bitrate=2500k rtsp=...
[vision] event published event_id=evt_xxxxxxxx objects=N max_conf=0.XX
```

### 6.2 MediaMTX 수신 확인

별도 터미널에서:
```powershell
curl -sI http://127.0.0.1:8889/cam01/
# HTTP/1.1 200 OK 응답
```

또는 브라우저에서 `http://127.0.0.1:8889/cam01/` 직접 열기 → MediaMTX WebRTC 플레이어 + 실시간 영상.

### 6.3 Dashboard 통합 (별도 PC)

main-server PC의 Dashboard에서:
```bash
MEDIA_URL="http://<vision-pc-lan-ip>:8889/cam01/" python dashboard_app.py
```

브라우저로 Dashboard 열면 iframe에 실시간 영상.

**중요**: URL 끝 `/` (trailing slash) 필수. MediaMTX 1.18.2가 `/cam01`은 302 redirect, iframe이 따라가지 않음.

### 6.4 NATS / MinIO 검증

main-server `/events` API에 event_id가 떠야 함. MinIO console (`http://localhost:9001`)의 `capstone2` bucket에 `events/<event_id>/thumb.jpg` 객체 누적.

---

## 7. 모듈 구조

```
vision-server/
├── README.md                  # 본 문서
├── start.ps1                  # 통합 launcher (MediaMTX + Vision Server)
├── mediamtx.yml               # MediaMTX 설정 (paths: all_others)
├── prototype.py               # 단일 이미지 프로토타입 (참고용)
├── requirements.txt           # cu128 PyTorch + ultralytics + nats-py + minio + ...
├── .env.example               # 환경변수 템플릿 (시크릿은 placeholder)
└── app/
    ├── main.py                # async loop orchestration
    ├── config.py              # python-dotenv + dataclass settings
    ├── video_source.py        # cv2.VideoCapture (DSHOW backend on Windows)
    ├── detector.py            # YOLO + person-only filter
    ├── storage.py             # MinIO in-memory JPEG upload
    ├── event_builder.py       # NATS payload + KST timestamp + uuid event_id
    ├── publisher.py           # JetStream persistent publisher
    └── stream_publisher.py    # ffmpeg subprocess + draw_overlay()
```

---

## 8. 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NATS_URL` | `nats://localhost:4222` | NATS JetStream endpoint |
| `NATS_SUBJECT` | `cs.vision.control.detected` | publish subject |
| `CAMERA_ID` | `cam01` | `cameras` 테이블 등록 ID |
| `VIDEO_SOURCE` | `0` | 웹캠 index / 파일 경로 / RTSP URL |
| `MODEL_PATH` | `yolov8n.pt` | Ultralytics 자동 다운로드 |
| `CONF_THRESHOLD` | `0.5` | YOLO confidence min |
| `DEVICE` | `cuda` | `cpu`로 override 가능 |
| `EVENT_COOLDOWN_SECONDS` | `3` | 동일 카메라 연속 publish 최소 간격 |
| `MINIO_ENDPOINT` | `localhost:9000` | SSH 터널 endpoint |
| `MINIO_ACCESS_KEY` | `minio_admin` | |
| `MINIO_SECRET_KEY` | (필수) | main-server `.env`의 `MINIO_ROOT_PASSWORD` |
| `MINIO_BUCKET` | `capstone2` | 사전 생성 필요 (없으면 첫 실행 시 직접 만듦) |
| `MINIO_SECURE` | `false` | dev/내부망 |
| `STREAM_ENABLED` | `true` | MediaMTX 푸시 활성화 |
| `MEDIAMTX_RTSP_URL` | `rtsp://127.0.0.1:8554/cam01` | 로컬 MediaMTX |
| `STREAM_FPS` | `30` | ffmpeg 입력 rate |
| `STREAM_WIDTH` | `0` | 0 = 첫 frame 실측, 양수 = 강제 resize |
| `STREAM_HEIGHT` | `0` | 동일 |
| `STREAM_BITRATE` | `2500k` | libx264 target |
| `STREAM_OVERLAY` | `true` | bbox/conf 라벨 그림 |
| `FFMPEG_PATH` | `ffmpeg` | PATH에 있으면 그대로 / `start.ps1`이 절대경로 override |
| `FFMPEG_LOG_PATH` | (빈 값) | 비면 stderr=DEVNULL, 경로 지정 시 파일로 |

---

## 9. 참고

- 설계: [docs/main-server-design.md](../docs/main-server-design.md), [docs/vision-server-integration.md](../docs/vision-server-integration.md)
- DB 스키마: [docs/db-schema.md](../docs/db-schema.md)
- NATS 메시지: [docs/nats-schema.md](../docs/nats-schema.md)
- 팀 셋업 가이드: [docs/onboarding.md](../docs/onboarding.md)
- 내부 작업 노트: [.ai-notes/handoff.md](.ai-notes/handoff.md) (gitignored)
