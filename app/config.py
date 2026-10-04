"""Application configuration loaded from environment variables (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    """Base configuration shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    DEBUG = os.environ.get("FLASK_ENV", "development") == "development"

    # --- Database -----------------------------------------------------------
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_NAME = os.environ.get("DB_NAME", "document_tracking")
    DB_USER = os.environ.get("DB_USER", "dts_user")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

    # --- Sessions & security ------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Enable in production behind HTTPS (SESSION_COOKIE_SECURE=1).
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours

    # --- Uploads ------------------------------------------------------------
    UPLOAD_FOLDER = os.path.join(BASE_DIR, os.environ.get("UPLOAD_FOLDER", "app/static/uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "10")) * 1024 * 1024
    ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "txt", "csv"}

    @staticmethod
    def db_config():
        """Connection kwargs for mysql.connector.connect()."""
        return {
            "host": Config.DB_HOST,
            "port": Config.DB_PORT,
            "user": Config.DB_USER,
            "password": Config.DB_PASSWORD,
            "database": Config.DB_NAME,
            "autocommit": False,  # explicit COMMIT/ROLLBACK everywhere
            "charset": "utf8mb4",
        }


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    """Used by the offline unit tests (no MySQL server required)."""

    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret-key"
    DB_NAME = "document_tracking_test"
    # Use a throwaway uploads directory during tests.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "tests", "_test_uploads")


class ProductionConfig(Config):
    DEBUG = False

    def __init__(self):
        if not os.environ.get("SECRET_KEY") or "change-me" in os.environ.get(
            "SECRET_KEY", ""
        ):
            raise RuntimeError(
                "Refusing to start production with an insecure SECRET_KEY."
            )
