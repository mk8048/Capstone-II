from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MAIN_SERVER_PORT: int = 8000
    DATABASE_URL: str
    NATS_URL: str

    NATS_STREAM: str = "CAPSTONE_EVENTS"
    NATS_DLQ_STREAM: str = "CAPSTONE_DLQ"
    NATS_DLQ_SUBJECT: str = "cs.main.dead_letter"
    NATS_VISION_SUBJECT: str = "cs.vision.control.detected"
    NATS_LLM_SUBJECT: str = "cs.llm.control.update"
    NATS_VISION_CONSUMER: str = "main-server-vision"
    NATS_LLM_CONSUMER: str = "main-server-llm"
    NATS_MAX_DELIVER: int = 5
    NATS_ACK_WAIT_SECONDS: int = 30
    NATS_NAK_DELAY_SECONDS: int = 10
    NATS_FETCH_BATCH: int = 10
    NATS_FETCH_TIMEOUT_SECONDS: int = 1


settings = Settings()
