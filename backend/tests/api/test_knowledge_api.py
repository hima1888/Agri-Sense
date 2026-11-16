"""Structured disease knowledge: complete coverage of the models' labels, endpoints, and attachment rules."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.knowledge import diseases as kb
from app.vision import disease
from tests.api.helpers import V1, err, ok
from tests.api.test_disease_api import CORN, fake_run, probs_for, screen, uploads  # noqa: F401  (fixtures)

FIELDS = (
    "what",
    "symptoms",
    "causes",
    "conditions",
    "spread",
    "management",
    "prevention",
    "sustainable",
    "monitor",
    "seek_advice",
)


def test_every_disease_label_of_every_model_has_a_knowledge_entry() -> None:
    for m in disease.MODELS.values():
        for crop, name in m.labels:
            if crop and name:
                key = kb.key_for(crop, name)
                assert key in kb.BY_KEY, f"{m.key}: no knowledge for {crop} / {name}"
                assert crop in kb.BY_KEY[key].crops
    assert set(kb.LABEL_MAP.values()) == set(kb.BY_KEY)  # no orphan entries


def test_entries_are_complete_and_name_no_products_or_doses() -> None:
    for e in kb.ENTRIES:
        d = e.to_dict()
        for f in FIELDS:
            assert d[f], f"{e.key}.{f} is empty"
        assert d["reviewed"] is False and "Not reviewed" in d["source"]
        text = " ".join(str(v) for v in d.values()).lower()
        assert "ml/l" not in text and "g/l" not in text and "kg/ha" not in text  # no dose advice


def test_label_lookup() -> None:
    assert kb.key_for_label("Corn: Gray leaf spot") == "gray_leaf_spot"
    assert kb.key_for_label("Bell pepper: Bacterial spot") == "bacterial_spot"
    assert kb.key_for_label("Tomato: healthy") is None and kb.key_for_label(None) is None


def test_knowledge_endpoints(api: TestClient) -> None:
    items = ok(api.get(f"{V1}/knowledge/diseases"))
    assert len(items) == len(kb.ENTRIES) and items[0]["source"]
    late = ok(api.get(f"{V1}/knowledge/diseases/late_blight"))
    assert late["pathogen"] == "Phytophthora infestans" and set(late["crops"]) == {"potato", "tomato"}
    err(api.get(f"{V1}/knowledge/diseases/nope"), 404, "not_found")


@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    f: dict[str, Any] = ok(api.post(f"{V1}/farms", json={"name": "Knowledge Farm", "timezone": "UTC"}), 201)
    return f


def test_knowledge_attached_only_to_a_confident_disease(
    api: TestClient,
    farm: dict[str, Any],
    fake_run: Any,  # noqa: F811
) -> None:
    data = CORN

    fake_run["p"] = lambda m: probs_for(m, {("tomato", "Late blight"): 0.9})
    r = ok(screen(api, farm["id"], data, crop="tomato"), 201)
    assert r["outcome"] == "possible_disease" and r["knowledge_key"] == "late_blight"
    assert r["knowledge"]["name"] == "Late blight" and r["healthy_guidance"] is None
    rec = ok(api.get(f"{V1}/vision/disease-checks/{r['detection_id']}"))
    assert rec["knowledge_key"] == "late_blight"  # saved history links to the same entry

    fake_run["p"] = lambda m: probs_for(m, {("tomato", None): 0.9})
    r = ok(screen(api, farm["id"], data, crop="tomato"), 201)
    assert r["outcome"] == "possible_healthy" and r["knowledge"] is None and r["healthy_guidance"]["monitor"]

    fake_run["p"] = lambda m: probs_for(m, {("tomato", "Late blight"): 0.55, ("tomato", "Early blight"): 0.4})
    r = ok(screen(api, farm["id"], data, crop="tomato"), 201)
    assert (
        r["outcome"] == "uncertain" and r["knowledge"] is None
    )  # unconfirmed: no guidance shown as the answer


def test_disease_check_in_a_zone_shows_on_the_twin_with_growth_stage(
    api: TestClient,
    admin: TestClient,
    farm: dict[str, Any],
    fake_run: Any,  # noqa: F811
) -> None:
    from datetime import date, timedelta

    from tests.api.helpers import make_zone

    zone = make_zone(api, farm["id"])
    other = make_zone(api, farm["id"], name="Other zone")
    tomato = ok(admin.post(f"{V1}/crops", json={"common_name": "Tomato", "category": "vegetable"}), 201)
    sown = (date.today() - timedelta(days=50)).isoformat()
    ok(api.post(f"{V1}/zones/{zone['id']}/crop-cycles",
                json={"crop_id": tomato["id"], "status": "growing", "planted_on": sown}), 201)  # fmt: skip

    twin = ok(api.get(f"{V1}/farms/{farm['id']}/twin"))
    z = next(x for x in twin["zones"] if x["id"] == zone["id"])
    assert z["health"] is None and z["crop"]["stage_key"] == "vegetative"  # 50 of 135 FAO days

    fake_run["p"] = lambda m: probs_for(m, {("tomato", "Late blight"): 0.9})
    r = ok(screen(api, farm["id"], CORN, zone_id=zone["id"]), 201)  # crop comes from the zone's cycle
    assert r["crop_source"] == "zone crop cycle" and r["saved"]

    twin = ok(api.get(f"{V1}/farms/{farm['id']}/twin"))
    z = next(x for x in twin["zones"] if x["id"] == zone["id"])
    assert z["health"]["state"] == "disease" and z["health"]["knowledge_key"] == "late_blight"
    assert z["health"]["detection_id"] == r["detection_id"]
    assert next(x for x in twin["zones"] if x["id"] == other["id"])["health"] is None  # only the checked zone
