import pytest
from pydantic import ValidationError

from aimg.common.settings import Settings

REQUIRED_ENV = {
    "AIMG_S3_ACCESS_KEY": "test-access-key",
    "AIMG_S3_SECRET_KEY": "test-secret-key",
    "AIMG_JWT_SECRET": "test-jwt-secret",
    "AIMG_ENCRYPTION_KEY": "test-encryption-key",
    "AIMG_ADMIN_SESSION_SECRET": "test-admin-session-secret",
}


def test_settings_defaults(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    s = Settings()

    assert s.database_url == "postgresql://aimg:aimg@localhost:5432/aimg"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.s3_endpoint == "http://localhost:9000"
    assert s.s3_bucket == "aimg"
    assert s.s3_presign_ttl == 3600
    assert s.worker_concurrency == 5
    assert s.worker_recovery_interval == 60
    assert s.user_rate_limit_jobs_per_hour == 60
    assert s.default_language == "en"
    assert s.log_level == "INFO"
    assert s.admin_port == 8001


def test_settings_missing_required(monkeypatch):
    # Clear any AIMG_ env vars that might be set
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_override_from_env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setenv("AIMG_DATABASE_URL", "postgresql://custom:pass@db:5432/mydb")
    monkeypatch.setenv("AIMG_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AIMG_WORKER_CONCURRENCY", "10")

    s = Settings()

    assert s.database_url == "postgresql://custom:pass@db:5432/mydb"
    assert s.log_level == "DEBUG"
    assert s.worker_concurrency == 10
