"""
Основной REST API для каталога судов.

Назначение модуля:
- отдавать список и карточки судов;
- выполнять фильтрацию, сортировку и пагинацию;
- поддерживать частичное обновление записей;
- предоставлять статистику и экспорт данных.

Стиль комментариев:
- поясняем архитектурные решения и ограничения;
- в docstring фиксируем вход/выход и поведение при ошибках.
"""

import csv
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from ais_shared.db import get_db_cursor
from ais_shared.log_setup import configure_service_logging

app = FastAPI()
IMAGES_BASE_DIR = Path("/app/images").resolve()
logger = logging.getLogger(__name__)
configure_service_logging("vessel_api")


def _raise_internal_error(exc: Exception, context: str) -> None:
    logger.exception("%s: %s", context, exc)
    raise HTTPException(status_code=500, detail="Internal server error")


# CORS для frontend.
# Управляется через CORS_ALLOW_ORIGINS:
# - "*" для полного открытия;
# - "http://localhost:3000,http://127.0.0.1:3000" для списка origin.
cors_origins_env = os.getenv(
    "CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
allow_origins = (
    ["*"]
    if cors_origins_env.strip() == "*"
    else [
        origin.strip()
        for origin in cors_origins_env.split(",")
        if origin.strip()
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Vessel(BaseModel):
    id: int | None = None
    name: str
    imo: str
    mmsi: str
    call_sign: str
    general_type: str | None = None
    detailed_type: str | None = None
    flag: str
    year_built: int | None = None
    length: int | None = None
    width: int | None = None
    dwt: int | None = None
    gt: int | None = None
    home_port: str | None = None
    photo_path: str | None = None
    description: str | None = None
    info_source: str
    updated_at: datetime | None = None


class VesselListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    vessels: list[Vessel]


class VesselUpdate(BaseModel):
    name: str | None = None
    imo: str | None = None
    mmsi: str | None = None
    call_sign: str | None = None
    general_type: str | None = None
    detailed_type: str | None = None
    flag: str | None = None
    year_built: int | None = None
    length: int | None = None
    width: int | None = None
    dwt: int | None = None
    gt: int | None = None
    home_port: str | None = None
    description: str | None = None


class VesselNote(BaseModel):
    note_uuid: str
    vessel_id: int
    body: str
    author: str | None = None
    source_node: str
    sync_version: int
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class VesselNoteCreate(BaseModel):
    body: str
    author: str | None = None


class VesselNoteUpdate(BaseModel):
    body: str | None = None
    author: str | None = None
    deleted: bool | None = None


class NotesPullRequest(BaseModel):
    since: str | None = None
    limit: int = 500


class NotesPushItem(BaseModel):
    note_uuid: str
    vessel_imo_or_mmsi: str
    body: str
    author: str | None = None
    source_node: str = "remote"
    sync_version: int = 1
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class NotesPushRequest(BaseModel):
    source_node: str
    notes: list[NotesPushItem]


class StatsResponse(BaseModel):
    total_vessels: int
    vessel_types: list[dict]
    flags: list[dict]


class ScraperStatus(BaseModel):
    scraper_name: str
    mode: str
    last_page: int
    vessels_count: int
    last_run_at: str | None


class ScraperMonitorResponse(BaseModel):
    total_scrapers: int
    total_vessels: int
    states: list[ScraperStatus]


class DatabaseHealth(BaseModel):
    ok: bool
    detail: str | None = None


class ScraperStateItem(BaseModel):
    scraper_name: str
    mode: str
    last_page: int
    vessels_count: int
    last_run_at: str | None = None
    last_data_at: str | None = None
    activity: str = Field(
        description="recent | stale | never — по last_run_at и SCRAPER_STALE_AFTER_MINUTES"
    )


class IngestionSourceBlock(BaseModel):
    source_name: str
    priority: int
    description: str | None = None
    is_active: bool
    scrapers: list[ScraperStateItem]


class IngestionStatsResponse(BaseModel):
    database: DatabaseHealth
    total_vessels: int | None
    stale_after_minutes: int
    sources: list[IngestionSourceBlock]
    orphan_scrapers: list[ScraperStateItem]
    generated_at: str


def _stale_after_delta() -> timedelta:
    raw = os.getenv("SCRAPER_STALE_AFTER_MINUTES", "120").strip()
    try:
        minutes = max(1, int(raw))
    except ValueError:
        minutes = 120
    return timedelta(minutes=minutes)


def _scraper_activity(
    last_run_at: datetime | None, stale_after: timedelta
) -> str:
    if last_run_at is None:
        return "never"
    now = datetime.now(timezone.utc)
    ts = last_run_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now - ts > stale_after:
        return "stale"
    return "recent"


def _serialize_scraper_row(
    row: dict, stale_after: timedelta, last_data_at: datetime | None = None
) -> dict:
    lr = row.get("last_run_at")
    return {
        "scraper_name": row["scraper_name"],
        "mode": row["mode"],
        "last_page": int(row["last_page"]),
        "vessels_count": int(row["vessels_count"]),
        "last_run_at": lr.isoformat() if lr else None,
        "last_data_at": (
            last_data_at.isoformat() if last_data_at is not None else None
        ),
        "activity": _scraper_activity(lr, stale_after),
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: процесс отвечает (без проверки БД)."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Readiness: доступность PostgreSQL."""
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as exc:
        logger.exception("readiness check failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="database unavailable"
        ) from exc
    return {"status": "ready"}


@app.get("/monitor/scrapers", response_model=ScraperMonitorResponse)
def monitor_scrapers() -> dict:
    """Состояние ingestion-контуров по таблице scraper_state."""
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT scraper_name, mode, last_page, vessels_count, last_run_at
                FROM scraper_state
                ORDER BY scraper_name, mode
                """
            )
            rows = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS total FROM vessels")
            total_vessels = cur.fetchone()["total"]

        states = []
        for row in rows:
            states.append(
                {
                    "scraper_name": row["scraper_name"],
                    "mode": row["mode"],
                    "last_page": row["last_page"],
                    "vessels_count": row["vessels_count"],
                    "last_run_at": (
                        row["last_run_at"].isoformat()
                        if row["last_run_at"]
                        else None
                    ),
                }
            )
        return {
            "total_scrapers": len(states),
            "total_vessels": total_vessels,
            "states": states,
        }
    except Exception as exc:
        _raise_internal_error(exc, "monitor_scrapers")


@app.get("/stats/ingestion", response_model=IngestionStatsResponse)
def stats_ingestion() -> dict:
    """Сводка для UI мониторинга: БД, приоритеты источников и состояние скраперов.

    Список источников строится по `source_priority`; строки `scraper_state`
    сопоставляются по равенству `scraper_name` и `source_name`. Записи
    состояния без записи в `source_priority` попадают в `orphan_scrapers`.
    Активность (`activity`) — эвристика по `last_run_at` и порогу
    SCRAPER_STALE_AFTER_MINUTES (по умолчанию 120).
    """
    stale_after = _stale_after_delta()
    generated = datetime.now(timezone.utc).isoformat()
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT 1")
            cur.execute("SELECT COUNT(*) AS total FROM vessels")
            total_vessels = int(cur.fetchone()["total"])
            cur.execute(
                """
                SELECT source_name, priority, description, is_active
                FROM source_priority
                ORDER BY priority ASC, source_name ASC
                """
            )
            priority_rows = cur.fetchall()
            cur.execute(
                """
                SELECT scraper_name, mode, last_page, vessels_count, last_run_at
                FROM scraper_state
                ORDER BY scraper_name ASC, mode ASC
                """
            )
            state_rows = cur.fetchall()
            cur.execute(
                """
                SELECT info_source, MAX(updated_at) AS last_data_at
                FROM vessels
                WHERE info_source IS NOT NULL
                GROUP BY info_source
                """
            )
            source_last_data_rows = cur.fetchall()
    except Exception as exc:
        logger.exception("stats_ingestion database error: %s", exc)
        return {
            "database": {"ok": False, "detail": "database unavailable"},
            "total_vessels": None,
            "stale_after_minutes": int(stale_after.total_seconds() // 60),
            "sources": [],
            "orphan_scrapers": [],
            "generated_at": generated,
        }

    by_name: dict[str, list] = {}
    for row in state_rows:
        by_name.setdefault(row["scraper_name"], []).append(row)
    last_data_by_source = {
        r["info_source"]: r["last_data_at"]
        for r in source_last_data_rows
        if r["info_source"]
    }

    catalog_names = {r["source_name"] for r in priority_rows}
    orphan: list[dict] = []
    for name, rows in by_name.items():
        if name not in catalog_names:
            for r in rows:
                orphan.append(
                    _serialize_scraper_row(
                        r, stale_after, last_data_by_source.get(name)
                    )
                )

    sources_out: list[dict] = []
    for pr in priority_rows:
        sn = pr["source_name"]
        scrapers = [
            _serialize_scraper_row(
                r, stale_after, last_data_by_source.get(sn)
            )
            for r in by_name.get(sn, [])
        ]
        sources_out.append(
            {
                "source_name": sn,
                "priority": int(pr["priority"]),
                "description": pr["description"],
                "is_active": bool(pr["is_active"]),
                "scrapers": scrapers,
            }
        )

    return {
        "database": {"ok": True, "detail": None},
        "total_vessels": total_vessels,
        "stale_after_minutes": int(stale_after.total_seconds() // 60),
        "sources": sources_out,
        "orphan_scrapers": orphan,
        "generated_at": generated,
    }


@app.get("/metrics")
def metrics() -> StreamingResponse:
    """Экспорт базовых метрик ingestion для Prometheus."""
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS total FROM vessels")
            total_vessels = cur.fetchone()["total"]
            cur.execute(
                """
                SELECT scraper_name, mode, last_page, vessels_count
                FROM scraper_state
                ORDER BY scraper_name, mode
                """
            )
            rows = cur.fetchall()

        lines = [
            "# HELP ais_vessels_total Total vessels in database.",
            "# TYPE ais_vessels_total gauge",
            f"ais_vessels_total {int(total_vessels)}",
            "# HELP ais_scraper_last_page Last scraped page per scraper/mode.",
            "# TYPE ais_scraper_last_page gauge",
            "# HELP ais_scraper_vessels_count Vessels processed per scraper/mode.",
            "# TYPE ais_scraper_vessels_count gauge",
        ]
        for row in rows:
            name = str(row["scraper_name"]).replace('"', '\\"')
            mode = str(row["mode"]).replace('"', '\\"')
            lines.append(
                f'ais_scraper_last_page{{scraper="{name}",mode="{mode}"}} '
                f"{int(row['last_page'])}"
            )
            lines.append(
                f'ais_scraper_vessels_count{{scraper="{name}",mode="{mode}"}} '
                f"{int(row['vessels_count'])}"
            )
        payload = "\n".join(lines) + "\n"
        return StreamingResponse(
            BytesIO(payload.encode("utf-8")),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
    except Exception as exc:
        _raise_internal_error(exc, "metrics")


def _serialize_note_row(row: dict) -> dict:
    return {
        "note_uuid": row["note_uuid"],
        "vessel_id": row["vessel_id"],
        "body": row["body"],
        "author": row["author"],
        "source_node": row["source_node"],
        "sync_version": row["sync_version"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "deleted_at": (
            row["deleted_at"].isoformat() if row["deleted_at"] else None
        ),
    }


def _get_vessel_id_by_key(cur, imo_or_mmsi: str) -> int:
    cur.execute(
        "SELECT id FROM vessels WHERE imo = %s OR mmsi = %s",
        (imo_or_mmsi, imo_or_mmsi),
    )
    vessel = cur.fetchone()
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")
    return vessel["id"]


@app.get("/vessels/{imo}/notes", response_model=list[VesselNote])
def get_vessel_notes(imo: str, include_deleted: bool = Query(False)):
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            vessel_id = _get_vessel_id_by_key(cur, imo)
            if include_deleted:
                cur.execute(
                    """
                    SELECT note_uuid, vessel_id, body, author, source_node,
                           sync_version, created_at, updated_at, deleted_at
                    FROM vessel_notes
                    WHERE vessel_id = %s
                    ORDER BY updated_at DESC
                    """,
                    (vessel_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT note_uuid, vessel_id, body, author, source_node,
                           sync_version, created_at, updated_at, deleted_at
                    FROM vessel_notes
                    WHERE vessel_id = %s AND deleted_at IS NULL
                    ORDER BY updated_at DESC
                    """,
                    (vessel_id,),
                )
            rows = cur.fetchall()
        return [_serialize_note_row(row) for row in rows]
    except HTTPException:
        raise
    except Exception as exc:
        _raise_internal_error(exc, "get_vessel_notes")


@app.post("/vessels/{imo}/notes", response_model=VesselNote)
def create_vessel_note(imo: str, payload: VesselNoteCreate):
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Note body is empty")
    try:
        with get_db_cursor(cursor_factory=RealDictCursor, commit=True) as cur:
            vessel_id = _get_vessel_id_by_key(cur, imo)
            note_uuid = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO vessel_notes (
                    note_uuid, vessel_id, body, author, source_node, sync_version
                )
                VALUES (%s, %s, %s, %s, %s, 1)
                RETURNING note_uuid, vessel_id, body, author, source_node,
                          sync_version, created_at, updated_at, deleted_at
                """,
                (note_uuid, vessel_id, body, payload.author, "local"),
            )
            row = cur.fetchone()
        return _serialize_note_row(row)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_internal_error(exc, "create_vessel_note")


@app.patch("/notes/{note_uuid}", response_model=VesselNote)
def update_vessel_note(note_uuid: str, payload: VesselNoteUpdate):
    try:
        with get_db_cursor(cursor_factory=RealDictCursor, commit=True) as cur:
            cur.execute(
                """
                SELECT note_uuid, vessel_id, body, author, source_node,
                       sync_version, created_at, updated_at, deleted_at
                FROM vessel_notes
                WHERE note_uuid = %s
                """,
                (note_uuid,),
            )
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Note not found")

            body = (
                payload.body.strip()
                if payload.body is not None
                else existing["body"]
            )
            if not body:
                raise HTTPException(
                    status_code=400, detail="Note body is empty"
                )
            author = (
                payload.author
                if payload.author is not None
                else existing["author"]
            )
            deleted_at = existing["deleted_at"]
            if payload.deleted is True:
                deleted_at = datetime.utcnow()
            elif payload.deleted is False:
                deleted_at = None

            cur.execute(
                """
                UPDATE vessel_notes
                SET body = %s,
                    author = %s,
                    deleted_at = %s,
                    sync_version = sync_version + 1,
                    updated_at = NOW()
                WHERE note_uuid = %s
                RETURNING note_uuid, vessel_id, body, author, source_node,
                          sync_version, created_at, updated_at, deleted_at
                """,
                (body, author, deleted_at, note_uuid),
            )
            row = cur.fetchone()
        return _serialize_note_row(row)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_internal_error(exc, "update_vessel_note")


@app.delete("/notes/{note_uuid}", response_model=VesselNote)
def delete_vessel_note(note_uuid: str):
    return update_vessel_note(note_uuid, VesselNoteUpdate(deleted=True))


@app.post("/sync/notes/pull")
def sync_notes_pull(payload: NotesPullRequest):
    limit = min(max(payload.limit, 1), 2000)
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            if payload.since:
                since_ts = datetime.fromisoformat(payload.since)
                cur.execute(
                    """
                    SELECT n.note_uuid, n.vessel_id, n.body, n.author,
                           n.source_node, n.sync_version, n.created_at,
                           n.updated_at, n.deleted_at, v.imo, v.mmsi
                    FROM vessel_notes n
                    JOIN vessels v ON v.id = n.vessel_id
                    WHERE n.updated_at > %s
                    ORDER BY n.updated_at ASC
                    LIMIT %s
                    """,
                    (since_ts, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT n.note_uuid, n.vessel_id, n.body, n.author,
                           n.source_node, n.sync_version, n.created_at,
                           n.updated_at, n.deleted_at, v.imo, v.mmsi
                    FROM vessel_notes n
                    JOIN vessels v ON v.id = n.vessel_id
                    ORDER BY n.updated_at ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
            rows = cur.fetchall()

        notes = []
        last_sync = payload.since
        for row in rows:
            serialized = _serialize_note_row(row)
            serialized["vessel_imo_or_mmsi"] = row["imo"] or row["mmsi"]
            notes.append(serialized)
            last_sync = serialized["updated_at"]
        return {"notes": notes, "next_since": last_sync}
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid 'since' timestamp format"
        ) from exc
    except Exception as exc:
        _raise_internal_error(exc, "sync_notes_pull")


@app.post("/sync/notes/push")
def sync_notes_push(payload: NotesPushRequest):
    upserted = 0
    skipped = 0
    try:
        with get_db_cursor(cursor_factory=RealDictCursor, commit=True) as cur:
            for note in payload.notes:
                vessel_id = _get_vessel_id_by_key(cur, note.vessel_imo_or_mmsi)
                created_at = datetime.fromisoformat(note.created_at)
                updated_at = datetime.fromisoformat(note.updated_at)
                deleted_at = (
                    datetime.fromisoformat(note.deleted_at)
                    if note.deleted_at
                    else None
                )

                cur.execute(
                    """
                    SELECT sync_version, updated_at
                    FROM vessel_notes
                    WHERE note_uuid = %s
                    """,
                    (note.note_uuid,),
                )
                existing = cur.fetchone()
                should_apply = existing is None
                if existing:
                    existing_version = int(existing["sync_version"])
                    existing_updated = existing["updated_at"]
                    should_apply = note.sync_version > existing_version or (
                        note.sync_version == existing_version
                        and updated_at > existing_updated
                    )

                if not should_apply:
                    skipped += 1
                    continue

                cur.execute(
                    """
                    INSERT INTO vessel_notes (
                        note_uuid, vessel_id, body, author, source_node,
                        sync_version, created_at, updated_at, deleted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (note_uuid) DO UPDATE
                    SET vessel_id = EXCLUDED.vessel_id,
                        body = EXCLUDED.body,
                        author = EXCLUDED.author,
                        source_node = EXCLUDED.source_node,
                        sync_version = EXCLUDED.sync_version,
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at,
                        deleted_at = EXCLUDED.deleted_at
                    """,
                    (
                        note.note_uuid,
                        vessel_id,
                        note.body,
                        note.author,
                        note.source_node or payload.source_node,
                        note.sync_version,
                        created_at,
                        updated_at,
                        deleted_at,
                    ),
                )
                upserted += 1
        return {"upserted": upserted, "skipped": skipped}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid timestamp format in notes payload",
        ) from exc
    except Exception as exc:
        _raise_internal_error(exc, "sync_notes_push")


@app.get("/vessels/", response_model=VesselListResponse)
def get_vessels(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    vessel_types: str | None = Query(None),
    flags: str | None = Query(None),
    info_sources: str | None = Query(None),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
    sort_by: str | None = Query("name"),
    sort_order: str | None = Query("asc"),
):
    """Получить список судов с фильтрацией, поиском, сортировкой и пагинацией.

    Параметры:
    - page/per_page: параметры пагинации;
    - search: строка поиска по name/imo/mmsi;
    - vessel_types/flags/info_sources: мультивыборные фильтры;
    - year_from/year_to: диапазон по году постройки;
    - sort_by/sort_order: сортировка только по whitelist-полям.

    Возвращает:
    - объект с total/page/per_page/vessels.
    """
    try:
        # Базовый запрос
        where_clauses = []
        params = []

        # Полнотекстовый поиск
        if search:
            where_clauses.append(
                "(name ILIKE %s OR imo ILIKE %s OR mmsi ILIKE %s)"
            )
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])

        # Фильтр по типам судов (мультивыбор)
        if vessel_types:
            types_list = vessel_types.split(",")
            placeholders = ",".join(["%s"] * len(types_list))
            where_clauses.append(f"general_type IN ({placeholders})")
            params.extend(types_list)

        # Фильтр по флагам (мультивыбор)
        if flags:
            flags_list = flags.split(",")
            placeholders = ",".join(["%s"] * len(flags_list))
            where_clauses.append(f"flag IN ({placeholders})")
            params.extend(flags_list)

        # Фильтр по источникам (мультивыбор)
        if info_sources:
            sources_list = info_sources.split(",")
            placeholders = ",".join(["%s"] * len(sources_list))
            where_clauses.append(f"info_source IN ({placeholders})")
            params.extend(sources_list)

        # Фильтр по годам
        if year_from:
            where_clauses.append("year_built >= %s")
            params.append(year_from)
        if year_to:
            where_clauses.append("year_built <= %s")
            params.append(year_to)

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Сортировка
        allowed_sort_fields = [
            "name",
            "imo",
            "mmsi",
            "general_type",
            "detailed_type",
            "flag",
            "year_built",
            "length",
            "width",
            "dwt",
            "gt",
            "home_port",
            "updated_at",
        ]
        if sort_by not in allowed_sort_fields:
            sort_by = "name"
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        offset = (page - 1) * per_page
        query = f"""
            SELECT
                id,
                COALESCE(TRIM(name),'') AS name,
                COALESCE(imo,'') AS imo,
                COALESCE(mmsi,'') AS mmsi,
                COALESCE(call_sign,'') AS call_sign,
                general_type,
                detailed_type,
                COALESCE(flag,'') AS flag,
                year_built,
                length,
                width,
                dwt,
                gt,
                home_port,
                photo_path,
                description,
                COALESCE(info_source,'') AS info_source,
                updated_at
            FROM vessels
            WHERE {where_clause}
            ORDER BY {sort_by} {sort_direction}
            LIMIT %s OFFSET %s
        """
        count_params = list(params)
        query_params = list(params) + [per_page, offset]

        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            # Подсчет общего количества
            cur.execute(
                f"SELECT COUNT(*) as total FROM vessels WHERE {where_clause}",
                count_params,
            )
            total = cur.fetchone()["total"]
            cur.execute(query, query_params)
            vessels = cur.fetchall()

        # COALESCE в запросе уже гарантирует отсутствие NULL в обязательных строках
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "vessels": vessels,
        }
    except Exception as e:
        _raise_internal_error(e, "get_vessels")


@app.get("/vessels/{imo}", response_model=Vessel)
def get_vessel_by_imo(imo: str):
    """Получить детальную информацию о судне по IMO или MMSI.

    Параметры:
    - imo: значение IMO или MMSI (поддерживается оба варианта).

    Ошибки:
    - 404, если запись не найдена.
    """
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
            SELECT
                id,
                COALESCE(TRIM(name),'') AS name,
                COALESCE(imo,'') AS imo,
                COALESCE(mmsi,'') AS mmsi,
                COALESCE(call_sign,'') AS call_sign,
                general_type,
                detailed_type,
                COALESCE(flag,'') AS flag,
                year_built,
                length,
                width,
                dwt,
                gt,
                home_port,
                photo_path,
                description,
                COALESCE(info_source,'') AS info_source,
                updated_at
            FROM vessels
            WHERE imo = %s OR mmsi = %s
            """,
                (imo, imo),
            )
            vessel = cur.fetchone()

        if not vessel:
            raise HTTPException(status_code=404, detail="Vessel not found")

        return vessel
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_error(e, "get_vessel_by_imo")


@app.patch("/vessels/{imo}", response_model=Vessel)
def update_vessel(imo: str, vessel_update: VesselUpdate):
    """Частично обновить информацию о судне.

    Особенности:
    - обновляются только поля, переданные в payload;
    - автоматически обновляется updated_at;
    - поиск записи выполняется по IMO или MMSI.
    """
    try:
        # Строим динамический UPDATE запрос
        update_fields = []
        params = []

        if vessel_update.name is not None:
            update_fields.append("name = %s")
            params.append(vessel_update.name.strip())
        if vessel_update.imo is not None:
            update_fields.append("imo = %s")
            params.append(vessel_update.imo.strip())
        if vessel_update.mmsi is not None:
            update_fields.append("mmsi = %s")
            params.append(vessel_update.mmsi.strip())
        if vessel_update.call_sign is not None:
            update_fields.append("call_sign = %s")
            params.append(vessel_update.call_sign.strip())
        if vessel_update.general_type is not None:
            update_fields.append("general_type = %s")
            params.append(vessel_update.general_type)
        if vessel_update.detailed_type is not None:
            update_fields.append("detailed_type = %s")
            params.append(vessel_update.detailed_type)
        if vessel_update.flag is not None:
            update_fields.append("flag = %s")
            params.append(vessel_update.flag.strip())
        if vessel_update.year_built is not None:
            update_fields.append("year_built = %s")
            params.append(vessel_update.year_built)
        if vessel_update.length is not None:
            update_fields.append("length = %s")
            params.append(vessel_update.length)
        if vessel_update.width is not None:
            update_fields.append("width = %s")
            params.append(vessel_update.width)
        if vessel_update.dwt is not None:
            update_fields.append("dwt = %s")
            params.append(vessel_update.dwt)
        if vessel_update.gt is not None:
            update_fields.append("gt = %s")
            params.append(vessel_update.gt)
        if vessel_update.home_port is not None:
            update_fields.append("home_port = %s")
            params.append(vessel_update.home_port)
        if vessel_update.description is not None:
            update_fields.append("description = %s")
            params.append(vessel_update.description)

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Добавляем updated_at
        update_fields.append("updated_at = NOW()")
        params.extend([imo, imo])

        query = f"""
            UPDATE vessels
            SET {", ".join(update_fields)}
            WHERE imo = %s OR mmsi = %s
            RETURNING
                id,
                COALESCE(TRIM(name),'') AS name,
                COALESCE(imo,'') AS imo,
                COALESCE(mmsi,'') AS mmsi,
                COALESCE(call_sign,'') AS call_sign,
                general_type,
                detailed_type,
                COALESCE(flag,'') AS flag,
                year_built,
                length,
                width,
                dwt,
                gt,
                home_port,
                photo_path,
                description,
                COALESCE(info_source,'') AS info_source,
                updated_at
        """

        with get_db_cursor(cursor_factory=RealDictCursor, commit=True) as cur:
            # Проверяем существование судна
            cur.execute(
                "SELECT id FROM vessels WHERE imo = %s OR mmsi = %s",
                (imo, imo),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Vessel not found")
            cur.execute(query, params)
            updated_vessel = cur.fetchone()

        return updated_vessel
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_error(e, "update_vessel")


@app.get("/vessels/stats/summary", response_model=StatsResponse)
def get_stats():
    """Получить агрегированную статистику по базе судов.

    Возвращает:
    - общее число записей;
    - распределение по general_type;
    - распределение по flag.
    """
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            # Общее количество
            cur.execute("SELECT COUNT(*) as total FROM vessels")
            total = cur.fetchone()["total"]

            # Статистика по типам
            cur.execute(
                """
            SELECT general_type, COUNT(*) as count
            FROM vessels
            WHERE general_type IS NOT NULL
            GROUP BY general_type
            ORDER BY count DESC
        """
            )
            vessel_types = cur.fetchall()

            # Статистика по флагам
            cur.execute(
                """
            SELECT flag, COUNT(*) as count
            FROM vessels
            GROUP BY flag
            ORDER BY count DESC
        """
            )
            flags = cur.fetchall()

        return {
            "total_vessels": total,
            "vessel_types": vessel_types,
            "flags": flags,
        }
    except Exception as e:
        _raise_internal_error(e, "get_stats")


@app.get("/vessels/stats/sources")
def get_sources():
    """Получить список источников данных с количеством судов."""
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
            SELECT info_source, COUNT(*) as count
            FROM vessels
            WHERE info_source IS NOT NULL
            GROUP BY info_source
            ORDER BY count DESC
        """
            )
            sources = cur.fetchall()

        return {"sources": sources}
    except Exception as e:
        _raise_internal_error(e, "get_sources")


@app.get("/vessels/export/{format}")
def export_vessels(
    format: str,
    search: str | None = Query(None),
    vessel_types: str | None = Query(None),
    flags: str | None = Query(None),
    info_sources: str | None = Query(None),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
):
    """Экспорт отфильтрованного набора судов.

    Поддерживаемые форматы:
    - csv
    - json

    Примечание:
    - фильтры полностью совпадают с endpoint /vessels/,
      чтобы выгрузка соответствовала текущему состоянию UI.
    """
    try:
        # Те же фильтры, что и в get_vessels
        where_clauses = []
        params = []

        if search:
            where_clauses.append(
                "(name ILIKE %s OR imo ILIKE %s OR mmsi ILIKE %s)"
            )
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])

        if vessel_types:
            types_list = vessel_types.split(",")
            placeholders = ",".join(["%s"] * len(types_list))
            where_clauses.append(f"general_type IN ({placeholders})")
            params.extend(types_list)

        if flags:
            flags_list = flags.split(",")
            placeholders = ",".join(["%s"] * len(flags_list))
            where_clauses.append(f"flag IN ({placeholders})")
            params.extend(flags_list)

        if info_sources:
            sources_list = info_sources.split(",")
            placeholders = ",".join(["%s"] * len(sources_list))
            where_clauses.append(f"info_source IN ({placeholders})")
            params.extend(sources_list)

        if year_from:
            where_clauses.append("year_built >= %s")
            params.append(year_from)
        if year_to:
            where_clauses.append("year_built <= %s")
            params.append(year_to)

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        query = f"SELECT * FROM vessels WHERE {where_clause}"

        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            vessels = cur.fetchall()

        if format.lower() == "csv":
            output = StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=vessels[0].keys() if vessels else [],
                extrasaction="ignore",
            )
            writer.writeheader()
            for vessel in vessels:
                writer.writerow(vessel)
            csv_bytes = output.getvalue().encode("utf-8")
            return StreamingResponse(
                BytesIO(csv_bytes),
                media_type="text/csv",
                headers={
                    "Content-Disposition": "attachment; filename=vessels.csv"
                },
            )
        elif format.lower() == "json":
            # Преобразуем datetime в строки
            for vessel in vessels:
                if vessel.get("updated_at"):
                    vessel["updated_at"] = vessel["updated_at"].isoformat()
            json_data = json.dumps(vessels, indent=2, ensure_ascii=False)
            return StreamingResponse(
                BytesIO(json_data.encode("utf-8")),
                media_type="application/json",
                headers={
                    "Content-Disposition": "attachment; filename=vessels.json"
                },
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported format. Use 'csv' or 'json'",
            )
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_error(e, "export_vessels")


@app.get("/images/{filename}")
def get_image(filename: str):
    """Отдать фото судна из локального каталога изображений."""
    candidate = (IMAGES_BASE_DIR / filename).resolve()
    if (
        IMAGES_BASE_DIR not in candidate.parents
        and candidate != IMAGES_BASE_DIR
    ):
        raise HTTPException(status_code=400, detail="Invalid image path")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(candidate))


@app.post("/vessels/")
def add_vessel(vessel: Vessel):
    """Добавить новую запись судна в базу.

    Примечание:
    - имя нормализуется (сжатие множественных пробелов),
      чтобы уменьшить дубликаты из-за разных форматов источников.
    """
    try:
        with get_db_cursor(commit=True) as cur:
            name_clean = " ".join(
                vessel.name.split()
            )  # сжатие множественных пробелов
            cur.execute(
                """
                INSERT INTO vessels (
                    name, imo, mmsi, call_sign, general_type, detailed_type, flag, year_built, length, width, dwt, gt, home_port, photo_path, description, info_source, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    name_clean,
                    vessel.imo,
                    vessel.mmsi,
                    vessel.call_sign,
                    vessel.general_type,
                    vessel.detailed_type,
                    vessel.flag,
                    vessel.year_built,
                    vessel.length,
                    vessel.width,
                    vessel.dwt,
                    vessel.gt,
                    vessel.home_port,
                    vessel.photo_path,
                    vessel.description,
                    vessel.info_source,
                    vessel.updated_at or datetime.utcnow(),
                ),
            )
        return {"status": "success"}
    except Exception as e:
        _raise_internal_error(e, "add_vessel")
