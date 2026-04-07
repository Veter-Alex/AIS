import hashlib
import importlib
import math
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor

# Этот модуль отвечает за первичную индексацию данных судов в ai-схему.
#
# Задача ingestion-процесса:
# 1. взять структурированные записи из таблицы vessels;
# 2. собрать из них удобный текстовый профиль;
# 3. сохранить профиль как документ и набор chunks.
#
# На этом этапе мы не используем embeddings и pgvector,
# но уже строим правильный "каркас" для последующего RAG.

EMBEDDING_DIM = 384
DEFAULT_EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "fastembed")
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


def _has_pgvector_column(cur: RealDictCursor) -> bool:
    # Проверяем, доступна ли колонка embedding_vec в ai.chunks.
    # Это позволяет писать код, который работает и с pgvector, и без него.
    cur.execute(
        """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'ai'
                    AND table_name = 'chunks'
                    AND column_name = 'embedding_vec'
                LIMIT 1
                """
    )
    return cur.fetchone() is not None


@lru_cache(maxsize=1)
def _get_fastembed_model():
    # Ленивая инициализация real embedding-модели.
    #
    # Модель загружается только при первом использовании.
    # Это ускоряет старт контейнера и упрощает разработку.
    try:
        fastembed_module = importlib.import_module("fastembed")
    except ImportError as exc:
        raise RuntimeError("fastembed is not installed") from exc

    text_embedding_cls = getattr(fastembed_module, "TextEmbedding")
    return text_embedding_cls(model_name=DEFAULT_EMBEDDING_MODEL)


def get_db_conn():
    # Подключение к той же БД, где уже работает основная система.
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "vessels_db"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )


def _clean(value: Any) -> str:
    # Нормализуем значения для текста документа.
    if value is None:
        return ""
    return str(value).strip()


def build_vessel_text(vessel: Dict[str, Any]) -> str:
    # Формируем единый текстовый профиль судна.
    # Этот текст позже будет дробиться на chunks и участвовать в retrieval.
    lines = [
        f"Name: {_clean(vessel.get('name'))}",
        f"IMO: {_clean(vessel.get('imo'))}",
        f"MMSI: {_clean(vessel.get('mmsi'))}",
        f"Call sign: {_clean(vessel.get('call_sign'))}",
        f"Flag: {_clean(vessel.get('flag'))}",
        f"General type: {_clean(vessel.get('general_type'))}",
        f"Detailed type: {_clean(vessel.get('detailed_type'))}",
        f"Year built: {_clean(vessel.get('year_built'))}",
        f"Length: {_clean(vessel.get('length'))}",
        f"Width: {_clean(vessel.get('width'))}",
        f"DWT: {_clean(vessel.get('dwt'))}",
        f"GT: {_clean(vessel.get('gt'))}",
        f"Home port: {_clean(vessel.get('home_port'))}",
        f"Info source: {_clean(vessel.get('info_source'))}",
        f"Description: {_clean(vessel.get('description'))}",
    ]
    return "\n".join(lines).strip()


def split_into_chunks(text: str, chunk_size: int = 800) -> List[str]:
    # Простейшее разбиение текста на куски фиксированного размера.
    #
    # Почему так пока достаточно:
    # - это максимально просто;
    # - не требует внешних зависимостей;
    # - позволяет быстро проверить весь pipeline.
    #
    # Позже лучше перейти на разбиение по токенам или по смысловым блокам.
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _tokenize(text: str) -> List[str]:
    # Простая токенизация для локального embedding без внешней модели.
    raw = [t.strip(" ,.:;!?()[]{}\"'\n\t").lower() for t in text.split()]
    return [t for t in raw if len(t) >= 2]


