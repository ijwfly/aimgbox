"""Seed providers, job types, and their linkages.

Replicate API key must be provided via REPLICATE_API_TOKEN env var.
If not set, the replicate provider is created with a placeholder key
and will fail at runtime until updated.

Revision ID: 004
Revises: 003
Create Date: 2026-03-01
"""

import json
import os

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

# Known Replicate model versions (pinned for stability)
_REMOVE_BG_VERSION = (
    "a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc"
)
_SDXL_VERSION = (
    "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"
)


def _get_replicate_key_encrypted() -> str:
    token = os.environ.get("REPLICATE_API_TOKEN", "")
    if not token:
        print(
            "WARNING: REPLICATE_API_TOKEN not set. "
            "Update providers SET api_key_encrypted=... "
            "WHERE slug='replicate' before use."
        )
        return "not-configured"

    encryption_key = os.environ.get("AIMG_ENCRYPTION_KEY", "")
    if not encryption_key:
        print("WARNING: AIMG_ENCRYPTION_KEY not set.")
        return "not-configured"

    from aimg.common.encryption import encrypt_value
    return encrypt_value(token, encryption_key)


def _esc(s: str) -> str:
    """Escape single quotes for SQL string literals."""
    return s.replace("'", "''")


def upgrade() -> None:
    replicate_key = _esc(_get_replicate_key_encrypted())

    # ── Providers ──────────────────────────────────────────

    op.execute(f"""
        INSERT INTO providers
            (slug, name, adapter_class, api_key_encrypted)
        VALUES
            ('replicate', 'Replicate',
             'aimg.providers.replicate.ReplicateAdapter',
             '{replicate_key}')
        ON CONFLICT (slug) DO UPDATE SET
            api_key_encrypted = EXCLUDED.api_key_encrypted,
            updated_at = now()
    """)

    op.execute("""
        INSERT INTO providers
            (slug, name, adapter_class, api_key_encrypted)
        VALUES
            ('mock', 'Mock Provider',
             'aimg.providers.mock.MockProvider',
             'not-needed')
        ON CONFLICT (slug) DO NOTHING
    """)

    op.execute("""
        INSERT INTO providers
            (slug, name, adapter_class, api_key_encrypted)
        VALUES
            ('failing_mock', 'Failing Mock Provider',
             'aimg.providers.failing_mock.FailingMockProvider',
             'not-needed')
        ON CONFLICT (slug) DO NOTHING
    """)

    # ── Job types ──────────────────────────────────────────

    _upsert_job_type(
        slug="remove_bg",
        name="Remove Background",
        description="Removes background from an image using AI",
        input_schema={
            "type": "object",
            "required": ["image"],
            "properties": {
                "image": {"type": "string", "format": "uuid"},
                "output_format": {
                    "type": "string",
                    "enum": ["png", "webp"],
                    "default": "png",
                },
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "image": {"type": "string", "format": "uuid"},
            },
        },
    )

    _upsert_job_type(
        slug="txt2img",
        name="Text to Image",
        description="Generates an image from a text prompt using AI",
        input_schema={
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2000,
                },
                "negative_prompt": {
                    "type": "string",
                    "default": "",
                },
                "width": {
                    "type": "integer",
                    "default": 1024,
                    "minimum": 256,
                    "maximum": 4096,
                },
                "height": {
                    "type": "integer",
                    "default": 1024,
                    "minimum": 256,
                    "maximum": 4096,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["png", "webp", "jpg"],
                    "default": "png",
                },
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "image": {"type": "string", "format": "uuid"},
            },
        },
    )

    _upsert_job_type(
        slug="img2img",
        name="Image to Image",
        description="Edits an image based on a text prompt using AI",
        input_schema={
            "type": "object",
            "required": ["image", "prompt"],
            "properties": {
                "image": {"type": "string", "format": "uuid"},
                "prompt": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2000,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["png", "webp", "jpg"],
                    "default": "png",
                },
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "image": {"type": "string", "format": "uuid"},
            },
        },
    )

    _upsert_job_type(
        slug="test_allfail",
        name="Test All Fail",
        description=(
            "Test handler where all providers intentionally fail"
        ),
        input_schema={
            "type": "object",
            "required": ["image"],
            "properties": {
                "image": {"type": "string", "format": "uuid"},
                "output_format": {
                    "type": "string",
                    "enum": ["png", "webp"],
                    "default": "png",
                },
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "image": {"type": "string", "format": "uuid"},
            },
        },
    )

    # ── Link providers → job types ─────────────────────────

    _link_provider(
        job_type_slug="remove_bg",
        provider_slug="replicate",
        priority=0,
        config_override={
            "model": "851-labs/background-remover",
            "version": _REMOVE_BG_VERSION,
            "sync_mode": True,
            "exclude_params": ["output_format"],
        },
    )

    _link_provider(
        job_type_slug="txt2img",
        provider_slug="replicate",
        priority=0,
        config_override={
            "model": "stability-ai/sdxl",
            "version": _SDXL_VERSION,
        },
    )

    _link_provider(
        job_type_slug="img2img",
        provider_slug="replicate",
        priority=0,
        config_override={
            "model": "prunaai/p-image-edit",
            "input_field": "images",
            "input_as_array": True,
            "exclude_params": ["output_format"],
            "default_params": {
                "aspect_ratio": "match_input_image",
            },
        },
    )

    _link_provider(
        job_type_slug="test_allfail",
        provider_slug="failing_mock",
        priority=0,
        config_override={},
    )


def downgrade() -> None:
    op.execute("DELETE FROM job_type_providers")
    op.execute("""
        DELETE FROM job_types
        WHERE slug IN (
            'remove_bg', 'txt2img', 'img2img', 'test_allfail'
        )
    """)
    op.execute("""
        DELETE FROM providers
        WHERE slug IN ('replicate', 'mock', 'failing_mock')
    """)


# ── Helpers ────────────────────────────────────────────────


def _upsert_job_type(
    slug: str,
    name: str,
    description: str,
    input_schema: dict,
    output_schema: dict,
) -> None:
    inp = _esc(json.dumps(input_schema))
    out = _esc(json.dumps(output_schema))
    op.execute(f"""
        INSERT INTO job_types
            (slug, name, description, input_schema, output_schema)
        VALUES
            ('{slug}', '{_esc(name)}', '{_esc(description)}',
             '{inp}'::jsonb, '{out}'::jsonb)
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            input_schema = EXCLUDED.input_schema,
            output_schema = EXCLUDED.output_schema,
            updated_at = now()
    """)


def _link_provider(
    job_type_slug: str,
    provider_slug: str,
    priority: int,
    config_override: dict,
) -> None:
    cfg = _esc(json.dumps(config_override))
    op.execute(f"""
        INSERT INTO job_type_providers
            (job_type_id, provider_id, priority, config_override)
        SELECT jt.id, p.id, {priority}, '{cfg}'::jsonb
        FROM job_types jt, providers p
        WHERE jt.slug = '{job_type_slug}'
          AND p.slug = '{provider_slug}'
        ON CONFLICT (job_type_id, provider_id) DO UPDATE SET
            priority = EXCLUDED.priority,
            config_override = EXCLUDED.config_override
    """)
