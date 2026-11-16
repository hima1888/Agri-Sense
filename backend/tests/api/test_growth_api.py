"""Crop growth stages: FAO-56 proportions, scaling, current position, endpoints."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain import growth
from tests.api.helpers import V1, err, make_zone, ok

KEYS = ["seed", "germination", "seedling", "vegetative", "flowering", "formation", "maturity", "harvest"]


@pytest.mark.parametrize("crop", growth.supported())
def test_stages_are_contiguous_and_cover_the_cycle(crop: str) -> None:
    m = growth.stages(crop, None)
    st = m["stages"]
    assert [s["key"] for s in st] == KEYS
    assert m["cycle_days"] == sum(growth.FAO56_STAGE_DAYS[crop][0])  # no catalogue length: FAO total
    for a, b in zip(st[1:-2], st[2:-1], strict=True):  # noqa: RUF007
        assert b["start_day"] == a["end_day"] + 1  # no gaps, no overlap
    assert (
        st[1]["start_day"] == 1
        and st[-2]["end_day"] == m["cycle_days"]
        and st[-1]["start_day"] == m["cycle_days"]
    )


def test_fao_lengths_scale_to_the_cycle_and_keep_proportions() -> None:
    m = growth.stages("Tomato", 110)  # FAO 30/40/40/25 = 135 days
    by = {s["key"]: s for s in m["stages"]}
    assert m["cycle_days"] == 110 and m["fao56"]["initial"] == 30
    initial = by["seedling"]["end_day"]  # end of FAO initial stage
    assert initial == round(30 * 110 / 135)
    assert by["vegetative"]["end_day"] - by["vegetative"]["start_day"] + 1 == round(40 * 110 / 135)
    assert (
        by["formation"]["name"] == "Fruiting"
        and growth.stages("Wheat", None)["stages"][5]["name"] == "Grain formation"
    )
    assert by["germination"]["approximate_boundary"] and not by["vegetative"]["approximate_boundary"]


def test_unsupported_and_perennial_crops_are_refused() -> None:
    with pytest.raises(growth.UnsupportedCropError, match="perennial"):
        growth.stages("Mango", None)
    with pytest.raises(growth.UnsupportedCropError, match="Supported"):
        growth.stages("Saffron", 100)
    assert growth.crop_key("Corn") == "maize"


def test_current_position() -> None:
    m = growth.stages("Maize", 150)
    today = date(2026, 6, 1)
    assert growth.current(m, None, today) is None
    assert growth.current(m, today, today)["stage_key"] == "seed"  # type: ignore[index]
    mid = growth.current(m, today - timedelta(days=60), today)
    assert mid is not None and mid["stage_key"] == "vegetative" and mid["progress"] == 0.4
    late = growth.current(m, today - timedelta(days=200), today)
    assert late is not None and late["stage_key"] == "harvest" and "Past" in late["note"]


def test_endpoints(api: TestClient, admin: TestClient) -> None:
    tomato = ok(
        admin.post(
            f"{V1}/crops", json={"common_name": "Tomato", "category": "vegetable", "typical_cycle_days": 110}
        ),
        201,
    )
    mango = ok(admin.post(f"{V1}/crops", json={"common_name": "Mango", "category": "fruit"}), 201)
    g = ok(api.get(f"{V1}/crops/{tomato['id']}/growth"))
    assert g["cycle_days"] == 110 and g["cycle_days_source"] == "crop catalogue" and len(g["stages"]) == 8
    e = err(api.get(f"{V1}/crops/{mango['id']}/growth"), 422, "invalid")
    assert "perennial" in e["message"]

    farm: dict[str, Any] = ok(api.post(f"{V1}/farms", json={"name": "Growth Farm", "timezone": "UTC"}), 201)
    zone = make_zone(api, farm["id"])
    sown = date.today() - timedelta(days=50)
    cyc = ok(api.post(f"{V1}/zones/{zone['id']}/crop-cycles", json={
        "crop_id": tomato["id"], "status": "growing", "planted_on": sown.isoformat(),
        "expected_harvest_on": (sown + timedelta(days=120)).isoformat()}), 201)  # fmt: skip
    cg = ok(api.get(f"{V1}/crop-cycles/{cyc['id']}/growth"))
    assert cg["cycle_days"] == 120 and cg["cycle_days_source"] == "crop cycle dates"
    assert cg["current"]["day"] == 50 and cg["current"]["stage_key"] == "vegetative"
