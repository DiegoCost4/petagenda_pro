import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def normalize_database_url(url: str) -> str:
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-petagenda-troque-em-producao")
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'petagenda.db'}")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
