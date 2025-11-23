import csv
import json
import os
from datetime import datetime
from io import BytesIO
from typing import List, Optional

import psycopg2
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

app = FastAPI()

# CORS для frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Vessel(BaseModel):
    id: Optional[int] = None
    name: str
    imo: str
    mmsi: str
    call_sign: str
    general_type: Optional[str] = None
    detailed_type: Optional[str] = None
    flag: str
    year_built: Optional[int] = None
    length: Optional[int] = None
    width: Optional[int] = None
    dwt: Optional[int] = None
    gt: Optional[int] = None
    home_port: Optional[str] = None
    photo_path: Optional[str] = None
    description: Optional[str] = None
    info_source: str
    updated_at: Optional[datetime] = None


class VesselListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    vessels: List[Vessel]


class VesselUpdate(BaseModel):
    name: Optional[str] = None
    imo: Optional[str] = None
    mmsi: Optional[str] = None
    call_sign: Optional[str] = None
    general_type: Optional[str] = None
    detailed_type: Optional[str] = None
    flag: Optional[str] = None
    year_built: Optional[int] = None
    length: Optional[int] = None
    width: Optional[int] = None
    dwt: Optional[int] = None
    gt: Optional[int] = None
    home_port: Optional[str] = None
    description: Optional[str] = None


class StatsResponse(BaseModel):
    total_vessels: int
    vessel_types: List[dict]
    flags: List[dict]


def get_db_conn():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "vessels_db"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )


@app.get("/vessels/", response_model=VesselListResponse)
def get_vessels(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    vessel_types: Optional[str] = Query(None),
    flags: Optional[str] = Query(None),
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
    sort_by: Optional[str] = Query("name"),
    sort_order: Optional[str] = Query("asc"),
):
    """Получить список судов с фильтрацией, поиском, сортировкой и пагинацией"""
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Базовый запрос
        where_clauses = []
        params = []

        # Полнотекстовый поиск
        if search:
            where_clauses.append("(name ILIKE %s OR imo ILIKE %s OR mmsi ILIKE %s)")
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

        # Фильтр по годам
        if year_from:
            where_clauses.append("year_built >= %s")
            params.append(year_from)
        if year_to:
            where_clauses.append("year_built <= %s")
            params.append(year_to)

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Подсчет общего количества
        cur.execute(
            f"SELECT COUNT(*) as total FROM vessels WHERE {where_clause}", params
        )
        total = cur.fetchone()["total"]

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

        # Запрос с пагинацией (COALESCE для обязательных строковых полей)
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
        params.extend([per_page, offset])
        cur.execute(query, params)
        vessels = cur.fetchall()

        cur.close()
        conn.close()

        # COALESCE в запросе уже гарантирует отсутствие NULL в обязательных строках
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "vessels": vessels,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vessels/{imo}", response_model=Vessel)
def get_vessel_by_imo(imo: str):
    """Получить детальную информацию о судне по IMO или MMSI"""
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
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
        cur.close()
        conn.close()

        if not vessel:
            raise HTTPException(status_code=404, detail="Vessel not found")

        return vessel
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/vessels/{imo}", response_model=Vessel)
def update_vessel(imo: str, vessel_update: VesselUpdate):
    """Обновить информацию о судне"""
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Проверяем существование судна
        cur.execute("SELECT id FROM vessels WHERE imo = %s OR mmsi = %s", (imo, imo))
        if not cur.fetchone():
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Vessel not found")

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

        cur.execute(query, params)
        updated_vessel = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return updated_vessel
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vessels/stats/summary", response_model=StatsResponse)
def get_stats():
    """Получить статистику по базе данных"""
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)

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

        cur.close()
        conn.close()

        return {
            "total_vessels": total,
            "vessel_types": vessel_types,
            "flags": flags,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/vessels/export/{format}")
def export_vessels(
    format: str,
    search: Optional[str] = Query(None),
    vessel_types: Optional[str] = Query(None),
    flags: Optional[str] = Query(None),
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
):
    """Экспорт данных в CSV, JSON или Excel"""
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Те же фильтры, что и в get_vessels
        where_clauses = []
        params = []

        if search:
            where_clauses.append("(name ILIKE %s OR imo ILIKE %s OR mmsi ILIKE %s)")
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

        if year_from:
            where_clauses.append("year_built >= %s")
            params.append(year_from)
        if year_to:
            where_clauses.append("year_built <= %s")
            params.append(year_to)

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"SELECT * FROM vessels WHERE {where_clause}"
        cur.execute(query, params)
        vessels = cur.fetchall()
        cur.close()
        conn.close()

        if format.lower() == "csv":
            output = BytesIO()
            writer = csv.DictWriter(
                output,
                fieldnames=vessels[0].keys() if vessels else [],
                extrasaction="ignore",
            )
            writer.writeheader()
            for vessel in vessels:
                writer.writerow(vessel)
            output.seek(0)
            return StreamingResponse(
                output,
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=vessels.csv"},
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
                headers={"Content-Disposition": "attachment; filename=vessels.json"},
            )
        else:
            raise HTTPException(
                status_code=400, detail="Unsupported format. Use 'csv' or 'json'"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/images/{filename}")
def get_image(filename: str):
    """Отдать фото судна"""
    image_path = f"/app/images/{filename}"
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)


@app.post("/vessels/")
def add_vessel(vessel: Vessel):
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        name_clean = " ".join(vessel.name.split())  # сжатие множественных пробелов
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
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
