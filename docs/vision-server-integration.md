# Vision Server Integration Guide

본 문서는 **vision-server** 담당자가 main-server / NATS / MinIO와 통합할 때 참조하는 안내서다.
설계 원본은 [`docs/main-server-design.md`](./main-server-design.md) §2, NATS 명세는 [`docs/nats-schema.md`](./nats-schema.md), DB 스키마는 [`docs/db-schema.md`](./db-schema.md)에 있다.

---

## 1. Vision Server 책임

| 책임 | 출력 |
|------|------|
| 카메라/영상 입력 → MediaMTX로 publish | 실시간 video stream |
| 객체 탐지 (YOLO 등) | 탐지 결과 |
| 탐지 프레임을 MinIO에 업로드 | `image_key` |
| `cs.vision.control.detected` NATS 발행 | event payload (`image_key` 포함) |

main-server는 NATS 메시지를 수신만 한다. **Vision Server는 main-server URL을 알 필요 없다.**

---

## 2. 환경 셋업 (Windows + GPU 기준)

NATS와 MinIO는 VM에 떠 있다. Vision Server PC에서 접근하려면 두 가지 방법.

### 2-1. SSH 터널 (권장)

main-server / dashboard 환경과 동일한 방식. 운영 환경 변경 시 코드 수정 불필요.

```powershell
# Windows PowerShell 또는 WSL
ssh -fN -L 4222:localhost:4222 -L 9000:localhost:9000 ubuntu@<VM_IP> -i <path-to>\keypairsw.pem
```

> `VM_IP`와 `keypairsw.pem`은 main-server 담당자에게 받는다.

Vision Server 코드:

```python
NATS_URL = "nats://localhost:4222"
MINIO_ENDPOINT = "localhost:9000"
```

### 2-2. VM 직접 (대안)

VM 인스턴스의 4222 / 9000 포트가 외부에서 열려 있어야 한다. (현재 VM ufw는 inactive이고 NATS/MinIO는 `0.0.0.0`에서 listen 중이라 OS 수준에서는 허용 — 클라우드 Security Group은 별도 확인 필요)

```python
NATS_URL = "nats://<VM_IP>:4222"
MINIO_ENDPOINT = "<VM_IP>:9000"
```

연결 확인 (Windows PowerShell):

```powershell
Test-NetConnection -ComputerName <VM_IP> -Port 4222
# TcpTestSucceeded : True 가 나와야 함
```

---

## 3. NATS 발행 계약

**Subject:** `cs.vision.control.detected`

**Stream:** `CAPSTONE_EVENTS` (main-server가 startup 시 자동 생성)

**전체 명세는 [`docs/nats-schema.md`](./nats-schema.md) §1 참조.** 핵심만 발췌:

```json
{
  "event_id": "evt_0001",
  "camera_id": "cam01",
  "event_type": "person_detected",
  "source": "vision",
  "timestamp": "2026-05-20T15:30:00+09:00",
  "data": {
    "object_count": 2,
    "max_confidence": 0.95,
    "image_key": "events/evt_0001/thumb.jpg",
    "objects": [
      {
        "class_name": "person",
        "confidence": 0.95,
        "bbox": [100, 200, 50, 100],
        "track_id": null
      }
    ]
  }
}
```

**필수 규칙:**

- `event_id`: Vision이 생성. UUID나 `evt_<random>` 형식 권장. 중복 발행되면 main-server가 `ON CONFLICT DO NOTHING`으로 무시 (idempotent).
- `camera_id`: **반드시 `cameras` 테이블에 미리 등록된 ID여야 함** — 미등록이면 main-server가 NAK 5회 후 DLQ로 보냄. §5 참조.
- `timestamp`: ISO 8601 + KST (`+09:00`)
- `bbox`: `[x, y, width, height]` (정수, 픽셀)
- `image_key`: §4 참조

---

## 4. MinIO 업로드 계약

탐지된 프레임은 Vision Server가 MinIO에 직접 업로드한다. main-server는 `image_key` 문자열만 받아서 저장하고 이미지 바이너리는 만지지 않는다.

### 4-1. `image_key` 패턴

```
events/<event_id>/thumb.jpg
```

main-server-design.md §12에 명시된 패턴. 예: `events/evt_0001/thumb.jpg`

### 4-2. MinIO 접속 정보

| 항목 | 값 |
|------|-----|
| Endpoint | `localhost:9000` (SSH 터널) or `<VM_IP>:9000` |
| Access Key | `minio_admin` (env `MINIO_ROOT_USER`) |
| Secret Key | main-server 담당자에게 받음 (env `MINIO_ROOT_PASSWORD`) |
| Use SSL | `False` (dev/내부망) |

### 4-3. Bucket 이름

> ⚠️ **TBD** — bucket 이름이 아직 docs에 명시되지 않음. main-server 담당자에게 확인 필요. (후보: `cctv-events`, `capstone-events` 등)

### 4-4. Python 예제 (minio-py 사용)

```python
from minio import Minio

client = Minio(
    "localhost:9000",
    access_key="minio_admin",
    secret_key="<password>",
    secure=False,
)

bucket = "cctv-events"  # TBD
event_id = "evt_0001"
object_name = f"events/{event_id}/thumb.jpg"

# 이미지를 파일로 저장 후 업로드
client.fput_object(bucket, object_name, "/tmp/thumb.jpg", content_type="image/jpeg")

# 또는 메모리(bytes)에서 바로 업로드
from io import BytesIO
img_bytes = ...  # YOLO 탐지 후 cv2.imencode 등으로 만든 bytes
client.put_object(
    bucket,
    object_name,
    data=BytesIO(img_bytes),
    length=len(img_bytes),
    content_type="image/jpeg",
)
```

