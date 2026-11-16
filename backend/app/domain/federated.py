"""Federated averaging (FedAvg, McMahan et al. 2017) for a small, explainable model (Phase 15).

Task: predict the change in root-zone soil moisture over the next 6 hours (percentage points) from
on-farm sensors at time t. Model: linear regression, trained by full-batch gradient descent with L2.

Features use FIXED physical scaling (no data-derived statistics), so a client never has to share
means or variances of its data:

    x0 bias, x1 (moisture - 25)/10, x2 (air temp - 25)/10, x3 (humidity - 60)/30,
    x4 light/50 000 lux, x5 rainfall sensor reading/5, x6 sin(hour), x7 cos(hour)

Protocol per round: the server sends global weights; each client runs E local gradient steps on its
own training split and returns (weights, n_samples, local loss); the server averages weights by
n_samples. Clients see only global weights; the server sees only weights, counts and metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

FEATURES = ["bias", "moisture", "air_temperature", "humidity", "light", "rainfall", "hour_sin", "hour_cos"]
HORIZON_HOURS = 6
TEST_FRACTION = 0.2


def featurize(theta: float, temp: float, rh: float, light: float, rain: float, hour: int) -> list[float]:
    a = 2 * math.pi * hour / 24
    return [
        1.0,
        (theta - 25) / 10,
        (temp - 25) / 10,
        (rh - 60) / 30,
        light / 50_000,
        rain / 5,
        math.sin(a),
        math.cos(a),
    ]


@dataclass
class ClientData:
    """A client's own samples, chronologically ordered. Only the client function touches these."""

    x: np.ndarray
    y: np.ndarray

    def split(self) -> tuple[ClientData, ClientData]:
        n_test = max(1, int(len(self.y) * TEST_FRACTION))
        return ClientData(self.x[:-n_test], self.y[:-n_test]), ClientData(self.x[-n_test:], self.y[-n_test:])


def mse(w: np.ndarray, d: ClientData) -> float:
    return float(np.mean((d.x @ w - d.y) ** 2))


def mae(w: np.ndarray, d: ClientData) -> float:
    return float(np.mean(np.abs(d.x @ w - d.y)))


def local_train(w: np.ndarray, d: ClientData, steps: int, lr: float, l2: float) -> np.ndarray:
    """Full-batch gradient descent on the client's own data; returns new weights only."""
    w = w.copy()
    n = len(d.y)
    for _ in range(steps):
        grad = (2 / n) * d.x.T @ (d.x @ w - d.y) + 2 * l2 * np.r_[0.0, w[1:]]  # no penalty on the bias
        w -= lr * grad
    return w


def fedavg(updates: list[tuple[np.ndarray, int]]) -> np.ndarray:
    total = sum(n for _, n in updates)
    return sum((w * (n / total) for w, n in updates), start=np.zeros_like(updates[0][0]))


def run_fedavg(
    clients: dict[str, ClientData], rounds: int, local_steps: int, lr: float, l2: float
) -> dict[str, Any]:
    """Train with FedAvg on each client's training split and evaluate on each client's held-out tail.

    Comparisons (all on the same held-out data):
    * persistence: predict no change (y = 0)
    * local-only: the same model trained only on the client's own data for rounds x local_steps steps
    * federated: the final global FedAvg model
    """
    splits = {k: d.split() for k, d in clients.items()}
    w = np.zeros(len(FEATURES))
    history = []
    round_updates: list[list[dict[str, Any]]] = []
    for r in range(1, rounds + 1):
        updates, this_round = [], []
        for key, (train, _) in splits.items():
            wk = local_train(w, train, local_steps, lr, l2)
            updates.append((wk, len(train.y)))
            this_round.append(
                {
                    "client": key,
                    "round": r,
                    "num_samples": len(train.y),
                    "weights": wk.round(6).tolist(),
                    "train_mse": round(mse(wk, train), 5),
                }
            )
        w = fedavg(updates)
        n_test = sum(len(t.y) for _, t in splits.values())
        global_test = sum(mse(w, t) * len(t.y) for _, t in splits.values()) / n_test
        history.append({"round": r, "test_mse": round(global_test, 5)})
        round_updates.append(this_round)

    per_client: dict[str, dict[str, float]] = {}
    for key, (train, test) in splits.items():
        local = local_train(np.zeros(len(FEATURES)), train, rounds * local_steps, lr, l2)
        per_client[key] = {
            "train_samples": len(train.y),
            "test_samples": len(test.y),
            "mae_persistence": round(mae(np.zeros(len(FEATURES)), test), 4),
            "mae_local_only": round(mae(local, test), 4),
            "mae_federated": round(mae(w, test), 4),
        }
    n_test = int(sum(c["test_samples"] for c in per_client.values()))

    def pooled(metric: str) -> float:
        return round(sum(c[metric] * c["test_samples"] for c in per_client.values()) / n_test, 4)

    return {
        "weights": w.round(6).tolist(),
        "features": FEATURES,
        "history": history,
        "round_updates": round_updates,
        "per_client": per_client,
        "overall": {
            "mae_persistence": pooled("mae_persistence"),
            "mae_local_only": pooled("mae_local_only"),
            "mae_federated": pooled("mae_federated"),
            "test_samples": n_test,
        },
    }


def explain(weights: list[float]) -> list[dict[str, Any]]:
    """Each feature's weight: the change in 6-h moisture change (points) per unit of its scaled feature."""
    return sorted(
        (
            {"feature": f, "weight": round(w, 4)}
            for f, w in zip(FEATURES, weights, strict=True)
            if f != "bias"
        ),
        key=lambda d: -abs(d["weight"]),
    )
