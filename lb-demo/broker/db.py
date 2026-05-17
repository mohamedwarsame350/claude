import os
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS service_instances (
    instance_id     TEXT PRIMARY KEY,
    service_id      TEXT NOT NULL,
    plan_id         TEXT NOT NULL,
    parameters      TEXT,
    status          TEXT NOT NULL DEFAULT 'in_progress',
    operation_token TEXT NOT NULL,
    artifact        TEXT,
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS provisioning_jobs (
    job_id      TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db(db_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_db(db_path: str):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()
