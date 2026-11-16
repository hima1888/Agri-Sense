"""Cross-table consistency rules the database cannot express with a single CHECK."""

from sqlalchemy.orm import Session

from app.api.errors import UnprocessableError
from app.models import CropCycle, Device, FarmZone, SoilProfile
from app.services.crud import get_or_404


def require_zone_in_farm(db: Session, zone_id: int | None, farm_id: int) -> None:
    if zone_id is None:
        return
    zone = db.get(FarmZone, zone_id)
    if zone is None or zone.farm_id != farm_id:
        raise UnprocessableError(f"Zone {zone_id} does not belong to farm {farm_id}.", {"field": "zone_id"})


def require_device_compatible(db: Session, device_id: int | None, farm_id: int, source: str) -> None:
    """A sensor on a device must be on the same farm and share its data source,
    so a simulated device can never feed a sensor labelled as hardware."""
    if device_id is None:
        return
    device = db.get(Device, device_id)
    if device is None or device.farm_id != farm_id:
        raise UnprocessableError(
            f"Device {device_id} does not belong to farm {farm_id}.", {"field": "device_id"}
        )
    if device.source != source:
        raise UnprocessableError(
            f"Sensor source '{source}' does not match device source '{device.source}'.", {"field": "source"}
        )


def require_cycle_in_zone(db: Session, crop_cycle_id: int | None, zone_id: int) -> None:
    if crop_cycle_id is None:
        return
    cycle = db.get(CropCycle, crop_cycle_id)
    if cycle is None or cycle.zone_id != zone_id:
        raise UnprocessableError(
            f"Crop cycle {crop_cycle_id} does not belong to zone {zone_id}.", {"field": "crop_cycle_id"}
        )


def require_profile_in_zone(db: Session, soil_profile_id: int | None, zone_id: int) -> None:
    if soil_profile_id is None:
        return
    profile = db.get(SoilProfile, soil_profile_id)
    if profile is None or profile.zone_id != zone_id:
        raise UnprocessableError(
            f"Soil profile {soil_profile_id} does not belong to zone {zone_id}.", {"field": "soil_profile_id"}
        )


def zone_farm_id(db: Session, zone_id: int) -> int:
    return get_or_404(db, FarmZone, zone_id, "Zone").farm_id
