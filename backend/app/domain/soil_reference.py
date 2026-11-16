"""Reference values for soil assessment, with their sources.

These are published, general-purpose reference values. They are approximations:
real soils and varieties differ, and local extension guidance should take precedence.

Sources
-------
* FAO Irrigation and Drainage Paper 56 (Allen et al., 1998), "Crop evapotranspiration":
  - Table 19: soil water characteristics (field capacity, wilting point) by texture;
  - Table 12: single crop coefficients Kc (initial, mid-season, end);
  - Table 22: maximum effective root depth Zr and soil water depletion fraction p.
* Soil Health Card scheme, Government of India: fertility rating limits for available
  N, P and K (kg/ha) and organic carbon (%).
"""

from dataclasses import dataclass

# ---------------------------------------------------------------- soil water (FAO-56 Table 19)
# Volumetric water content (%) at field capacity and wilting point: midpoints of the FAO
# ranges. Classes not listed in Table 19 are interpolated from neighbouring classes.
TEXTURE_WATER: dict[str, tuple[float, float]] = {
    "sand": (12.0, 4.5),
    "loamy_sand": (15.0, 6.5),
    "sandy_loam": (23.0, 11.0),
    "loam": (25.0, 12.0),
    "silt_loam": (29.0, 15.0),
    "silt": (32.0, 17.0),
    "sandy_clay_loam": (27.0, 16.0),  # interpolated
    "clay_loam": (32.0, 19.0),  # interpolated
    "silty_clay_loam": (33.5, 20.5),
    "sandy_clay": (30.0, 19.0),  # interpolated
    "silty_clay": (36.0, 23.0),
    "clay": (36.0, 22.0),
}
DEFAULT_TEXTURE = "loam"


@dataclass(frozen=True)
class CropWater:
    kc_ini: float
    kc_mid: float
    kc_end: float
    root_depth_m: float  # effective rooting depth used for the water balance
    p: float  # fraction of total available water that can be depleted before stress


# FAO-56 Tables 12 and 22 (root depth: lower-middle of the published range, as an
# effective depth for irrigation scheduling).
CROP_WATER: dict[str, CropWater] = {
    "tomato": CropWater(0.60, 1.15, 0.80, 0.7, 0.40),
    "maize": CropWater(0.30, 1.20, 0.60, 1.0, 0.55),
    "rice": CropWater(1.05, 1.20, 0.90, 0.5, 0.20),
    "wheat": CropWater(0.40, 1.15, 0.40, 1.0, 0.55),
    "potato": CropWater(0.50, 1.15, 0.75, 0.5, 0.35),
    "onion": CropWater(0.70, 1.05, 0.75, 0.4, 0.30),
    "soybean": CropWater(0.40, 1.15, 0.50, 0.8, 0.50),
    "groundnut": CropWater(0.40, 1.15, 0.60, 0.6, 0.50),
    "cotton": CropWater(0.35, 1.18, 0.60, 1.2, 0.65),
    "banana": CropWater(0.50, 1.10, 1.00, 0.6, 0.35),
    "chilli pepper": CropWater(0.60, 1.05, 0.90, 0.6, 0.30),
    "mango": CropWater(0.85, 0.85, 0.85, 1.2, 0.50),  # perennial; not in Table 12, conservative
}
CATEGORY_WATER: dict[str, CropWater] = {
    "cereal": CropWater(0.35, 1.15, 0.50, 1.0, 0.55),
    "vegetable": CropWater(0.60, 1.05, 0.85, 0.5, 0.40),
    "fruit": CropWater(0.80, 0.95, 0.85, 1.0, 0.50),
    "legume": CropWater(0.40, 1.15, 0.55, 0.7, 0.45),
    "oilseed": CropWater(0.40, 1.15, 0.60, 0.8, 0.55),
    "fiber": CropWater(0.35, 1.15, 0.60, 1.2, 0.65),
    "spice": CropWater(0.60, 1.05, 0.90, 0.5, 0.35),
}
DEFAULT_CROP_WATER = CropWater(0.50, 1.00, 0.80, 0.6, 0.50)


def crop_water(common_name: str | None, category: str | None) -> tuple[CropWater, str]:
    """Return parameters and where they came from ('crop', 'category' or 'default')."""
    if common_name and common_name.strip().lower() in CROP_WATER:
        return CROP_WATER[common_name.strip().lower()], "crop"
    if category and category in CATEGORY_WATER:
        return CATEGORY_WATER[category], "category"
    return DEFAULT_CROP_WATER, "default"


def kc_for_growth(cw: CropWater, growth: float | None) -> float:
    """FAO-56 Kc curve by growth stage: initial (<20 %), development (linear to 45 %),
    mid-season (to 80 %), late season (linear to end)."""
    if growth is None:
        return cw.kc_mid
    g = max(0.0, min(1.0, growth))
    if g < 0.20:
        return cw.kc_ini
    if g < 0.45:
        return cw.kc_ini + (cw.kc_mid - cw.kc_ini) * (g - 0.20) / 0.25
    if g < 0.80:
        return cw.kc_mid
    return cw.kc_mid + (cw.kc_end - cw.kc_mid) * (g - 0.80) / 0.20


# ---------------------------------------------------------------- fertility ratings (Soil Health Card)
# A soil test in mg/kg converts to kg/ha for a 0-15 cm furrow slice at bulk density
# ~1.49 g/cm3 (2.24 million kg of soil per hectare).
MG_KG_TO_KG_HA = 2.24

# (low_below, high_above) in kg/ha; between them is "medium".
NPK_LIMITS_KG_HA: dict[str, tuple[float, float]] = {
    "nitrogen": (280.0, 560.0),  # available N (alkaline permanganate)
    "phosphorus": (10.0, 25.0),  # available P (Olsen)
    "potassium": (110.0, 280.0),  # available K (ammonium acetate)
}
ORGANIC_CARBON_LIMITS_PCT = (0.50, 0.75)

# Electrical conductivity of a 1:2 soil:water extract (dS/m): general salinity classes.
EC_CLASSES = ((1.0, "normal"), (2.0, "slightly saline"), (4.0, "moderately saline"))


def rate(value: float, low_below: float, high_above: float) -> str:
    if value < low_below:
        return "low"
    if value > high_above:
        return "high"
    return "medium"
