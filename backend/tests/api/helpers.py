from typing import Any

from fastapi.testclient import TestClient

V1 = "/api/v1"


def ok(res: Any, status: int = 200) -> Any:
    assert res.status_code == status, f"{res.status_code}: {res.text}"
    return res.json() if res.content else None


def err(res: Any, status: int, code: str) -> dict[str, Any]:
    assert res.status_code == status, f"{res.status_code}: {res.text}"
    body: dict[str, Any] = res.json()["error"]
    assert body["code"] == code, body
    return body


def make_farm(api: TestClient, name: str = "Farm A") -> dict[str, Any]:
    """Create a farm owned by whoever `api` is signed in as."""
    farm: dict[str, Any] = ok(api.post(f"{V1}/farms", json={"name": name}), 201)
    return farm


def make_zone(api: TestClient, farm_id: int, name: str = "Block 1") -> dict[str, Any]:
    zone: dict[str, Any] = ok(api.post(f"{V1}/farms/{farm_id}/zones", json={"name": name}), 201)
    return zone
