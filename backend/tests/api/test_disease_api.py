"""Leaf-disease screening: routing and fallback rules (controlled probabilities) and the API (real models)."""

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.vision import disease, recognizer
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor

FIX = Path(__file__).parents[1] / "fixtures"
CORN = (FIX / "corn_rust_field.jpg").read_bytes()
WHEAT = (FIX / "wheat_leaf_rust_field.jpg").read_bytes()
BANANA = (FIX / "banana.jpg").read_bytes()
needs_models = pytest.mark.skipif(
    not (disease.model_available(disease.VIT) and disease.model_available(disease.PLANTVILLAGE)),
    reason="disease models not installed (docs/DISEASE_MODELS.md)",
)


def probs_for(m: disease.DiseaseModel, spec: dict[tuple[str | None, str | None], float]) -> np.ndarray:
    p = np.full(len(m.labels), 0.0)
    for lbl, v in spec.items():
        p[m.labels.index(lbl)] = v
    rest = (1 - p.sum()) / max(1, (p == 0).sum())
    return np.where(p == 0, rest, p)


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace inference with chosen probabilities; also mark the photo as not-produce."""
    state: dict[str, Any] = {}
    monkeypatch.setattr(
        disease, "run", lambda m, img: (state.setdefault("models", []).append(m.key), state["p"](m))[1]
    )
    monkeypatch.setattr(
        recognizer,
        "recognize",
        lambda data, explain=True: {"outcome": "unsupported", "label": None, "confidence": 0},
    )
    return state


# --- routing ------------------------------------------------------------------------
def test_routing_prefers_vit_and_uses_plantvillage_only_for_other_crops() -> None:
    assert disease.model_for_crop("rice") is disease.VIT
    assert disease.model_for_crop("corn") is disease.VIT  # both cover corn: ViT wins
    assert disease.model_for_crop("potato") is disease.VIT
    assert disease.model_for_crop("tomato") is disease.PLANTVILLAGE
    assert disease.model_for_crop("mango") is None
    assert disease.normalise_crop("Maize") == "corn" and disease.normalise_crop(" Paddy ") == "rice"


def test_preprocessing_shapes_and_normalisation() -> None:
    img = Image.new("RGB", (640, 300), (255, 0, 0))
    for m in (disease.VIT, disease.PLANTVILLAGE):
        x = disease.preprocess(m, img)
        assert x.shape == (1, 3, 224, 224) and x.dtype == np.float32
        assert x[0, 0].max() == pytest.approx(1.0) and x[0, 1].min() == pytest.approx(-1.0)


def test_label_tables_match_model_outputs() -> None:
    assert len(disease.VIT.labels) == 13 and disease.VIT.labels[3] == (None, None)  # "Invalid"
    assert len(disease.PLANTVILLAGE.labels) == 38 and disease.PLANTVILLAGE.labels[37] == ("tomato", None)


# --- decision rules (controlled probabilities) --------------------------------------
def test_confident_answer_for_chosen_crop_is_a_possible_disease(fake_run: Any) -> None:
    fake_run["p"] = lambda m: probs_for(m, {("tomato", "Early blight"): 0.9})
    r = disease.screen(CORN, "tomato")
    assert fake_run["models"] == ["plantvillage"]
    assert (r["outcome"], r["label"], r["is_healthy"]) == ("possible_disease", "Tomato: Early blight", False)
    assert r["severity"] in ("low", "moderate", "high") and r["model"]["key"] == "plantvillage"
    assert all(c["passed"] for c in r["checks"])
    assert any("not a diagnosis" in lim for lim in r["limitations"])


def test_healthy_answer(fake_run: Any) -> None:
    fake_run["p"] = lambda m: probs_for(m, {("rice", None): 0.95})
    r = disease.screen(CORN, "rice")
    assert (r["outcome"], r["severity"], r["affected_area_pct"]) == ("possible_healthy", "none", None)


def test_model_naming_another_crop_is_refused_not_rescored(fake_run: Any) -> None:
    # The tomato-as-potato failure seen in the smoke test.
    fake_run["p"] = lambda m: probs_for(m, {("potato", "Early blight"): 0.99})
    r = disease.screen(CORN, "corn")
    assert r["outcome"] == "cannot_identify" and r["label"] is None
    assert "potato class" in r["reason"]


def test_invalid_class_is_refused(fake_run: Any) -> None:
    fake_run["p"] = lambda m: probs_for(m, {(None, None): 0.7})
    r = disease.screen(CORN, "wheat")
    assert r["outcome"] == "cannot_identify" and "Invalid" in r["reason"]


@pytest.mark.parametrize(("top", "second"), [(0.55, 0.10), (0.62, 0.45)])
def test_low_confidence_or_small_margin_is_uncertain(fake_run: Any, top: float, second: float) -> None:
    fake_run["p"] = lambda m: probs_for(m, {("corn", "Common rust"): top, ("corn", "Gray leaf spot"): second})
    r = disease.screen(CORN, "corn")
    assert r["outcome"] == "uncertain" and r["label"] == "Corn: Common rust" and r["severity"] is None
    assert r["candidates"][1]["label"] == "Corn: Gray leaf spot"


def test_missing_or_unsupported_crop(fake_run: Any) -> None:
    fake_run["p"] = lambda m: probs_for(m, {})
    assert disease.screen(CORN, None)["outcome"] == "cannot_identify"
    r = disease.screen(CORN, "mango")
    assert r["outcome"] == "unsupported_crop" and "Supported:" in r["reason"]
    assert "models" not in fake_run  # no model was run


def test_lesion_area_heuristic() -> None:
    img = Image.new("RGB", (200, 200), (40, 140, 40))
    img.paste((140, 90, 30), (0, 0, 100, 100))  # brown quarter
    assert disease.lesion_area(img) == pytest.approx(25, abs=1)
    assert disease.lesion_area(Image.new("RGB", (200, 200), (255, 255, 255))) is None


def test_checksum_mismatch_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = tmp_path / "x.onnx"
    bad.write_bytes(b"not the model")
    m = disease.DiseaseModel(**{**disease.VIT.__dict__, "key": "tmp", "file": str(bad)})
    monkeypatch.setattr(disease, "MODEL_DIR", tmp_path)
    with pytest.raises(recognizer.ModelUnavailableError, match="checksum"):
        disease._session(m)
    assert hashlib.sha256(b"not the model").hexdigest() != m.sha256


# --- real models ---------------------------------------------------------------------
@needs_models
def test_real_models_on_field_photos_and_produce() -> None:
    # Known, documented behaviour (docs/DISEASE_MODELS.md): a field corn-rust photo slips through as a
    # wrong "gray leaf spot" call; a wheat leaf-rust photo is refused; a banana is "not a leaf".
    corn = disease.screen(CORN, "corn")
    assert corn["outcome"] == "possible_disease" and corn["model"]["key"] == "crop_vit"
    assert disease.screen(WHEAT, "wheat")["outcome"] == "cannot_identify"
    assert disease.screen(BANANA, "rice")["outcome"] == "not_a_leaf"


@pytest.fixture(autouse=True)
def uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    return tmp_path


@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    f: dict[str, Any] = ok(api.post(f"{V1}/farms", json={"name": "Disease Farm", "timezone": "UTC"}), 201)
    return f


def screen(client: TestClient, farm_id: int, data: bytes, **form: Any) -> Any:
    files = {"file": ("leaf.jpg", data, "image/jpeg")}
    return client.post(f"{V1}/farms/{farm_id}/vision/disease-checks", files=files, data=form)


def test_models_endpoint(api: TestClient) -> None:
    info = ok(api.get(f"{V1}/vision/disease/models"))
    assert [m["key"] for m in info["models"]] == ["crop_vit", "plantvillage"]
    assert (
        info["supported_crops"]["rice"] == "crop_vit" and info["supported_crops"]["tomato"] == "plantvillage"
    )
    assert info["thresholds"] == {"min_top1": 0.6, "min_margin": 0.2}
    assert "Conflicting" in info["models"][1]["published_accuracy"]


@needs_models
def test_screen_store_list_image_delete(
    api: TestClient, admin: TestClient, farm: dict[str, Any], uploads: Path
) -> None:
    zone = make_zone(api, farm["id"])
    crop = ok(admin.post(f"{V1}/crops", json={"common_name": "Maize", "category": "cereal"}), 201)
    ok(
        api.post(f"{V1}/zones/{zone['id']}/crop-cycles", json={"crop_id": crop["id"], "status": "growing"}),
        201,
    )

    r = ok(screen(api, farm["id"], CORN, zone_id=zone["id"]), 201)  # crop taken from the zone
    assert (r["crop"], r["crop_source"], r["model"]["key"]) == ("corn", "zone crop cycle", "crop_vit")
    assert r["saved"] and r["model"]["id"]
    det = ok(api.get(f"{V1}/vision/disease-checks/{r['detection_id']}"))
    assert det["explanation"]["model"]["name"] == "crop-leaf-diseases-vit" and det["explanation"]["checks"]
    assert ok(api.get(f"{V1}/farms/{farm['id']}/vision/disease-checks"))["total"] == 1
    img = api.get(f"{V1}/vision/disease-checks/{det['id']}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert api.delete(f"{V1}/vision/disease-checks/{det['id']}").status_code == 204
    assert not list(uploads.rglob("*.jpg"))


@needs_models
def test_refusals_are_returned_but_not_stored(api: TestClient, farm: dict[str, Any]) -> None:
    for data, crop, outcome in (
        (WHEAT, "wheat", "cannot_identify"),
        (BANANA, "rice", "not_a_leaf"),
        (CORN, "mango", "unsupported_crop"),
    ):
        r = ok(screen(api, farm["id"], data, crop=crop), 201)
        assert (r["outcome"], r["saved"]) == (outcome, False)
    r = ok(screen(api, farm["id"], CORN), 201)  # no crop, no zone
    assert r["outcome"] == "cannot_identify" and "Choose the crop" in r["reason"]
    assert ok(api.get(f"{V1}/farms/{farm['id']}/vision/disease-checks"))["total"] == 0


def test_bad_upload_and_isolation(client_for: ClientFor, api: TestClient, farm: dict[str, Any]) -> None:
    err(
        api.post(
            f"{V1}/farms/{farm['id']}/vision/disease-checks", files={"file": ("a.txt", b"x", "text/plain")}
        ),
        422,
        "invalid",
    )
    mallory = client_for("mallory@example.com")
    err(screen(mallory, farm["id"], CORN, crop="corn"), 404, "not_found")
    err(mallory.get(f"{V1}/farms/{farm['id']}/vision/disease-checks"), 404, "not_found")


@needs_models
def test_healthy_field_leaf_is_refused_not_misdiagnosed() -> None:
    """TEST 3 (real models): a healthy tomato field photo (CC0, Wikimedia Commons).

    The disease model alone says 'Tomato: Late blight' at about 77 %, a false positive that would pass the
    thresholds; the produce gate refuses the photo first. The app must never report this leaf as diseased.
    """
    data = (FIX / "tomato_healthy_field.jpg").read_bytes()
    r = disease.screen(data, "tomato")
    assert r["outcome"] == "not_a_leaf" and r["disease"] is None
    raw = disease.run(disease.PLANTVILLAGE, disease.decode(data))
    assert (
        disease.label_text(disease.PLANTVILLAGE, int(raw.argmax())) == "Tomato: Late blight"
    )  # documented model error
