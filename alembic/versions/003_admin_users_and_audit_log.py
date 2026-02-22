"""Admin users and audit log tables

Revision ID: 003
Revises: 002
Create Date: 2026-02-22
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE admin_users (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'viewer',
            status        TEXT NOT NULL DEFAULT 'active',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE audit_log (
            id            BIGSERIAL PRIMARY KEY,
            admin_user_id UUID REFERENCES admin_users(id),
            action        TEXT NOT NULL,
            entity_type   TEXT NOT NULL,
            entity_id     UUID,
            details       JSONB NOT NULL DEFAULT '{}',
            ip_address    INET,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id)")
    op.execute("CREATE INDEX idx_audit_created ON audit_log(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS admin_users CASCADE")
