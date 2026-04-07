import importlib
import json
import os
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from services.ingestion import list_ingestion_jobs, run_ingestion, search_chunks


def _generate_answer_with_llm(
    question: str,
    chunks: List[Dict[str, Any]],
    max_chars: int,
    provider: Optional[str],
    model: Optional[str],
) -> Dict[str, str]:
    llm_module = importlib.import_module("services.llm")
    return llm_module.generate_answer(
        question=question,
        chunks=chunks,
        max_chars=max_chars,
        provider=provider,
        model=model,
    )


# Создаем приложение FastAPI.
# title и version полезны для автодокументации Swagger (раздел /docs).
# Это отдельный сервис для ИИ-логики, а не замена текущему backend.
# Такой подход удобен архитектурно:
# - обычное API по судам остается простым и стабильным;
# - агент можно развивать независимо;
# - позже сюда безболезненно добавятся LLM, RAG и гибридный поиск.


class Utf8JSONResponse(JSONResponse):
    # Явно закрепляем UTF-8 и отключаем ASCII-экранирование.
    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="AIS AI Agent",
    version="0.1.0",
    default_response_class=Utf8JSONResponse,
)


class ChatRequest(BaseModel):
    # Текст вопроса от пользователя.
    question: str
    # Ограничение количества строк в ответе (чтобы не вернуть слишком много данных).
    # По умолчанию 10.
    # Это также первый элемент защиты от слишком тяжелых запросов.
    # Позже здесь стоит добавить строгие границы, например не больше 20-50 записей.
    limit: Optional[int] = 10


class ChatResponse(BaseModel):
    # Текстовый ответ "агента" для пользователя.
    # Пока текст формируется по шаблону.
    # В будущем сюда будет подставляться ответ от LLM на основе найденного контекста.
    answer: str
    # Какая стратегия была выбрана: sql или semantic_stub.
    # Позже тут могут появиться дополнительные режимы, например:
    # rag, hybrid, summary, compare.
    strategy: str
    # Сырые строки из БД, которые использовались для ответа.
    # На этапе разработки это особенно полезно: можно видеть, откуда берутся факты.
    # В продакшене вместо полных rows часто возвращают citations или краткие источники.
    rows: List[Dict[str, Any]]


class IngestRequest(BaseModel):
    # Ограничение количества судов для индексации.
    #
    # Удобно для первых тестов:
    # - limit=10 для быстрой проверки pipeline;
    # - limit=None для полной индексации всей таблицы vessels.
    limit: Optional[int] = None
    # Delta-режим: индексируем только изменившиеся записи.
    incremental: Optional[bool] = False
    # Явная нижняя граница updated_at в ISO-формате.
    updated_after: Optional[str] = None


class IngestResponse(BaseModel):
    # Идентификатор записи в ai.ingestion_jobs.
    job_id: int
    # Сколько судов было обработано за запуск.
    vessels_processed: int
    # Сколько документов обновлено/создано в ai.documents.
    documents_upserted: int
    # Сколько chunks создано в ai.chunks.
    chunks_upserted: int


class IngestionJobsResponse(BaseModel):
    # Количество jobs в ответе.
    total: int
    # Сырые записи из ai.ingestion_jobs.
    jobs: List[Dict[str, Any]]


class ChunkSearchRequest(BaseModel):
    # Текст, который ищем внутри ai.chunks.content.
    query: str
    # Количество результатов в выдаче.
    limit: Optional[int] = 5
    # Режим поиска:
    # - hybrid: сначала vector, затем lexical fallback;
    # - vector: только vector similarity;
    # - lexical: только ILIKE/token search.
    mode: Optional[str] = "hybrid"
    # Максимально допустимая vector distance.
    # Если указано значение, слишком далекие vector-совпадения будут отброшены.
    max_distance: Optional[float] = None


class ChunkSearchResponse(BaseModel):
    # Повторяем запрос для удобства отладки на клиенте.
    query: str
    # Какой режим retrieval был реально использован.
    mode_used: str
    # Количество найденных результатов в этом ответе.
    total: int
    # Список найденных chunks с метаданными документа.
    results: List[Dict[str, Any]]


