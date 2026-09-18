-- EDna database schema (Postgres)
-- One enriched events table: every event, plus the three facts every tab
-- needs (category, ship, vehicle_state), precomputed once at migration
-- time -- see functional-requirements.md sections 1.2-1.4 for exactly what
-- these mean and the rules that must not regress.

CREATE TABLE IF NOT EXISTS events (
    id            BIGSERIAL PRIMARY KEY,
    "timestamp"   TIMESTAMP NOT NULL,
    event         TEXT NOT NULL,
    source_file   TEXT NOT NULL,
    raw           JSONB NOT NULL,
    star_system   TEXT,
    category      TEXT,
    ship          TEXT,
    vehicle_state TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events ("timestamp");
CREATE INDEX IF NOT EXISTS idx_events_event ON events (event);
CREATE INDEX IF NOT EXISTS idx_events_source_file ON events (source_file);
CREATE INDEX IF NOT EXISTS idx_events_ship ON events (ship);
CREATE INDEX IF NOT EXISTS idx_events_category ON events (category);
CREATE INDEX IF NOT EXISTS idx_events_raw ON events USING GIN (raw);

CREATE TABLE IF NOT EXISTS sessions (
    source_file     TEXT PRIMARY KEY,
    session_start   TIMESTAMP NOT NULL,
    session_end     TIMESTAMP NOT NULL,
    event_count     INTEGER NOT NULL,
    duration_hours  DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions (session_start);
