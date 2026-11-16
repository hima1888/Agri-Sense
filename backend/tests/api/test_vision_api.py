"""Plant & produce recognition with the real ONNX model (skipped if the model is not installed)."""

import io
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.vision import recognizer
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor

BANANA = (Path(__file__).parents[1] / "fixtures" / "banana.jpg").read_bytes()
needs_model = pytest.mark.skipif(
    not recognizer.model_available(), reason="run python -m app.cli.fetch_models"
)


def png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8)).save(buf, "PNG")
    return buf.getvalue()


NOISE = png(np.random.default_rng(1).integers(0, 255, (300, 300, 3)))
DARK_SMALL = png(np.full((120, 160, 3), 8))


@pytest.fixture(autouse=True)
def uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    return tmp_path


@pytest.fixture
def farm(api: TestClient) -> dict[str, Any]:
    f: dict[str, Any] = ok(api.post(f"{V1}/farms", json={"name": "Vision Farm", "timezone": "UTC"}), 201)
    return f


def upload(client: TestClient, farm_id: int, data: bytes, ctype: str = "image/jpeg", **form: Any) -> Any:
    return client.post(
        f"{V1}/farms/{farm_id}/vision/recognitions", files={"file": ("photo", data, ctype)}, data=form
    )


# --- model-level ----------------------------------------------------------------
def test_quality_checks_flag_dark_low_resolution_images() -> None:
    img = recognizer.decode(DARK_SMALL)
    status = {q["key"]: q["status"] for q in recognizer.quality(img, recognizer.preprocess(img))}
    assert status["resolution"] == "low" and status["brightness"] == "poor" and status["contrast"] == "poor"


def test_preprocess_matches_model_input() -> None:
    arr = recognizer.preprocess(recognizer.decode(BANANA))
    assert arr.shape == (224, 224, 3) and arr.min() >= 0 and arr.max() <= 1


def test_corrupt_file_is_rejected() -> None:
    with pytest.raises(recognizer.BadImageError):
        recognizer.decode(b"<html>not an image</html>")


@needs_model
def test_real_photo_is_recognised_with_explanation() -> None:
    r = recognizer.recognize(BANANA)
    assert (r["outcome"], r["label"], r["subject_type"]) == ("recognized", "banana", "fruit")
    assert r["confidence"] > 0.9 and r["candidates"][0]["label"] == "banana"
    grid = r["explanation"]["grid"]
    assert len(grid) == 7 and all(len(row) == 7 for row in grid) and max(map(max, grid)) == 1.0
    assert any("not trained on farm photos" in lim for lim in r["limitations"])


@needs_model
def test_non_produce_image_is_unsupported_not_forced_into_a_class() -> None:
    r = recognizer.recognize(NOISE)
    assert r["outcome"] == "unsupported" and r["label"] is None and r["explanation"]["grid"] is None
    assert r["model_sees"][0]["label"]  # still shows what the model thinks it sees


# --- API --------------------------------------------------------------------------
def test_model_info_lists_supported_classes_and_metrics(api: TestClient) -> None:
    info = ok(api.get(f"{V1}/vision/model"))
    assert info["metrics"]["top1_accuracy"] == 0.6948 and len(info["supported"]) == 25
    assert {"label": "banana", "subject_type": "fruit"} in info["supported"]


@needs_model
def test_recognise_store_list_image_delete(api: TestClient, farm: dict[str, Any], uploads: Path) -> None:
    zone = make_zone(api, farm["id"])
    r = ok(upload(api, farm["id"], BANANA, zone_id=zone["id"]), 201)
    assert r["saved"] and r["label"] == "banana" and r["model"]["name"] == "mobilenetv2-imagenet"
    files = list(uploads.rglob("*.jpg"))
    assert len(files) == 1 and Image.open(files[0]).getexif() == {}  # re-encoded, EXIF stripped

    listing = ok(api.get(f"{V1}/farms/{farm['id']}/vision/recognitions"))
    assert listing["total"] == 1
    det = listing["items"][0]
    assert det["zone_id"] == zone["id"] and det["explanation"]["occlusion"]["grid"]
    img = api.get(f"{V1}/vision/recognitions/{det['id']}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"

    assert api.delete(f"{V1}/vision/recognitions/{det['id']}").status_code == 204
    assert not files[0].exists()
    err(api.get(f"{V1}/vision/recognitions/{det['id']}"), 404, "not_found")


@needs_model
def test_unsupported_result_is_returned_but_not_stored(api: TestClient, farm: dict[str, Any]) -> None:
    r = ok(upload(api, farm["id"], NOISE, "image/png"), 201)
    assert r["outcome"] == "unsupported" and r["saved"] is False and r["detection_id"] is None
    assert ok(api.get(f"{V1}/farms/{farm['id']}/vision/recognitions"))["total"] == 0


def test_upload_validation(api: TestClient, farm: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    err(upload(api, farm["id"], b"hello", "text/plain"), 422, "invalid")
    err(upload(api, farm["id"], b"", "image/jpeg"), 422, "invalid")
    err(upload(api, farm["id"], b"not really a jpeg", "image/jpeg"), 422, "invalid")
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0.001)
    err(upload(api, farm["id"], BANANA), 422, "invalid")


def test_missing_model_is_a_clear_503(
    api: TestClient, farm: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(recognizer, "_model", None)
    monkeypatch.setattr(recognizer, "MODEL_FILE", tmp_path / "missing.onnx")
    e = err(upload(api, farm["id"], BANANA), 503, "model_unavailable")
    assert "fetch_models" in e["message"]


@needs_model
def test_recognition_is_owner_only(client_for: ClientFor, api: TestClient, farm: dict[str, Any]) -> None:
    det = ok(upload(api, farm["id"], BANANA), 201)["detection_id"]
    mallory = client_for("mallory@example.com")
    err(upload(mallory, farm["id"], BANANA), 404, "not_found")
    err(mallory.get(f"{V1}/vision/recognitions/{det}/image"), 404, "not_found")
    err(mallory.delete(f"{V1}/vision/recognitions/{det}"), 404, "not_found")
    other = ok(api.post(f"{V1}/farms", json={"name": "Other", "timezone": "UTC"}), 201)
    zone = make_zone(api, other["id"])
    err(upload(api, farm["id"], BANANA, zone_id=zone["id"]), 422, "invalid")