class RetrievalDiagnosticsRequest(BaseModel):
    # Вопрос для анализа retrieval-пайплайна.
    question: str
    # Режим retrieval: hybrid, vector, lexical, exact.
    retrieval_mode: Optional[str] = "hybrid"
    # Финальный размер ответа после всех этапов.
    top_k: Optional[int] = 5
    # Размер кандидатов до reranking.
    candidate_limit: Optional[int] = 20
    # Порог по vector distance.
    max_distance: Optional[float] = None


class RetrievalDiagnosticsResponse(BaseModel):
    # Исходный вопрос.
    question: str
    # Режим, запрошенный клиентом.
    retrieval_mode_requested: str
    # Режим после нормализации в API.
    retrieval_mode_used: str
    # Лимит кандидатов до rerank.
    candidate_limit: int
    # Применялся ли фильтр max_distance.
    distance_filter_applied: bool
    # Количество кандидатов до фильтра max_distance (оценка).
    retrieved_count_before_distance: int
    # Количество кандидатов после фильтра max_distance.
    retrieved_count_after_distance: int
    # Сколько кандидатов было отфильтровано порогом distance.
    distance_filtered_out: int
    # Количество элементов после reranking.
    reranked_count: int
    # Количество элементов в итоговом top-k.
    final_count: int
    # Кандидаты сразу после retrieval.
    candidates: List[Dict[str, Any]]
    # Результат reranking (или тот же список для vector-only).
    reranked: List[Dict[str, Any]]
    # Итоговый top-k.
    final: List[Dict[str, Any]]


class RagAnswerRequest(BaseModel):
    # Вопрос пользователя, на который нужно дать ответ по найденным chunks.
    question: str
    # Сколько chunks максимум использовать как контекст.
    top_k: Optional[int] = 5
    # Максимальный размер итогового ответа в символах.
    max_answer_chars: Optional[int] = 1200
    # Режим retrieval для мини-RAG.
    retrieval_mode: Optional[str] = "hybrid"
    # Порог для vector distance.
    max_distance: Optional[float] = None
    # Провайдер генерации ответа: mock или ollama.
    llm_provider: Optional[str] = None
    # Имя модели LLM (например, llama3.2:3b, qwen2.5:7b).
    llm_model: Optional[str] = None


class RagAnswerResponse(BaseModel):
    # Исходный вопрос пользователя.
    question: str
    # Режим retrieval, который использовался при поиске контекста.
    retrieval_mode: str
    # Реально использованный LLM-провайдер.
    llm_provider: str
    # Реально использованная LLM-модель.
    llm_model: str
    # Сформированный ответ на основе контекста (без LLM, extractive-режим).
    answer: str
    # Количество реально использованных chunks.
    used_chunks: int
    # Источники, чтобы можно было проверить происхождение фактов.
    sources: List[Dict[str, Any]]


class LlmRuntimeResponse(BaseModel):
    # Активный провайдер генерации.
    provider: str
    # Модель, сконфигурированная через переменные окружения.
    configured_model: str
    # Доступные модели в провайдере (для Ollama: локально загруженные модели).
    available_models: List[str]
    # Расширенные метаданные по каждой модели.
    available_models_info: List[Dict[str, Any]]
    # Квантование модели из конфигурации LLM_MODEL (если модель найдена локально).
    configured_model_quantization: Optional[str] = None
    # Доступен ли Ollama runtime по сети.
    ollama_reachable: bool
    # Текст ошибки для диагностики, если runtime недоступен.
    error: Optional[str] = None


class LlmPullRequest(BaseModel):
    # Имя модели для загрузки в Ollama, например llama3.2:3b.
    model: str


class LlmPullResponse(BaseModel):
    # Провайдер, который выполнил загрузку.
    provider: str
    # Имя модели, которую запрашивали.
    model: str
    # Итоговый статус операции.
    status: str
    # Сырой ответ провайдера для диагностики.
    detail: Dict[str, Any]


class LlmDeleteRequest(BaseModel):
    # Имя модели для удаления из Ollama.
    model: str


class LlmDeleteResponse(BaseModel):
    # Провайдер, который выполнил удаление.
    provider: str
    # Имя модели, которую удалили.
    model: str
    # Итоговый статус операции.
    status: str
    # Сырой ответ провайдера для диагностики.
    detail: Dict[str, Any]


