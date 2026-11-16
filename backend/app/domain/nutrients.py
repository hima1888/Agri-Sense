# ruff: noqa: E501  (reference tables and explanatory strings)
"""Soil-test-based fertilizer planning (Phase 13).

Method, as used with India's Soil Health Card scheme ("general recommended dose adjusted by soil test"):
1. Start from the crop's recommended dose (RDF) of N, P2O5 and K2O in kg/ha. The farmer's own value
   (from the state Package of Practices or the Soil Health Card) is used when recorded; otherwise an
   indicative reference value below, clearly marked as such.
2. Adjust each nutrient by the lab soil-test rating: low x 1.25, medium x 1.00, high x 0.75.
   Without a lab test the dose is not adjusted (sensor/probe ratings are not used for dosing).
3. Subtract nutrients already applied to this crop cycle (from logged fertilizer applications).
4. Convert the remainder to common straight fertilizers: DAP (18-46-0) for P2O5 first, MOP (0-0-60)
   for K2O, urea (46-0-0) for the N still needed after DAP's N.

Grades are on the label basis N - P2O5 - K2O (%), as fertilizer bags in India are labelled.
"""

from __future__ import annotations

from typing import Any

# Indicative general recommendations, kg/ha N : P2O5 : K2O, for irrigated crops.
# These are commonly cited national-level starting values; state Packages of Practices differ by
# region, season, variety and irrigation. Always replace with the local recommendation when known.
REFERENCE_RDF: dict[str, tuple[float, float, float]] = {
    "rice": (120, 60, 40),
    "wheat": (120, 60, 40),
    "maize": (120, 60, 40),
    "potato": (150, 80, 100),
    "tomato": (120, 60, 60),
    "onion": (100, 50, 50),
    "cotton": (100, 50, 50),
    "soybean": (20, 60, 40),
    "groundnut": (20, 40, 40),
}
REFERENCE_SOURCE = (
    "indicative national-level general recommendation (irrigated); replace with your state "
    "Package of Practices or Soil Health Card value"
)

RATING_FACTOR = {"low": 1.25, "medium": 1.0, "high": 0.75}
SOIL_KEYS = {"n": "nitrogen", "p2o5": "phosphorus", "k2o": "potassium"}

PRODUCTS = {
    "DAP": {"n": 18.0, "p2o5": 46.0, "k2o": 0.0},
    "Urea": {"n": 46.0, "p2o5": 0.0, "k2o": 0.0},
    "MOP": {"n": 0.0, "p2o5": 0.0, "k2o": 60.0},
}

N_SPLIT_NOTE = (
    "Apply N in splits rather than all at once (for example half at sowing/transplanting and the rest in "
    "two top-dressings), all P and K as basal; split N reduces leaching losses."
)
FERTIGATION_NOTE = (
    "On drip, N and K can be given through fertigation in weekly doses instead of top-dressing."
)


def applied_nutrients(applications: list[dict[str, Any]], area_ha: float) -> dict[str, float]:
    """kg/ha of N, P2O5, K2O from logged applications (quantity_kg x grade %)."""
    tot = {"n": 0.0, "p2o5": 0.0, "k2o": 0.0}
    for a in applications:
        q = float(a["quantity_kg"])
        for key, col in (("n", "n_pct"), ("p2o5", "p_pct"), ("k2o", "k_pct")):
            if a.get(col) is not None:
                tot[key] += q * float(a[col]) / 100
    return {k: round(v / area_ha, 1) for k, v in tot.items()}


def products_for(need: dict[str, float]) -> list[dict[str, Any]]:
    """kg/ha of DAP, MOP and urea that supply ``need`` (kg/ha N, P2O5, K2O)."""
    out = []
    n_left = need["n"]
    if need["p2o5"] > 0:
        dap = need["p2o5"] / (PRODUCTS["DAP"]["p2o5"] / 100)
        n_left -= dap * PRODUCTS["DAP"]["n"] / 100
        out.append(
            {
                "product": "DAP",
                "grade": "18-46-0",
                "kg_per_ha": round(dap, 1),
                "supplies": "all P2O5 and some N",
            }
        )
    if need["k2o"] > 0:
        out.append(
            {
                "product": "MOP",
                "grade": "0-0-60",
                "kg_per_ha": round(need["k2o"] / 0.60, 1),
                "supplies": "K2O",
            }
        )
    if n_left > 0:
        out.append(
            {
                "product": "Urea",
                "grade": "46-0-0",
                "kg_per_ha": round(n_left / 0.46, 1),
                "supplies": "remaining N",
            }
        )
    return out


