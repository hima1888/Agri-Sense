"""Tenant isolation: one user can never see or change another user's farm data."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from tests.api.helpers import V1, err, make_farm, make_zone, ok
from tests.conftest import ClientFor


def build_alice_farm(alice: TestClient, admin: TestClient) -> dict[str, int]:
    farm = make_farm(alice, "Alice Farm")
    zone = make_zone(alice, farm["id"])
    sensor = ok(
        alice.post(
            f"{V1}/farms/{farm['id']}/sensors",
            json={"name": "s", "sensor_type": "humidity", "source": "simulated"},
        ),
        201,
    )
    device = ok(
        alice.post(
            f"{V1}/farms/{farm['id']}/devices", json={"name": "d", "device_type": "esp32", "protocol": "http"}
        ),
        201,
    )
    ok(
        alice.post(
            f"{V1}/sensors/{sensor['id']}/readings",
            json={"readings": [{"recorded_at": datetime.now(UTC).isoformat(), "value": 55}]},
        )
    )
    alert = ok(
        alice.post(
            f"{V1}/farms/{farm['id']}/alerts",
            json={"severity": "info", "category": "soil", "title": "t", "message": "m"},
        ),
        201,
    )
    crop = ok(admin.post(f"{V1}/crops", json={"common_name": "Iso crop", "category": "cereal"}), 201)
    cycle = ok(alice.post(f"{V1}/zones/{zone['id']}/crop-cycles", json={"crop_id": crop["id"]}), 201)
    profile = ok(alice.post(f"{V1}/zones/{zone['id']}/soil-profiles", json={"texture": "loam"}), 201)
    irrigation = ok(alice.post(f"{V1}/zones/{zone['id']}/irrigation-events", json={"method": "drip"}), 201)
    return {
        "farm": farm["id"],
        "zone": zone["id"],
        "sensor": sensor["id"],
        "device": device["id"],
        "alert": alert["id"],
        "cycle": cycle["id"],
        "profile": profile["id"],
        "irrigation": irrigation["id"],
    }


def test_other_users_cannot_read_or_modify_anything(client_for: ClientFor, admin: TestClient) -> None:
    alice = client_for("alice@example.com")
    mallory = client_for("mallory@example.com")
    ids = build_alice_farm(alice, admin)

    # Mallory's farm list is empty; Alice's records look like they do not exist (404, not 403).
    assert ok(mallory.get(f"{V1}/farms"))["total"] == 0
    reads = [
        f"/farms/{ids['farm']}",
        f"/farms/{ids['farm']}/zones",
        f"/farms/{ids['farm']}/sensors",
        f"/farms/{ids['farm']}/devices",
        f"/farms/{ids['farm']}/alerts",
        f"/zones/{ids['zone']}",
        f"/zones/{ids['zone']}/crop-cycles",
        f"/zones/{ids['zone']}/soil-profiles",
        f"/zones/{ids['zone']}/soil-measurements",
        f"/zones/{ids['zone']}/irrigation-events",
        f"/zones/{ids['zone']}/fertilizer-applications",
        f"/zones/{ids['zone']}/pesticide-applications",
        f"/sensors/{ids['sensor']}",
        f"/sensors/{ids['sensor']}/readings",
        f"/sensors/{ids['sensor']}/readings/latest",
        f"/devices/{ids['device']}",
        f"/alerts/{ids['alert']}",
        f"/crop-cycles/{ids['cycle']}",
        f"/soil-profiles/{ids['profile']}",
        f"/irrigation-events/{ids['irrigation']}",
    ]
    for path in reads:
        err(mallory.get(V1 + path), 404, "not_found")

    writes = [
        ("patch", f"/farms/{ids['farm']}", {"name": "pwned"}),
        ("delete", f"/farms/{ids['farm']}", None),
        ("post", f"/farms/{ids['farm']}/zones", {"name": "z"}),
        ("patch", f"/zones/{ids['zone']}", {"name": "pwned"}),
        (
            "post",
            f"/farms/{ids['farm']}/sensors",
            {"name": "s", "sensor_type": "light", "source": "simulated"},
        ),
        (
            "post",
            f"/sensors/{ids['sensor']}/readings",
            {"readings": [{"recorded_at": datetime.now(UTC).isoformat(), "value": 1}]},
        ),
        ("delete", f"/sensors/{ids['sensor']}", None),
        ("delete", f"/devices/{ids['device']}", None),
        ("post", f"/alerts/{ids['alert']}/acknowledge", None),
        ("patch", f"/crop-cycles/{ids['cycle']}", {"status": "failed"}),
        ("post", f"/zones/{ids['zone']}/irrigation-events", {"method": "flood"}),
    ]
    for method, path, body in writes:
        res = getattr(mallory, method)(V1 + path, **({"json": body} if body is not None else {}))
        err(res, 404, "not_found")

    # Nothing changed for Alice.
    assert ok(alice.get(f"{V1}/farms/{ids['farm']}"))["name"] == "Alice Farm"
    assert ok(alice.get(f"{V1}/alerts/{ids['alert']}"))["status"] == "open"
    assert ok(alice.get(f"{V1}/sensors/{ids['sensor']}/readings"))["count"] == 1


def test_admin_can_see_all_farms(client_for: ClientFor, admin: TestClient) -> None:
    alice = client_for("alice@example.com")
    farm = make_farm(alice, "Alice Farm")
    assert ok(admin.get(f"{V1}/farms/{farm['id']}"))["name"] == "Alice Farm"
    assert farm["id"] in [f["id"] for f in ok(admin.get(f"{V1}/farms"))["items"]]


def test_crop_catalogue_is_shared_but_admin_managed(client_for: ClientFor, admin: TestClient) -> None:
    farmer = client_for("farmer@example.com")
    crop = ok(admin.post(f"{V1}/crops", json={"common_name": "Shared crop", "category": "legume"}), 201)
    assert ok(farmer.get(f"{V1}/crops/{crop['id']}"))["common_name"] == "Shared crop"
    err(farmer.post(f"{V1}/crops", json={"common_name": "Mine", "category": "legume"}), 403, "forbidden")
    err(farmer.patch(f"{V1}/crops/{crop['id']}", json={"category": "other"}), 403, "forbidden")
    err(farmer.delete(f"{V1}/crops/{crop['id']}"), 403, "forbidden")
