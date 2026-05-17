"""
Async provisioning worker.

Polls the 'provisioning_jobs' SQLite table for pending work.

What this hides vs. real SQS
─────────────────────────────
• Visibility timeout   — a crashed worker leaves rows stuck in 'processing';
                         SQS would re-enqueue the message after the timeout.
• Dead-letter queue    — SQS moves poison messages aside after N delivery
                         attempts; here a failed job stays 'failed' in the DB.
• Horizontal scaling   — SQS enables N parallel workers across hosts;
                         our SELECT … LIMIT 1 claim is single-consumer.
• At-least-once delivery — SQS may deliver the same message twice; our
                           row claim is at-most-once within one process.
• Long-poll / back-pressure — SQS long-poll blocks up to 20 s waiting for
                              messages; we just sleep POLL_INTERVAL between sweeps.
"""

import asyncio
import json
import logging
import os
import sqlite3

from provisioner import provision_instance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("worker")

DB_PATH = os.environ.get("DB_PATH", "./demo.db")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL_SECONDS", "2.0"))

_SCHEMA = """
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


def _ensure_schema() -> None:
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    os.makedirs(parent, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.executescript(_SCHEMA)


def _claim_job() -> dict | None:
    """Atomically claim one pending job; returns job dict or None."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        job = conn.execute(
            """SELECT j.job_id, j.instance_id, i.service_id, i.plan_id, i.parameters
               FROM provisioning_jobs j
               JOIN service_instances i ON j.instance_id = i.instance_id
               WHERE j.status = 'pending'
               ORDER BY j.created_at ASC
               LIMIT 1"""
        ).fetchone()
        if job is None:
            return None
        conn.execute(
            "UPDATE provisioning_jobs SET status='processing', updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
            (job["job_id"],),
        )
        conn.commit()
        return dict(job)
    finally:
        conn.close()


def _update_instance(
    instance_id: str, job_id: str, status: str, artifact: str | None, error: str | None
) -> None:
    job_status = "done" if status == "succeeded" else "failed"
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute(
            """UPDATE service_instances
               SET status=?, artifact=?, error_message=?, updated_at=CURRENT_TIMESTAMP
               WHERE instance_id=?""",
            (status, artifact, error, instance_id),
        )
        conn.execute(
            "UPDATE provisioning_jobs SET status=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
            (job_status, job_id),
        )
        conn.commit()
    finally:
        conn.close()


async def handle_job(job: dict) -> None:
    job_id = job["job_id"]
    instance_id = job["instance_id"]
    logger.info("Processing job=%s instance=%s", job_id, instance_id)
    parameters = json.loads(job.get("parameters") or "{}")
    try:
        artifact = await provision_instance(
            instance_id=instance_id,
            service_id=job["service_id"],
            plan_id=job["plan_id"],
            parameters=parameters,
        )
        _update_instance(instance_id, job_id, "succeeded", json.dumps(artifact), None)
        logger.info("Job %s succeeded", job_id)
    except Exception as exc:
        logger.error("Job %s failed: %s", job_id, exc)
        _update_instance(instance_id, job_id, "failed", None, str(exc))


async def run_worker() -> None:
    logger.info("Worker started, polling %s every %.1fs", DB_PATH, POLL_INTERVAL)
    _ensure_schema()
    while True:
        try:
            job = _claim_job()
            if job:
                await handle_job(job)
        except sqlite3.OperationalError as exc:
            # Schema not yet created by broker on first startup
            logger.warning("DB not ready (%s), will retry", exc)
        except Exception as exc:
            logger.exception("Poll loop error: %s", exc)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_worker())
