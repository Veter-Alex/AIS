// Контракты фронтенда для AI-endpoints.
//
// Рекомендации по стилю:
// - имена интерфейсов повторяют backend-схемы, чтобы было проще трассировать API;
// - nullable-поля отмечаются явно, чтобы UI корректно рендерил fallback-значения;
// - для retrieval mode используем union-тип вместо string, чтобы избежать опечаток.
export interface LlmModelInfo {
  // Полное имя модели в Ollama, например: qwen2.5:3b
  name: string;
  // Размер blob'а модели в байтах.
  size_bytes: number;
  modified_at: string | null;
  format: string | null;
  family: string | null;
  parameter_size: string | null;
  quantization_level: string | null;
}

export interface LlmRuntimeResponse {
  provider: string;
  configured_model: string;
  available_models: string[];
  available_models_info: LlmModelInfo[];
  configured_model_quantization: string | null;
  ollama_reachable: boolean;
  error: string | null;
}

export interface RagSource {
  // Технические идентификаторы источника chunk'а.
  chunk_id: number;
  document_id: number;
  // Заголовок документа-источника (обычно имя судна).
  title: string;
  source_table: string;
  source_pk: string;
  chunk_index: number;
  distance: number | null;
  score: number | null;
  // Короткий релевантный фрагмент текста из chunk'а.
  snippet: string;
}

export interface RagAnswerRequest {
  question: string;
  top_k: number;
  // exact применяется для точного поиска по IMO/MMSI.
  retrieval_mode: "hybrid" | "vector" | "lexical" | "exact";
  max_distance?: number;
  llm_provider: string;
  llm_model: string;
}

export interface RagAnswerResponse {
  question: string;
  retrieval_mode: string;
  llm_provider: string;
  llm_model: string;
  answer: string;
  used_chunks: number;
  sources: RagSource[];
}

export interface RetrievalCandidate {
  chunk_id: number;
  document_id: number;
  chunk_index: number;
  title: string;
  source_pk: string;
  // Полный текст chunk'а может возвращаться для diagnostics-экрана.
  content?: string;
  distance?: number | null;
  lexical_score?: number | null;
  _score?: number | null;
  document_flag?: string | null;
  document_general_type?: string | null;
  document_imo?: string | null;
  document_mmsi?: string | null;
}

export interface RetrievalDiagnosticsRequest {
  question: string;
  retrieval_mode: "hybrid" | "vector" | "lexical" | "exact";
  top_k: number;
  candidate_limit: number;
  max_distance?: number;
}

export interface RetrievalDiagnosticsResponse {
  question: string;
  retrieval_mode_requested: string;
  retrieval_mode_used: string;
  candidate_limit: number;
  distance_filter_applied: boolean;
  retrieved_count_before_distance: number;
  retrieved_count_after_distance: number;
  distance_filtered_out: number;
  reranked_count: number;
  final_count: number;
  candidates: RetrievalCandidate[];
  reranked: RetrievalCandidate[];
  final: RetrievalCandidate[];
}
