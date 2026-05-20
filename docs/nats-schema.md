# NATS Message Schema

본 문서는 **capstone-llm-cctv** 프로젝트의 NATS 메시지 명세를 정의한다.
모든 서버(Vision / LLM / Main)는 이 문서를 기준으로 메시지를 발행·구독한다.

---

## 공통 규칙

| 항목 | 값 |
|------|-----|
| 메시지 형식 | JSON (UTF-8) |
| 시간 형식 | ISO 8601 + KST (`+09:00`) |
| Subject 네이밍 | `cs.<source>.<channel>.<action>` |
| `event_id` | Vision 탐지부터 LLM 분석까지 **동일 ID 유지** |
| `source` | 메시지 발행 서버 이름 (`vision`, `llm`) |
| 탐지 프레임 | Vision Server가 저장하고, NATS에는 참조용 `image_key`만 포함 |

---

## Subject 목록

| Subject | 발행자 | 구독자 | 용도 |
|---------|--------|--------|------|
| `cs.vision.control.detected` | Vision Server | Main Server, LLM Server | 객체 탐지 이벤트 |
| `cs.llm.control.update`      | LLM Server    | Main Server             | LLM 분석 결과 |

---

## 1. `cs.vision.control.detected`

Vision Server가 객체를 탐지하면 발행한다.
한 프레임에서 여러 객체가 탐지될 수 있으므로 `objects`는 배열로 전송한다.
객체가 탐지된 프레임은 Vision Server가 자체 DB/스토리지에 저장하고, Main Server와 LLM Server는 `data.image_key`로 같은 프레임을 참조한다.

```json
{
  "event_id": "evt_0001",
  "camera_id": "cam01",
  "event_type": "person_detected",
  "source": "vision",
  "timestamp": "2026-03-23T15:30:00+09:00",
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
      },
      {
        "class_name": "bag",
        "confidence": 0.72,
        "bbox": [180, 250, 30, 40],
        "track_id": null
      }
    ]
  }
}
```

### 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `event_id` | string | 이벤트 고유 ID (예: `evt_0001`) |
| `camera_id` | string | 카메라 ID |
| `event_type` | string | `person_detected`, `intrusion`, `loitering` 등 |
| `source` | string | 고정값 `"vision"` |
| `timestamp` | string (ISO 8601 +09:00) | 탐지 발생 시각 |
| `data.object_count` | int | 탐지 객체 수 |
| `data.max_confidence` | float | 최고 confidence (0.0 ~ 1.0) |
| `data.image_key` | string | Vision Server가 저장한 탐지 프레임의 MinIO/object key (예: `events/evt_0001/thumb.jpg`) |
| `data.objects[].class_name` | string | `person`, `car`, `bag` 등 |
| `data.objects[].confidence` | float | 0.0 ~ 1.0 |
| `data.objects[].bbox` | int[4] | `[x, y, width, height]` |
| `data.objects[].track_id` | string \| null | 추적 ID, MVP에서는 `null` |

---

## 2. `cs.llm.control.update`

LLM Server가 이미지 분석을 완료하면 발행한다.
LLM Server는 Vision Server DB/스토리지에 저장된 탐지 프레임을 URL 또는 object key로 가져와 분석한다. Main Server로 보내는 NATS 메시지는 분석 결과와 Vision이 만든 `event_id`를 포함한다.

```json
{
  "event_id": "evt_0001",
  "camera_id": "cam01",
  "source": "llm",
  "timestamp": "2026-03-23T15:30:02+09:00",
  "data": {
    "model_name": "llava:7b",
    "summary": "A person appears to be entering the monitored area."
  }
}
```

### 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `event_id` | string | 분석 대상 이벤트 ID (Vision 메시지와 동일) |
| `camera_id` | string | 카메라 ID |
| `event_type` | string | Optional. LLM이 별도로 판단한 이벤트 유형 |
| `source` | string | 고정값 `"llm"` |
| `timestamp` | string (ISO 8601 +09:00) | 분석 완료 시각 |
| `data.model_name` | string | 사용된 모델명 (예: `llava:7b`, `ministral-3:8b`) |
| `data.summary` | string | 상황 요약 (자연어) |
| `data.object_state` | string | Optional. 객체 상태 설명 |
| `data.action_description` | string | Optional. 행동 설명 |
| `data.risk_level` | string | Optional. `normal` / `caution` / `danger` 중 하나 |
| `data.recommended_action` | string | Optional. 권장 대응 |
| `data.raw_response` | object | Optional. LLM 원본 응답 (디버깅용) |

---

## 예외 / 에러 처리

- LLM 분석 실패 시: `risk_level`을 생략하고 `data.error` 필드를 추가한다.
- 동일 `event_id`로 LLM 결과가 여러 번 올 수 있다 (재분석 시). Main Server는 새로운 `llm_analysis` 행으로 INSERT한다.

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-05-20 | LLM Server가 Vision 저장 프레임을 가져와 분석한 뒤 최소 `model_name`/`summary` 결과를 보낼 수 있도록 LLM payload 명세 수정. |
| 2026-05-20 | Vision Server가 탐지 프레임을 저장하고 NATS에는 `image_key` 참조만 싣는 계약 명시. |
| 2026-05-13 | 초안 확정. `image_url` → `image_key`로 변경 (object key만 저장). `data.objects` 배열 구조 도입. |
