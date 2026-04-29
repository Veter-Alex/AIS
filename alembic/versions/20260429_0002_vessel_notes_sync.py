"""Add vessel notes and sync metadata.

Revision ID: 0002_vessel_notes_sync
Revises: 0001_initial
Create Date: 2026-04-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_vessel_notes_sync"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vessel_notes (
            id BIGSERIAL PRIMARY KEY,
            note_uuid VARCHAR(64) NOT NULL UNIQUE,
            vessel_id INTEGER NOT NULL REFERENCES vessels(id) ON DELETE CASCADE,
            body TEXT NOT NULL,
            author VARCHAR(120),
            source_node VARCHAR(120) NOT NULL DEFAULT 'local',
            sync_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vessel_notes_vessel_id ON vessel_notes(vessel_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vessel_notes_updated_at ON vessel_notes(updated_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vessel_notes;")
