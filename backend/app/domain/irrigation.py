"""Irrigation scheduling (Phase 12): FAO-56 daily root-zone water balance with forecast ET0 and rain.

Method (FAO Irrigation and Drainage Paper 56, ch. 8):
* Dr(day) = Dr(prev) + Kc * ET0 - effective rain - net irrigation, bounded to [0, TAW].
* Effective rain = 0.8 x rain on days with more than 2 mm (light showers mostly evaporate).
* Irrigate on a day when the end-of-day depletion would pass RAW (= p x TAW, the stress threshold),
  unless forecast effective rain over the next 2 days covers the shortfall and the soil would not
  reach the wilting point first ("rain-aware deferral").
* Net amount refills to field capacity, minus effective rain expected the next day, so a refill is not
  wasted as drainage. Gross = net / application efficiency.
"""

# ruff: noqa: E501  (explanatory strings)
from __future__ import annotations

from typing import Any

# Typical field application efficiencies (FAO Irrigation Water Management, Training Manual 4).
APPLICATION_EFFICIENCY = {
    "drip": 0.9, "sprinkler": 0.75, "pivot": 0.85, "furrow": 0.6, "flood": 0.6, "manual": 0.7,
}  # fmt: skip
DEFAULT_EFFICIENCY = 0.7
LIGHT_RAIN_MM = 2.0
RAIN_EFFECTIVENESS = 0.8
DEFER_LOOKAHEAD_DAYS = 2
MORNING = (5, 9)  # local hours preferred for irrigating (low evaporation and wind)
MAX_WIND_SPRINKLER_MS = 4.0


def efficiency(method: str | None) -> float:
    return APPLICATION_EFFICIENCY.get((method or "").lower(), DEFAULT_EFFICIENCY)


def effective_rain(mm: float) -> float:
    return RAIN_EFFECTIVENESS * mm if mm > LIGHT_RAIN_MM else 0.0


def net_mm_from_volume(volume_liters: float, area_ha: float, method: str | None) -> float:
    """Water that reached the root zone: litres over the area (1 L/m2 = 1 mm) x application efficiency."""
    return volume_liters / (area_ha * 10_000) * efficiency(method)


def plan(
    *,
    depletion_mm: float,
    taw_mm: float,
    raw_mm: float,
    kc: float,
    forecast: list[dict[str, Any]],
    method: str | None,
    area_ha: float | None,
    rain_aware: bool = True,
) -> dict[str, Any]:
    """Simulate the forecast days and place irrigations. ``forecast`` items: date, et0_mm, precipitation_mm."""
    eff = efficiency(method)
    days = []
    events = []
    dr = max(0.0, min(taw_mm, depletion_mm))
    deferred_mm = 0.0
    for i, d in enumerate(forecast):
        et0 = float(d.get("et0_mm") or 0)
        rain = float(d.get("precipitation_mm") or 0)
        etc, eff_rain = kc * et0, effective_rain(rain)
        start = dr
        end_without = min(taw_mm, max(0.0, start + etc - eff_rain))
        irrigation = None
        if end_without > raw_mm:
            ahead = forecast[i + 1 : i + 1 + DEFER_LOOKAHEAD_DAYS]
            rain_ahead = sum(effective_rain(float(a.get("precipitation_mm") or 0)) for a in ahead)
            etc_ahead = sum(kc * float(a.get("et0_mm") or 0) for a in ahead)
            # Defer only if the coming rain brings depletion back under RAW and we never reach TAW meanwhile.
            covered = end_without + etc_ahead - rain_ahead <= raw_mm and end_without < taw_mm
            if rain_aware and covered and rain_ahead > 0:
                deferred_mm += end_without
                reason = (
                    f"deferred: {rain_ahead:.1f} mm effective rain forecast in the next {len(ahead)} day(s)"
                )
                days.append(_day(d, et0, rain, etc, eff_rain, start, end_without, None, reason))
                dr = end_without
                continue
            next_rain = (
                effective_rain(float(forecast[i + 1].get("precipitation_mm") or 0))
                if i + 1 < len(forecast)
                else 0.0
            )
            net = max(0.0, round(end_without - (next_rain if rain_aware else 0.0), 1))
            if net > 0:
                gross = round(net / eff, 1)
                irrigation = {
                    "date": d["date"],
                    "day_index": i,
                    "net_mm": net,
                    "gross_mm": gross,
                    "volume_liters": round(gross * area_ha * 10_000) if area_ha else None,
                    "depletion_before_mm": round(end_without, 1),
                    "urgent": i == 0 and start > raw_mm,
                    "reason": (
                        f"depletion would reach {end_without:.1f} mm, past the {raw_mm:.1f} mm stress threshold"
                        + (f"; refill reduced by {next_rain:.1f} mm rain expected the next day" if next_rain and rain_aware else "")
                    ),
                }  # fmt: skip
                events.append(irrigation)
        end = max(0.0, end_without - (irrigation["net_mm"] if irrigation else 0.0))
        days.append(
            _day(d, et0, rain, etc, eff_rain, start, end, irrigation["net_mm"] if irrigation else None, None)
        )
        dr = end
    total_gross = round(sum(e["gross_mm"] for e in events), 1)
    return {
        "events": events,
        "days": days,
        "total_net_mm": round(sum(e["net_mm"] for e in events), 1),
        "total_gross_mm": total_gross,
        "total_volume_liters": round(total_gross * area_ha * 10_000) if area_ha else None,
        "application_efficiency": eff,
        "deferred_by_rain_mm": round(deferred_mm, 1),
    }


def _day(d: dict[str, Any], et0: float, rain: float, etc: float, eff_rain: float, start: float, end: float,
         irrigation_net: float | None, note: str | None) -> dict[str, Any]:  # fmt: skip
    return {
        "date": d["date"],
        "et0_mm": round(et0, 2),
        "etc_mm": round(etc, 2),
        "rain_mm": round(rain, 1),
        "effective_rain_mm": round(eff_rain, 1),
        "depletion_start_mm": round(start, 1),
        "irrigation_net_mm": irrigation_net,
        "depletion_end_mm": round(end, 1),
        "note": note,
    }


def best_window(hours: list[dict[str, Any]], method: str | None) -> dict[str, Any]:
    """Pick the calmest early-morning hour of a day (wind matters for sprinkler/pivot drift)."""
    morning = [h for h in hours if MORNING[0] <= h["local_hour"] < MORNING[1]]
    if not morning:
        return {
            "start_local_hour": MORNING[0],
            "basis": "default early morning (no hourly forecast for this day)",
        }
    calm = min(morning, key=lambda h: (h.get("wind_speed_ms") or 0, h["local_hour"]))
    wind = calm.get("wind_speed_ms")
    windy = (method or "") in ("sprinkler", "pivot") and wind is not None and wind > MAX_WIND_SPRINKLER_MS
    return {
        "start_local_hour": calm["local_hour"],
        "wind_speed_ms": wind,
        "basis": "calmest early-morning hour in the forecast"
        + ("; still windy for sprinklers, expect drift losses" if windy else ""),
    }
