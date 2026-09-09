-- Capital Pro | Phuket — общая схема БД для агентского и гостевого ботов

CREATE TABLE IF NOT EXISTS properties (
    id              TEXT PRIMARY KEY,          -- тикер, напр. LBS-1505
    type            TEXT NOT NULL,             -- villa / apartment / townhouse
    title           TEXT NOT NULL,
    district        TEXT,
    bedrooms        INTEGER,
    sqm             TEXT,
    view            TEXT,
    pool_access     TEXT,
    address         TEXT,
    map_link        TEXT,
    max_guests      INTEGER,
    links           JSONB DEFAULT '[]',
    prices          JSONB DEFAULT '[]',        -- список из 11 периодов {period, price_month_thb, price_night_thb}
    currency        TEXT DEFAULT 'THB',
    description     TEXT DEFAULT '',
    photos          JSONB DEFAULT '[]',
    status          TEXT DEFAULT 'available',  -- available / booked
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agents (
    id              SERIAL PRIMARY KEY,
    telegram_id     BIGINT UNIQUE NOT NULL,
    telegram_username TEXT,
    name            TEXT NOT NULL,
    agency          TEXT NOT NULL,
    contact         TEXT,
    registered_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS leads (
    id              SERIAL PRIMARY KEY,
    source          TEXT NOT NULL,             -- 'guest' / 'agent'
    property_id     TEXT REFERENCES properties(id) ON DELETE SET NULL,
    property_title  TEXT,
    client_name     TEXT,
    client_contact  TEXT,
    dates           TEXT,
    budget          TEXT,
    comment         TEXT,
    agent_id        INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    telegram_user_id BIGINT,
    telegram_username TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_properties_type ON properties(type);
CREATE INDEX IF NOT EXISTS idx_leads_agent ON leads(agent_id);
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);

-- Миграция: добавлены поля депозита и коммунальных услуг (для карточки объекта)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS deposit TEXT;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS utilities_included TEXT;

-- Настройки бота, редактируемые через админ-панель (тексты, контакты)
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TIMESTAMPTZ DEFAULT now()
);
