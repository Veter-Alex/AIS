-- SQL для создания таблицы vessels
CREATE TABLE IF NOT EXISTS vessels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    imo VARCHAR(20),
    mmsi VARCHAR(20) NOT NULL UNIQUE,
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

CREATE INDEX IF NOT EXISTS idx_vessels_name ON vessels(name);
CREATE INDEX IF NOT EXISTS idx_vessels_imo ON vessels(imo);
CREATE INDEX IF NOT EXISTS idx_vessels_flag ON vessels(flag);
CREATE INDEX IF NOT EXISTS idx_vessels_type ON vessels(general_type);
CREATE INDEX IF NOT EXISTS idx_vessels_source ON vessels(info_source);

-- Таблица приоритетов источников данных
CREATE TABLE IF NOT EXISTS source_priority (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL UNIQUE,
    priority INTEGER NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO source_priority (source_name, priority, description) VALUES
    ('marinetraffic.org', 1, 'Основной источник - самая полная база данных судов'),
    ('maritime-database.com', 2, 'Общая база данных судов'),
    ('vesselfinder.com', 3, 'Детальные данные и фотографии'),
    ('myshiptracking.com', 4, 'Дополнительные данные и фотографии')
ON CONFLICT (source_name) DO NOTHING;

-- Таблица для хранения состояния скрапера
CREATE TABLE IF NOT EXISTS scraper_state (
    id SERIAL PRIMARY KEY,
    scraper_name VARCHAR(100) NOT NULL,
    mode VARCHAR(20) NOT NULL,
    last_page INTEGER NOT NULL DEFAULT 1,
    vessels_count INTEGER NOT NULL DEFAULT 0,
    last_run_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(scraper_name, mode)
);

ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS scraper_name VARCHAR(100);