def build_hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    # Локальный deterministic embedding для fallback-режима.
    #
    # Важно: это уже не основной режим, а страховка на случай,
    # если real embedding-модель недоступна.
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec

    for tok in tokens:
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], byteorder="big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[bucket] += sign

    # L2-нормализация, чтобы косинусное расстояние работало стабильнее.
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def build_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    # Основная точка получения embeddings.
    #
    # Логика работы:
    # 1. По умолчанию пытаемся использовать реальную модель через fastembed.
    # 2. Если модель недоступна или произошла ошибка, падаем обратно в hash fallback.
    #
    # Это удобно для разработки:
    # - в нормальной среде работает real embedding;
    # - в ограниченной среде сервис не ломается полностью.
    provider = DEFAULT_EMBEDDING_PROVIDER.strip().lower()
    if provider == "hash":
        return build_hash_embedding(text, dim=dim)

    try:
        model = _get_fastembed_model()
        vectors = list(model.embed([text]))
        if not vectors:
            return build_hash_embedding(text, dim=dim)

        vector = vectors[0]
        # У fastembed обычно приходит numpy array, поэтому приводим к обычному list[float].
        result = [float(value) for value in vector.tolist()]
        if len(result) != dim:
            # На случай несоответствия размерности между схемой и моделью.
            return build_hash_embedding(text, dim=dim)
        return result
    except Exception:
        return build_hash_embedding(text, dim=dim)


def _vector_literal(values: List[float]) -> str:
    # Формируем текстовый литерал формата pgvector: [0.1,0.2,...]
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def _normalize_query_tokens(query: str) -> List[str]:
    # Унифицированная токенизация для lexical search.
    raw_tokens = [t.strip(" ,.:;!?()[]{}\"'").lower() for t in query.split()]
    tokens = [t for t in raw_tokens if len(t) >= 3]
    return list(dict.fromkeys(tokens))[:8]


def _extract_numeric_tokens(query: str) -> List[str]:
    # Отдельно выделяем числовые идентификаторы IMO/MMSI.
    raw_tokens = [t.strip(" ,.:;!?()[]{}\"'") for t in query.split()]
    numeric_tokens = [t for t in raw_tokens if t.isdigit() and len(t) >= 6]
    return list(dict.fromkeys(numeric_tokens))[:4]


