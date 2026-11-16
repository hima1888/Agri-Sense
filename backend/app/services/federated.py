# ruff: noqa: E501  (compact result dictionaries)
"""Federated learning (Phase 15): enrollment, per-farm client datasets, FedAvg runs, model use.

Boundary: ``client_dataset`` reads ONE farm's readings and is only ever called from that farm's
client step. Runs persist weights, sample counts and metrics, never readings or features.
All clients execute inside this backend process (a simulated federation, not separate devices).
"""

import secrets
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import federated as fl
from app.models import (
    Farm,
    FarmZone,
    FederatedClient,
    FederatedClientUpdate,
    FederatedLearningRun,
    ModelVersion,
    Sensor,
    SensorReading,
)

MODEL_NAME = "soil-moisture-6h-fedavg"
TYPES = ("soil_moisture", "temperature", "humidity", "light", "rainfall")
MIN_SAMPLES = 30
MIN_CLIENTS = 2
DEFAULTS = {"rounds": 20, "local_steps": 5, "lr": 0.05, "l2": 0.001}
LIMITATIONS = [
    "All clients run inside this one backend: the farm boundary is enforced in code, not by separate devices or networks.",
    "Plain FedAvg is not a formal privacy guarantee: model updates can leak information about training data. No differential privacy or secure aggregation is applied.",
    "A linear model of 6-hour moisture change from on-farm sensors; it ignores irrigation events and forecasts.",
]


