import json
import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from catalog import CATALOG
from db import get_db, init_db
from models import ProvisionRequest

app = FastAPI(title="Open Service Broker (demo)")

DB_PATH = os.environ.get("DB_PATH", "./demo.db")


@app.on_event("startup")
async def startup() -> None:
    init_db(DB_PATH)


@app.get("/v2/catalog")
async def get_catalog():
    return CATALOG


@app.put("/v2/service_instances/{instance_id}")
async def provision_instance(instance_id: str, request: ProvisionRequest):
    service = next(
        (s for s in CATALOG["services"] if s["id"] == request.service_id), None
    )
    if service is None:
        raise HTTPException(
            status_code=400, detail=f"Unknown service_id: {request.service_id}"
        )

    plan = next((p for p in service["plans"] if p["id"] == request.plan_id), None)
    if plan is None:
        raise HTTPException(
            status_code=400, detail=f"Unknown plan_id: {request.plan_id}"
        )

    operation_token = str(uuid.uuid4())

    with get_db(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT status, operation_token FROM service_instances WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()

        if existing:
            if existing["status"] == "succeeded":
                return JSONResponse(
                    status_code=200, content={"description": "already exists"}
                )
            return JSONResponse(
                status_code=202,
                content={"operation": existing["operation_token"]},
            )

        conn.execute(
            """INSERT INTO service_instances
               (instance_id, service_id, plan_id, parameters, status, operation_token)
               VALUES (?, ?, ?, ?, 'in_progress', ?)""",
            (
                instance_id,
                request.service_id,
                request.plan_id,
                json.dumps(request.parameters or {}),
                operation_token,
            ),
        )
        conn.execute(
            "INSERT INTO provisioning_jobs (job_id, instance_id, status) VALUES (?, ?, 'pending')",
            (str(uuid.uuid4()), instance_id),
        )
        conn.commit()

    return JSONResponse(status_code=202, content={"operation": operation_token})


@app.get("/v2/service_instances/{instance_id}/last_operation")
async def last_operation(instance_id: str, operation: str = None):
    with get_db(DB_PATH) as conn:
        row = conn.execute(
            "SELECT status, error_message FROM service_instances WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    return {
        "state": row["status"],
        "description": row["error_message"] or f"Instance is {row['status']}",
    }
