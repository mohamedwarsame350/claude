"""Tests for the async provisioning worker."""
import asyncio
import importlib.util
import json
import os
import sqlite3
import sys

import pytest

_WORKER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "worker"))


def _import(alias: str, filename: str):
    path = os.path.join(_WORKER, filename)
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


_provisioner = _import("worker_provisioner", "provisioner.py")
# Register under plain name so worker/main.py's `from provisioner import ...` resolves
sys.modules.setdefault("provisioner", _provisioner)
_worker_main = _import("worker_main", "main.py")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS service_instances (
    instance_id TEXT PRIMARY KEY, service_id TEXT NOT NULL,
    plan_id TEXT NOT NULL, parameters TEXT,
    status TEXT NOT NULL DEFAULT 'in_progress',
    operation_token TEXT NOT NULL, artifact TEXT, error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS provisioning_jobs (
    job_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "worker_test.db")
    conn = sqlite3.connect(p)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    _worker_main.DB_PATH = p
    return p


def _seed(db_path: str, instance_id: str, plan_id: str = "plan-basic-001") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO service_instances
           (instance_id, service_id, plan_id, parameters, status, operation_token)
           VALUES (?, 'load-balancer-svc-001', ?, '{}', 'in_progress', 'tok-test')""",
        (instance_id, plan_id),
    )
    conn.execute(
        "INSERT INTO provisioning_jobs (job_id, instance_id) VALUES (?, ?)",
        ("job-" + instance_id, instance_id),
    )
    conn.commit()
    conn.close()


def _get_status(db_path: str, instance_id: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status, artifact FROM service_instances WHERE instance_id=?",
        (instance_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def test_provisioner_basic():
    art = asyncio.run(
        _provisioner.provision_instance(
            instance_id="t-basic",
            service_id="load-balancer-svc-001",
            plan_id="plan-basic-001",
            parameters={"listener_port": 10000},
        )
    )
    assert art["cluster_name"] == "cluster_t_basic"
    assert art["lb_algorithm"] == "round_robin"
    assert len(art["upstreams"]) == 1
    assert "cluster" in art["rendered_config"].lower()


def test_provisioner_ha():
    art = asyncio.run(
        _provisioner.provision_instance(
            instance_id="t-ha",
            service_id="load-balancer-svc-001",
            plan_id="plan-ha-001",
            parameters={},
        )
    )
    assert art["lb_algorithm"] == "least_request"
    assert len(art["upstreams"]) == 3


def test_worker_processes_job(db_path):
    _seed(db_path, "w-job-001")
    asyncio.run(
        _worker_main.handle_job(
            {
                "job_id": "job-w-job-001",
                "instance_id": "w-job-001",
                "service_id": "load-balancer-svc-001",
                "plan_id": "plan-basic-001",
                "parameters": "{}",
            }
        )
    )
    result = _get_status(db_path, "w-job-001")
    assert result["status"] == "succeeded"
    art = json.loads(result["artifact"])
    assert "cluster_name" in art


def test_worker_state_transitions(db_path):
    _seed(db_path, "w-trans-001")
    before = _get_status(db_path, "w-trans-001")
    assert before["status"] == "in_progress"

    asyncio.run(
        _worker_main.handle_job(
            {
                "job_id": "job-w-trans-001",
                "instance_id": "w-trans-001",
                "service_id": "load-balancer-svc-001",
                "plan_id": "plan-ha-001",
                "parameters": "{}",
            }
        )
    )
    after = _get_status(db_path, "w-trans-001")
    assert after["status"] == "succeeded"
    assert after["status"] != "in_progress"