def _hourly(
    db: Session, farm: Farm, since: datetime | None = None
) -> tuple[dict[int, dict[datetime, dict[str, float]]], bool]:
    """Per zone: hour -> {sensor_type: mean of good readings}. Reads only this farm's sensors."""
    hour = func.date_trunc("hour", SensorReading.recorded_at)
    q = (
        select(
            Sensor.zone_id,
            Sensor.sensor_type,
            hour,
            func.avg(SensorReading.value),
            func.bool_or(Sensor.source == "simulated"),
        )
        .join(Sensor, Sensor.id == SensorReading.sensor_id)
        .where(
            Sensor.farm_id == farm.id,
            Sensor.zone_id.is_not(None),
            Sensor.sensor_type.in_(TYPES),
            SensorReading.quality == "good",
        )
        .group_by(Sensor.zone_id, Sensor.sensor_type, hour)
    )
    if since is not None:
        q = q.where(SensorReading.recorded_at >= since)
    data: dict[int, dict[datetime, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    simulated = False
    for zone_id, kind, at, avg, sim in db.execute(q).all():
        data[zone_id][at][kind] = float(avg)
        simulated = simulated or bool(sim)
    return data, simulated


def client_dataset(db: Session, farm: Farm) -> tuple[fl.ClientData | None, bool]:
    tz = ZoneInfo(farm.timezone)
    data, simulated = _hourly(db, farm)
    rows: list[tuple[datetime, list[float], float]] = []
    for hours in data.values():
        for at, v in hours.items():
            later = hours.get(at + timedelta(hours=fl.HORIZON_HOURS), {})
            if all(k in v for k in TYPES) and "soil_moisture" in later:
                x = fl.featurize(
                    v["soil_moisture"],
                    v["temperature"],
                    v["humidity"],
                    v["light"],
                    v["rainfall"],
                    at.astimezone(tz).hour,
                )
                rows.append((at, x, later["soil_moisture"] - v["soil_moisture"]))
    if not rows:
        return None, simulated
    rows.sort(key=lambda r: r[0])  # chronological, so the held-out test split is the most recent data
    return fl.ClientData(np.array([r[1] for r in rows]), np.array([r[2] for r in rows])), simulated


# ------------------------------------------------------------------ enrollment
def enrollment(db: Session, farm: Farm) -> FederatedClient | None:
    return db.scalar(select(FederatedClient).where(FederatedClient.farm_id == farm.id))


def enroll(db: Session, farm: Farm) -> FederatedClient:
    c = enrollment(db, farm)
    if c is None:
        c = FederatedClient(farm_id=farm.id, client_key=f"fc_{secrets.token_hex(8)}", status="active")
        db.add(c)
    else:
        c.status = "active"
    db.flush()
    return c


def leave(db: Session, farm: Farm) -> FederatedClient | None:
    c = enrollment(db, farm)
    if c is not None:
        c.status = "inactive"
        db.flush()
    return c


# ------------------------------------------------------------------ runs
def start_run(
    db: Session, config: dict[str, Any] | None = None, now: datetime | None = None
) -> FederatedLearningRun:
    now = now or datetime.now(UTC)
    cfg = {**DEFAULTS, **(config or {})}
    run = FederatedLearningRun(model_name=MODEL_NAME, aggregation_strategy="fedavg", status="running",
                               total_rounds=cfg["rounds"], current_round=0, config=cfg, started_at=now)  # fmt: skip
    db.add(run)
    db.flush()
    clients = db.scalars(
        select(FederatedClient).where(FederatedClient.status == "active").order_by(FederatedClient.id)
    ).all()
    datasets: dict[str, fl.ClientData] = {}
    skipped, simulated = [], False
    for c in clients:
        farm = db.get(Farm, c.farm_id)
        assert farm is not None
        d, sim = client_dataset(db, farm)  # the client's local step: its own farm only
        c.last_seen_at = now
        if d is None or len(d.y) < MIN_SAMPLES:
            skipped.append(
                {
                    "client": c.client_key,
                    "samples": 0 if d is None else len(d.y),
                    "reason": f"fewer than {MIN_SAMPLES} samples",
                }
            )
            continue
        datasets[c.client_key] = d
        simulated = simulated or sim
    if len(datasets) < MIN_CLIENTS:
        run.status = "failed"
        run.completed_at = now
        run.metrics = {
            "reason": f"Federated averaging needs at least {MIN_CLIENTS} enrolled farms with {MIN_SAMPLES}+ samples; {len(datasets)} qualified.",
            "skipped": skipped,
        }
        db.flush()
        return run

    result = fl.run_fedavg(datasets, cfg["rounds"], cfg["local_steps"], cfg["lr"], cfg["l2"])
    by_key = {c.client_key: c for c in clients}
    for round_updates in result["round_updates"]:
        for u in round_updates:
            db.add(FederatedClientUpdate(run_id=run.id, client_id=by_key[u["client"]].id, round_number=u["round"], num_samples=u["num_samples"],
                                         local_metrics={"weights": u["weights"], "train_mse": u["train_mse"]}))  # fmt: skip
    mv = ModelVersion(
        model_name=MODEL_NAME, version=f"run-{run.id}", task="other", framework="numpy-linear", status="staging",
        labels=["delta_soil_moisture_6h_pct_points"],
        input_spec={"features": fl.FEATURES, "scaling": "fixed physical scaling, see app/domain/federated.py", "weights": result["weights"], "horizon_hours": fl.HORIZON_HOURS},
        metrics={**result["overall"], "clients": len(datasets), "uses_simulated_data": simulated},
        training_dataset=f"{len(datasets)} federated farm clients; raw data not collected",
        known_limitations=" ".join(LIMITATIONS),
        trained_at=now,
    )  # fmt: skip
    db.add(mv)
    db.flush()
    run.result_model_version_id = mv.id
    run.current_round = cfg["rounds"]
    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    run.metrics = {"overall": result["overall"], "history": result["history"], "per_client": result["per_client"],
                   "clients": len(datasets), "skipped": skipped, "uses_simulated_data": simulated, "weights": result["weights"]}  # fmt: skip
    db.flush()
    return run


def latest_model(db: Session) -> tuple[FederatedLearningRun, ModelVersion] | None:
    row = db.execute(
        select(FederatedLearningRun, ModelVersion)
        .join(ModelVersion, ModelVersion.id == FederatedLearningRun.result_model_version_id)
        .where(FederatedLearningRun.status == "completed")
        .order_by(FederatedLearningRun.completed_at.desc(), FederatedLearningRun.id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def run_summary(run: FederatedLearningRun, own_key: str | None = None, admin: bool = False) -> dict[str, Any]:
    """What a participant may see: overall metrics and only its own per-client numbers (admins see all)."""
    m = run.metrics or {}
    per_client = m.get("per_client", {})
    return {
        "id": run.id, "status": run.status, "model_name": run.model_name, "aggregation": run.aggregation_strategy,
        "rounds": run.total_rounds, "config": run.config, "started_at": run.started_at, "completed_at": run.completed_at,
        "clients": m.get("clients"), "overall": m.get("overall"), "history": m.get("history"), "reason": m.get("reason"),
        "uses_simulated_data": m.get("uses_simulated_data"),
        "your_metrics": per_client.get(own_key) if own_key else None,
        "per_client": per_client if admin else None,
        "explanation": fl.explain(m["weights"]) if m.get("weights") else None,
    }  # fmt: skip


def farm_view(db: Session, farm: Farm, is_admin: bool) -> dict[str, Any]:
    c = enrollment(db, farm)
    data, sim = client_dataset(db, farm)
    runs = db.scalars(select(FederatedLearningRun).order_by(FederatedLearningRun.id.desc()).limit(10)).all()
    key = c.client_key if c else None
    participated = (
        set(
            db.scalars(
                select(FederatedClientUpdate.run_id).where(FederatedClientUpdate.client_id == c.id).distinct()
            ).all()
        )
        if c
        else set()
    )
    return {
        "farm_id": farm.id,
        "enrollment": None
        if c is None
        else {
            "status": c.status,
            "client_key": c.client_key,
            "enrolled_at": c.created_at,
            "last_seen_at": c.last_seen_at,
        },
        "local_samples": 0 if data is None else len(data.y),
        "min_samples": MIN_SAMPLES,
        "uses_simulated_data": sim,
        "shared": "model weights, sample count and local error metrics only",
        "not_shared": "sensor readings, features, zone names, locations",
        "runs": [
            {
                **run_summary(r, key if r.id in participated else None, is_admin),
                "participated": r.id in participated,
            }
            for r in runs
        ],
        "limitations": LIMITATIONS,
    }


def zone_forecast(db: Session, zone: FarmZone, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    latest = latest_model(db)
    if latest is None:
        return {"status": "no_model", "message": "No federated model has been trained yet."}
    run, mv = latest
    farm = db.get(Farm, zone.farm_id)
    assert farm is not None
    data, sim = _hourly(db, farm, since=now - timedelta(hours=3))
    hours = data.get(zone.id, {})
    complete = [at for at, v in hours.items() if all(k in v for k in TYPES)]
    if not complete:
        return {
            "status": "no_recent_data",
            "message": "No complete sensor hour (moisture, temperature, humidity, light, rainfall) in the last 3 hours.",
            "model_version": mv.version,
        }
    at = max(complete)
    v = hours[at]
    x = np.array(
        fl.featurize(
            v["soil_moisture"],
            v["temperature"],
            v["humidity"],
            v["light"],
            v["rainfall"],
            at.astimezone(ZoneInfo(farm.timezone)).hour,
        )
    )
    w = np.array((mv.input_spec or {})["weights"])
    delta = float(x @ w)
    overall = (run.metrics or {}).get("overall", {})
    beats = bool(overall) and overall.get("mae_federated", 1e9) < overall.get("mae_persistence", 0)
    return {
        "status": "forecast", "model_version": mv.version, "run_id": run.id, "based_on_hour": at,
        "moisture_now_pct": round(v["soil_moisture"], 2), "predicted_change_6h_pct_points": round(delta, 2),
        "predicted_moisture_6h_pct": round(v["soil_moisture"] + delta, 2),
        "expected_error_pct_points": overall.get("mae_federated"), "persistence_error_pct_points": overall.get("mae_persistence"),
        "beats_baseline": beats,
        "advice": None if beats else "On held-out data this model is NOT more accurate than assuming moisture stays the same. Do not use it for decisions.",
        "uses_simulated_data": sim or bool((run.metrics or {}).get("uses_simulated_data")),
        "limitations": LIMITATIONS,
    }  # fmt: skip
