CREATE TABLE IF NOT EXISTS countries (
    id SERIAL PRIMARY KEY,
    code VARCHAR(3) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gdp_data (
    id SERIAL PRIMARY KEY,
    country_code VARCHAR(3) NOT NULL REFERENCES countries(code),
    year INTEGER NOT NULL,
    gdp_usd NUMERIC(25, 2),
    gdp_growth_rate NUMERIC(10, 4),
    ingested_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(country_code, year)
);

CREATE TABLE IF NOT EXISTS event_types (
    id SERIAL PRIMARY KEY,
    theme_code VARCHAR(50) UNIQUE NOT NULL,
    theme_name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS gdelt_events (
    id SERIAL PRIMARY KEY,
    country_code VARCHAR(3) NOT NULL REFERENCES countries(code),
    event_type_id INTEGER REFERENCES event_types(id),
    year INTEGER NOT NULL,
    month INTEGER,
    article_count INTEGER DEFAULT 0,
    ingested_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(country_code, event_type_id, year, month)
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id SERIAL PRIMARY KEY,
    country_code VARCHAR(3) REFERENCES countries(code),
    event_type_id INTEGER REFERENCES event_types(id),
    year_start INTEGER,
    year_end INTEGER,
    correlation_coefficient NUMERIC(10, 6),
    sample_size INTEGER,
    calculated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    records_fetched INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP
);

INSERT INTO countries (code, name) VALUES
    ('POL', 'Poland'),
    ('DEU', 'Germany'),
    ('USA', 'United States'),
    ('FRA', 'France'),
    ('BRA', 'Brazil'),
    ('IND', 'India'),
    ('CHN', 'China'),
    ('JPN', 'Japan'),
    ('GBR', 'United Kingdom'),
    ('ITA', 'Italy')
ON CONFLICT (code) DO NOTHING;

INSERT INTO event_types (theme_code, theme_name, description) VALUES
    ('PROTEST', 'Protests & Demonstrations', 'Mass protests, demonstrations, strikes'),
    ('MILITARY', 'Military & Conflict', 'Armed conflict, military operations'),
    ('ELECTION', 'Elections & Politics', 'Elections, political events'),
    ('ECONOMY', 'Economic Events', 'Economic crises, financial events'),
    ('DISASTER', 'Natural Disasters', 'Earthquakes, floods, storms'),
    ('CRIME', 'Crime & Security', 'Criminal activity, law enforcement')
ON CONFLICT (theme_code) DO NOTHING;
