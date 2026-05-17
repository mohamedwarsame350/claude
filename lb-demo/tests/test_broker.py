"""Tests for the Open Service Broker API."""
import importlib.util
import json
import os
import sys
import sqlite3

import pytest
from fastapi.testclient import TestClient

_BROKER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "broker"))


def _import(alias: str, filename: str):
    """Import a file by absolute path under a unique module alias."""
    path = os.path.join(_BROKER, filename)
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


# Register broker sub-modules under their plain names BEFORE importing main,
# so that broker/main.py's `from catalog import ...` etc. resolve correctly.
_db_mod = _import("broker_db", "db.py")
_catalog_mod = _import("broker_catalog", "catalog.py")
_models_mod = _import("broker_models", "models.py")
sys.modules.setdefault("db", _db_mod)
sys.modules.setdefault("catalog", _catalog_mod)
sys.modules.setdefault("models", _models_mod)
_main_mod = _import("broker_main", "main.py")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("broker") / "test.db")
    # Update module-level DB_PATH so all route handlers and the startup event use it
    _main_mod.DB_PATH = db_path
    _db_mod.init_db(db_path)
    with TestClient(_main_mod.app) as c:
        yield c


def test_catalog(client):
    r = client.get("/v2/catalog")
    assert r.status_code == 200
    data = r.json()
    assert "services" in data
    assert data["services"][0]["name"] == "load-balancer"


def test_catalog_has_two_plans(client):
    plans = client.get("/v2/catalog").json()["services"][0]["plans"]
    assert len(plans) >= 2


def test_provision_returns_202(client):
    r = client.put(
        "/v2/service_instances/broker-test-001",
        json={
            "service_id": "load-balancer-svc-001",
            "plan_id": "plan-basic-001",
            "parameters": {"listener_port": 10000},
        },
    )
    assert r.status_code == 202
    assert "operation" in r.json()


def test_provision_invalid_service(client):
    r = client.put(
        "/v2/service_instances/bad-svc",
        json={"service_id": "nonexistent", "plan_id": "plan-basic-001"},
    )
    assert r.status_code == 400


def test_provision_invalid_plan(client):
    r = client.put(
        "/v2/service_instances/bad-plan",
        json={"service_id": "load-balancer-svc-001", "plan_id": "nonexistent"},
    )
    assert r.status_code == 400


def test_last_operation_returns_state(client):
    client.put(
        "/v2/service_instances/poll-001",
        json={"service_id": "load-balancer-svc-001", "plan_id": "plan-basic-001"},
    )
    r = client.get("/v2/service_instances/poll-001/last_operation")
    assert r.status_code == 200
    assert r.json()["state"] in ("in_progress", "succeeded", "failed")


def test_last_operation_not_found(client):
    r = client.get("/v2/service_instances/ghost-xyz/last_operation")
    assert r.status_code == 404


def test_provision_idempotent(client):
    payload = {"service_id": "load-balancer-svc-001", "plan_id": "plan-basic-001"}
    r1 = client.put("/v2/service_instances/idem-001", json=payload)
    assert r1.status_code == 202
    r2 = client.put("/v2/service_instances/idem-001", json=payload)
    assert r2.status_code in (200, 202)
