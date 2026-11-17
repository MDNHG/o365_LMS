import math
from dataclasses import dataclass
from typing import Optional, Tuple

EARTH_RADIUS_METERS: float = 6371000.0


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float

    def __post_init__(self):
        try:
            lat = float(self.latitude)
            lon = float(self.longitude)
        except (TypeError, ValueError):
            raise ValueError(f"Tọa độ không hợp lệ: ({self.latitude}, {self.longitude})")

        if math.isnan(lat) or math.isinf(lat) or not (-90.0 <= lat <= 90.0):
            raise ValueError(f"Latitude phải nằm trong [-90, 90]. Nhận: {self.latitude}")
        if math.isnan(lon) or math.isinf(lon) or not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Longitude phải nằm trong [-180, 180]. Nhận: {self.longitude}")

        # Ensure values stored are floats
        object.__setattr__(self, "latitude", lat)
        object.__setattr__(self, "longitude", lon)

    def to_tuple(self) -> Tuple[float, float]:
        return self.latitude, self.longitude

    def to_google_maps_url(self) -> str:
        return f"https://www.google.com/maps?q={self.latitude:.6f},{self.longitude:.6f}"


@dataclass
class CheckInResult:
    is_valid: bool
    distance_meters: float
    allowed_radius_meters: float
    message: str
    user_coordinates: Coordinates
    target_coordinates: Coordinates
    accuracy_meters: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "success": self.is_valid,
            "message": self.message,
            "distance_meters": round(self.distance_meters, 2),
            "allowed_radius_meters": self.allowed_radius_meters,
            "user_location": {
                "latitude": self.user_coordinates.latitude,
                "longitude": self.user_coordinates.longitude,
                "accuracy_meters": self.accuracy_meters,
                "maps_url": self.user_coordinates.to_google_maps_url(),
            },
            "target_location": {
                "latitude": self.target_coordinates.latitude,
                "longitude": self.target_coordinates.longitude,
                "maps_url": self.target_coordinates.to_google_maps_url(),
            },
        }


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Tính khoảng cách hình cầu lớn giữa 2 tọa độ theo mét."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp 'a' to [0.0, 1.0] to prevent math domain error due to floating point inaccuracies
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def verify_check_in(
    user_latitude: float,
    user_longitude: float,
    target_latitude: float,
    target_longitude: float,
    max_radius_meters: float = 50.0,
    accuracy_meters: Optional[float] = None,
    allow_accuracy_buffer: bool = False,
) -> CheckInResult:
    """Xác thực khoảng cách check-in giữa người dùng và vị trí mục tiêu."""
    if max_radius_meters <= 0:
        raise ValueError("Bán kính cho phép (max_radius_meters) phải lớn hơn 0.")

    user_coords = Coordinates(latitude=user_latitude, longitude=user_longitude)
    target_coords = Coordinates(latitude=target_latitude, longitude=target_longitude)

    raw_distance = haversine_distance(
        user_coords.latitude,
        user_coords.longitude,
        target_coords.latitude,
        target_coords.longitude,
    )

    effective_distance = raw_distance
    buffer_applied = 0.0

    if allow_accuracy_buffer and accuracy_meters is not None:
        if not math.isnan(accuracy_meters) and accuracy_meters > 0:
            # Buffer is capped to max_radius_meters to avoid bypass from extreme distances
            buffer_applied = min(float(accuracy_meters), float(max_radius_meters))
            effective_distance = max(0.0, raw_distance - buffer_applied)

    is_valid = effective_distance <= max_radius_meters

    if is_valid:
        if raw_distance <= max_radius_meters:
            message = (
                f"Điểm danh thành công! Bạn cách vị trí {round(raw_distance, 1)}m "
                f"(trong bán kính cho phép {max_radius_meters}m)."
            )
        else:
            message = (
                f"Điểm danh thành công! Bạn cách vị trí {round(raw_distance, 1)}m "
                f"(hợp lệ nhờ bù sai số GPS ±{round(buffer_applied, 1)}m, bán kính cho phép {max_radius_meters}m)."
            )
    else:
        overshoot = round(raw_distance - max_radius_meters, 1)
        message = (
            f"Điểm danh thất bại! Bạn cách vị trí {round(raw_distance, 1)}m "
            f"(vượt quá {overshoot}m so với bán kính cho phép {max_radius_meters}m)."
        )

    return CheckInResult(
        is_valid=is_valid,
        distance_meters=raw_distance,
        allowed_radius_meters=max_radius_meters,
        message=message,
        user_coordinates=user_coords,
        target_coordinates=target_coords,
        accuracy_meters=accuracy_meters,
    )