def _normalize_retrieval_mode(mode: Optional[str]) -> str:
    # Нормализуем пользовательский режим retrieval.
    # Если пришло неизвестное значение, безопасно откатываемся в hybrid.
    value = (mode or "hybrid").strip().lower()
    if value in {"hybrid", "vector", "lexical", "exact"}:
        return value
    return "hybrid"


def get_db_conn():
    # Создаем новое подключение к PostgreSQL на каждый запрос.
    # Параметры берутся из переменных окружения Docker Compose.
    # Если переменные не заданы, используются безопасные дефолты.
    #
    # Почему агенту вообще полезно ходить в БД напрямую:
    # - для точных запросов SQL надежнее, чем LLM;
    # - не нужно гонять лишние запросы через другой backend;
    # - позже в той же БД можно хранить RAG-таблицы и embeddings.
    #
    # Когда сервис станет более зрелым, здесь можно перейти на пул подключений.
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "vessels_db"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )


def _extract_relevant_lines(
    content: str, question: str, max_lines: int = 4
) -> List[str]:
    # Простой extractive-алгоритм:
    # берем строки из chunk, где встречается слово из вопроса.
    # Если совпадений нет, возвращаем первые информативные строки профиля.
    q_tokens = {
        t.strip(" ,.:;!?()[]{}\"'").lower() for t in question.split() if t.strip()
    }
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    matched: List[str] = []
    for line in lines:
        low = line.lower()
        if any(token and token in low for token in q_tokens):
            matched.append(line)
        if len(matched) >= max_lines:
            break

    if matched:
        return matched

    # Fallback для случаев, когда ключевые слова вопроса не совпали с chunk-текстом.
    return lines[:max_lines]


def _tokenize_query(text: str) -> List[str]:
    # Унифицированная токенизация запроса для reranking.
    #
    # Почему это важно:
    # - retrieval в ingestion уже ищет по токенам;
    # - reranking должен использовать похожие правила,
    #   чтобы ранжирование было предсказуемым.
    raw_tokens = [t.strip(" ,.:;!?()[]{}\"'").lower() for t in text.split()]
    tokens = [t for t in raw_tokens if len(t) >= 3]
    return list(dict.fromkeys(tokens))[:12]


def _extract_numeric_query_tokens(text: str) -> List[str]:
    # Отдельно выделяем длинные числовые токены, похожие на IMO/MMSI.
    raw_tokens = [t.strip(" ,.:;!?()[]{}\"'") for t in text.split()]
    tokens = [t for t in raw_tokens if t.isdigit() and len(t) >= 6]
    return list(dict.fromkeys(tokens))[:4]


def _expand_query_for_retrieval(text: str) -> str:
    # Добавляем англоязычные синонимы к частым русским доменным словам,
    # чтобы lexical/general_type-поиск корректно работал при русских запросах.
    lower = text.lower()
    extra_terms: List[str] = []

    if any(term in lower for term in ["пассажир", "круиз", "паром"]):
        extra_terms.extend(["passenger", "cruise", "ferry"])
    if any(term in lower for term in ["контейнер", "контейнеровоз"]):
        extra_terms.extend(["container"])
    if any(term in lower for term in ["танкер", "нефт"]):
        extra_terms.extend(["tanker"])
    if any(term in lower for term in ["рыбол", "рыболо"]):
        extra_terms.extend(["fishing"])

    if not extra_terms:
        return text

    # Не дублируем уже имеющиеся токены в вопросе.
    original_tokens = set(_tokenize_query(text))
    unique_extras = [term for term in extra_terms if term not in original_tokens]
    if not unique_extras:
        return text
    return f"{text} {' '.join(unique_extras)}"


def _distance_sort_value(item: Dict[str, Any]) -> float:
    # Для lexical-only результатов distance может отсутствовать.
    distance = item.get("distance")
    if distance is None:
        return 999.0
    return float(distance)


