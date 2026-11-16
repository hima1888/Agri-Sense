# ruff: noqa: E501  (reference table and explanatory strings)
"""Water-limited yield estimate (Phase 14).

FAO Irrigation and Drainage Paper 33 (Doorenbos & Kassam, 1979; restated in FAO-66):

    1 - Ya/Ym = Ky x (1 - ETa/ETc)

* Ym  attainable (water-unstressed) yield: the farmer's reference for this variety and field, or the
      best per-hectare yield from their own past harvests of the crop. Never invented here.
* Ky  seasonal yield-response factor from FAO-33 (below).
* ETa/ETc  seasonal relative evapotranspiration, from the FAO-56 daily water-stress coefficient
      Ks = (TAW - Dr) / ((1 - p) x TAW) when Dr > RAW, else 1, on days with a moisture measurement.
      Days are weighted by the crop coefficient for their growth stage (a proxy for daily ETc).

Days without a moisture measurement are unknown, so the estimate is a range:
* high:    unknown past days and the rest of the season unstressed (Ks = 1)
* central: unknown past days like the measured days; rest of the season unstressed (well irrigated)
* low:     unknown past days and the rest of the season like the measured days
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.domain.soil_reference import CropWater, kc_for_growth

# FAO-33 seasonal Ky (total growing period). Rice is not covered by FAO-33.
KY: dict[str, float] = {
    "maize": 1.25, "wheat": 1.15, "sorghum": 0.90, "tomato": 1.05, "potato": 1.10, "onion": 1.10,
    "cabbage": 0.95, "bell pepper": 1.10, "chilli pepper": 1.10, "cotton": 0.85, "soybean": 0.85,
    "groundnut": 0.70, "sunflower": 0.95, "sugarcane": 1.20, "banana": 1.25, "watermelon": 1.10,
    "beans": 1.15, "peas": 1.15,
}  # fmt: skip
KY_SOURCE = "FAO Irrigation and Drainage Paper 33, seasonal Ky"


def ks(depletion_mm: float, taw_mm: float, raw_mm: float, p: float) -> float:
    if depletion_mm <= raw_mm:
        return 1.0
    return max(0.0, min(1.0, (taw_mm - depletion_mm) / ((1 - p) * taw_mm)))


def season_days(planted: date, end: date) -> list[date]:
    return [planted + timedelta(days=i) for i in range((end - planted).days + 1)]


def estimate(
    *,
    crop: str,
    planted: date,
    harvest: date,
    today: date,
    daily_ks: dict[date, float],
    cw: CropWater,
    ym_kg_ha: float | None,
    ym_source: str | None,
) -> dict[str, Any]:
    key = crop.strip().lower()
    ky = KY.get(key)
    limitations = [
        "Water-limited estimate only (FAO-33): nutrients, pests, diseases, weeds, heat at flowering, lodging and harvest losses are NOT modelled.",
        "Not a trained model; its accuracy on this farm is unknown until harvested yields are recorded and back-tested.",
    ]
    if ky is None:
        return {
            "status": "ky_unknown",
            "message": f"FAO-33 has no yield-response factor (Ky) for {crop}, so a water-based estimate is not possible.",
            "limitations": limitations,
        }
    if ym_kg_ha is None:
        return {"status": "no_reference", "ky": ky, "message": "Enter the attainable yield for this variety and field (kg/ha) and its source, or record past harvests, to estimate yield.", "limitations": limitations}  # fmt: skip

    season = season_days(planted, harvest)
    total = len(season)
    elapsed = [d for d in season if d <= today]
    future = [d for d in season if d > today]
    weight = {d: kc_for_growth(cw, (i + 0.5) / total) for i, d in enumerate(season)}
    measured = [d for d in elapsed if d in daily_ks]
    unknown = [d for d in elapsed if d not in daily_ks]

    def w(days: list[date]) -> float:
        return sum(weight[d] for d in days)

    w_total = w(season)
    ks_measured = sum(daily_ks[d] * weight[d] for d in measured) / w(measured) if measured else None
    coverage_elapsed = len(measured) / len(elapsed) if elapsed else 0.0
    coverage_season = w(measured) / w_total

    def ratio(unknown_ks: float, future_ks: float) -> float:
        num = sum(daily_ks[d] * weight[d] for d in measured) + unknown_ks * w(unknown) + future_ks * w(future)
        return num / w_total

    base = ks_measured if ks_measured is not None else 1.0
    ratios = {"high": ratio(1.0, 1.0), "central": ratio(base, 1.0), "low": ratio(base, base)}
    yields = {k: round(max(0.0, ym_kg_ha * (1 - ky * (1 - r))), 0) for k, r in ratios.items()}
    stressed_days = sum(1 for d in measured if daily_ks[d] < 1)
    if ks_measured is None:
        limitations.insert(
            0,
            "No moisture measurements during this season: the range only reflects the attainable yield, not this field's water status.",
        )
    elif coverage_elapsed < 0.5:
        limitations.insert(
            0,
            f"Moisture was measured on only {len(measured)} of {len(elapsed)} days so far ({coverage_elapsed:.0%}); the range is wide for that reason.",
        )
    confidence = round(
        min(0.9, 0.3 + 0.6 * coverage_season) * (1.0 if ym_source and "past harvest" in ym_source else 0.85),
        2,
    )
    factors = [
        {"name": "Attainable yield (Ym)", "value": ym_kg_ha, "unit": "kg/ha", "source": ym_source},
        {"name": "Yield response to water (Ky)", "value": ky, "unit": "", "source": KY_SOURCE},
        {
            "name": "Relative ET on measured days (Ks)",
            "value": None if ks_measured is None else round(ks_measured, 3),
            "unit": "",
            "source": "FAO-56 Ks from soil-moisture history",
        },
        {
            "name": "Days with water stress",
            "value": stressed_days,
            "unit": f"of {len(measured)} measured",
            "source": "soil-moisture history",
        },
        {
            "name": "Season covered by measurements",
            "value": round(coverage_season * 100),
            "unit": "% (ETc-weighted)",
            "source": "soil-moisture history",
        },
    ]
    return {
        "status": "estimate",
        "ky": ky,
        "ym_kg_ha": ym_kg_ha,
        "ym_source": ym_source,
        "yield_kg_ha": yields,
        "relative_et": {k: round(v, 3) for k, v in ratios.items()},
        "water_loss_pct_central": round((1 - yields["central"] / ym_kg_ha) * 100, 1) if ym_kg_ha else None,
        "season": {
            "planted": planted,
            "harvest": harvest,
            "days_total": total,
            "days_elapsed": len(elapsed),
            "days_measured": len(measured),
            "coverage_elapsed": round(coverage_elapsed, 3),
            "coverage_season": round(coverage_season, 3),
        },
        "factors": factors,
        "confidence": confidence,
        "limitations": limitations,
    }
