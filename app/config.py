import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def resolve_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((BASE_DIR / path).resolve())


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{resolve_path(os.getenv('DATABASE_PATH', 'storage/inventory_intake.db'))}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    WATCH_FOLDER = resolve_path(os.getenv("WATCH_FOLDER", "storage/incoming"))
    PROCESSING_FOLDER = resolve_path(os.getenv("PROCESSING_FOLDER", "storage/processing"))
    REVIEWED_FOLDER = resolve_path(os.getenv("REVIEWED_FOLDER", "storage/reviewed"))
    ERROR_FOLDER = resolve_path(os.getenv("ERROR_FOLDER", "storage/error"))

    EXTRACTION_PROVIDER = os.getenv("EXTRACTION_PROVIDER", "mock")
    WATCHER_ENABLED = os.getenv("WATCHER_ENABLED", "true").lower() == "true"
    FILE_STABILITY_CHECK_INTERVAL = int(os.getenv("FILE_STABILITY_CHECK_INTERVAL", "2"))
    FILE_STABILITY_REQUIRED_PASSES = int(os.getenv("FILE_STABILITY_REQUIRED_PASSES", "2"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
