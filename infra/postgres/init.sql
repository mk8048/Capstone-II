-- ============================================================
-- LLM 기반 CCTV 관제 시스템 DB 초기화 스크립트
-- Project: capstone-llm-cctv
-- DB:      PostgreSQL 18
-- Encoding: UTF-8
-- ============================================================

-- ============================================================
-- 1. cameras: 카메라 메타데이터
-- ============================================================
CREATE TABLE IF NOT EXISTS cameras (
    camera_id    VARCHAR(64)  PRIMARY KEY,
    name         VARCHAR(128) NOT NULL,
    location     VARCHAR(256),
    stream_url   VARCHAR(512),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. detection_events: Vision 서버가 발행한 탐지 이벤트
-- ============================================================
CREATE TABLE IF NOT EXISTS detection_events (
    event_id        VARCHAR(64)  PRIMARY KEY,
    camera_id       VARCHAR(64)  NOT NULL REFERENCES cameras(camera_id),
    occurred_at     TIMESTAMPTZ  NOT NULL,
    event_type      VARCHAR(64)  NOT NULL,
    image_key       VARCHAR(512),
    object_count    INTEGER      NOT NULL DEFAULT 0,
    max_confidence  REAL,
    status          VARCHAR(32)  NOT NULL DEFAULT 'created',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_status CHECK (status IN ('created', 'analyzed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON detection_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_camera_id   ON detection_events(camera_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type  ON detection_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_status      ON detection_events(status);

-- ============================================================
-- 3. detected_objects: 이벤트 내 개별 객체
-- ============================================================
CREATE TABLE IF NOT EXISTS detected_objects (
    object_id    BIGSERIAL    PRIMARY KEY,
    event_id     VARCHAR(64)  NOT NULL REFERENCES detection_events(event_id) ON DELETE CASCADE,
    class_name   VARCHAR(64)  NOT NULL,
    confidence   REAL         NOT NULL,
    bbox_x       INTEGER      NOT NULL,
    bbox_y       INTEGER      NOT NULL,
    bbox_width   INTEGER      NOT NULL,
    bbox_height  INTEGER      NOT NULL,
    track_id     VARCHAR(64),
    extra        JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_objects_event_id ON detected_objects(event_id);
CREATE INDEX IF NOT EXISTS idx_objects_track_id ON detected_objects(track_id) WHERE track_id IS NOT NULL;

-- ============================================================
-- 4. llm_analysis: LLM 분석 결과
-- ============================================================
CREATE TABLE IF NOT EXISTS llm_analysis (
    analysis_id          BIGSERIAL    PRIMARY KEY,
    event_id             VARCHAR(64)  NOT NULL REFERENCES detection_events(event_id) ON DELETE CASCADE,
    model_name           VARCHAR(128) NOT NULL,
    summary              TEXT,
    object_state         TEXT,
    action_description   TEXT,
    risk_level           VARCHAR(16),
    recommended_action   TEXT,
    raw_response         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_risk_level CHECK (risk_level IN ('normal', 'caution', 'danger') OR risk_level IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_analysis_event_id   ON llm_analysis(event_id);
CREATE INDEX IF NOT EXISTS idx_analysis_risk_level ON llm_analysis(risk_level);

-- ============================================================
-- Seed data (MVP 테스트용)
-- ============================================================
INSERT INTO cameras (camera_id, name, location, stream_url, is_active)
VALUES
    ('cam01', 'Test Camera 01', 'Lab Entrance', 'samples/penguin1.mp4', TRUE)
ON CONFLICT (camera_id) DO NOTHING;
