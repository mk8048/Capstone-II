# Dashboard / NATS 작업 정리

## 2026-05-22 변경 사항

### `dashboard_app.py` 수정

- DB/main-server `/events` 조회는 우선 보류하고, NATS 실시간 메시지와 카메라 영상 표시 중심으로 재구성했다.
- 화면 배치를 변경했다.
  - 왼쪽: 카메라 영상 영역
  - 오른쪽: 실시간 탐지 이벤트 영역
- MediaMTX 영상은 페이지 로드 시 자동 요청하지 않도록 했다.
  - 초기 iframe 주소는 `about:blank`
  - `영상 불러오기` 버튼을 눌렀을 때만 `MEDIA_URL`을 로드
  - 기존처럼 브라우저 인증 팝업이 바로 뜨는 문제를 피하기 위한 처리
- `/messages` 엔드포인트를 구조화된 JSON 응답으로 변경했다.
  - 기존 단순 문자열 메시지 목록 대신 `events` 배열 반환
  - 프론트는 3초마다 `/messages`를 polling
- NATS 메시지를 `event_id` 기준으로 병합하도록 변경했다.
  - `cs.vision.control.detected` 메시지에서 탐지 정보 수집
  - `cs.llm.control.update` 메시지에서 LLM 요약 수집
  - 같은 `event_id`이면 하나의 이벤트 카드에 합쳐서 표시

### 대시보드에 표시하도록 추가한 항목

- 탐지 시간: payload의 `timestamp`
- 카메라 위치: `CAMERA_LOCATIONS` 환경 변수 또는 기본값 `cam01 -> Lab Entrance`
- 탐지 객체 종류: `data.objects[].class_name`
- confidence: `data.max_confidence` 또는 객체별 confidence 중 최대값
- 탐지 이미지:
  - `data.image_url`이 있으면 이미지 표시
  - `data.image_base64`가 있으면 이미지 표시
  - `data.image_key`만 있으면 placeholder에 key 표시
- bbox 표시:
  - 텍스트로 원본 bbox 표시
  - 이미지가 있으면 bbox 오버레이도 표시
- LLM 요약: `data.summary`
- 원본 NATS payload: 상세 펼침 영역에서 확인 가능

### 확인한 내용

- `python -m py_compile dashboard/dashboard_app.py` 통과
- dashboard `/` 응답 확인
- dashboard `/messages` 응답 확인
- NATS 연결 상태 `connected` 확인
- 샘플 Vision/LLM NATS 메시지를 발행해 이벤트 카드 표시 확인

### 현재 보류한 사항

- main-server DB 연동 기반 과거 이벤트 조회
  - `GET /events` 쪽은 현재 Windows Python `asyncpg`와 Docker Postgres 연결에서 오류가 있어 우선 제외
  - NATS 실시간 표시와 영상 표시를 먼저 안정화하는 방향으로 진행
- MinIO `image_key`를 실제 이미지 URL로 변환하는 기능
  - 현재는 `image_url` 또는 `image_base64`가 payload에 있을 때 실제 이미지 표시 가능
  - `image_key`만 있을 경우 key만 표시

---

## 현재 구현 파일

### `dashboard_app.py`

- Flask 기반 대시보드 웹 앱
- NATS 구독자 역할 수행
- 기본 NATS URL: `nats://127.0.0.1:4222`
- 기본 MediaMTX URL: `http://127.0.0.1:8889/cam01/`
- 수신 subject:
  - `cs.vision.control.detected`
  - `cs.llm.control.update`
- 수신한 NATS 메시지를 메모리에 보관하고 화면에 실시간 표시
- MediaMTX 스트림 URL 입력 폼 제공
- NATS 연결 상태를 화면에 표시

### `send_nats_test.py`

- 테스트용 NATS 메시지 발행 스크립트
- 로컬 NATS에 메시지를 발행해 `dashboard_app.py` 수신 여부 확인 가능
- 실행 시 `cs.vision.control.detected` 메시지 발행

---

## 실행 방법

1. Docker 인프라 실행

```powershell
docker compose up -d
```

2. dashboard 실행

```powershell
python dashboard/dashboard_app.py
```

3. 브라우저 접속

```text
http://127.0.0.1:5001
```

4. NATS 테스트 메시지 발행

```powershell
python dashboard/send_nats_test.py
```

---

## 참고 메시지 형식

### Vision 이벤트 예시

```json
{
  "event_id": "evt_0001",
  "camera_id": "cam01",
  "event_type": "person_detected",
  "source": "vision",
  "timestamp": "2026-05-22T21:00:00+09:00",
  "data": {
    "object_count": 1,
    "max_confidence": 0.88,
    "image_key": "events/evt_0001/thumb.jpg",
    "objects": [
      {
        "class_name": "person",
        "confidence": 0.88,
        "bbox": [100, 120, 80, 180],
        "track_id": null
      }
    ]
  }
}
```

### LLM 이벤트 예시

```json
{
  "event_id": "evt_0001",
  "camera_id": "cam01",
  "event_type": "person_detected",
  "source": "llm",
  "timestamp": "2026-05-22T21:00:02+09:00",
  "data": {
    "model_name": "demo-llm",
    "summary": "사람이 카메라 앞에서 탐지되었습니다.",
    "risk_level": "caution"
  }
}
```

---

## 다음 작업 후보

- 실제 Vision Server payload와 필드명 최종 대조
- `image_key`를 MinIO presigned URL 또는 static URL로 변환
- 카메라 위치 정보를 환경 변수 대신 main-server 또는 설정 파일에서 관리
- bbox 좌표 기준 이미지 해상도 설정 추가
- main-server `/events` DB 조회 오류 해결 후 과거 이벤트 로드 재연동
