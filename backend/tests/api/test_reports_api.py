"""Analytics and reports: known records inside and outside the period, comparison, snapshots, CSV."""

import csv
import io
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import V1, err, ok
from tests.conftest import ClientFor

TODAY = datetime.now(UTC).date()
START, END = TODAY - timedelta(days=9), TODAY  # 10-day period; previous period is the 10 days before


def at(day: date, hour: int = 8) -> str:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC).isoformat()


@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    f = ok(api.post(f"{V1}/farms", json={"name": "Report Farm", "timezone": "UTC"}), 201)
    z1 = ok(
        api.post(
            f"{V1}/farms/{f['id']}/zones", json={"name": "A", "zone_type": "field", "area_hectares": 1.5}
        ),
        201,
    )
    z2 = ok(
        api.post(
            f"{V1}/farms/{f['id']}/zones", json={"name": "B", "zone_type": "field", "area_hectares": 0.5}
        ),
        201,
    )
    irr = {"method": "drip", "status": "completed", "trigger": "manual"}
    ok(
        api.post(
            f"{V1}/zones/{z1['id']}/irrigation-events",
            json={**irr, "started_at": at(START + timedelta(days=1)), "volume_liters": 30000},
        ),
        201,
    )
    ok(
        api.post(
            f"{V1}/zones/{z2['id']}/irrigation-events",
            json={**irr, "started_at": at(START + timedelta(days=2)), "volume_liters": 10000},
        ),
        201,
    )
    ok(
        api.post(
            f"{V1}/zones/{z1['id']}/irrigation-events",
            json={**irr, "started_at": at(START - timedelta(days=3)), "volume_liters": 80000},
        ),
        201,
    )  # previous period
    ok(
        api.post(
            f"{V1}/zones/{z1['id']}/irrigation-events",
            json={**irr, "started_at": at(START + timedelta(days=3)), "status": "scheduled"},
        ),
        201,
    )  # not completed
    ok(
        api.post(
            f"{V1}/zones/{z1['id']}/fertilizer-applications",
            json={
                "applied_at": at(START + timedelta(days=4)),
                "product_name": "Urea",
                "method": "broadcast",
                "quantity_kg": 100,
                "n_pct": 46,
            },
        ),
        201,
    )
    ok(
        api.post(
            f"{V1}/zones/{z2['id']}/fertilizer-applications",
            json={
                "applied_at": at(START + timedelta(days=4)),
                "product_name": "FYM",
                "method": "broadcast",
                "quantity_kg": 500,
                "is_organic": True,
            },
        ),
        201,
    )
    spray = {"product_name": "Mancozeb", "pesticide_type": "fungicide", "quantity": 2, "quantity_unit": "kg"}
    ok(
        api.post(
            f"{V1}/zones/{z1['id']}/pesticide-applications",
            json={**spray, "applied_at": at(START + timedelta(days=5))},
        ),
        201,
    )
    ok(
        api.post(
            f"{V1}/zones/{z1['id']}/pesticide-applications",
            json={**spray, "applied_at": at(START - timedelta(days=2))},
        ),
        201,
    )
    ok(
        api.post(
            f"{V1}/zones/{z1['id']}/pesticide-applications",
            json={**spray, "applied_at": at(START - timedelta(days=4))},
        ),
        201,
    )
    return {**f, "zones": [z1, z2]}


def test_analytics_counts_only_the_period_and_compares(api: TestClient, farm: dict[str, Any]) -> None:
    a = ok(api.get(f"{V1}/farms/{farm['id']}/analytics?start={START}&end={END}"))
    assert a["period"] == {"start": START.isoformat(), "end": END.isoformat(), "days": 10, "timezone": "UTC"}
    assert a["previous_period"]["end"] == (START - timedelta(days=1)).isoformat()
    w = a["water"]
    assert (w["irrigation_events"], w["irrigation_liters"], a["area_ha"]) == (2, 40000, 2.0)
    assert w["irrigation_liters_per_ha"] == 20000 and w["irrigation_mm"] == 2.0  # 40 m3 over 2 ha
    assert {z["zone"]: z["mm"] for z in w["by_zone"]} == {"A": 2.0, "B": 2.0}
    assert w["rain_mm"] is None and w["weather_days_covered"] == 0  # no stored weather: unknown, not zero
    f = a["fertilizer"]
    assert f["nutrients_kg"] == {"n": 46.0, "p2o5": 0.0, "k2o": 0.0} and f["nutrients_kg_per_ha"]["n"] == 23.0
    assert (f["organic_kg"], f["without_grade"]) == (500, 1)
    p = a["pesticides"]
    assert (p["applications"], p["applications_per_ha"], p["evidence_share"]) == (1, 0.5, 0.0)
    ind = {i["indicator"]: i for i in a["indicators"]}
    water = ind["Irrigation water per ha"]
    assert (water["current"], water["previous"], water["change_pct"]) == (20000.0, 40000.0, -50.0)
    sprays = ind["Pesticide applications per ha"]
    assert (sprays["current"], sprays["previous"], sprays["change_pct"]) == (0.5, 1.0, -50.0)
    assert (
        any("only from records in AGRI-SENSE" in n for n in a["notes"]) and a["uses_simulated_data"] is False
    )


