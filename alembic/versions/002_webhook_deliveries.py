"""Webhook deliveries table + external_transaction_id on credit_transactions

Revision ID: 002
Revises: 001
Create Date: 2026-02-22
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE webhook_deliveries (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id  UUID NOT NULL REFERENCES integrations(id),
            job_id          UUID NOT NULL REFERENCES jobs(id),
            event           TEXT NOT NULL,
            payload         JSONB NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            attempts        INT NOT NULL DEFAULT 0,
            last_status_code INT,
            last_error      TEXT,
            next_retry_at   TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_wd_job_id ON webhook_deliveries(job_id)")
    op.execute("""
        CREATE INDEX idx_wd_pending_retry ON webhook_deliveries(next_retry_at)
        WHERE status = 'pending'
    """)

    op.execute("""
        ALTER TABLE credit_transactions
        ADD COLUMN external_transaction_id TEXT
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_ct_external_txn
        ON credit_transactions(user_id, external_transaction_id)
        WHERE external_transaction_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ct_external_txn")
    op.execute("ALTER TABLE credit_transactions DROP COLUMN IF EXISTS external_transaction_id")
    op.execute("DROP TABLE IF EXISTS webhook_deliveries CASCADE")