def plan(
    *,
    crop: str | None,
    target: dict[str, float] | None,
    target_source: str | None,
    soil_ratings: dict[str, dict[str, Any]],
    applied_kg_ha: dict[str, float],
    area_ha: float | None,
    irrigation_method: str | None,
) -> dict[str, Any]:
    """Returns the adjusted dose, the remaining need, products, factors and limitations."""
    limitations = [
        "Rule-based soil-test adjustment of a recommended dose; not a trained model and not a soil-test "
        "crop-response (STCR) equation for your variety.",
        "Check with your local agriculture officer or Krishi Vigyan Kendra before buying fertilizer.",
    ]
    key = (crop or "").strip().lower()
    if target is None and key in REFERENCE_RDF:
        n, p, k = REFERENCE_RDF[key]
        target, target_source = {"n": n, "p2o5": p, "k2o": k}, REFERENCE_SOURCE
        limitations.insert(
            0,
            "Using an INDICATIVE reference dose: set your state's recommended dose for this crop for a reliable plan.",
        )
    if target is None:
        return {"status": "no_target", "message": f"No recommended dose for {crop or 'this zone (no crop)'}: enter the N, P2O5 and K2O dose from your Package of Practices.", "limitations": limitations}  # fmt: skip

    factors: list[dict[str, Any]] = []
    adjusted: dict[str, float] = {}
    need: dict[str, float] = {}
    surplus: dict[str, float] = {}
    any_lab = False
    for nut, soil_key in SOIL_KEYS.items():
        c = soil_ratings.get(soil_key)
        from_lab = bool(c and c["source"].startswith("lab"))
        any_lab = any_lab or from_lab
        factor = RATING_FACTOR.get(c["status"], 1.0) if (c and from_lab) else 1.0
        adjusted[nut] = round(target[nut] * factor, 1)
        need[nut] = round(max(0.0, adjusted[nut] - applied_kg_ha[nut]), 1)
        if applied_kg_ha[nut] > adjusted[nut]:
            surplus[nut] = round(applied_kg_ha[nut] - adjusted[nut], 1)
        factors.append({
            "nutrient": nut, "recommended_kg_ha": target[nut],
            "soil_rating": c["status"] if c else None, "soil_source": c["source"] if c else "not measured",
            "factor": factor, "adjusted_kg_ha": adjusted[nut],
            "applied_kg_ha": applied_kg_ha[nut], "remaining_kg_ha": need[nut], "surplus_kg_ha": surplus.get(nut, 0.0),
            "note": None if from_lab or not c else "rating from sensors/probes is not used to change the dose",
        })  # fmt: skip
    if not any_lab:
        limitations.append(
            "No lab values for N, P or K: the dose is not adjusted for soil fertility. A lab test of available N, P and K often lowers P and K needs."
        )
    products = products_for(need)
    if area_ha:
        for pr in products:
            pr["kg_for_zone"] = round(pr["kg_per_ha"] * area_ha, 1)
            pr["bags_50kg"] = round(pr["kg_for_zone"] / 50, 1)
    else:
        limitations.append("Zone area unknown: quantities are per hectare only.")
    saving = {nut: round(target[nut] - adjusted[nut], 1) for nut in SOIL_KEYS if target[nut] > adjusted[nut]}
    notes = [N_SPLIT_NOTE] + ([FERTIGATION_NOTE] if (irrigation_method or "") == "drip" else [])
    return {
        "status": "complete" if not any(need.values()) else "plan",
        "target_kg_ha": target,
        "target_source": target_source,
        "adjusted_kg_ha": adjusted,
        "applied_kg_ha": applied_kg_ha,
        "remaining_kg_ha": need,
        "factors": factors,
        "products": products,
        "surplus_kg_ha": surplus,
        "soil_test_saving_kg_ha": saving,
        "notes": notes,
        "confidence": round(
            (0.85 if target_source != REFERENCE_SOURCE else 0.5) * (1.0 if any_lab else 0.75), 2
        ),
        "limitations": limitations,
    }
