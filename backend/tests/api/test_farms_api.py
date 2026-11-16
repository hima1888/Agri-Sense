from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from tests.api.helpers import V1, err, make_farm, make_zone, ok


def test_farm_and_zone_crud_lifecycle(api: TestClient) -> None:
    me = ok(api.get(f"{V1}/me"))
    farm = make_farm(api)
    assert farm["owner_id"] == me["id"]  # owner is always the caller
    assert farm["timezone"] == "UTC"

    updated = ok(api.patch(f"{V1}/farms/{farm['id']}", json={"latitude": 17.385, "area_hectares": "12.5"}))
    assert updated["latitude"] == 17.385  # NUMERIC is returned as a JSON number, not a string
    assert updated["area_hectares"] == 12.5
    assert updated["name"] == "Farm A"  # PATCH leaves unspecified fields alone

    zone = make_zone(api, farm["id"])
    assert zone["zone_type"] == "field"
    ok(api.patch(f"{V1}/zones/{zone['id']}", json={"irrigation_method": "drip"}))
    assert ok(api.get(f"{V1}/zones/{zone['id']}"))["irrigation_method"] == "drip"

    ok(api.delete(f"{V1}/farms/{farm['id']}"), 204)
    err(api.get(f"{V1}/farms/{farm['id']}"), 404, "not_found")
    err(api.get(f"{V1}/zones/{zone['id']}"), 404, "not_found")  # cascaded


def test_owner_cannot_be_chosen_by_client(api: TestClient) -> None:
    body = {"name": "x", "owner_id": "00000000-0000-0000-0000-000000000000"}
    err(api.post(f"{V1}/farms", json=body), 422, "validation_error")


def test_pagination(api: TestClient) -> None:
    for i in range(4):
        make_farm(api, f"F{i}")
    page = ok(api.get(f"{V1}/farms", params={"limit": 2, "offset": 1}))
    assert page["total"] == 4
    assert (page["limit"], page["offset"]) == (2, 1)
    assert [f["name"] for f in page["items"]] == ["F1", "F2"]
    err(api.get(f"{V1}/farms", params={"limit": 500}), 422, "validation_error")


def test_validation_errors_use_one_shape(api: TestClient) -> None:
    body = err(api.post(f"{V1}/farms", json={"name": "x", "latitude": 123}), 422, "validation_error")
    assert body["details"][0]["loc"][-1] == "latitude"
    farm = make_farm(api)
    # Unknown fields are rejected rather than silently ignored.
    body = err(api.patch(f"{V1}/farms/{farm['id']}", json={"nmae": "typo"}), 422, "validation_error")
    assert body["details"][0]["type"] == "extra_forbidden"


def test_database_conflicts_become_clean_client_errors(api: TestClient) -> None:
    farm = make_farm(api)
    make_zone(api, farm["id"], "Block 1")
    body = err(api.post(f"{V1}/farms/{farm['id']}/zones", json={"name": "Block 1"}), 409, "duplicate")
    assert body["details"] == {"constraint": "uq_farm_zones_farm_id_name"}
    # Setting a required column to null fails cleanly (422), not with a 500.
    err(api.patch(f"{V1}/farms/{farm['id']}", json={"name": None}), 422, "missing_value")


def test_missing_records_return_404(api: TestClient) -> None:
    err(api.post(f"{V1}/farms/999999/zones", json={"name": "x"}), 404, "not_found")
    err(api.get(f"{V1}/does-not-exist"), 404, "not_found")


def test_mutations_are_audited_with_the_acting_user(api: TestClient, db: Session) -> None:
    me = ok(api.get(f"{V1}/me"))
    farm = make_farm(api)
    ok(api.patch(f"{V1}/farms/{farm['id']}", json={"name": "Renamed"}))
    entries = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "farms", AuditLog.entity_id == str(farm["id"]))
        .order_by(AuditLog.id)
    ).all()
    assert [e.action for e in entries] == ["farms.create", "farms.update"]
    assert entries[1].changes == {"name": "Renamed"}
    assert all(str(e.user_id) == me["id"] and e.farm_id == farm["id"] for e in entries)


def test_me_profile_is_created_on_first_request_and_editable(api: TestClient, db: Session) -> None:
    me = ok(api.get(f"{V1}/me"))
    assert (me["email"], me["role"]) == ("owner@example.com", "farmer")
    assert db.get(User, me["id"]) is not None
    ok(api.patch(f"{V1}/me", json={"full_name": "Asha Rao"}))
    assert ok(api.get(f"{V1}/me"))["full_name"] == "Asha Rao"
    # A user cannot promote themselves.
    err(api.patch(f"{V1}/me", json={"role": "admin"}), 422, "validation_error")
