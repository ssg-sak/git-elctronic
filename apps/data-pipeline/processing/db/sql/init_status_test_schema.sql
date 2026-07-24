-- DA➀ status 테스트 스키마 (DBeaver / docker init)
-- 원본 CSV 정본은 SANDBOX snapshots 유지. 여기는 분석 복제본.

CREATE TABLE IF NOT EXISTS meta_collection_schedule (
    id              SERIAL PRIMARY KEY,
    source          TEXT NOT NULL,          -- sandbox_loop | collection_scheduler
    interval_minutes INTEGER NOT NULL,
    period_minutes   INTEGER NOT NULL,
    note            TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS charger_status_tick (
    snapshot_id     TEXT PRIMARY KEY,
    fetched_at      TIMESTAMPTZ,
    rows_n          INTEGER,
    api_calls       INTEGER,
    period_minutes  INTEGER,
    ok              BOOLEAN,
    path            TEXT
);

CREATE TABLE IF NOT EXISTS station_feature_panel (
    stat_id                     TEXT NOT NULL,
    panel_ts                    TIMESTAMPTZ NOT NULL,
    known_chargers              INTEGER,
    available_count             INTEGER,
    in_use_count                INTEGER,
    usable_known                INTEGER,
    availability_ratio_observed DOUBLE PRECISION,
    has_confirmed_available     BOOLEAN,
    segment_id                  INTEGER,
    avail_rate_lag_15m          DOUBLE PRECISION,
    avail_rate_lag_60m          DOUBLE PRECISION,
    schema_version              TEXT,
    source_status               TEXT,
    PRIMARY KEY (stat_id, panel_ts)
);

CREATE INDEX IF NOT EXISTS idx_panel_ts ON station_feature_panel (panel_ts);
CREATE INDEX IF NOT EXISTS idx_panel_stat ON station_feature_panel (stat_id);

COMMENT ON TABLE station_feature_panel IS 'D2 gap-safe panel copy for DBeaver analysis';
COMMENT ON TABLE charger_status_tick IS 'SANDBOX index.csv snapshot ticks';
