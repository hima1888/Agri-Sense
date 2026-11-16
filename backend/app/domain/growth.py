# ruff: noqa: E501
"""Crop growth stages from FAO-56 stage lengths.

FAO-56 (Allen et al., 1998), Table 11, gives four stage lengths in days for annual crops: initial,
crop development, mid-season and late season, each for one listed region. Here they are kept as proportions and
scaled to the crop's cycle length (the zone's crop cycle dates if known, else the catalogue's typical cycle).

The eight user-facing stages are mapped onto the four FAO stages:

  seed (sowing day) | germination + seedling = initial | vegetative = development |
  flowering + fruiting/grain formation = mid-season | maturity = late season | harvest (last day)

FAO-56 does not split the initial or mid-season stage. The split points used here (germination = first 40 % of
the initial stage; flowering = first 35 % of mid-season) are APPROXIMATIONS and are reported as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

# FAO-56 Table 11: (initial, development, mid-season, late season) in days, and the region listed.
FAO56_STAGE_DAYS: dict[str, tuple[tuple[int, int, int, int], str]] = {
    "tomato": ((30, 40, 40, 25), "California, USA"),
    "maize": ((30, 40, 50, 30), "Africa, E. Mediterranean (grain maize)"),
    "rice": ((30, 30, 60, 30), "Tropics; Mediterranean"),
    "wheat": ((20, 25, 60, 30), "California, USA (spring wheat)"),
    "potato": ((25, 30, 45, 30), "semi-arid climate"),
    "onion": ((15, 25, 70, 40), "Mediterranean (dry onion)"),
    "soybean": ((20, 30, 60, 25), "Central USA"),
    "groundnut": ((25, 35, 45, 25), "West Africa"),
    "cotton": ((30, 50, 60, 55), "Egypt, Pakistan"),
    "chilli pepper": ((25, 35, 40, 20), "Europe and Mediterranean (sweet pepper)"),
}
CROP_ALIASES = {
    "corn": "maize",
    "sweet pepper": "chilli pepper",
    "bell pepper": "chilli pepper",
    "paddy": "rice",
}
PERENNIAL = {"banana", "mango"}

GERMINATION_SHARE = 0.40  # of the initial stage (approximation, see module docstring)
FLOWERING_SHARE = 0.35  # of the mid-season stage (approximation)

# What the "fruiting / grain formation" stage is called for each crop.
FORMATION_NAME = {
    "tomato": "Fruiting",
    "chilli pepper": "Fruiting",
    "maize": "Grain formation",
    "rice": "Grain formation",
    "wheat": "Grain formation",
    "potato": "Tuber bulking",
    "onion": "Bulb formation",
    "soybean": "Pod filling",
    "groundnut": "Pod filling",
    "cotton": "Boll formation",
}


class UnsupportedCropError(ValueError):
    pass


@dataclass(frozen=True)
class Stage:
    key: str
    name: str
    start_day: int  # day after sowing, inclusive
    end_day: int  # inclusive
    fao_stage: str
    approximate_boundary: bool
    description: str


def crop_key(common_name: str) -> str:
    n = common_name.strip().lower()
    return CROP_ALIASES.get(n, n)


def supported() -> list[str]:
    return sorted(FAO56_STAGE_DAYS)


def _scale(parts: tuple[int, int, int, int], total: int) -> list[int]:
    """Scale the four lengths to `total` days, keeping every stage at least 1 day and the sum exact."""
    s = sum(parts)
    out = [max(1, round(p * total / s)) for p in parts]
    out[2] += total - sum(out)  # absorb rounding in the longest-lived stage
    return out


def stages(common_name: str, cycle_days: int | None) -> dict[str, Any]:
    key = crop_key(common_name)
    if key in PERENNIAL:
        raise UnsupportedCropError(
            f"{common_name} is perennial; the FAO-56 annual stage model does not apply. Not modelled."
        )
    if key not in FAO56_STAGE_DAYS:
        raise UnsupportedCropError(
            f"No FAO-56 stage lengths for {common_name}. Supported: {', '.join(supported())}."
        )
    fao, region = FAO56_STAGE_DAYS[key]
    total = cycle_days if cycle_days and cycle_days >= 20 else sum(fao)
    ini, dev, mid, late = _scale(fao, total)
    germ = max(1, round(ini * GERMINATION_SHARE))
    flower = max(1, round(mid * FLOWERING_SHARE))
    formation = FORMATION_NAME.get(key, "Fruiting / grain formation")

    d0 = 1
    rows: list[Stage] = [Stage("seed", "Seed", 0, 0, "sowing", False, "Seed sown; the cycle starts (day 0).")]

    def add(k: str, name: str, length: int, fao_stage: str, approx: bool, text: str) -> None:
        nonlocal d0
        rows.append(Stage(k, name, d0, d0 + length - 1, fao_stage, approx, text))
        d0 += length

    add("germination", "Germination", germ, "initial", True, "Seed absorbs water, the root and shoot emerge.")
    add(
        "seedling",
        "Seedling",
        ini - germ,
        "initial",
        True,
        "First true leaves; ground cover below about 10 %.",
    )
    add(
        "vegetative",
        "Vegetative",
        dev,
        "development",
        False,
        "Rapid leaf and stem growth until near-full ground cover.",
    )
    add(
        "flowering",
        "Flowering",
        flower,
        "mid-season",
        True,
        "Flowers open; the crop is most sensitive to water stress.",
    )
    add("formation", formation, mid - flower, "mid-season", True, f"{formation}: yield is being formed.")
    add(
        "maturity",
        "Maturity",
        late,
        "late season",
        False,
        "Leaves age and yellow; the crop dries down or ripens.",
    )
    rows.append(
        Stage("harvest", "Harvest", total, total, "end of season", False, "Harvest at the end of the cycle.")
    )

    return {
        "crop": common_name,
        "crop_key": key,
        "cycle_days": total,
        "fao56": {
            "initial": fao[0],
            "development": fao[1],
            "mid_season": fao[2],
            "late_season": fao[3],
            "region": region,
        },
        "stages": [s.__dict__ for s in rows],
        "method": (
            "FAO-56 Table 11 stage proportions scaled to the cycle length. Germination/seedling and "
            "flowering/formation splits inside a FAO stage are approximations."
        ),
        "limitations": [
            "FAO-56 lengths are for one listed region; local varieties, sowing dates and climate change them.",
            "Stage dates are calendar estimates from the sowing date, not observations of the crop.",
            "Split points inside the initial and mid-season stages are approximations (not in FAO-56).",
        ],
    }


def current(model: dict[str, Any], planted_on: date | None, today: date) -> dict[str, Any] | None:
    """Where a cycle sown on `planted_on` is today. None when the sowing date is unknown."""
    if planted_on is None:
        return None
    day = (today - planted_on).days
    if day < 0:
        return {"day": day, "stage_key": None, "progress": 0.0, "note": "Sowing date is in the future."}
    total = model["cycle_days"]
    stage = next((s for s in model["stages"] if s["start_day"] <= day <= s["end_day"]), None)
    if day >= total:
        stage = model["stages"][-1]
    return {
        "day": day,
        "stage_key": stage["key"] if stage else None,
        "progress": round(min(1.0, day / total), 3),
        "note": "Past the expected harvest date." if day > total else None,
    }