def _merge_candidate_rows(
    vector_rows: List[Dict[str, Any]],
    lexical_rows: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    # Объединяем vector и lexical кандидатов по chunk_id.
    # Если chunk найден обоими режимами, сохраняем лучшую distance
    # и максимальный lexical_score.
    merged: Dict[Any, Dict[str, Any]] = {}

    for row in vector_rows:
        merged[row.get("chunk_id")] = dict(row)

    for row in lexical_rows:
        chunk_id = row.get("chunk_id")
        if chunk_id in merged:
            existing = merged[chunk_id]
            existing["lexical_score"] = max(
                int(existing.get("lexical_score") or 0),
                int(row.get("lexical_score") or 0),
            )
            if existing.get("distance") is None and row.get("distance") is not None:
                existing["distance"] = row.get("distance")
        else:
            merged[chunk_id] = dict(row)

    merged_rows = list(merged.values())

    def _distance_sort_value(item: Dict[str, Any]) -> float:
        distance = item.get("distance")
        if distance is None:
            return 999.0
        return float(distance)

    merged_rows.sort(
        key=lambda x: (
            -int(x.get("lexical_score") or 0),
            _distance_sort_value(x),
            -int(x.get("chunk_id") or 0),
        )
    )
    return merged_rows[:limit]


def _search_vector_candidates(
    cur: RealDictCursor,
    query: str,
    limit: int,
    max_distance: Optional[float],
) -> List[Dict[str, Any]]:
    # Векторный поиск по embedding_vec.
    query_vec = _vector_literal(build_embedding(query))
    cur.execute(
        """
        SELECT
            c.id AS chunk_id,
            c.document_id,
            c.chunk_index,
            c.content,
            c.token_count,
            c.metadata,
            d.title,
            d.source_table,
            d.source_pk,
            d.metadata->>'imo' AS document_imo,
            d.metadata->>'mmsi' AS document_mmsi,
            d.metadata->>'flag' AS document_flag,
            d.metadata->>'general_type' AS document_general_type,
            (c.embedding_vec <=> %s::vector) AS distance,
            0 AS lexical_score
        FROM ai.chunks c
        JOIN ai.documents d ON d.id = c.document_id
        WHERE c.embedding_vec IS NOT NULL
        ORDER BY c.embedding_vec <=> %s::vector ASC, c.id DESC
        LIMIT %s
        """,
        (query_vec, query_vec, limit),
    )
    rows = cur.fetchall()
    if max_distance is not None:
        rows = [
            row
            for row in rows
            if row.get("distance") is not None
            and float(row["distance"]) <= max_distance
        ]
    return rows


def _search_lexical_candidates(
    cur: RealDictCursor,
    query: str,
    tokens: List[str],
    numeric_tokens: List[str],
    limit: int,
) -> List[Dict[str, Any]]:
    # Lexical search не только по content, но и по title/metadata.
    # Это важно для точных запросов вида IMO/MMSI/flag/type.
    params: List[Any] = []
    score_parts: List[str] = []
    where_parts: List[str] = []

    normalized_query = query.strip().lower()
    if normalized_query:
        score_parts.append("CASE WHEN LOWER(d.title) = %s THEN 40 ELSE 0 END")
        params.append(normalized_query)
        score_parts.append("CASE WHEN LOWER(d.title) LIKE %s THEN 18 ELSE 0 END")
        params.append(f"%{normalized_query}%")
        where_parts.append("LOWER(d.title) LIKE %s")
        params.append(f"%{normalized_query}%")

    for token in tokens:
        score_parts.extend(
            [
                "CASE WHEN LOWER(d.title) LIKE %s THEN 10 ELSE 0 END",
                "CASE WHEN LOWER(COALESCE(d.metadata->>'flag', '')) LIKE %s THEN 8 ELSE 0 END",
                "CASE WHEN LOWER(COALESCE(d.metadata->>'general_type', '')) LIKE %s THEN 7 ELSE 0 END",
                "CASE WHEN LOWER(c.content) LIKE %s THEN 3 ELSE 0 END",
            ]
        )
        params.extend([f"%{token}%", f"%{token}%", f"%{token}%", f"%{token}%"])
        where_parts.extend(
            [
                "LOWER(d.title) LIKE %s",
                "LOWER(COALESCE(d.metadata->>'flag', '')) LIKE %s",
                "LOWER(COALESCE(d.metadata->>'general_type', '')) LIKE %s",
                "LOWER(c.content) LIKE %s",
            ]
        )
        params.extend([f"%{token}%", f"%{token}%", f"%{token}%", f"%{token}%"])

    for numeric_token in numeric_tokens:
        score_parts.extend(
            [
                "CASE WHEN COALESCE(d.metadata->>'imo', '') = %s THEN 60 ELSE 0 END",
                "CASE WHEN COALESCE(d.metadata->>'mmsi', '') = %s THEN 60 ELSE 0 END",
                "CASE WHEN c.content LIKE %s THEN 12 ELSE 0 END",
            ]
        )
        params.extend([numeric_token, numeric_token, f"%{numeric_token}%"])
        where_parts.extend(
            [
                "COALESCE(d.metadata->>'imo', '') = %s",
                "COALESCE(d.metadata->>'mmsi', '') = %s",
                "c.content LIKE %s",
            ]
        )
        params.extend([numeric_token, numeric_token, f"%{numeric_token}%"])

    if not score_parts:
        score_parts.append("CASE WHEN LOWER(c.content) LIKE %s THEN 1 ELSE 0 END")
        params.append(f"%{normalized_query}%")
        where_parts.append("LOWER(c.content) LIKE %s")
        params.append(f"%{normalized_query}%")

    score_sql = " + ".join(score_parts)
    where_sql = " OR ".join(where_parts)
    params.append(limit)

    query_sql = f"""
    SELECT
        c.id AS chunk_id,
        c.document_id,
        c.chunk_index,
        c.content,
        c.token_count,
        c.metadata,
        d.title,
        d.source_table,
        d.source_pk,
        d.metadata->>'imo' AS document_imo,
        d.metadata->>'mmsi' AS document_mmsi,
        d.metadata->>'flag' AS document_flag,
        d.metadata->>'general_type' AS document_general_type,
        NULL::float AS distance,
        ({score_sql}) AS lexical_score
    FROM ai.chunks c
    JOIN ai.documents d ON d.id = c.document_id
    WHERE {where_sql}
    ORDER BY lexical_score DESC, c.id DESC
    LIMIT %s
    """
    cur.execute(query_sql, params)
    return cur.fetchall()


def _search_exact_candidates(
    cur: RealDictCursor,
    query: str,
    numeric_tokens: List[str],
    limit: int,
) -> List[Dict[str, Any]]:
    # Специальный short-path для точных IMO/MMSI-запросов.
    # Здесь не нужен широкий recall: ищем ровно по идентификаторам.
    normalized_query = query.strip().lower()
    params: List[Any] = []
    where_parts: List[str] = []
    score_parts: List[str] = []

    for numeric_token in numeric_tokens:
        where_parts.extend(
            [
                "COALESCE(d.metadata->>'imo', '') = %s",
                "COALESCE(d.metadata->>'mmsi', '') = %s",
            ]
        )
        params.extend([numeric_token, numeric_token])
        score_parts.extend(
            [
                "CASE WHEN COALESCE(d.metadata->>'imo', '') = %s THEN 100 ELSE 0 END",
                "CASE WHEN COALESCE(d.metadata->>'mmsi', '') = %s THEN 100 ELSE 0 END",
            ]
        )
        params.extend([numeric_token, numeric_token])

    if normalized_query:
        where_parts.append("LOWER(d.title) = %s")
        params.append(normalized_query)
        score_parts.append("CASE WHEN LOWER(d.title) = %s THEN 40 ELSE 0 END")
        params.append(normalized_query)

    if not where_parts:
        return []

    query_sql = f"""
    SELECT
        c.id AS chunk_id,
        c.document_id,
        c.chunk_index,
        c.content,
        c.token_count,
        c.metadata,
        d.title,
        d.source_table,
        d.source_pk,
        d.metadata->>'imo' AS document_imo,
        d.metadata->>'mmsi' AS document_mmsi,
        d.metadata->>'flag' AS document_flag,
        d.metadata->>'general_type' AS document_general_type,
        NULL::float AS distance,
        ({" + ".join(score_parts)}) AS lexical_score
    FROM ai.chunks c
    JOIN ai.documents d ON d.id = c.document_id
    WHERE {" OR ".join(where_parts)}
    ORDER BY lexical_score DESC, c.id DESC
    LIMIT %s
    """
    params.append(limit)
    cur.execute(query_sql, params)
    return cur.fetchall()


def _parse_iso_datetime(value: str) -> datetime:
    # Принимаем ISO-строку и приводим к naive UTC для сравнения в PostgreSQL.
    raw = value.strip()
    if not raw:
        raise ValueError("updated_after must not be empty")

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _resolve_ingestion_since(
    cur: RealDictCursor,
    incremental: bool,
    updated_after: Optional[str],
) -> Optional[datetime]:
    # Определяем нижнюю границу updated_at для delta-индексации.
    if updated_after is not None:
        return _parse_iso_datetime(updated_after)

    if not incremental:
        return None

    cur.execute(
        """
        SELECT MAX(finished_at) AS finished_at
        FROM ai.ingestion_jobs
        WHERE status = 'done'
        """
    )
    row = cur.fetchone()
    if not row:
        return None
    return row.get("finished_at")


def _create_ingestion_job(meta_conn, payload: Dict[str, Any]) -> int:
    # Создаем запись job сразу, чтобы статус running был виден во время индексации.
    with meta_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO ai.ingestion_jobs(status, payload, started_at)
            VALUES ('running', %s, NOW())
            RETURNING id
            """,
            (Json(payload),),
        )
        return int(cur.fetchone()["id"])


def _update_ingestion_job(
    meta_conn,
    job_id: int,
    *,
    status: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    finished: bool = False,
) -> None:
    sets: List[str] = []
    params: List[Any] = []

    if status is not None:
        sets.append("status = %s")
        params.append(status)
    if payload is not None:
        sets.append("payload = %s")
        params.append(Json(payload))
    if error_message is not None:
        sets.append("error_message = %s")
        params.append(error_message)
    if finished:
        sets.append("finished_at = NOW()")

    if not sets:
        return

    params.append(job_id)
    sql = f"UPDATE ai.ingestion_jobs SET {', '.join(sets)} WHERE id = %s"
    with meta_conn.cursor() as cur:
        cur.execute(sql, params)


def run_ingestion(
    limit: Optional[int] = None,
    incremental: bool = False,
    updated_after: Optional[str] = None,
) -> Dict[str, int]:
    # Главная функция индексации.
    # Возвращает статистику, чтобы было понятно, сколько записей обработано.
    conn = get_db_conn()
    meta_conn = get_db_conn()
    meta_conn.autocommit = True
    job_id: Optional[int] = None
    progress_payload: Dict[str, Any] = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            has_vector_col = _has_pgvector_column(cur)
            since_ts = _resolve_ingestion_since(
                cur=cur,
                incremental=incremental,
                updated_after=updated_after,
            )

            # Берем суда из основной таблицы.
            query = """
                SELECT
                    id,
                    name,
                    imo,
                    mmsi,
                    call_sign,
                    flag,
                    general_type,
                    detailed_type,
                    year_built,
                    length,
                    width,
                    dwt,
                    gt,
                    home_port,
                    description,
                    info_source,
                    updated_at
                FROM vessels
            """
            params: List[Any] = []
            where_parts: List[str] = []

            if since_ts is not None:
                where_parts.append("updated_at IS NOT NULL AND updated_at > %s")
                params.append(since_ts)

            if where_parts:
                query += " WHERE " + " AND ".join(where_parts)

            query += " ORDER BY updated_at ASC NULLS LAST, id ASC"

            if limit is not None:
                query += " LIMIT %s"
                params.append(limit)

            cur.execute(query, params)
            vessels = cur.fetchall()

        progress_payload = {
            "limit": limit,
            "incremental": incremental,
            "updated_after": updated_after,
            "resolved_since": (since_ts.isoformat() if since_ts is not None else None),
            "progress": {
                "total": len(vessels),
                "processed": 0,
                "documents_upserted": 0,
                "chunks_upserted": 0,
            },
        }
        job_id = _create_ingestion_job(meta_conn, progress_payload)

        documents_upserted = 0
        chunks_upserted = 0

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for vessel in vessels:
                source_pk = str(vessel["id"])
                title = _clean(vessel.get("name")) or f"Vessel {source_pk}"
                profile_text = build_vessel_text(vessel)
                metadata = {
                    "imo": _clean(vessel.get("imo")),
                    "mmsi": _clean(vessel.get("mmsi")),
                    "flag": _clean(vessel.get("flag")),
                    "general_type": _clean(vessel.get("general_type")),
                    "info_source": _clean(vessel.get("info_source")),
                }

                # Upsert документа в ai.documents.
                cur.execute(
                    """
                    INSERT INTO ai.documents(source_table, source_pk, title, metadata, updated_at)
                    VALUES ('vessels', %s, %s, %s, NOW())
                    ON CONFLICT (source_table, source_pk)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (source_pk, title, Json(metadata)),
                )
                document_id = cur.fetchone()["id"]
                documents_upserted += 1

                # Чтобы не копить мусор и дубликаты,
                # перед вставкой новых chunks удаляем старые для этого документа.
                cur.execute(
                    "DELETE FROM ai.chunks WHERE document_id = %s", (document_id,)
                )

                chunks = split_into_chunks(profile_text)
                for idx, chunk in enumerate(chunks):
                    chunk_vec = build_embedding(chunk)
                    vec_literal = _vector_literal(chunk_vec)
                    if has_vector_col:
                        cur.execute(
                            """
                            INSERT INTO ai.chunks(
                                document_id,
                                chunk_index,
                                content,
                                token_count,
                                embedding,
                                embedding_vec,
                                metadata
                            )
                            VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
                            """,
                            (
                                document_id,
                                idx,
                                chunk,
                                len(chunk.split()),
                                chunk_vec,
                                vec_literal,
                                Json({"source": "vessels", "source_pk": source_pk}),
                            ),
                        )
                    else:
                        # Режим без pgvector: сохраняем только массив embedding.
                        cur.execute(
                            """
                            INSERT INTO ai.chunks(
                                document_id,
                                chunk_index,
                                content,
                                token_count,
                                embedding,
                                metadata
                            )
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                document_id,
                                idx,
                                chunk,
                                len(chunk.split()),
                                chunk_vec,
                                Json({"source": "vessels", "source_pk": source_pk}),
                            ),
                        )
                    chunks_upserted += 1

                processed = documents_upserted
                if processed % 100 == 0:
                    conn.commit()
                    progress_payload["progress"] = {
                        "total": len(vessels),
                        "processed": processed,
                        "documents_upserted": documents_upserted,
                        "chunks_upserted": chunks_upserted,
                    }
                    _update_ingestion_job(meta_conn, job_id, payload=progress_payload)

        conn.commit()
        progress_payload["progress"] = {
            "total": len(vessels),
            "processed": len(vessels),
            "documents_upserted": documents_upserted,
            "chunks_upserted": chunks_upserted,
        }
        _update_ingestion_job(
            meta_conn,
            job_id,
            status="done",
            payload=progress_payload,
            error_message="",
            finished=True,
        )
        return {
            "job_id": job_id,
            "vessels_processed": len(vessels),
            "documents_upserted": documents_upserted,
            "chunks_upserted": chunks_upserted,
        }
    except Exception as exc:
        conn.rollback()

        # Пытаемся записать ошибку в ingestion_jobs,
        # чтобы вы могли видеть причину падения прямо в БД.
        try:
            if job_id is None:
                fallback_payload = {
                    "limit": limit,
                    "incremental": incremental,
                    "updated_after": updated_after,
                }
                job_id = _create_ingestion_job(meta_conn, fallback_payload)

            progress_payload["error"] = str(exc)
            _update_ingestion_job(
                meta_conn,
                job_id,
                status="failed",
                payload=progress_payload,
                error_message=str(exc),
                finished=True,
            )
        except Exception:
            pass

        raise
    finally:
        conn.close()
        meta_conn.close()


def list_ingestion_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    # Возвращает последние записи о запусках индексации.
    # Это помогает быстро понимать, что происходило с ingestion-процессом:
    # - когда запускали;
    # - успешно ли завершилось;
    # - была ли ошибка.
    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, status, payload, error_message, created_at, started_at, finished_at
                FROM ai.ingestion_jobs
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def search_chunks(
    query: str,
    limit: int = 5,
    mode: str = "hybrid",
    max_distance: Optional[float] = None,
) -> List[Dict[str, Any]]:
    # Базовый retrieval по chunks через ILIKE.
    #
    # Это промежуточный этап до внедрения pgvector:
    # - уже можно искать релевантные куски текста;
    # - уже можно строить прототип RAG-ответа;
    # - позже легко заменить эту функцию на vector similarity.
    #
    # Поддерживаем 3 режима:
    # - hybrid: vector search с lexical fallback;
    # - vector: только vector similarity;
    # - lexical: только текстовый поиск.
    # Разбиваем запрос на токены, чтобы искать не только по полной фразе,
    # но и по отдельным значимым словам (Panama, container, tanker и т.д.).
    tokens = _normalize_query_tokens(query)
    numeric_tokens = _extract_numeric_tokens(query)
    mode = (mode or "hybrid").strip().lower()
    if mode not in {"hybrid", "vector", "lexical", "exact"}:
        mode = "hybrid"

    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            vector_rows: List[Dict[str, Any]] = []
            lexical_rows: List[Dict[str, Any]] = []

            if mode == "exact":
                return _search_exact_candidates(
                    cur=cur,
                    query=query,
                    numeric_tokens=numeric_tokens,
                    limit=limit,
                )

            # Сначала пробуем vector similarity, если pgvector доступен.
            if mode in {"hybrid", "vector"}:
                try:
                    vector_rows = _search_vector_candidates(
                        cur=cur,
                        query=query,
                        limit=limit,
                        max_distance=max_distance,
                    )
                    if mode == "vector":
                        return vector_rows
                except Exception:
                    # Если vector-режим недоступен, продолжаем с lexical fallback.
                    conn.rollback()
                    if mode == "vector":
                        return []

            if mode == "vector":
                return []

            lexical_rows = _search_lexical_candidates(
                cur=cur,
                query=query,
                tokens=tokens,
                numeric_tokens=numeric_tokens,
                limit=limit,
            )

            if mode == "lexical":
                return lexical_rows

            # Hybrid: объединяем оба набора кандидатов и отдаем единый пул.
            return _merge_candidate_rows(
                vector_rows=vector_rows,
                lexical_rows=lexical_rows,
                limit=limit,
            )
    finally:
        conn.close()
