# ruff: noqa: E501  (explanatory strings)
"""Pesticide-use tracking and a pre-spray check (Phase 13).

Everything here is computed from the farm's own logs; nothing is estimated from outside data.
* Use summary per crop cycle: applications, by type, product quantity per hectare (by unit), share of
  applications linked to evidence (a disease check), pre-harvest-interval (PHI) status.
* Reduction is reported only as a comparison between this cycle and the zone's previous cycle,
  normalised per hectare, when both exist.
* Pre-spray check: evidence, weather (rain and wind in the next 6 h), PHI against the expected
  harvest date, and how recently the same type was sprayed. It advises; it never blocks logging.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

RAIN_PROB_PCT = 40.0
RAIN_MM = 1.0
WIND_MS = 4.0  # drift risk above ~15 km/h
HOT_C = 30.0
EVIDENCE_DAYS = 14
REPEAT_DAYS = 7


def use_summary(
    apps: list[dict[str, Any]], area_ha: float | None, expected_harvest: date | None, today: date
) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    qty: dict[str, float] = {}
    for a in apps:
        by_type[a["pesticide_type"]] = by_type.get(a["pesticide_type"], 0) + 1
        qty[a["quantity_unit"]] = qty.get(a["quantity_unit"], 0.0) + float(a["quantity"])
    with_evidence = sum(1 for a in apps if a.get("disease_detection_id"))
    phi = []
    for a in apps:
        days = a.get("pre_harvest_interval_days")
        if days is None:
            phi.append(
                {
                    "id": a["id"],
                    "product": a["product_name"],
                    "status": "unknown",
                    "detail": "no PHI recorded",
                }
            )
            continue
        safe_from = a["applied_at"].date() + timedelta(days=days)
        if expected_harvest is None:
            status = "safe" if safe_from <= today else "wait"
        else:
            status = (
                "conflict" if safe_from > expected_harvest else ("safe" if safe_from <= today else "wait")
            )
        phi.append(
            {"id": a["id"], "product": a["product_name"], "status": status, "safe_to_harvest_from": safe_from}
        )
    return {
        "applications": len(apps),
        "by_type": by_type,
        "quantity_by_unit": {u: round(v, 3) for u, v in qty.items()},
        "quantity_per_ha_by_unit": {u: round(v / area_ha, 3) for u, v in qty.items()} if area_ha else None,
        "with_evidence": with_evidence,
        "evidence_share": round(with_evidence / len(apps), 2) if apps else None,
        "phi": phi,
        "phi_conflicts": sum(1 for p in phi if p["status"] == "conflict"),
        "harvest_blocked_until": max(
            (p["safe_to_harvest_from"] for p in phi if p.get("safe_to_harvest_from")), default=None
        ),
    }


def compare(
    current: dict[str, Any], previous: dict[str, Any] | None, cur_area: float | None, prev_area: float | None
) -> dict[str, Any] | None:
    """Change in sprays per hectare vs the previous cycle (negative = reduction). None if not comparable."""
    if previous is None or not cur_area or not prev_area:
        return None
    cur, prev = current["applications"] / cur_area, previous["applications"] / prev_area
    out: dict[str, Any] = {
        "applications_per_ha": {"current": round(cur, 2), "previous": round(prev, 2)},
        "change_pct": round((cur - prev) / prev * 100, 1) if prev else None,
        "by_unit_per_ha": {},
    }
    for unit in set(current["quantity_by_unit"]) | set(previous["quantity_by_unit"]):
        c = current["quantity_by_unit"].get(unit, 0.0) / cur_area
        p = previous["quantity_by_unit"].get(unit, 0.0) / prev_area
        out["by_unit_per_ha"][unit] = {
            "current": round(c, 3),
            "previous": round(p, 3),
            "change_pct": round((c - p) / p * 100, 1) if p else None,
        }
    return out


def spray_check(
    *,
    pesticide_type: str,
    phi_days: int | None,
    now: datetime,
    expected_harvest: date | None,
    evidence: list[dict[str, Any]],
    hourly: list[dict[str, Any]],
    recent_same_type: list[datetime],
) -> dict[str, Any]:
    checks = []

    def add(key: str, ok: bool | None, detail: str) -> None:
        checks.append(
            {
                "check": key,
                "status": "ok" if ok else ("unknown" if ok is None else "warning"),
                "detail": detail,
            }
        )

    if pesticide_type in ("fungicide", "bactericide"):
        if evidence:
            e = evidence[0]
            add(
                "evidence",
                True,
                f"{e['outcome'].replace('_', ' ')}: {e['label']} on {e['detected_at']:%d %b} (confirm in the field; the model is a screening aid)",
            )
        else:
            add(
                "evidence",
                False,
                f"No disease check in the last {EVIDENCE_DAYS} days. Scout and confirm a problem before a preventive spray.",
            )
    else:
        add(
            "evidence", None, "Pest/weed sprays need field scouting; record what you saw in the target field."
        )

    nxt = [h for h in hourly if now <= h["valid_at"] < now + timedelta(hours=6)]
    if not nxt:
        add("weather", None, "No stored forecast for the next 6 hours; check rain and wind before spraying.")
    else:
        rain = [
            h
            for h in nxt
            if (h["precipitation_probability_pct"] or 0) >= RAIN_PROB_PCT
            or (h["precipitation_mm"] or 0) >= RAIN_MM
        ]
        wind = max((h["wind_speed_ms"] or 0) for h in nxt)
        hot = max((h["temperature_c"] or 0) for h in nxt)
        add(
            "rain",
            not rain,
            f"Rain likely within 6 h ({len(rain)} hour(s)); it can wash the product off."
            if rain
            else "No rain expected in the next 6 h.",
        )
        add(
            "wind",
            wind <= WIND_MS,
            f"Wind up to {wind:.1f} m/s: drift risk above {WIND_MS:.0f} m/s."
            if wind > WIND_MS
            else f"Wind up to {wind:.1f} m/s.",
        )
        add(
            "heat",
            hot < HOT_C,
            f"Up to {hot:.0f} deg C: spray in the cooler early morning or evening."
            if hot >= HOT_C
            else f"Up to {hot:.0f} deg C.",
        )

    if phi_days is None:
        add(
            "pre_harvest_interval",
            None,
            "Enter the product's pre-harvest interval (on the label) to check harvest timing.",
        )
    elif expected_harvest is None:
        add(
            "pre_harvest_interval",
            None,
            f"Harvest allowed {phi_days} days after spraying; no expected harvest date is recorded.",
        )
    else:
        safe_from = now.date() + timedelta(days=phi_days)
        add("pre_harvest_interval", safe_from <= expected_harvest,
            f"Safe to harvest from {safe_from:%d %b}; expected harvest {expected_harvest:%d %b}." + ("" if safe_from <= expected_harvest else " This product would still be within its PHI at harvest."))  # fmt: skip

    recent = [t for t in recent_same_type if t >= now - timedelta(days=REPEAT_DAYS)]
    add(
        "repeat",
        not recent,
        f"A {pesticide_type} was already applied {(now - max(recent)).days} day(s) ago; check the label's re-application interval."
        if recent
        else f"No {pesticide_type} in the last {REPEAT_DAYS} days.",
    )

    warnings = [c for c in checks if c["status"] == "warning"]
    return {
        "verdict": "hold" if warnings else "ok_to_proceed",
        "checks": checks,
        "warnings": len(warnings),
        "limitations": [
            "Advisory only: it does not replace the product label, local regulations or an agronomist.",
            "Weather is the stored forecast, not conditions in the field right now.",
        ],
    }
