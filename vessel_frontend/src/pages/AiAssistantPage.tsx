import { useMutation, useQuery } from "@tanstack/react-query";
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { aiApi } from "../api/aiApi";
import type {
  RagAnswerResponse,
  RetrievalDiagnosticsResponse,
} from "../types/ai";

// Страница AI-ассистента для RAG-поиска по индексу судов.
//
// Сценарий работы:
// 1) пользователь задает вопрос, выбирает модель и режим retrieval;
// 2) UI вызывает /rag/answer и (опционально) /retrieve/diagnostics;
// 3) показывает ответ, источники и отладочные данные пайплайна.
interface AskResult {
  answer: RagAnswerResponse;
  diagnostics: RetrievalDiagnosticsResponse | null;
}

const MODEL_STORAGE_KEY = "ai-assistant-selected-model";

const AiAssistantPage: React.FC = () => {
  const [question, setQuestion] = useState(
    "Под каким флагом ходит MSC NEDERLAND?",
  );
  const [retrievalMode, setRetrievalMode] = useState<
    "hybrid" | "vector" | "lexical" | "exact"
  >("hybrid");
  const [selectedModel, setSelectedModel] = useState(() => {
    if (typeof window === "undefined") {
      return "llama3.2:3b";
    }
    return window.localStorage.getItem(MODEL_STORAGE_KEY) || "llama3.2:3b";
  });
  const [topK, setTopK] = useState(5);
  const [candidateLimit, setCandidateLimit] = useState(12);
  const [maxDistance, setMaxDistance] = useState("");
  const [showDiagnostics, setShowDiagnostics] = useState(true);

  // Загружаем список доступных моделей и активную конфигурацию AI-рантайма.
  const runtimeQuery = useQuery({
    queryKey: ["ai-runtime"],
    queryFn: aiApi.getRuntime,
  });

  const askMutation = useMutation({
    mutationFn: async (): Promise<AskResult> => {
      const distanceValue = maxDistance.trim()
        ? Number(maxDistance)
        : undefined;
      const answer = await aiApi.answerQuestion({
        question,
        top_k: topK,
        retrieval_mode: retrievalMode,
        max_distance: distanceValue,
        llm_provider: "ollama",
        llm_model: selectedModel,
      });

      if (!showDiagnostics) {
        return { answer, diagnostics: null };
      }

      const diagnostics = await aiApi.getDiagnostics({
        question,
        retrieval_mode: retrievalMode,
        top_k: topK,
        candidate_limit: candidateLimit,
        max_distance: distanceValue,
      });

      return { answer, diagnostics };
    },
  });

  const runtime = runtimeQuery.data;
  const result = askMutation.data;

  // Сохраняем выбор модели локально, чтобы при следующем открытии страницы
  // пользователь продолжил работать с тем же локальным LLM.
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(MODEL_STORAGE_KEY, selectedModel);
  }, [selectedModel]);

  // Если сохраненная модель исчезла из рантайма, выбираем первую доступную,
  // чтобы UI не держал невалидное значение select.
  useEffect(() => {
    if (!runtime?.available_models?.length) {
      return;
    }

    if (!runtime.available_models.includes(selectedModel)) {
      setSelectedModel(runtime.available_models[0]);
    }
  }, [runtime, selectedModel]);

  return (
    <div className="min-h-screen bg-dark-bg text-gray-100">
      <div className="border-b border-dark-border bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.22),_transparent_38%),linear-gradient(180deg,_rgba(15,23,42,0.98),_rgba(15,23,42,0.92))]">
        <div className="container mx-auto px-4 py-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="mb-3 inline-flex items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs uppercase tracking-[0.24em] text-cyan-200">
                AI Navigator
              </div>
              <h1 className="text-4xl font-bold tracking-tight text-white">
                AI-поиск по судам
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
                Интерфейс для RAG-поиска по индексу судов: вопрос, выбор модели,
                режим retrieval, диагностика кандидатов, точный short-path для
                IMO/MMSI и прозрачные источники ответа.
              </p>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <Link
                to="/"
                className="rounded-lg border border-dark-border bg-dark-card px-4 py-2 text-slate-200 transition-colors hover:bg-dark-hover"
              >
                К списку судов
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto grid grid-cols-1 gap-6 px-4 py-6 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="space-y-6">
          <section className="rounded-2xl border border-dark-border bg-dark-card p-5 shadow-[0_20px_60px_rgba(2,6,23,0.35)]">
            <h2 className="mb-4 text-lg font-semibold text-white">
              Параметры запроса
            </h2>

            <div className="space-y-4">
              <div>
                <label className="mb-2 block text-sm text-slate-300">
                  Вопрос
                </label>
                <textarea
                  value={question}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                    setQuestion(e.target.value)
                  }
                  rows={5}
                  className="w-full rounded-xl border border-dark-border bg-slate-950/60 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/40"
                />
              </div>

              <div>
                <label className="mb-2 block text-sm text-slate-300">
                  Модель LLM
                </label>
                <select
                  value={selectedModel}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                    setSelectedModel(e.target.value)
                  }
                  className="w-full rounded-xl border border-dark-border bg-slate-950/60 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/40"
                >
                  {(runtime?.available_models || ["llama3.2:3b"]).map(
                    (model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ),
                  )}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-2 block text-sm text-slate-300">
                    Retrieval mode
                  </label>
                  <select
                    value={retrievalMode}
                    onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                      setRetrievalMode(
                        e.target.value as
                          | "hybrid"
                          | "vector"
                          | "lexical"
                          | "exact",
                      )
                    }
                    className="w-full rounded-xl border border-dark-border bg-slate-950/60 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/40"
                  >
                    <option value="hybrid">hybrid</option>
                    <option value="vector">vector</option>
                    <option value="lexical">lexical</option>
                    <option value="exact">exact (IMO/MMSI)</option>
                  </select>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    Для точных идентификаторов лучше выбирать режим exact: он
                    использует специальный путь поиска по IMO и MMSI без лишнего
                    шума от широкого retrieval.
                  </p>
                </div>
                <div>
                  <label className="mb-2 block text-sm text-slate-300">
                    Top K
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={topK}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setTopK(Number(e.target.value) || 1)
                    }
                    className="w-full rounded-xl border border-dark-border bg-slate-950/60 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/40"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-2 block text-sm text-slate-300">
                    Candidate limit
                  </label>
                  <input
                    type="number"
                    min={topK}
                    max={50}
                    value={candidateLimit}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setCandidateLimit(Number(e.target.value) || topK)
                    }
                    className="w-full rounded-xl border border-dark-border bg-slate-950/60 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/40"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm text-slate-300">
                    Max distance
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={maxDistance}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setMaxDistance(e.target.value)
                    }
                    placeholder="например 0.35"
                    className="w-full rounded-xl border border-dark-border bg-slate-950/60 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/40"
                  />
                </div>
              </div>

              <label className="flex items-center gap-3 rounded-xl border border-dark-border bg-slate-950/40 px-4 py-3 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={showDiagnostics}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setShowDiagnostics(e.target.checked)
                  }
                  className="h-4 w-4 rounded border-gray-600 bg-dark-bg text-cyan-500 focus:ring-cyan-500"
                />
                Показывать retrieval diagnostics
              </label>

              <button
                onClick={() => askMutation.mutate()}
                disabled={askMutation.isPending || !question.trim()}
                className="w-full rounded-xl bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-300"
              >
                {askMutation.isPending
                  ? "Выполняем запрос..."
                  : "Задать вопрос"}
              </button>
            </div>
          </section>

          <section className="rounded-2xl border border-dark-border bg-dark-card p-5">
            <h2 className="mb-3 text-lg font-semibold text-white">
              LLM runtime
            </h2>
            {runtimeQuery.isLoading && (
              <p className="text-sm text-slate-400">Загрузка моделей...</p>
            )}
            {runtimeQuery.isError && (
              <p className="text-sm text-red-300">
                Не удалось получить список моделей.
              </p>
            )}
            {runtime && (
              <div className="space-y-3 text-sm text-slate-300">
                <div className="rounded-xl border border-dark-border bg-slate-950/40 p-3">
                  <div>
                    Провайдер:{" "}
                    <span className="font-medium text-white">
                      {runtime.provider}
                    </span>
                  </div>
                  <div>
                    Активная модель:{" "}
                    <span className="font-medium text-white">
                      {runtime.configured_model}
                    </span>
                  </div>
                  <div>
                    Квантование:{" "}
                    <span className="font-medium text-white">
                      {runtime.configured_model_quantization || "n/a"}
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  {runtime.available_models_info.map((model) => (
                    <div
                      key={model.name}
                      className="rounded-xl border border-dark-border bg-slate-950/30 p-3"
                    >
                      <div className="font-medium text-white">{model.name}</div>
                      <div className="text-xs text-slate-400">
                        {model.family} • {model.parameter_size} •{" "}
                        {model.quantization_level}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </aside>

        <main className="space-y-6">
          <section className="rounded-2xl border border-dark-border bg-dark-card p-6 shadow-[0_20px_60px_rgba(2,6,23,0.35)]">
            <div className="mb-4 flex items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-semibold text-white">
                  Ответ модели
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                  Результат RAG-пайплайна с выбранной моделью и источниками.
                </p>
              </div>
              {result?.answer && (
                <div className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200">
                  {result.answer.llm_model}
                </div>
              )}
            </div>

            {!result && !askMutation.isPending && (
              <div className="rounded-2xl border border-dashed border-dark-border bg-slate-950/30 px-6 py-12 text-center text-slate-400">
                Здесь появится ответ модели, когда вы отправите вопрос.
              </div>
            )}

            {askMutation.isPending && (
              <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/5 px-6 py-12 text-center text-cyan-100">
                Выполняем retrieval, собираем контекст и запрашиваем модель...
              </div>
            )}

            {askMutation.isError && (
              <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-4 text-red-200">
                Ошибка запроса:{" "}
                {askMutation.error instanceof Error
                  ? askMutation.error.message
                  : "Неизвестная ошибка"}
              </div>
            )}

            {result?.answer && (
              <div className="space-y-5">
                <div className="rounded-2xl border border-dark-border bg-slate-950/45 p-5">
                  <div className="mb-3 text-xs uppercase tracking-[0.22em] text-slate-500">
                    Answer
                  </div>
                  <p className="whitespace-pre-wrap text-base leading-7 text-slate-100">
                    {result.answer.answer}
                  </p>
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                  <div className="rounded-2xl border border-dark-border bg-slate-950/30 p-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                      LLM
                    </div>
                    <div className="mt-2 text-sm text-white">
                      {result.answer.llm_provider} / {result.answer.llm_model}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-dark-border bg-slate-950/30 p-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                      Retrieval
                    </div>
                    <div className="mt-2 text-sm text-white">
                      {result.answer.retrieval_mode}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-dark-border bg-slate-950/30 p-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                      Sources used
                    </div>
                    <div className="mt-2 text-sm text-white">
                      {result.answer.used_chunks}
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="mb-3 text-lg font-semibold text-white">
                    Источники
                  </h3>
                  <div className="grid gap-3">
                    {result.answer.sources.map((source, index) => (
                      <div
                        key={`${source.chunk_id}-${index}`}
                        className="rounded-2xl border border-dark-border bg-slate-950/35 p-4"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="font-medium text-white">
                              [{index + 1}] {source.title}
                            </div>
                            <div className="mt-1 text-sm text-slate-400">
                              source_pk={source.source_pk} • chunk=
                              {source.chunk_index}
                            </div>
                          </div>
                          <div className="text-right text-xs text-slate-400">
                            <div>distance: {source.distance ?? "n/a"}</div>
                            <div>score: {source.score ?? "n/a"}</div>
                          </div>
                        </div>
                        {source.snippet && (
                          <div className="mt-3 rounded-xl border border-cyan-500/15 bg-cyan-500/5 p-3 text-sm leading-6 text-slate-200">
                            {source.snippet}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </section>

          {result?.diagnostics && (
            <section className="rounded-2xl border border-dark-border bg-dark-card p-6">
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-semibold text-white">
                    Retrieval diagnostics
                  </h2>
                  <p className="mt-1 text-sm text-slate-400">
                    Прозрачная картина по кандидатам до и после reranking.
                  </p>
                </div>
              </div>

              <div className="mb-5 grid gap-4 md:grid-cols-5">
                <div className="rounded-2xl border border-dark-border bg-slate-950/30 p-4">
                  <div className="text-xs text-slate-500">До distance</div>
                  <div className="mt-2 text-xl font-semibold text-white">
                    {result.diagnostics.retrieved_count_before_distance}
                  </div>
                </div>
                <div className="rounded-2xl border border-dark-border bg-slate-950/30 p-4">
                  <div className="text-xs text-slate-500">После distance</div>
                  <div className="mt-2 text-xl font-semibold text-white">
                    {result.diagnostics.retrieved_count_after_distance}
                  </div>
                </div>
                <div className="rounded-2xl border border-dark-border bg-slate-950/30 p-4">
                  <div className="text-xs text-slate-500">Отфильтровано</div>
                  <div className="mt-2 text-xl font-semibold text-white">
                    {result.diagnostics.distance_filtered_out}
                  </div>
                </div>
                <div className="rounded-2xl border border-dark-border bg-slate-950/30 p-4">
                  <div className="text-xs text-slate-500">После rerank</div>
                  <div className="mt-2 text-xl font-semibold text-white">
                    {result.diagnostics.reranked_count}
                  </div>
                </div>
                <div className="rounded-2xl border border-dark-border bg-slate-950/30 p-4">
                  <div className="text-xs text-slate-500">Финал</div>
                  <div className="mt-2 text-xl font-semibold text-white">
                    {result.diagnostics.final_count}
                  </div>
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-3">
                <DiagnosticsColumn
                  title="Candidates"
                  items={result.diagnostics.candidates}
                />
                <DiagnosticsColumn
                  title="Reranked"
                  items={result.diagnostics.reranked}
                />
                <DiagnosticsColumn
                  title="Final top-k"
                  items={result.diagnostics.final}
                />
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  );
};

interface DiagnosticsColumnProps {
  title: string;
  items: RetrievalDiagnosticsResponse["final"];
}

const DiagnosticsColumn: React.FC<DiagnosticsColumnProps> = ({
  title,
  items,
}) => {
  return (
    <div className="rounded-2xl border border-dark-border bg-slate-950/20 p-4">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">
        {title}
      </h3>
      <div className="space-y-3">
        {items.map((item) => (
          <div
            key={`${title}-${item.chunk_id}`}
            className="rounded-xl border border-dark-border bg-slate-950/40 p-3"
          >
            <div className="font-medium text-white">{item.title}</div>
            <div className="mt-1 text-xs text-slate-400">
              flag={item.document_flag || "n/a"} • type=
              {item.document_general_type || "n/a"}
            </div>
            {item.content && (
              <div className="mt-2 rounded-lg border border-slate-800 bg-slate-950/50 p-2 text-xs leading-5 text-slate-300">
                {item.content.length > 280
                  ? `${item.content.slice(0, 280)}...`
                  : item.content}
              </div>
            )}
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-300">
              <div>distance: {item.distance ?? "n/a"}</div>
              <div>lexical: {item.lexical_score ?? "n/a"}</div>
              <div>score: {item._score ?? "n/a"}</div>
              <div>imo: {item.document_imo || "n/a"}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AiAssistantPage;