def _rerank_chunks(question: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Простой lexical reranking без внешней модели.
    #
    # Стратегия:
    # 1) считаем совпадения токенов вопроса в title;
    # 2) считаем совпадения токенов в content;
    # 3) даем больший вес title, так как это обычно имя/тип судна;
    # 4) сортируем по score по убыванию.
    #
    # Это уменьшает шум от OR-поиска в ILIKE и делает top-k заметно лучше
    # до внедрения pgvector.
    q_tokens = _tokenize_query(question)
    q_numeric_tokens = _extract_numeric_query_tokens(question)
    normalized_question = question.strip().lower()
    if not q_tokens:
        q_tokens = []

    ranked: List[Dict[str, Any]] = []
    for item in chunks:
        title = str(item.get("title") or "").lower()
        content = str(item.get("content") or "").lower()
        document_imo = str(item.get("document_imo") or "")
        document_mmsi = str(item.get("document_mmsi") or "")
        document_flag = str(item.get("document_flag") or "").lower()
        document_general_type = str(item.get("document_general_type") or "").lower()
        lexical_score = int(item.get("lexical_score") or 0)

        title_hits = sum(1 for tok in q_tokens if tok in title)
        content_hits = sum(1 for tok in q_tokens if tok in content)
        flag_hits = sum(1 for tok in q_tokens if tok in document_flag)
        type_hits = sum(1 for tok in q_tokens if tok in document_general_type)
        exact_title_hit = (
            20 if normalized_question and normalized_question == title else 0
        )
        exact_id_hits = sum(
            30
            for tok in q_numeric_tokens
            if tok == document_imo or tok == document_mmsi
        )

        score = (
            lexical_score
            + exact_title_hit
            + exact_id_hits
            + (title_hits * 6)
            + (flag_hits * 5)
            + (type_hits * 4)
            + (content_hits * 2)
        )

        enriched = dict(item)
        enriched["_score"] = score
        ranked.append(enriched)

    ranked.sort(
        key=lambda x: (
            -x.get("_score", 0),
            _distance_sort_value(x),
            -x.get("chunk_id", 0),
        )
    )
    return ranked


def _build_rag_answer(
    question: str, chunks: List[Dict[str, Any]], max_chars: int
) -> str:
    # Формируем понятный ответ из найденных chunks.
    #
    # Это "mini-RAG" без LLM: мы извлекаем релевантные строки и объединяем их
    # в краткое резюме. Подход полезен для старта, потому что:
    # - прозрачно видно, откуда взялись факты;
    # - нет риска генеративных галлюцинаций;
    # - легко отлаживать до подключения модели.
    if not chunks:
        return (
            "Не нашел релевантный контекст в индексе chunks. "
            "Попробуйте уточнить запрос или расширить индексацию."
        )

    parts: List[str] = ["Найденный контекст по вашему вопросу:"]
    for idx, chunk in enumerate(chunks, start=1):
        title = (chunk.get("title") or "Unknown vessel").strip()
        lines = _extract_relevant_lines(chunk.get("content") or "", question)
        if not lines:
            continue
        parts.append(f"{idx}. {title}: " + " | ".join(lines))

    answer = "\n".join(parts).strip()
    if len(answer) > max_chars:
        answer = answer[: max_chars - 3].rstrip() + "..."
    return answer


def route_strategy(question: str) -> str:
    # Очень простой "роутер" стратегии:
    # если в вопросе есть признаки структурированного запроса,
    # считаем, что лучше идти через SQL.
    #
    # Это задел под будущий агент:
    # позже здесь может быть LLM-классификатор интента, а пока достаточно правил.
    #
    # Именно этот блок со временем станет точкой принятия решения:
    # - если запрос точный и табличный -> SQL;
    # - если запрос смысловой -> RAG;
    # - если запрос смешанный -> hybrid retrieval.
    q = question.lower()
    sql_hints = [
        "imo",
        "mmsi",
        "флаг",
        "flag",
        "тип",
        "type",
        "year",
        "год",
        "dwt",
        "gt",
    ]
    if any(h in q for h in sql_hints):
        return "sql"

    # Пока настоящего semantic search здесь нет.
    # semantic_stub означает, что архитектурное место уже подготовлено,
    # и позже сюда будет подключаться работа с embeddings и векторным поиском.
    return "semantic_stub"


def run_sql_lookup(question: str, limit: int) -> List[Dict[str, Any]]:
    # Выполняем SQL-поиск по базе.
    # Важно: используем параметризованные запросы (%s), чтобы исключить SQL-инъекции.
    #
    # Это хороший старт для вашего проекта, потому что основная информация о судах
    # уже структурирована: IMO, MMSI, флаг, тип, тоннаж, год постройки и т.д.
    # Для таких фактов SQL должен быть первым инструментом, а не запасным.
    q = question.lower().strip()
    conn = get_db_conn()
    try:
        # RealDictCursor возвращает строки как словари:
        # {"name": "...", "imo": "..."} вместо кортежей.
        # Это удобно как для JSON API, так и для будущей передачи данных в LLM-контекст.
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Специальная ветка для вопросов с IMO.
            # Логика простая: ищем первое "похожее на номер" число в тексте.
            # Это пример детерминированного сценария: если вопрос точный,
            # не нужно притворяться "умным" поиском, лучше делать точный lookup.
            if "imo" in q:
                parts = q.replace("?", " ").split()
                imo_value = None
                for p in parts:
                    # Минимальная эвристика: только цифры и длина от 6 символов.
                    # Можно улучшить до строгой проверки IMO формата.
                    # Позже имеет смысл вынести это в отдельную validate-функцию.
                    if p.isdigit() and len(p) >= 6:
                        imo_value = p
                        break
                if not imo_value:
                    return []

                cur.execute(
                    """
                    SELECT name, imo, mmsi, flag, general_type, year_built, dwt, gt
                    FROM vessels
                    WHERE imo = %s
                    LIMIT %s
                    """,
                    (imo_value, limit),
                )
                return cur.fetchall()

            # Общий fallback-поиск:
            # ищем текст вопроса в имени судна, типе и флаге.
            # Это не полноценный semantic search, но полезный базовый режим.
            #
            # Именно этот участок позже можно заменить на гибридную схему:
            # 1. сначала SQL-фильтрация по явным условиям;
            # 2. потом векторный поиск по embeddings;
            # 3. потом reranking лучших результатов.
            #
            # Для pgvector это будет одно из основных мест интеграции.
            # Обычно рядом появляется отдельная таблица вида ai.vessel_chunks,
            # где хранится текстовый профиль судна и embedding-вектор.
            cur.execute(
                """
                SELECT name, imo, mmsi, flag, general_type, year_built, dwt, gt
                FROM vessels
                WHERE
                    name ILIKE %s
                    OR general_type ILIKE %s
                    OR flag ILIKE %s
                ORDER BY updated_at DESC NULLS LAST
                LIMIT %s
                """,
                (f"%{question}%", f"%{question}%", f"%{question}%", limit),
            )
            return cur.fetchall()
    finally:
        # Гарантированно закрываем подключение даже при ошибках.
        # Это важно, чтобы не копить зависшие соединения при отладке и тестах.
        conn.close()


@app.get("/health")
def health():
    # Технический эндпоинт для проверки, что сервис жив.
    # Используется при ручной проверке и в healthchecks.
    # Позже health-check можно усилить и проверять не только сам FastAPI,
    # но и подключение к PostgreSQL, доступность embedding-модели и LLM-провайдера.
    return {"status": "ok"}


@app.get("/llm/models", response_model=LlmRuntimeResponse)
def llm_models(provider: Optional[str] = None):
    # Возвращаем runtime-диагностику LLM-провайдера и список доступных моделей.
    # provider можно передать как query-параметр, например: ?provider=ollama
    try:
        llm_module = importlib.import_module("services.llm")
        return llm_module.get_llm_runtime(provider=provider)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/llm/pull-model", response_model=LlmPullResponse)
def llm_pull_model(req: LlmPullRequest):
    # Загружает модель в Ollama runtime по имени.
    # Полезно для удаленного развертывания без ручного docker exec.
    try:
        llm_module = importlib.import_module("services.llm")
        return llm_module.pull_ollama_model(model=req.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/llm/delete-model", response_model=LlmDeleteResponse)
def llm_delete_model(req: LlmDeleteRequest):
    # Удаляет модель из Ollama runtime по имени.
    # Если модель не найдена, возвращаем 404.
    try:
        llm_module = importlib.import_module("services.llm")
        return llm_module.delete_ollama_model(model=req.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        status_code = getattr(e, "status_code", 500)
        raise HTTPException(status_code=status_code, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Основной эндпоинт "агента".
    # Текущая версия:
    # 1) выбирает стратегию
    # 2) получает строки из БД
    # 3) формирует человекочитаемый ответ
    #
    # В будущем этот метод станет оркестратором пайплайна:
    # - router
    # - SQL tool / retrieval tool
    # - сбор контекста
    # - генерация ответа через LLM
    # - возврат источников
    try:
        strategy = route_strategy(req.question)

        # Пока оба режима используют один и тот же механизм извлечения данных.
        # Это нормально для первого этапа: мы сначала делаем рабочий каркас,
        # а затем уже разводим поведение по стратегиям.
        rows = run_sql_lookup(req.question, req.limit or 10)

        if strategy == "sql":
            if rows:
                # При желании сюда потом можно добавить краткую сводку по строкам,
                # чтобы ответ выглядел не как "сырой список", а как осмысленное резюме.
                return {
                    "answer": f"Найдено записей: {len(rows)}. Возвращаю наиболее релевантные результаты.",
                    "strategy": strategy,
                    "rows": rows,
                }

            # Если ничего не найдено, честно сообщаем об этом.
            # Это важный принцип для AI-сервиса: лучше пустой и правдивый ответ,
            # чем красивая, но выдуманная интерпретация.
            return {
                "answer": "По SQL-запросу ничего не найдено. Уточните IMO/MMSI или параметры фильтра.",
                "strategy": strategy,
                "rows": [],
            }

        # semantic_stub означает "заглушка семантического режима":
        # пока используем тот же SQL-like поиск, но помечаем стратегию отдельно.
        # Позже именно здесь появится настоящий RAG-проход:
        # embedding(question) -> vector search -> context assembly -> answer generation.
        if rows:
            return {
                "answer": "Семантический режим пока базовый. Нашел похожие записи по текстовому совпадению.",
                "strategy": strategy,
                "rows": rows,
            }

        # Это честное сообщение пользователю о текущем состоянии системы.
        # В образовательной и ранней разработке такая прозрачность особенно полезна.
        return {
            "answer": "Пока не нашел совпадений. На следующем этапе добавим векторный поиск.",
            "strategy": strategy,
            "rows": [],
        }

    except Exception as e:
        # Отдаем 500 и текст ошибки.
        # Для production лучше логировать детали, а пользователю отдавать более нейтральное сообщение.
        # Позже здесь стоит добавить более точечную обработку ошибок:
        # - ошибки подключения к БД;
        # - ошибки retrieval-пайплайна;
        # - ошибки модели;
        # - ошибки валидации входного вопроса.
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/run", response_model=IngestResponse)
def ingest_run(req: IngestRequest):
    # Ручной запуск индексации данных судов в ai-схему.
    #
    # На текущем этапе это синхронный endpoint:
    # запрос ждет, пока ingestion завершится.
    # Для больших объемов данных позже лучше вынести запуск в очередь/воркер.
    try:
        return run_ingestion(
            limit=req.limit,
            incremental=bool(req.incremental),
            updated_after=req.updated_after,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ingest/jobs", response_model=IngestionJobsResponse)
def ingest_jobs(limit: int = 20):
    # Просмотр истории запусков индексации.
    #
    # Полезно для контроля пайплайна: видно успешные и неуспешные прогоны,
    # а также текст ошибки при падении.
    try:
        jobs = list_ingestion_jobs(limit=limit)
        return {"total": len(jobs), "jobs": jobs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/retrieve/chunks", response_model=ChunkSearchResponse)
def retrieve_chunks(req: ChunkSearchRequest):
    # Базовый retrieval endpoint без векторного поиска.
    #
    # Сейчас поиск идет через ILIKE по ai.chunks.content.
    # На следующем этапе функцию search_chunks можно заменить
    # на поиск через pgvector с тем же API-контрактом.
    try:
        mode = _normalize_retrieval_mode(req.mode)
        retrieval_query = _expand_query_for_retrieval(req.query)
        results = search_chunks(
            query=retrieval_query,
            limit=req.limit or 5,
            mode=mode,
            max_distance=req.max_distance,
        )
        if mode != "vector":
            results = _rerank_chunks(question=retrieval_query, chunks=results)
        return {
            "query": req.query,
            "mode_used": mode,
            "total": len(results),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/retrieve/diagnostics", response_model=RetrievalDiagnosticsResponse)
def retrieve_diagnostics(req: RetrievalDiagnosticsRequest):
    # Диагностика retrieval: кандидаты, reranking и финальный top-k.
    try:
        mode = _normalize_retrieval_mode(req.retrieval_mode)
        retrieval_query = _expand_query_for_retrieval(req.question)
        top_k = max(req.top_k or 5, 1)
        candidate_limit = max(req.candidate_limit or (top_k * 4), top_k)

        candidates = search_chunks(
            query=retrieval_query,
            limit=candidate_limit,
            mode=mode,
            max_distance=req.max_distance,
        )
        retrieved_count_after_distance = len(candidates)

        # Для vector/hybrid можем дополнительно оценить размер пула
        # без порога distance, чтобы увидеть влияние фильтра.
        retrieved_count_before_distance = retrieved_count_after_distance
        if req.max_distance is not None and mode in {"hybrid", "vector"}:
            unfiltered_candidates = search_chunks(
                query=retrieval_query,
                limit=candidate_limit,
                mode=mode,
                max_distance=None,
            )
            retrieved_count_before_distance = len(unfiltered_candidates)

        if mode in {"vector", "exact"}:
            reranked = candidates
        else:
            reranked = _rerank_chunks(question=retrieval_query, chunks=candidates)

        final = reranked[:top_k]
        reranked_count = len(reranked)
        final_count = len(final)
        distance_filtered_out = max(
            retrieved_count_before_distance - retrieved_count_after_distance, 0
        )

        return {
            "question": req.question,
            "retrieval_mode_requested": req.retrieval_mode or "hybrid",
            "retrieval_mode_used": mode,
            "candidate_limit": candidate_limit,
            "distance_filter_applied": req.max_distance is not None,
            "retrieved_count_before_distance": retrieved_count_before_distance,
            "retrieved_count_after_distance": retrieved_count_after_distance,
            "distance_filtered_out": distance_filtered_out,
            "reranked_count": reranked_count,
            "final_count": final_count,
            "candidates": candidates,
            "reranked": reranked,
            "final": final,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rag/answer", response_model=RagAnswerResponse)
def rag_answer(req: RagAnswerRequest):
    # Mini-RAG endpoint: retrieval + extractive answer + sources.
    #
    # Текущий pipeline:
    # 1) Ищем релевантные chunks по question.
    # 2) Собираем ответ из строк этих chunks без генеративной модели.
    # 3) Возвращаем список источников для прозрачности.
    #
    # Когда вы добавите LLM, менять контракт endpoint почти не придется:
    # retrieval останется, поменяется только способ формирования поля answer.
    try:
        mode = _normalize_retrieval_mode(req.retrieval_mode)
        retrieval_query = _expand_query_for_retrieval(req.question)
        top_k = req.top_k or 5
        max_chars = req.max_answer_chars or 1200
        # Берем расширенный набор кандидатов, затем применяем reranking
        # и отдаем итоговый top_k.
        candidates = search_chunks(
            query=retrieval_query,
            limit=max(top_k * 3, 10),
            mode=mode,
            max_distance=req.max_distance,
        )
        if mode in {"vector", "exact"}:
            chunks = candidates[:top_k]
        else:
            reranked = _rerank_chunks(question=retrieval_query, chunks=candidates)
            chunks = reranked[:top_k]

        llm_result = _generate_answer_with_llm(
            question=req.question,
            chunks=chunks,
            max_chars=max_chars,
            provider=req.llm_provider,
            model=req.llm_model,
        )

        sources = [
            {
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "title": item.get("title"),
                "source_table": item.get("source_table"),
                "source_pk": item.get("source_pk"),
                "chunk_index": item.get("chunk_index"),
                "distance": item.get("distance"),
                "score": item.get("_score"),
                "snippet": " | ".join(
                    _extract_relevant_lines(
                        item.get("content") or "",
                        req.question,
                        max_lines=2,
                    )
                ),
            }
            for item in chunks
        ]

        return {
            "question": req.question,
            "retrieval_mode": mode,
            "llm_provider": llm_result["provider_used"],
            "llm_model": llm_result["model_used"],
            "answer": llm_result["answer"],
            "used_chunks": len(chunks),
            "sources": sources,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