---

## 5. camera_id 등록 요구사항

main-server는 미등록 `camera_id`로 들어온 이벤트를 거부한다. 새 카메라는 **DB에 먼저 insert**해야 한다.

### 5-1. 현재 등록된 카메라

API로 확인:

```bash
curl http://127.0.0.1:8000/events?limit=1 | jq '.[].camera_id'
```

현재 `cam01` 1개 등록되어 있음. 테스트는 이걸로 가능.

### 5-2. 신규 카메라 등록 (SQL 직접)

`cameras` 테이블 스키마 (infra/postgres/init.sql):

```sql
CREATE TABLE cameras (
    camera_id    VARCHAR(64)  PRIMARY KEY,
    name         VARCHAR(128) NOT NULL,
    location     VARCHAR(256),
    stream_url   VARCHAR(512),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

Insert 예:

```sql
INSERT INTO cameras (camera_id, name, location, stream_url)
VALUES ('cam02', '로비 1번 카메라', '본관 1층 로비', 'rtsp://mediamtx:8554/cam02');
```

main-server에는 `/cameras` 등록 API가 아직 없다 (MVP 범위 외). 임시로 main-server 담당자에게 등록 요청하면 된다.

---

## 6. 샘플 발행 코드

작동 확인된 발행 예제는 [`dashboard/send_nats_test.py`](../dashboard/send_nats_test.py)에 있다. 참고용으로 그대로 복사해서 시작점으로 써도 된다.

핵심 발행 코드:

```python
import asyncio
import json
from datetime import datetime, timedelta, timezone

from nats.aio.client import Client as NATS

KST = timezone(timedelta(hours=9))


async def publish_detection(event_id: str, camera_id: str, image_key: str, objects: list):
    nc = NATS()
    await nc.connect("nats://localhost:4222")

    payload = {
        "event_id": event_id,
        "camera_id": camera_id,
        "event_type": "person_detected",
        "source": "vision",
        "timestamp": datetime.now(KST).isoformat(),
        "data": {
            "object_count": len(objects),
            "max_confidence": max((o["confidence"] for o in objects), default=0.0),
            "image_key": image_key,
            "objects": objects,
        },
    }

    await nc.publish(
        "cs.vision.control.detected",
        json.dumps(payload).encode("utf-8"),
    )
    await nc.flush()
    await nc.close()
```

---

## 7. 로컬 통합 테스트 흐름

main-server 담당자 환경에서 검증된 흐름:

1. **SSH 터널 확인** — `ss -tlnp | grep -E ':(4222|9000)\s'`
2. **main-server 실행** — `cd main-server && .venv/bin/python -m uvicorn app.main:app --port 8000`
3. **dashboard 실행** (선택) — `cd dashboard && .venv/bin/python dashboard_app.py` → http://127.0.0.1:5001
4. **Vision Server에서 publish**
5. **확인 포인트**:
   - main-server 로그: `vision saved event_id=... camera_id=... inserted=True`
   - API: `curl http://127.0.0.1:8000/events?limit=5` → 새 이벤트 포함
   - dashboard 화면: 메시지 카운트 증가 + payload 표시
   - 중복 발행 시 main-server `inserted=False` + dashboard 카운트 그대로

**확인된 사항 (2026-05-20):**
- `evt_dashboard_test_001` 발행 → 전체 흐름 통과 + 중복 처리 OK
- DLQ 동작: 미등록 camera_id → NAK 5회 → `CAPSTONE_DLQ` stream으로 이동 + `inserted=True`/`False` ack

---

## 8. 미정 / 후속 이슈

| 항목 | 상태 | 비고 |
|------|------|------|
| MediaMTX infra 추가 | ❌ 미배포 | Vision Server publish 대상. 별도 docker-compose 추가 필요 |
| MinIO bucket 이름 | ❌ docs 미명시 | main-server 담당자에게 확인 |
| `/cameras` 등록 API | ❌ MVP 범위 외 | 신규 카메라는 SQL insert |
| MinIO presigned URL API | ❌ MVP 범위 외 | dashboard가 이미지 직접 표시 필요해지면 추가 |
| event_type 표준화 | ⚠️ 협의 필요 | 현재 `person_detected`만 사용. `intrusion`, `loitering` 등 추가 시 합의 |

---

## 9. 빠른 참조

| 항목 | 값 |
|------|-----|
| NATS Subject | `cs.vision.control.detected` |
| NATS Stream | `CAPSTONE_EVENTS` (자동 생성) |
| NATS URL (터널) | `nats://localhost:4222` |
| MinIO Endpoint (터널) | `localhost:9000` |
| image_key 패턴 | `events/<event_id>/thumb.jpg` |
| 현재 등록 카메라 | `cam01` |
| 명세 문서 | [nats-schema.md](./nats-schema.md), [db-schema.md](./db-schema.md), [main-server-design.md](./main-server-design.md) |
| 샘플 코드 | [dashboard/send_nats_test.py](../dashboard/send_nats_test.py) |

---

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-20 | 초안 작성 (main-server + dashboard 라이브 검증 완료 시점 기준) |
