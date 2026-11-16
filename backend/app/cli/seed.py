"""Seed reference data.

    python -m app.cli.seed            # crop catalogue only (idempotent)
    python -m app.cli.seed --demo     # + a clearly-labelled demo user, farm and zones

Crop values are typical ranges from general agronomic references (e.g. FAO crop
water requirement guidance). They are indicative defaults for recommendations,
not prescriptions; real values vary with variety, climate and season.
"""

import argparse
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models import Crop, Farm, FarmZone, User

D = Decimal

# common, scientific, category, cycle days, pH min, pH max, temp min, temp max, seasonal water mm
CROPS: list[tuple[str, str, str, int | None, str, str, str, str, str]] = [
    ("Rice", "Oryza sativa", "cereal", 120, "5.5", "6.5", "20", "35", "1200"),
    ("Wheat", "Triticum aestivum", "cereal", 120, "6.0", "7.5", "12", "25", "450"),
    ("Maize", "Zea mays", "cereal", 110, "5.8", "7.0", "18", "32", "550"),
    ("Tomato", "Solanum lycopersicum", "vegetable", 110, "6.0", "6.8", "18", "27", "500"),
    ("Potato", "Solanum tuberosum", "vegetable", 100, "5.0", "6.5", "15", "20", "500"),
    ("Chilli pepper", "Capsicum annuum", "spice", 120, "6.0", "7.0", "20", "30", "600"),
    ("Onion", "Allium cepa", "vegetable", 130, "6.0", "7.0", "13", "24", "450"),
    ("Soybean", "Glycine max", "legume", 110, "6.0", "7.0", "20", "30", "500"),
    ("Groundnut", "Arachis hypogaea", "oilseed", 120, "5.9", "7.0", "22", "30", "500"),
    ("Cotton", "Gossypium hirsutum", "fiber", 170, "5.8", "8.0", "21", "32", "700"),
    ("Banana", "Musa acuminata", "fruit", 330, "5.5", "7.0", "20", "30", "1500"),
    ("Mango", "Mangifera indica", "fruit", None, "5.5", "7.5", "24", "30", "1000"),
]

DEMO_EMAIL = "demo@example.com"


def seed_crops(db: Session) -> int:
    rows: list[dict[str, Any]] = [
        {
            "common_name": c[0],
            "scientific_name": c[1],
            "category": c[2],
            "typical_cycle_days": c[3],
            "optimal_ph_min": D(c[4]),
            "optimal_ph_max": D(c[5]),
            "optimal_temp_min_c": D(c[6]),
            "optimal_temp_max_c": D(c[7]),
            "water_requirement_mm": D(c[8]),
        }
        for c in CROPS
    ]
    result = db.execute(
        insert(Crop).values(rows).on_conflict_do_nothing(index_elements=["common_name"]).returning(Crop.id)
    )
    return len(result.all())


def seed_demo(db: Session) -> str:
    """A demo farm so the UI has something to show before sign-up exists. Named 'Demo' everywhere."""
    if db.scalar(select(User).where(User.email == DEMO_EMAIL)):
        return "demo data already present"
    user = User(email=DEMO_EMAIL, full_name="Demo Grower", role="farmer")
    farm = Farm(
        owner=user,
        name="Demo Farm",
        description="Demonstration farm. Not a real property; contains no real sensor data.",
        latitude=D("17.385"),
        longitude=D("78.4867"),
        area_hectares=D("12.5"),
        timezone="Asia/Kolkata",
    )
    zones = [
        ("North Field", "field", "5.0", "drip"),
        ("South Field", "field", "4.5", "sprinkler"),
        ("Greenhouse", "greenhouse", "0.5", "drip"),
        ("Orchard", "orchard", "2.5", "drip"),
    ]
    farm.zones.extend(
        FarmZone(name=n, zone_type=t, area_hectares=D(a), irrigation_method=m) for n, t, a, m in zones
    )
    db.add(farm)
    db.flush()
    return f"created demo farm id={farm.id} with {len(farm.zones)} zones"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed AGRI-SENSE reference data.")
    parser.add_argument("--demo", action="store_true", help="also create a demo user, farm and zones")
    args = parser.parse_args()
    with get_sessionmaker()() as db:
        print(f"crops: {seed_crops(db)} inserted ({len(CROPS)} in catalogue)")
        if args.demo:
            print(f"demo: {seed_demo(db)}")
        db.commit()


if __name__ == "__main__":
    main()