def test_reports_snapshot_csv_and_delete(api: TestClient, farm: dict[str, Any]) -> None:
    body = {"report_type": "farm_summary", "period_start": START.isoformat(), "period_end": END.isoformat()}
    r = ok(api.post(f"{V1}/farms/{farm['id']}/reports", json=body), 201)
    assert r["status"] == "ready" and r["title"].startswith("Farm summary: Report Farm")
    assert r["content"]["water"]["irrigation_liters"] == 40000

    # A snapshot does not change when records change afterwards.
    ok(
        api.post(
            f"{V1}/zones/{farm['zones'][0]['id']}/irrigation-events",
            json={
                "method": "drip",
                "status": "completed",
                "trigger": "manual",
                "started_at": at(START + timedelta(days=6)),
                "volume_liters": 5000,
            },
        ),
        201,
    )
    assert ok(api.get(f"{V1}/reports/{r['id']}"))["content"]["water"]["irrigation_liters"] == 40000

    sus = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/reports",
            json={**body, "report_type": "sustainability", "title": "Season indicators"},
        ),
        201,
    )
    assert (
        sus["title"] == "Season indicators"
        and "water" not in sus["content"]
        and len(sus["content"]["indicators"]) == 7
    )
    listing = ok(api.get(f"{V1}/farms/{farm['id']}/reports"))
    assert listing["total"] == 2 and "content" not in listing["items"][0]

    res = api.get(f"{V1}/reports/{r['id']}/csv")
    assert (
        res.status_code == 200
        and res.headers["content-type"].startswith("text/csv")
        and "attachment" in res.headers["content-disposition"]
    )
    rows = list(csv.reader(io.StringIO(res.text)))
    assert rows[0] == ["section", "metric", "value"] and ["water", "irrigation_liters", "40000"] in rows

    assert api.delete(f"{V1}/reports/{r['id']}").status_code == 204
    err(api.get(f"{V1}/reports/{r['id']}"), 404, "not_found")


def test_validation_and_isolation(client_for: ClientFor, api: TestClient, farm: dict[str, Any]) -> None:
    err(api.get(f"{V1}/farms/{farm['id']}/analytics?start={END}&end={START}"), 422, "invalid")
    err(
        api.get(f"{V1}/farms/{farm['id']}/analytics?start={END - timedelta(days=500)}&end={END}"),
        422,
        "invalid",
    )
    err(
        api.post(
            f"{V1}/farms/{farm['id']}/reports",
            json={
                "report_type": "farm_summary",
                "period_start": END.isoformat(),
                "period_end": START.isoformat(),
            },
        ),
        422,
        "validation_error",
    )
    default = ok(api.get(f"{V1}/farms/{farm['id']}/analytics"))
    assert default["period"]["days"] == 30
    r = ok(
        api.post(
            f"{V1}/farms/{farm['id']}/reports",
            json={
                "report_type": "sustainability",
                "period_start": START.isoformat(),
                "period_end": END.isoformat(),
            },
        ),
        201,
    )
    mallory = client_for("mallory@example.com")
    err(mallory.get(f"{V1}/farms/{farm['id']}/analytics"), 404, "not_found")
    err(mallory.get(f"{V1}/reports/{r['id']}"), 404, "not_found")
    err(mallory.get(f"{V1}/reports/{r['id']}/csv"), 404, "not_found")
    err(mallory.delete(f"{V1}/reports/{r['id']}"), 404, "not_found")
