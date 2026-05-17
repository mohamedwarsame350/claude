CATALOG = {
    "services": [
        {
            "id": "load-balancer-svc-001",
            "name": "load-balancer",
            "description": "Managed Envoy-backed load balancer (demo)",
            "bindable": False,
            "plans": [
                {
                    "id": "plan-basic-001",
                    "name": "basic",
                    "description": "Single upstream cluster, round-robin",
                    "metadata": {
                        "upstream_count": 1,
                        "algorithm": "round_robin",
                    },
                },
                {
                    "id": "plan-ha-001",
                    "name": "high-availability",
                    "description": "Multi-upstream cluster with least-request LB",
                    "metadata": {
                        "upstream_count": 3,
                        "algorithm": "least_request",
                    },
                },
            ],
        }
    ]
}
