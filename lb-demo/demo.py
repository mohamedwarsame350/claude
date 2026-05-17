#!/usr/bin/env python3
"""
End-to-end happy-path demo.

Usage (from lb-demo/):
    python demo.py           # services must already be up
    make demo-flow           # builds + starts services then runs this
"""
import sys
import time
import uuid

try:
    import requests
except ImportError:
    sys.exit("ERROR: 'requests' not installed. Run: pip install requests")

BROKER = "http://localhost:8000"
CP = "http://localhost:8001"
SERVICE_ID = "load-balancer-svc-001"
PLAN_ID = "plan-ha-001"
BAR = "─" * 62


def step(n: int, msg: str) -> None:
    print(f"\n[Step {n}] {msg}")


def banner(msg: str) -> None:
    print(f"\n{BAR}\n  {msg}\n{BAR}")


def wait_for_services(timeout: int = 60) -> None:
    print("Waiting for broker and control plane...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(f"{BROKER}/v2/catalog", timeout=2).raise_for_status()
            requests.get(f"{CP}/health", timeout=2).raise_for_status()
            print(" ready!")
            return
        except Exception:
            print(".", end="", flush=True)
            time.sleep(2)
    sys.exit("\nERROR: Services did not become ready within timeout.")


def main() -> None:
    instance_id = f"demo-{uuid.uuid4().hex[:8]}"
    banner(f"Load Balancing Platform  —  End-to-End Demo\nInstance: {instance_id}")

    wait_for_services()

    # 1. Catalog
    step(1, "Fetching service catalog")
    catalog = requests.get(f"{BROKER}/v2/catalog").json()
    for svc in catalog["services"]:
        print(f"  service={svc['name']}  plans={[p['name'] for p in svc['plans']]}")

    # 2. Provision
    step(2, f"Requesting provisioning  plan={PLAN_ID}")
    r = requests.put(
        f"{BROKER}/v2/service_instances/{instance_id}",
        json={
            "service_id": SERVICE_ID,
            "plan_id": PLAN_ID,
            "parameters": {"listener_port": 10001},
            "organization_guid": "demo-org",
            "space_guid": "demo-space",
        },
    )
    assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
    op_token = r.json()["operation"]
    print(f"  Accepted. operation={op_token}")

    # 3. Poll last_operation
    step(3, "Polling last_operation until succeeded (max 30s)")
    deadline = time.time() + 30
    state, attempt = "in_progress", 0
    while time.time() < deadline and state == "in_progress":
        time.sleep(2)
        attempt += 1
        data = requests.get(
            f"{BROKER}/v2/service_instances/{instance_id}/last_operation",
            params={"operation": op_token},
        ).json()
        state = data["state"]
        print(f"  poll {attempt:02d}: state={state!r}  desc={data.get('description', '')!r}")

    if state != "succeeded":
        sys.exit(f"\nERROR: Instance did not succeed (final state: {state})")

    print(f"\n  Provisioning complete after {attempt} poll(s).")

    # 4. xDS snapshot
    step(4, "Fetching rendered xDS snapshot from control plane")
    snap = requests.get(f"{CP}/xds/snapshot/{instance_id}")
    snap.raise_for_status()
    banner("RENDERED xDS CONFIG (YAML)")
    print(snap.text)

    # 5. Cluster list
    step(5, "Listing all active clusters")
    clusters = requests.get(f"{CP}/xds/clusters").json()["clusters"]
    print(f"  Active clusters: {len(clusters)}")
    for c in clusters:
        print(f"    {c['name']}  lb={c['lb_policy']}  upstreams={len(c['upstreams'])}")

    banner(
        "DEMO COMPLETE — end-to-end flow verified\n"
        "  Broker → SQLite queue → Worker → SQLite store → Control Plane"
    )


if __name__ == "__main__":
    main()
