import base64
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def development_key() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).decode()


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("DATABASE_PATH", "data/social-studio.db"))
    fake_platform_url: str = os.getenv("FAKE_PLATFORM_URL", "http://localhost:9000")
    encryption_key: str = os.getenv("ENCRYPTION_KEY", development_key())
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "development-webhook-secret")
    worker_poll_seconds: float = float(os.getenv("WORKER_POLL_SECONDS", "2"))


settings = Settings()

