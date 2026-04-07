-- Этап 3: переход на размерность реальной embedding-модели.
--
-- Раньше в прототипе использовался vector(64) для локального hash-embedding.
-- Для real embeddings через fastembed используем размерность 384.
--
-- Важно: колонка embedding_vec является производной от исходных данных,
-- поэтому ее безопасно пересоздать и затем заново заполнить через ingestion.

DROP INDEX IF EXISTS idx_ai_chunks_embedding_vec;

ALTER TABLE ai.chunks
DROP COLUMN IF EXISTS embedding_vec;

ALTER TABLE ai.chunks
ADD COLUMN embedding_vec vector(384);

CREATE INDEX IF NOT EXISTS idx_ai_chunks_embedding_vec
ON ai.chunks USING ivfflat (embedding_vec vector_cosine_ops)
WITH (lists = 50);
