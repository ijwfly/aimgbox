from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "AIMG_"}

    # Database
    database_url: str = "postgresql://aimg:aimg@localhost:5432/aimg"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # S3 / MinIO
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "aimg"
    s3_presign_ttl: int = 3600

    # Auth
    jwt_secret: str
    encryption_key: str

    # Worker
    worker_concurrency: int = 5
    worker_recovery_interval: int = 60

    # Rate limiting
    user_rate_limit_jobs_per_hour: int = 60

    # Localization
    default_language: str = "en"

    # Logging
    log_level: str = "INFO"

    # Admin
    admin_session_secret: str
    admin_port: int = 8001
