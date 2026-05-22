# LLM Server with NATS

이미지를 LLaVA 모델로 분석한 뒤, 분석 결과를 정해진 JSON 형식으로 변환하여 Main Server로 NATS 메시지를 전송하는 LLM 서버입니다.

## 시스템 구조

```text
Vision/Camera
      ↓
LLM Server (FastAPI)
      ↓
Image Analysis (LLaVA)
      ↓
NATS Publish
      ↓
Main Server
      ↓
DB / Dashboard
```

## 구성

- `app.py` : FastAPI 기반 LLM 서버
- `llm_client.py` : LLaVA 이미지 분석 요청
- `nats_publisher.py` : 분석 결과를 NATS로 publish
- `nats_subscriber.py` : NATS 메시지 수신 테스트용 subscriber
- `main.py` : 단일 이미지 분석 demo 실행 파일
- `test.jpg` : 테스트용 이미지

## 기능

- `/analyze` API 요청 처리
- 이미지 분석
- 영어 상황 요약 생성
- NATS 메시지 publish
- Main Server에서 subscribe 가능한 JSON 메시지 전송

## 실행 방법

### 1. NATS 서버 실행

```bash
nats-server.exe
```

### 2. Subscriber 실행

```bash
python nats_subscriber.py
```

### 3. LLM 서버 실행

```bash
uvicorn app:app --reload
```

서버 실행 후 브라우저에서 접속합니다.

```text
http://127.0.0.1:8000/docs
```

## `/analyze` 요청 예시

```json
{
  "image_path": "test.jpg",
  "event_id": "evt_0001",
  "camera_id": "cam01"
}
```

## LLM Server 응답 결과

```json
{
  "status": "success",
  "message": {
    "event_id": "evt_0001",
    "camera_id": "cam01",
    "source": "llm",
    "timestamp": "2026-05-22T12:51:13.496654+09:00",
    "data": {
      "model_name": "llava:7b",
      "summary": "People walking across a busy street in a bustling urban area."
    }
  }
}
```

## NATS 메시지 형식

```json
{
  "event_id": "evt_0001",
  "camera_id": "cam01",
  "source": "llm",
  "timestamp": "2026-05-22T12:51:13.496654+09:00",
  "data": {
    "model_name": "llava:7b",
    "summary": "People walking across a busy street in a bustling urban area."
  }
}
```

Subscriber에서 동일한 JSON 메시지가 출력되면 LLM Server에서 Main Server로 NATS 메시지 전송이 정상적으로 동작한 것입니다.
