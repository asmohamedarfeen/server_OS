import docker
from docker.errors import DockerException

def client():
    try:
        return docker.from_env(timeout=20)
    except DockerException as exc:
        raise RuntimeError(f"Docker Engine is unavailable: {exc}") from exc

def serialize(container):
    container.reload()
    attrs = container.attrs
    ports = attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
    mapped = [{"container": port, "host": bindings[0].get("HostPort")} for port, bindings in ports.items() if bindings]
    labels=attrs.get("Config",{}).get("Labels") or {}
    return {"id": container.short_id, "full_id": container.id, "name": container.name, "image": container.image.tags[0] if container.image.tags else container.image.short_id, "status": container.status, "created": attrs.get("Created"), "ports": mapped, "cpu_percent": None, "memory_usage": attrs.get("HostConfig", {}).get("Memory", 0), "managed": labels.get("com.arfeen.managed")=="true", "system": labels.get("com.arfeen.system")=="true"}
