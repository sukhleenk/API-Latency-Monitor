import yaml
from pathlib import Path
from dataclasses import dataclass, field

DEFAULT_CONFIG_PATH = Path("config.yaml")


@dataclass
class Endpoint:
    name: str
    url: str
    method: str = "GET"
    headers: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    threshold_ms: int = 500


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> list[Endpoint]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    endpoints = []
    for ep in data.get("endpoints", []):
        endpoints.append(Endpoint(
            name=ep["name"],
            url=ep["url"],
            method=ep.get("method", "GET").upper(),
            headers=ep.get("headers", {}),
            body=ep.get("body", {}),
            threshold_ms=ep.get("threshold_ms", 500),
        ))
    return endpoints
