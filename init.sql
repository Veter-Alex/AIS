-- SQL для создания таблицы vessels
CREATE TABLE IF NOT EXISTS vessels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    imo VARCHAR(20),
    mmsi VARCHAR(20),
    call_sign VARCHAR(20),
    general_type VARCHAR(50),
    detailed_type VARCHAR(100),
    flag VARCHAR(50),
    year_built INTEGER,
    length INTEGER,
    width INTEGER,
    dwt INTEGER,
    gt INTEGER,
    home_port VARCHAR(100),
    photo_url TEXT,
    photo_path TEXT,
    info_source VARCHAR(100),
    updated_at TIMESTAMP,
    vessel_key VARCHAR(32) UNIQUE
);
