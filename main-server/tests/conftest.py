import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_test_env_from_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_test_env_from_dotenv()

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://capstone2:test-password@localhost:5432/capstone2",
)
os.environ.setdefault("NATS_URL", "nats://localhost:4222")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
