import asyncio
import os

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_jinja = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=False)

_PLAN_UPSTREAMS = {
    "plan-basic-001": [{"address": "10.0.0.1", "port": 8080}],
    "plan-ha-001": [
        {"address": "10.0.0.1", "port": 8080},
        {"address": "10.0.0.2", "port": 8080},
        {"address": "10.0.0.3", "port": 8080},
    ],
}

_PLAN_ALGORITHMS = {
    "plan-basic-001": "round_robin",
    "plan-ha-001": "least_request",
}


async def provision_instance(
    instance_id: str,
    service_id: str,
    plan_id: str,
    parameters: dict,
) -> dict:
    """
    Simulates async provisioning: renders an Envoy config artifact.
    In production this would allocate a VIP, register upstreams in the
    service mesh, and push xDS config to real Envoy sidecars.
    """
    await asyncio.sleep(1.0)  # simulate infra round-trip latency

    upstreams = _PLAN_UPSTREAMS.get(plan_id, _PLAN_UPSTREAMS["plan-basic-001"])
    algorithm = _PLAN_ALGORITHMS.get(plan_id, "round_robin")
    cluster_name = f"cluster_{instance_id.replace('-', '_')}"
    listener_port = parameters.get("listener_port", 10000)

    rendered = _jinja.get_template("envoy_config.j2").render(
        instance_id=instance_id,
        cluster_name=cluster_name,
        upstreams=upstreams,
        lb_algorithm=algorithm,
        listener_port=listener_port,
        plan_id=plan_id,
    )

    return {
        "cluster_name": cluster_name,
        "plan_id": plan_id,
        "upstreams": upstreams,
        "lb_algorithm": algorithm,
        "listener_port": listener_port,
        "rendered_config": rendered,
    }
