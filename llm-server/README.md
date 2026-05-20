# LLM Image Analysis with NATS

이미지를 LLM으로 분석한 뒤, 분석 결과를 JSON 형식으로 변환하여 NATS 메시지로 publish/subscribe 하는 프로젝트입니다.

## 구성

- `main.py` : 이미지 분석 실행 및 NATS 메시지 생성
- `llm_client.py` : LLM 이미지 분석 요청
- `nats_publisher.py` : 분석 결과를 NATS로 publish
- `nats_subscriber.py` : NATS 메시지 subscribe 및 출력
- `test.jpg` : 테스트용 이미지

## 기능

- 이미지 입력
- LLM 기반 상황 요약 생성
- JSON 메시지 생성
- NATS publish
- NATS subscribe

## NATS 메시지 형식

```json
{
  "event_id": "evt_0001", # 분석 대상 이벤트 ID
  "camera_id": "cam01", # 카메라 ID
  "source": "llm", # 고정값 "llm"
  "timestamp": "2026-03-23T15:30:02+09:00", # 분석 완료 시각
  "data": {
    "model_name": "llava:7b", # 사용된 모델명
    "summary": "A person appears to be entering the monitored area." # 상황 요약 (자연어)
  }
}
```

## 실행 순서

### 1. NATS 서버 실행

```bash
nats-server.exe
```

### 2. Subscriber 실행

```bash
python nats_subscriber.py
```

### 3. Main 실행

```bash
python main.py
```

## 실행 결과

### Main 실행 결과

```text
NATS 전송 메시지:
{
  "event_id": "evt_0001",
  "camera_id": "cam01",
  "source": "llm",
  "timestamp": "2026-05-20T13:00:13.255713+09:00",
  "data": {
    "model_name": "ministral-3:latest",
    "summary": "도로는 주행 중인 차량과 버스, 그리고 횡단보도를 건너는 여러 사람이 있는 도시의 활기찬 도로 상황으로, 일부 사람들은 마스크를 쓰고 있다."
  }
}
NATS publish 완료
```

### Subscriber 실행 결과

```text
NATS 메시지 수신:
{
  "event_id": "evt_0001",
  "camera_id": "cam01",
  "source": "llm",
  "timestamp": "2026-05-20T13:00:13.255713+09:00",
  "data": {
    "model_name": "ministral-3:latest",
    "summary": "도로는 주행 중인 차량과 버스, 그리고 횡단보도를 건너는 여러 사람이 있는 도시의 활기찬 도로 상황으로, 일부 사람들은 마스크를 쓰고 있다."
  }
}
```

Subscriber에서 Main이 publish한 JSON 메시지가 동일하게 수신되면 NATS publish/subscribe가 정상적으로 동작한 것입니다.
