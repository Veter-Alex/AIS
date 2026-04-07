-- Базовая AI-схема для будущего RAG (без pgvector на стартовом этапе)
--
-- Почему без pgvector сейчас:
-- 1) это снижает порог входа;
-- 2) все можно применить на стандартном postgres:15;
-- 3) позже добавим отдельную миграцию для vector-типа и индексов.

CREATE SCHEMA IF NOT EXISTS ai;

-- Документы/сущности, из которых строится retrieval-контекст.
-- В вашем кейсе это в основном записи о судах.
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

-- Текстовые фрагменты (chunks), по которым потом будет поиск.
-- embedding пока храним как массив чисел, чтобы не зависеть от pgvector.
-- Когда перейдете на pgvector, это поле заменим на vector(N).
CREATE TABLE IF NOT EXISTS ai.chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES ai.documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    token_count INT,
    embedding DOUBLE PRECISION[],
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

-- Служебная таблица джобов ingestion/обновления индекса.
CREATE TABLE IF NOT EXISTS ai.ingestion_jobs (
    id BIGSERIAL PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

-- Полезные индексы для базовой эксплуатации.
CREATE INDEX IF NOT EXISTS idx_ai_documents_source ON ai.documents(source_table, source_pk);
CREATE INDEX IF NOT EXISTS idx_ai_documents_updated_at ON ai.documents(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_chunks_document ON ai.chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_ai_ingestion_jobs_status ON ai.ingestion_jobs(status, created_at DESC);
