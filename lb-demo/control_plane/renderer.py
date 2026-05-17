import os

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_jinja = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=False)


def render_cluster(instance: dict) -> dict:
    art = instance.get("artifact", {})
    return {
        "name": art.get("cluster_name", f"cluster_{instance['instance_id']}"),
        "type": "STRICT_DNS",
        "lb_policy": art.get("lb_algorithm", "round_robin").upper(),
        "upstreams": art.get("upstreams", []),
        "instance_id": instance["instance_id"],
    }


def render_listener(instance: dict) -> dict:
    art = instance.get("artifact", {})
    return {
        "name": f"listener_{instance['instance_id'].replace('-', '_')}",
        "port": art.get("listener_port", 10000),
        "cluster": art.get("cluster_name", f"cluster_{instance['instance_id']}"),
        "instance_id": instance["instance_id"],
    }


def render_full_snapshot(instance: dict) -> str:
    return _jinja.get_template("snapshot.j2").render(
        instance_id=instance["instance_id"],
        plan_id=instance["plan_id"],
        cluster=render_cluster(instance),
        listener=render_listener(instance),
        artifact=instance.get("artifact", {}),
    )
