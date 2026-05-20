# DB Schema

본 문서는 **capstone-llm-cctv** 프로젝트의 PostgreSQL 18 데이터베이스 스키마를 정의한다.
실제 생성 스크립트는 `infra/postgres/init.sql`에 있다.

---

## 전체 ER 관계

```
cameras (1) ──┐
              │
              ▼
        detection_events (1) ──┬──▶ detected_objects (N)
                                │
                                └──▶ llm_analysis (N)
```

- 한 카메라에서 여러 이벤트가 발생
- 한 이벤트에 여러 객체가 탐지
- 한 이벤트에 LLM 분석이 여러 번 누적 가능 (재분석 시)

---

## 공통 설계 원칙

| 항목 | 결정 |
|------|------|
| `event_id` 형식 | 문자열 (`VARCHAR(64)`, 예: `evt_0001`) |
| 시간 컬럼 | `TIMESTAMPTZ` (KST `+09:00` 저장) |
| bbox 저장 | `bbox_x, bbox_y, bbox_width, bbox_height` 분리 컬럼 |
| `track_id` | NULL 허용 (MVP에서는 미사용) |
| 이미지 참조 | Vision Server가 저장한 탐지 프레임의 MinIO/object key만 저장 (URL 아님) |
| 확장 필드 | `extra` / `raw_response` 컬럼에 `JSONB`로 저장 |

---

## 1. `cameras`

카메라 메타데이터.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `camera_id` | `VARCHAR(64)` | PK | 카메라 ID (예: `cam01`) |
| `name` | `VARCHAR(128)` | NOT NULL | 카메라 이름 |
| `location` | `VARCHAR(256)` | | 설치 위치 |
| `stream_url` | `VARCHAR(512)` | | Dashboard 재생용 MediaMTX WebRTC URL/path 또는 원본 RTSP URL |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT TRUE | 활성 여부 |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW() | 등록 시각 |

---

## 2. `detection_events`

Vision 서버가 발행한 탐지 이벤트.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `event_id` | `VARCHAR(64)` | PK | 이벤트 ID (예: `evt_0001`) |
| `camera_id` | `VARCHAR(64)` | FK → cameras | 카메라 ID |
| `occurred_at` | `TIMESTAMPTZ` | NOT NULL | 탐지 발생 시각 |
| `event_type` | `VARCHAR(64)` | NOT NULL | `person_detected`, `intrusion`, `loitering` 등 |
| `image_key` | `VARCHAR(512)` | | Vision Server가 저장한 탐지 프레임의 MinIO/object key (예: `events/evt_0001/thumb.jpg`) |
| `object_count` | `INTEGER` | NOT NULL, DEFAULT 0 | 탐지 객체 수 |
| `max_confidence` | `REAL` | | 최고 confidence |
| `status` | `VARCHAR(32)` | NOT NULL, DEFAULT `'created'` | `created` / `analyzed` / `failed` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW() | DB 저장 시각 |

### 인덱스
- `occurred_at DESC` — 최신순 조회
- `camera_id` — 카메라별 필터
- `event_type` — 이벤트 종류별 필터
- `status` — 미분석 이벤트 조회

---

## 3. `detected_objects`

이벤트 내 개별 객체. 한 이벤트에 0~N개.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `object_id` | `BIGSERIAL` | PK | 자동 증가 |
| `event_id` | `VARCHAR(64)` | FK → events, ON DELETE CASCADE | 이벤트 ID |
| `class_name` | `VARCHAR(64)` | NOT NULL | `person`, `car`, `bag` 등 |
| `confidence` | `REAL` | NOT NULL | 0.0 ~ 1.0 |
| `bbox_x` | `INTEGER` | NOT NULL | bbox 좌측 x |
| `bbox_y` | `INTEGER` | NOT NULL | bbox 상단 y |
| `bbox_width` | `INTEGER` | NOT NULL | bbox 너비 |
| `bbox_height` | `INTEGER` | NOT NULL | bbox 높이 |
| `track_id` | `VARCHAR(64)` | NULL 허용 | 추적 ID, MVP에서는 NULL |
| `extra` | `JSONB` | NOT NULL, DEFAULT `{}` | 추가 정보 |

### 인덱스
- `event_id` — 이벤트별 조회
- `track_id` (partial, NOT NULL) — 추적 시 사용

---

## 4. `llm_analysis`

LLM 분석 결과. 한 이벤트에 누적 가능 (재분석 지원).

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `analysis_id` | `BIGSERIAL` | PK | 자동 증가 |
| `event_id` | `VARCHAR(64)` | FK → events, ON DELETE CASCADE | 분석 대상 이벤트 |
| `model_name` | `VARCHAR(128)` | NOT NULL | `llava:7b`, `ministral-3:8b` 등 |
| `summary` | `TEXT` | | 상황 요약 |
| `object_state` | `TEXT` | | 객체 상태 설명 |
| `action_description` | `TEXT` | | 행동 설명 |
| `risk_level` | `VARCHAR(16)` | CHECK | `normal` / `caution` / `danger` / NULL |
| `recommended_action` | `TEXT` | | 권장 대응 |
| `raw_response` | `JSONB` | NOT NULL, DEFAULT `{}` | LLM 원본 응답 (디버깅용) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW() | 분석 시각 |

### 인덱스
- `event_id` — 이벤트별 분석 조회
- `risk_level` — 위험도별 필터

---

## 자주 쓰는 쿼리 예시

### 최신 이벤트 10개
```sql
SELECT e.event_id, e.camera_id, e.occurred_at, e.event_type, e.max_confidence, e.image_key
FROM detection_events e
ORDER BY e.occurred_at DESC
LIMIT 10;
```

### 이벤트 + 객체 + 최신 LLM 분석 한 번에
```sql
SELECT
    e.event_id, e.camera_id, e.occurred_at, e.event_type, e.image_key,
    o.class_name, o.confidence, o.bbox_x, o.bbox_y, o.bbox_width, o.bbox_height,
    a.summary, a.risk_level, a.recommended_action
FROM detection_events e
LEFT JOIN detected_objects o ON o.event_id = e.event_id
LEFT JOIN LATERAL (
    SELECT * FROM llm_analysis
    WHERE event_id = e.event_id
    ORDER BY created_at DESC LIMIT 1
) a ON TRUE
WHERE e.event_id = 'evt_0001';
```

### 아직 LLM 분석 안 된 이벤트
```sql
SELECT event_id, camera_id, occurred_at, event_type
FROM detection_events
WHERE status = 'created'
ORDER BY occurred_at ASC;
```

---

## 향후 확장 시 추가 예상 테이블 (MVP 이후)

| 테이블 | 용도 |
|--------|------|
| `zones` | 위험 구역 polygon 정의 |
| `tracks` | 객체 추적 trajectory |
| `event_summaries` | 시간대별 통계 |
| Vision Server 소유 `detected_frames` | 탐지 프레임 저장 메타데이터. 이미지 바이너리는 MinIO/object storage에 두고 DB에는 object key와 object/bbox 요약 저장 권장 |

이 테이블들은 MVP 완료 후 Alembic 마이그레이션으로 추가한다.

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-05-20 | 실시간 스트림 URL 의미와 Vision Server 탐지 프레임 저장 책임 명시. |
| 2026-05-13 | 초안 확정. `image_url` → `image_key`로 변경. |
