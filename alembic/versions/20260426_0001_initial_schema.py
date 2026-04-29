"""Начальная схема: public (vessels, source_priority, scraper_state) + ai.*.

Бывшие init.sql и историческая AI-схема; дальнейшие изменения — новыми
ревизиями Alembic.

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-26

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vessels (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200),
            imo VARCHAR(20),
            mmsi VARCHAR(20) NOT NULL UNIQUE,
            call_sign VARCHAR(20),
            general_type VARCHAR(100),
            detailed_type VARCHAR(100),
            flag VARCHAR(100),
            year_built INTEGER,
            length INTEGER,
            width INTEGER,
            dwt INTEGER,
            gt INTEGER,
            home_port VARCHAR(100),
            photo_url TEXT,
            photo_path TEXT,
            description TEXT,
            info_source VARCHAR(100),
            updated_at TIMESTAMP,
            vessel_key VARCHAR(32)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_vessels_name ON vessels(name);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_vessels_imo ON vessels(imo);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_vessels_flag ON vessels(flag);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vessels_type ON vessels(general_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vessels_source ON vessels(info_source);"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_priority (
            id SERIAL PRIMARY KEY,
            source_name VARCHAR(100) NOT NULL UNIQUE,
            priority INTEGER NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        INSERT INTO source_priority (source_name, priority, description) VALUES
            ('marinetraffic.org', 1,
             'Основной источник - самая полная база данных судов (250,000+ судов)'),
            ('maritime-database.com', 2, 'Общая база данных судов'),
            ('vesselfinder.com', 3,
             'Наиболее детальные данные, фотографии судов'),
            ('myshiptracking.com', 4,
             'Дополнительные данные и фотографии судов'),
            ('marinetraffic.com', 5, 'Резервный источник'),
            ('fleetmon.com', 6, 'Дополнительный источник')
        ON CONFLICT (source_name) DO NOTHING;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scraper_state (
            id SERIAL PRIMARY KEY,
            scraper_name VARCHAR(100) NOT NULL,
            mode VARCHAR(20) NOT NULL,
            last_page INTEGER NOT NULL DEFAULT 1,
            vessels_count INTEGER NOT NULL DEFAULT 0,
            last_run_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(scraper_name, mode)
        );
        """
    )
    op.execute(
        "ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS "
        "scraper_name VARCHAR(100);"
    )
    op.execute(
        "ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS mode VARCHAR(20);"
    )
    op.execute(
        "ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS last_page INTEGER;"
    )
    op.execute(
        "ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS "
        "vessels_count INTEGER;"
    )
    op.execute(
        "ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP;"
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS ai;")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai.documents (
            id BIGSERIAL PRIMARY KEY,
            source_table TEXT NOT NULL,
            source_pk TEXT NOT NULL,
            title TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            content_hash TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_table, source_pk)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai.chunks (
            id BIGSERIAL PRIMARY KEY,
            document_id BIGINT NOT NULL
                REFERENCES ai.documents(id) ON DELETE CASCADE,
            chunk_index INT NOT NULL,
            content TEXT NOT NULL,
            token_count INT,
            embedding DOUBLE PRECISION[],
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, chunk_index)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai.ingestion_jobs (
            id BIGSERIAL PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_documents_source ON "
        "ai.documents(source_table, source_pk);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_documents_updated_at ON "
        "ai.documents(updated_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chunks_document ON "
        "ai.chunks(document_id, chunk_index);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_ingestion_jobs_status ON "
        "ai.ingestion_jobs(status, created_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai.chunks CASCADE;")
    op.execute("DROP TABLE IF EXISTS ai.documents CASCADE;")
    op.execute("DROP TABLE IF EXISTS ai.ingestion_jobs CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS ai CASCADE;")
    op.execute("DROP TABLE IF EXISTS scraper_state;")
    op.execute("DROP TABLE IF EXISTS source_priority;")
    op.execute("DROP TABLE IF EXISTS vessels CASCADE;")
