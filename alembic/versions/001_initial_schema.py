"""Initial schema: 11 core tables

Revision ID: 001
Revises:
Create Date: 2026-02-22
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- No-FK tables ---

    op.execute("""
        CREATE TABLE partners (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE providers (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug                TEXT NOT NULL UNIQUE,
            name                TEXT NOT NULL,
            adapter_class       TEXT NOT NULL,
            base_url            TEXT,
            api_key_encrypted   TEXT NOT NULL,
            config              JSONB NOT NULL DEFAULT '{}',
            status              TEXT NOT NULL DEFAULT 'active',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE job_types (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug            TEXT NOT NULL UNIQUE,
            name            TEXT NOT NULL,
            description     TEXT,
            input_schema    JSONB NOT NULL DEFAULT '{}',
            output_schema   JSONB NOT NULL DEFAULT '{}',
            credit_cost     INT NOT NULL DEFAULT 1,
            timeout_seconds INT NOT NULL DEFAULT 300,
            status          TEXT NOT NULL DEFAULT 'active',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # --- FK: partners ---

    op.execute("""
        CREATE TABLE integrations (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            partner_id          UUID NOT NULL REFERENCES partners(id),
            name                TEXT NOT NULL,
            status              TEXT NOT NULL DEFAULT 'active',
            webhook_url         TEXT,
            webhook_secret      TEXT,
            rate_limit_rpm      INT NOT NULL DEFAULT 60,
            default_free_credits INT NOT NULL DEFAULT 10,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_integrations_partner_id ON integrations(partner_id)")

    # --- FK: integrations ---

    op.execute("""
        CREATE TABLE api_keys (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id  UUID NOT NULL REFERENCES integrations(id),
            key_hash        TEXT NOT NULL UNIQUE,
            label           TEXT,
            is_revoked      BOOLEAN NOT NULL DEFAULT false,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at      TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_api_keys_integration_id ON api_keys(integration_id)")
    op.execute("CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash)")

    op.execute("""
        CREATE TABLE users (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id    UUID NOT NULL REFERENCES integrations(id),
            external_user_id  TEXT NOT NULL,
            free_credits      INT NOT NULL DEFAULT 0,
            paid_credits      INT NOT NULL DEFAULT 0,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(integration_id, external_user_id)
        )
    """)
    op.execute(
        "CREATE INDEX idx_users_integration_external ON users(integration_id, external_user_id)"
    )

    # --- FK: job_types, providers ---

    op.execute("""
        CREATE TABLE job_type_providers (
            job_type_id     UUID NOT NULL REFERENCES job_types(id),
            provider_id     UUID NOT NULL REFERENCES providers(id),
            priority        INT NOT NULL DEFAULT 0,
            config_override JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (job_type_id, provider_id)
        )
    """)
    op.execute(
        "CREATE INDEX idx_jtp_job_type_priority ON job_type_providers(job_type_id, priority)"
    )

    # --- FK: integrations, users ---

    op.execute("""
        CREATE TABLE files (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id    UUID NOT NULL REFERENCES integrations(id),
            user_id           UUID REFERENCES users(id),
            s3_bucket         TEXT NOT NULL,
            s3_key            TEXT NOT NULL,
            original_filename TEXT,
            content_type      TEXT NOT NULL,
            size_bytes        BIGINT NOT NULL,
            purpose           TEXT NOT NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_files_integration ON files(integration_id)")

    # --- FK: integrations, users, job_types, providers ---

    op.execute("""
        CREATE TABLE jobs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id  UUID NOT NULL REFERENCES integrations(id),
            user_id         UUID NOT NULL REFERENCES users(id),
            job_type_id     UUID NOT NULL REFERENCES job_types(id),
            status          TEXT NOT NULL DEFAULT 'pending',
            input_data      JSONB NOT NULL,
            output_data     JSONB,
            provider_id     UUID REFERENCES providers(id),
            credit_charged  INT NOT NULL DEFAULT 0,
            error_code      TEXT,
            error_message   TEXT,
            provider_job_id TEXT,
            attempts        INT NOT NULL DEFAULT 0,
            language        TEXT NOT NULL DEFAULT 'en',
            idempotency_key TEXT,
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_jobs_integration_user ON jobs(integration_id, user_id)")
    op.execute("""
        CREATE INDEX idx_jobs_status ON jobs(status)
        WHERE status IN ('pending', 'running')
    """)
    op.execute("CREATE INDEX idx_jobs_created_at ON jobs(created_at)")
    op.execute("""
        CREATE UNIQUE INDEX idx_jobs_idempotency
        ON jobs(integration_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)

    # --- FK: jobs, providers ---

    op.execute("""
        CREATE TABLE job_attempts (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id          UUID NOT NULL REFERENCES jobs(id),
            provider_id     UUID NOT NULL REFERENCES providers(id),
            attempt_number  INT NOT NULL,
            status          TEXT NOT NULL,
            error_code      TEXT,
            error_message   TEXT,
            duration_ms     INT,
            started_at      TIMESTAMPTZ NOT NULL,
            completed_at    TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_ja_job_id ON job_attempts(job_id)")

    # --- FK: users, jobs ---

    op.execute("""
        CREATE TABLE credit_transactions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES users(id),
            amount          INT NOT NULL,
            credit_type     TEXT NOT NULL,
            reason          TEXT NOT NULL,
            job_id          UUID REFERENCES jobs(id),
            admin_user_id   UUID,
            comment         TEXT,
            balance_after   INT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_ct_user_id ON credit_transactions(user_id)")
    op.execute("CREATE INDEX idx_ct_job_id ON credit_transactions(job_id)")
    op.execute("CREATE INDEX idx_ct_created_at ON credit_transactions(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS credit_transactions CASCADE")
    op.execute("DROP TABLE IF EXISTS job_attempts CASCADE")
    op.execute("DROP TABLE IF EXISTS jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS files CASCADE")
    op.execute("DROP TABLE IF EXISTS job_type_providers CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS api_keys CASCADE")
    op.execute("DROP TABLE IF EXISTS integrations CASCADE")
    op.execute("DROP TABLE IF EXISTS job_types CASCADE")
    op.execute("DROP TABLE IF EXISTS providers CASCADE")
    op.execute("DROP TABLE IF EXISTS partners CASCADE")
