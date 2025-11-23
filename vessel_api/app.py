import os
from datetime import datetime

import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


class Vessel(BaseModel):
    name: str
    imo: str
    mmsi: str
    call_sign: str
    general_type: str
    detailed_type: str
    flag: str
    year_built: str | None = None
    length: str | None = None
    width: str | None = None
    dwt: str | None = None
    gt: str | None = None
    home_port: str | None = None
    photo_url: str | None = None
    info_source: str
    updated_at: datetime | None = None


def get_db_conn():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "vessels_db"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )


@app.post("/vessels/")
def add_vessel(vessel: Vessel):
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO vessels (
                name, imo, mmsi, call_sign, general_type, detailed_type, flag, year_built, length, width, dwt, gt, home_port, photo_url, info_source, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                vessel.name,
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
                vessel.photo_url,
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
        raise HTTPException(status_code=500, detail=str(e))
