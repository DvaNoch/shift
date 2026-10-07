import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id              TEXT PRIMARY KEY,
    start_at        TEXT    NOT NULL,  -- ISO 8601 с исходным смещением
    end_at          TEXT    NOT NULL,
    start_utc       TEXT    NOT NULL,  -- для сортировки по фактическому времени
    local_date      TEXT    NOT NULL,  -- YYYY-MM-DD по смещению самой поездки
    amount_tiyn     INTEGER NOT NULL CHECK (amount_tiyn > 0),
    payment         TEXT    NOT NULL CHECK (payment IN ('cash', 'card')),
    commission_tiyn INTEGER NOT NULL CHECK (commission_tiyn >= 0)
);
CREATE INDEX IF NOT EXISTS trips_by_day ON trips (local_date, start_utc);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    # FastAPI может выполнять зависимость и обработчик в разных потоках пула.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
