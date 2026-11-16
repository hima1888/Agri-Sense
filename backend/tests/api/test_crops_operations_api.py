from fastapi.testclient import TestClient

from tests.api.helpers import V1, err, make_farm, make_zone, ok

TOMATO = {
    "common_name": "Test Tomato",
    "scientific_name": "Solanum lycopersicum",
    "category": "vegetable",
    "optimal_ph_min": 6.0,
    "optimal_ph_max": 6.8,
}


def test_crop_catalogue_and_search(api: TestClient, admin: TestClient) -> None:
    crop = ok(admin.post(f"{V1}/crops", json=TOMATO), 201)
    assert crop["optimal_ph_max"] == 6.8
    found = ok(api.get(f"{V1}/crops", params={"q": "lycopersicum"}))
    assert crop["id"] in [c["id"] for c in found["items"]]
    bad = {**TOMATO, "common_name": "Bad", "optimal_ph_min": 7.5, "optimal_ph_max": 6.0}
    err(admin.post(f"{V1}/crops", json=bad), 422, "validation_error")
    err(admin.post(f"{V1}/crops", json={**TOMATO, "category": "mushroom"}), 422, "validation_error")


def test_crop_cycle_lifecycle_and_in_use_protection(api: TestClient, admin: TestClient) -> None:
    farm = make_farm(api)
    zone = make_zone(api, farm["id"])
    crop = ok(admin.post(f"{V1}/crops", json=TOMATO), 201)
    cycle = ok(
        api.post(
            f"{V1}/zones/{zone['id']}/crop-cycles",
            json={"crop_id": crop["id"], "status": "growing", "planted_on": "2026-07-01"},
        ),
        201,
    )
    ok(
        api.patch(
            f"{V1}/crop-cycles/{cycle['id']}",
            json={"status": "harvested", "harvested_on": "2026-10-20", "actual_yield_kg": 4200},
        )
    )
    listed = ok(api.get(f"{V1}/zones/{zone['id']}/crop-cycles", params={"status": "harvested"}))
    assert listed["items"][0]["actual_yield_kg"] == 4200

    body = err(admin.delete(f"{V1}/crops/{crop['id']}"), 409, "in_use")
    assert body["details"]["constraint"] == "fk_crop_cycles_crop_id_crops"
    err(api.post(f"{V1}/zones/{zone['id']}/crop-cycles", json={"crop_id": 999999}), 404, "not_found")
    err(
        api.post(
            f"{V1}/zones/{zone['id']}/crop-cycles",
            json={"crop_id": crop["id"], "planted_on": "2026-07-01", "harvested_on": "2026-06-01"},
        ),
        422,
        "validation_error",
    )
    # The DB check still guards updates that bypass request-level validation.
    err(
        api.patch(f"{V1}/crop-cycles/{cycle['id']}", json={"harvested_on": "2026-01-01"}),
        422,
        "constraint_violation",
    )


def test_soil_profile_and_measurements(api: TestClient) -> None:
    farm = make_farm(api)
    zone = make_zone(api, farm["id"])
    profile = ok(
        api.post(
            f"{V1}/zones/{zone['id']}/soil-profiles",
            json={
                "texture": "loam",
                "sand_pct": 40,
                "silt_pct": 40,
                "clay_pct": 20,
                "field_capacity_pct": 28,
                "wilting_point_pct": 12,
            },
        ),
        201,
    )
    err(
        api.post(
            f"{V1}/zones/{zone['id']}/soil-profiles", json={"sand_pct": 60, "silt_pct": 40, "clay_pct": 20}
        ),
        422,
        "validation_error",
    )

    for day, ph in ((1, 6.4), (5, 6.6), (9, 6.9)):
        ok(
            api.post(
                f"{V1}/zones/{zone['id']}/soil-measurements",
                json={
                    "measured_at": f"2026-10-0{day}T06:00:00Z",
                    "source": "lab",
                    "ph": ph,
                    "nitrogen_mg_kg": 210,
                    "soil_profile_id": profile["id"],
                },
            ),
            201,
        )
    window = ok(
        api.get(
            f"{V1}/zones/{zone['id']}/soil-measurements",
            params={"start": "2026-10-04T00:00:00Z", "end": "2026-10-10T00:00:00Z"},
        )
    )
    assert [m["ph"] for m in window["items"]] == [6.9, 6.6]  # newest first
    err(
        api.post(
            f"{V1}/zones/{zone['id']}/soil-measurements",
            json={"measured_at": "2026-10-01T06:00:00Z", "source": "lab", "ph": 15},
        ),
        422,
        "validation_error",
    )

    other_zone = make_zone(api, farm["id"], "Block 2")
    err(
        api.post(
            f"{V1}/zones/{other_zone['id']}/soil-measurements",
            json={"measured_at": "2026-10-01T06:00:00Z", "source": "lab", "soil_profile_id": profile["id"]},
        ),
        422,
        "invalid",
    )


