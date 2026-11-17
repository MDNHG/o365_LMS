"""
Dữ liệu tọa độ GPS Đại học Bách Khoa Hà Nội (HUST)
Trích xuất từ hust_gps_coordinates.md
"""
from typing import List, Dict, Any

HUST_LOCATIONS_DATA: List[Dict[str, Any]] = [
    # ─── Academic / office buildings – C zone (north) ───
    {"name": "C1", "latitude": 21.00977, "longitude": 105.84462, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C1B", "latitude": 21.00956, "longitude": 105.84653, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C2 (north block)", "latitude": 21.00895, "longitude": 105.84301, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C2 (south block)", "latitude": 21.00856, "longitude": 105.84290, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C3", "latitude": 21.00886, "longitude": 105.84622, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C3B", "latitude": 21.00899, "longitude": 105.84783, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C3-4", "latitude": 21.00847, "longitude": 105.84564, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C4", "latitude": 21.00810, "longitude": 105.84636, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C4B", "latitude": 21.00847, "longitude": 105.84685, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C4-5", "latitude": 21.00768, "longitude": 105.84564, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C5", "latitude": 21.00732, "longitude": 105.84636, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C5-10", "latitude": 21.00705, "longitude": 105.84573, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C10", "latitude": 21.00666, "longitude": 105.84699, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C7", "latitude": 21.00695, "longitude": 105.84859, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C9 (west wing)", "latitude": 21.00742, "longitude": 105.84211, "zone": "C zone (north)", "radius": 50.0},
    {"name": "C9 (east wing)", "latitude": 21.00742, "longitude": 105.84329, "zone": "C zone (north)", "radius": 50.0},

    # ─── Open spaces / parking – C zone ───
    {"name": "Quảng trường C1 (C1 Square)", "latitude": 21.00810, "longitude": 105.84455, "zone": "Bãi xe & Quảng trường", "radius": 70.0},
    {"name": "Bãi xe C1 (parking)", "latitude": 21.01031, "longitude": 105.84462, "zone": "Bãi xe & Quảng trường", "radius": 60.0},
    {"name": "Bãi xe C2 (parking)", "latitude": 21.01025, "longitude": 105.84231, "zone": "Bãi xe & Quảng trường", "radius": 60.0},
    {"name": "Bãi xe C9 (parking)", "latitude": 21.00660, "longitude": 105.84259, "zone": "Bãi xe & Quảng trường", "radius": 60.0},
    {"name": "Lối ra Hầm gửi xe C7 (underground parking exit)", "latitude": 21.00797, "longitude": 105.84794, "zone": "Bãi xe & Quảng trường", "radius": 50.0},

    # ─── D zone (south) ───
    {"name": "D2A", "latitude": 21.00553, "longitude": 105.84343, "zone": "D zone (south)", "radius": 50.0},
    {"name": "D2B", "latitude": 21.00553, "longitude": 105.84423, "zone": "D zone (south)", "radius": 50.0},
    {"name": "D3", "latitude": 21.00536, "longitude": 105.84870, "zone": "D zone (south)", "radius": 50.0},
    {"name": "D4", "latitude": 21.00433, "longitude": 105.84273, "zone": "D zone (south)", "radius": 50.0},
    {"name": "D5", "latitude": 21.00453, "longitude": 105.84771, "zone": "D zone (south)", "radius": 50.0},
    {"name": "D6", "latitude": 21.00446, "longitude": 105.84410, "zone": "D zone (south)", "radius": 50.0},
    {"name": "D7", "latitude": 21.00389, "longitude": 105.84787, "zone": "D zone (south)", "radius": 50.0},
    {"name": "D8", "latitude": 21.00376, "longitude": 105.84365, "zone": "D zone (south)", "radius": 50.0},
    {"name": "D9", "latitude": 21.00349, "longitude": 105.84706, "zone": "D zone (south)", "radius": 50.0},

    # ─── Landmarks ───
    {"name": "Thư viện Tạ Quang Bửu (Library)", "latitude": 21.00490, "longitude": 105.84650, "zone": "Landmarks", "radius": 60.0},
    {"name": "Hồ Tiền (Tien Lake)", "latitude": 21.00412, "longitude": 105.84497, "zone": "Landmarks", "radius": 80.0},
    {"name": "A1", "latitude": 21.00362, "longitude": 105.84252, "zone": "Landmarks", "radius": 50.0},

    # ─── B1 ───
    {"name": "Nhà B1 (and Bãi xe B1 parking)", "latitude": 21.01019, "longitude": 105.84106, "zone": "B1", "radius": 60.0},
]


def seed_hust_locations():
    """
    Tự động kiểm tra và đồng bộ 34 địa điểm từ hust_gps_coordinates.md vào database.
    Luôn đảm bảo database có đầy đủ địa điểm ngay cả khi reset db.
    """
    from check_in.models import CheckInLocation

    for item in HUST_LOCATIONS_DATA:
        CheckInLocation.objects.get_or_create(
            name=item["name"],
            defaults={
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "zone": item["zone"],
                "default_radius_meters": item["radius"],
                "is_active": True,
            },
        )


def get_current_active_location():
    """
    Lấy địa điểm mốc điểm danh đang được chọn làm active trên hệ thống (do Giảng viên chọn).
    Nếu chưa có địa điểm nào được chọn, trả về None (để fallback về DEFAULT_TARGET_LATITUDE / LONGITUDE).
    """
    from check_in.models import CheckInLocation
    return CheckInLocation.objects.filter(is_active=True, is_current=True).first()
