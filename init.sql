-- SQL для создания таблицы vessels
CREATE TABLE IF NOT EXISTS vessels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200),
    imo VARCHAR(20),
    mmsi VARCHAR(20) NOT NULL UNIQUE,
    call_sign VARCHAR(20),
    general_type VARCHAR(100),
    detailed_type VARCHAR(100),
    flag VARCHAR(100),
    year_built INTEGER,
    length INTEGER,
    width INTEGER,
    dwt INTEGER,
    gt INTEGER,
    home_port VARCHAR(100),
    photo_url TEXT,
    photo_path TEXT,
    description TEXT,
    info_source VARCHAR(100),
    updated_at TIMESTAMP,
    vessel_key VARCHAR(32)
);

-- Создать индексы для быстрого поиска
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

-- Начальные приоритеты (чем меньше число - тем выше приоритет)
INSERT INTO source_priority (source_name, priority, description) VALUES
    ('marinetraffic.org', 1, 'Основной источник - самая полная база данных судов (250,000+ судов)'),
    ('maritime-database.com', 2, 'Общая база данных судов'),
    ('vesselfinder.com', 3, 'Наиболее детальные данные, фотографии судов'),
    ('myshiptracking.com', 4, 'Дополнительные данные и фотографии судов'),
    ('marinetraffic.com', 5, 'Резервный источник'),
    ('fleetmon.com', 6, 'Дополнительный источник')
ON CONFLICT (source_name) DO NOTHING;

-- Таблица для хранения состояния скраперов
CREATE TABLE IF NOT EXISTS scraper_state (
    id SERIAL PRIMARY KEY,
    scraper_name VARCHAR(100) NOT NULL,
    mode VARCHAR(20) NOT NULL,
    last_page INTEGER NOT NULL DEFAULT 1,
    vessels_count INTEGER NOT NULL DEFAULT 0,
    last_run_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(scraper_name, mode)
);

-- Миграции для устаревших схем: добавить недостающие колонки (идемпотентно)
ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS scraper_name VARCHAR(100);
ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS mode VARCHAR(20);
ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS last_page INTEGER;
ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS vessels_count INTEGER;
ALTER TABLE scraper_state ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP;