def test_irrigation_fertilizer_pesticide_records(api: TestClient, admin: TestClient) -> None:
    farm = make_farm(api)
    zone = make_zone(api, farm["id"])
    event = ok(
        api.post(
            f"{V1}/zones/{zone['id']}/irrigation-events",
            json={"method": "drip", "started_at": "2026-11-01T05:00:00Z"},
        ),
        201,
    )
    done = ok(
        api.patch(
            f"{V1}/irrigation-events/{event['id']}",
            json={"status": "completed", "ended_at": "2026-11-01T05:40:00Z", "volume_liters": 1800},
        )
    )
    assert (done["status"], done["volume_liters"]) == ("completed", 1800)
    err(
        api.post(
            f"{V1}/zones/{zone['id']}/irrigation-events",
            json={"method": "drip", "started_at": "2026-11-01T05:00:00Z", "ended_at": "2026-11-01T04:00:00Z"},
        ),
        422,
        "validation_error",
    )

    fert = ok(
        api.post(
            f"{V1}/zones/{zone['id']}/fertilizer-applications",
            json={
                "applied_at": "2026-10-15T07:00:00Z",
                "product_name": "Urea 46-0-0",
                "method": "broadcast",
                "quantity_kg": 25,
                "n_pct": 46,
            },
        ),
        201,
    )
    assert fert["n_pct"] == 46
    other_zone = make_zone(api, farm["id"], "Block 2")
    crop = ok(admin.post(f"{V1}/crops", json=TOMATO), 201)
    cycle = ok(api.post(f"{V1}/zones/{other_zone['id']}/crop-cycles", json={"crop_id": crop["id"]}), 201)
    err(
        api.post(
            f"{V1}/zones/{zone['id']}/fertilizer-applications",
            json={
                "applied_at": "2026-10-15T07:00:00Z",
                "product_name": "x",
                "method": "foliar",
                "quantity_kg": 1,
                "crop_cycle_id": cycle["id"],
            },
        ),
        422,
        "invalid",
    )

    pest = ok(
        api.post(
            f"{V1}/zones/{zone['id']}/pesticide-applications",
            json={
                "applied_at": "2026-10-20T07:00:00Z",
                "product_name": "Neem oil",
                "pesticide_type": "biological",
                "quantity": 2.5,
                "quantity_unit": "l",
                "pre_harvest_interval_days": 0,
            },
        ),
        201,
    )
    assert pest["quantity"] == 2.5
    ok(api.delete(f"{V1}/pesticide-applications/{pest['id']}"), 204)
    assert ok(api.get(f"{V1}/zones/{zone['id']}/pesticide-applications"))["total"] == 0


def test_alert_lifecycle(api: TestClient) -> None:
    farm = make_farm(api)
    alert = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/alerts",
            json={
                "severity": "warning",
                "category": "soil",
                "title": "Low moisture",
                "message": "North block below 18% VWC",
            },
        ),
        201,
    )
    assert alert["status"] == "open"
    assert ok(api.get(f"{V1}/farms/{farm['id']}/alerts", params={"status": "open"}))["total"] == 1

    acked = ok(api.post(f"{V1}/alerts/{alert['id']}/acknowledge"))
    assert acked["status"] == "acknowledged"
    assert acked["acknowledged_at"] is not None
    resolved = ok(api.post(f"{V1}/alerts/{alert['id']}/resolve"))
    assert resolved["resolved_at"] is not None
    err(api.post(f"{V1}/alerts/{alert['id']}/acknowledge"), 409, "conflict")  # resolved is final

    other = make_farm(api, "Other")
    foreign_sensor = ok(
        api.post(
            f"{V1}/farms/{other['id']}/sensors",
            json={"name": "x", "sensor_type": "light", "source": "simulated"},
        ),
        201,
    )
    err(
        api.post(
            f"{V1}/farms/{farm['id']}/alerts",
            json={
                "severity": "info",
                "category": "sensor",
                "title": "t",
                "message": "m",
                "sensor_id": foreign_sensor["id"],
            },
        ),
        422,
        "invalid",
    )
