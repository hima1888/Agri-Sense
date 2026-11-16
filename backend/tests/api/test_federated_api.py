"""Federated learning: FedAvg maths on synthetic data with a known answer, then the API with two farms."""

from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import federated as fl
from app.models import FederatedClientUpdate, SensorReading
from tests.api.helpers import V1, err, make_zone, ok
from tests.conftest import ClientFor

TRUE_W = np.array([0.1, -0.8, -0.3, 0.2, -0.5, 1.5, 0.0, 0.4])


def synthetic(n: int, seed: int, shift: float = 0.0) -> fl.ClientData:
    rng = np.random.default_rng(seed)
    x = np.c_[np.ones(n), rng.normal(shift, 1, (n, 7))]
    return fl.ClientData(x, x @ TRUE_W + rng.normal(0, 0.05, n))


# --- FedAvg maths -------------------------------------------------------------------
def test_fedavg_is_the_sample_weighted_mean() -> None:
    w = fl.fedavg([(np.array([1.0, 0.0]), 1), (np.array([4.0, 3.0]), 3)])
    assert w.tolist() == [3.25, 2.25]


def test_local_training_recovers_a_known_linear_relation() -> None:
    d = synthetic(400, 1)
    w = fl.local_train(np.zeros(8), d, steps=2000, lr=0.05, l2=0.0)
    assert np.allclose(w, TRUE_W, atol=0.02)


def test_federated_beats_persistence_and_matches_clients_without_pooling() -> None:
    clients = {"a": synthetic(120, 2, shift=-0.5), "b": synthetic(120, 3, shift=0.5)}
    r = fl.run_fedavg(clients, rounds=60, local_steps=10, lr=0.05, l2=0.0)
    o = r["overall"]
    assert o["mae_federated"] < 0.2 * o["mae_persistence"]
    assert np.allclose(r["weights"], TRUE_W, atol=0.05)
    assert [h["round"] for h in r["history"]] == list(range(1, 61))
    assert r["history"][-1]["test_mse"] < r["history"][0]["test_mse"]
    first = r["round_updates"][0]
    assert {u["client"] for u in first} == {"a", "b"} and all(
        u["num_samples"] == 96 for u in first
    )  # 80 % train
    assert set(r["per_client"]["a"]) == {
        "train_samples",
        "test_samples",
        "mae_persistence",
        "mae_local_only",
        "mae_federated",
    }
    assert fl.explain(r["weights"])[0]["feature"] == "rainfall"  # largest |weight| in TRUE_W


def test_featurize_uses_fixed_scaling() -> None:
    x = fl.featurize(theta=35, temp=15, rh=90, light=25_000, rain=10, hour=6)
    assert x[:6] == [1.0, 1.0, -1.0, 1.0, 0.5, 2.0] and x[6] == pytest.approx(1.0) and abs(x[7]) < 1e-9


# --- API ----------------------------------------------------------------------------
def simulated_farm(client: TestClient, name: str) -> dict[str, Any]:
    farm = ok(
        client.post(
            f"{V1}/farms", json={"name": name, "timezone": "UTC", "latitude": 17.4, "longitude": 78.5}
        ),
        201,
    )
    zone = make_zone(client, farm["id"])
    ok(client.post(f"{V1}/zones/{zone['id']}/simulator/provision", json={}), 201)
    ok(client.post(f"{V1}/farms/{farm['id']}/simulator/backfill", json={"hours": 48, "step_minutes": 30}))
    return {**farm, "zone_id": zone["id"]}


def test_enrollment_run_privacy_and_forecast(
    client_for: ClientFor, api: TestClient, admin: TestClient, db: Session
) -> None:
    other = client_for("neighbour@example.com")
    a = simulated_farm(api, "Farm A")
    b = simulated_farm(other, "Farm B")

    view = ok(api.get(f"{V1}/farms/{a['id']}/federated"))
    assert view["enrollment"] is None and view["local_samples"] >= view["min_samples"]
    assert view["uses_simulated_data"] and "sensor readings" in view["not_shared"]
    assert ok(api.get(f"{V1}/zones/{a['zone_id']}/federated/forecast"))["status"] == "no_model"

    ok(api.post(f"{V1}/farms/{a['id']}/federated/enroll"))
    failed = ok(admin.post(f"{V1}/federated/runs", json={"rounds": 3}), 201)
    assert failed["status"] == "failed" and "at least 2" in failed["reason"]  # one farm is not a federation

    ok(other.post(f"{V1}/farms/{b['id']}/federated/enroll"))
    run = ok(admin.post(f"{V1}/federated/runs", json={"rounds": 5, "local_steps": 5}), 201)
    assert run["status"] == "completed" and run["clients"] == 2 and len(run["history"]) == 5
    assert set(run["overall"]) == {"mae_persistence", "mae_local_only", "mae_federated", "test_samples"}
    assert run["uses_simulated_data"] is True and len(run["per_client"]) == 2

    # Only weights, counts and metrics were stored: 2 clients x 5 rounds, no readings copied anywhere.
    updates = db.scalars(select(FederatedClientUpdate).where(FederatedClientUpdate.run_id == run["id"])).all()
    assert len(updates) == 10 and all(set(u.local_metrics or {}) == {"weights", "train_mse"} for u in updates)
    assert all(len(u.local_metrics["weights"]) == len(fl.FEATURES) for u in updates if u.local_metrics)

    # Each owner sees overall results and only their own farm's numbers.
    mine = ok(api.get(f"{V1}/farms/{a['id']}/federated"))["runs"][0]
    assert mine["participated"] and mine["your_metrics"]["test_samples"] > 0 and mine["per_client"] is None
    theirs = ok(other.get(f"{V1}/farms/{b['id']}/federated"))["runs"][0]
    assert theirs["your_metrics"] != mine["your_metrics"] and theirs["per_client"] is None

    fc = ok(api.get(f"{V1}/zones/{a['zone_id']}/federated/forecast"))
    assert fc["status"] in ("forecast", "no_recent_data")
    if fc["status"] == "forecast":
        assert fc["uses_simulated_data"] and isinstance(fc["beats_baseline"], bool)
        assert fc["predicted_moisture_6h_pct"] == pytest.approx(
            fc["moisture_now_pct"] + fc["predicted_change_6h_pct_points"], abs=0.02
        )
        assert (fc["advice"] is None) == fc["beats_baseline"]

    ok(api.post(f"{V1}/farms/{a['id']}/federated/leave"))
    assert ok(api.get(f"{V1}/farms/{a['id']}/federated"))["enrollment"]["status"] == "inactive"
    assert db.scalar(select(SensorReading.id).limit(1)) is not None  # readings stay where they were


def test_permissions(client_for: ClientFor, api: TestClient) -> None:
    farm = ok(api.post(f"{V1}/farms", json={"name": "Private", "timezone": "UTC"}), 201)
    err(api.post(f"{V1}/federated/runs", json={}), 403, "forbidden")
    err(api.get(f"{V1}/federated/runs"), 403, "forbidden")
    mallory = client_for("mallory@example.com")
    err(mallory.get(f"{V1}/farms/{farm['id']}/federated"), 404, "not_found")
    err(mallory.post(f"{V1}/farms/{farm['id']}/federated/enroll"), 404, "not_found")
