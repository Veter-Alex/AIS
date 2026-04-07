-- Этап 2: подготовка pgvector в существующей ai-схеме.
--
-- Этот скрипт безопасно добавляет vector-расширение и колонку в таблицу chunks.
-- Если extension уже есть, повторный запуск не навредит.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE ai.chunks
ADD COLUMN IF NOT EXISTS embedding_vec vector(64);

-- Индекс для ускорения vector similarity запросов.
-- Для ivfflat обычно нужно заполнить таблицу данными до создания индекса,
-- но на этапе прототипа можно создать заранее.
CREATE INDEX IF NOT EXISTS idx_ai_chunks_embedding_vec
ON ai.chunks USING ivfflat (embedding_vec vector_cosine_ops)
WITH (lists = 50);
