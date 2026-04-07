import axios from "axios";
import type {
  LlmRuntimeResponse,
  RagAnswerRequest,
  RagAnswerResponse,
  RetrievalDiagnosticsRequest,
  RetrievalDiagnosticsResponse,
} from "../types/ai";

// Клиент AI-эндпоинтов.
//
// Весь доступ к /llm, /rag и /retrieve инкапсулирован здесь,
// чтобы страницы/компоненты не знали деталей HTTP-контракта.
// Используем относительные пути, чтобы nginx проксировал запросы
// к ai_agent внутри docker-сети без CORS-настроек на фронтенде.
const api = axios.create({
  baseURL: "",
  headers: {
    "Content-Type": "application/json",
  },
});

export const aiApi = {
  // Получаем доступные локальные модели и активную конфигурацию LLM.
  getRuntime: async (): Promise<LlmRuntimeResponse> => {
    const response = await api.get<LlmRuntimeResponse>("/llm/models", {
      params: { provider: "ollama" },
    });
    return response.data;
  },

  // Выполняем основной RAG-запрос: retrieval + генерация ответа.
  answerQuestion: async (
    payload: RagAnswerRequest,
  ): Promise<RagAnswerResponse> => {
    const response = await api.post<RagAnswerResponse>("/rag/answer", payload);
    return response.data;
  },

  // Получаем детальную диагностику retrieval-пайплайна для UI.
  getDiagnostics: async (
    payload: RetrievalDiagnosticsRequest,
  ): Promise<RetrievalDiagnosticsResponse> => {
    const response = await api.post<RetrievalDiagnosticsResponse>(
      "/retrieve/diagnostics",
      payload,
    );
    return response.data;
  },
};
