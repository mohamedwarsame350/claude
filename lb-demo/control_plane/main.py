"""
xDS-style Control Plane (HTTP polling, not gRPC)
================================================
Real Envoy xDS uses gRPC streaming (Aggregated Discovery Service, ADS) over
the envoy.service.discovery.v3 proto surface. Envoy holds a long-lived
bidirectional stream and ACKs/NACKs each resource version; the control plane
pushes updates instantly on change. This demo replaces the entire gRPC layer
with plain HTTP polling: clients call GET /xds/snapshot/{id} on demand and
the control plane re-renders from SQLite on every request. What this omits:
version/nonce handshakes, ACK/NACK flow, delta (incremental) xDS, type-URL
routing across CDS/LDS/RDS/EDS, and push latency. A real Envoy sidecar would
reject this endpoint entirely — it speaks proto over gRPC, not JSON/HTTP.
"""

import json
import os
import sqlite3
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from renderer import render_cluster, render_full_snapshot, render_listener

app = FastAPI(title="xDS Control Plane (demo)")

DB_PATH = os.environ.get("DB_PATH", "./demo.db")


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_instance(row) -> dict:
    d = dict(row)
    d["artifact"] = json.loads(d["artifact"]) if d["artifact"] else {}
    return d


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/xds/snapshot/{instance_id}", response_class=PlainTextResponse)
async def get_snapshot(instance_id: str):
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM service_instances WHERE instance_id = ? AND status = 'succeeded'",
            (instance_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"No succeeded instance: {instance_id}"
        )
    return render_full_snapshot(_row_to_instance(row))


@app.get("/xds/clusters")
async def get_clusters():
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM service_instances WHERE status = 'succeeded'"
        ).fetchall()
    return {"clusters": [render_cluster(_row_to_instance(r)) for r in rows]}


@app.get("/xds/listeners")
async def get_listeners():
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM service_instances WHERE status = 'succeeded'"
        ).fetchall()
    return {"listeners": [render_listener(_row_to_instance(r)) for r in rows]}
