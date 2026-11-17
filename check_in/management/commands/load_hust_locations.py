"""
Management command to load HUST GPS coordinates from hust_gps_coordinates.md
into the CheckInLocation table.

Usage:
    python manage.py load_hust_locations
"""
import os
import re
from django.core.management.base import BaseCommand
from check_in.models import CheckInLocation


class Command(BaseCommand):
    help = "Nạp các địa điểm HUST từ file hust_gps_coordinates.md vào bảng CheckInLocation"

    def handle(self, *args, **options):
        md_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "hust_gps_coordinates.md",
        )

        if not os.path.exists(md_path):
            self.stderr.write(self.style.ERROR(f"Không tìm thấy file: {md_path}"))
            return

        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse markdown tables: | Name | Latitude | Longitude | ...
        # Match lines like: | C1 | 21.00977 | 105.84462 | ...
        # We need to find the zone headers too
        current_zone = ""
        created_count = 0
        skipped_count = 0

        for line in content.split("\n"):
            line = line.strip()

            # Detect zone headers
            zone_match = re.match(r"^##\s+(.+)$", line)
            if zone_match:
                current_zone = zone_match.group(1).strip()
                continue

            # Skip header/separator rows
            if line.startswith("|---") or line.startswith("| Name") or line.startswith("| ---"):
                continue

            # Parse data rows: | Name | Lat | Lon | ... |
            row_match = re.match(
                r"^\|\s*(.+?)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|",
                line,
            )
            if row_match:
                name = row_match.group(1).strip()
                try:
                    lat = float(row_match.group(2))
                    lon = float(row_match.group(3))
                except ValueError:
                    continue

                # Skip if already exists with same name + coordinates
                exists = CheckInLocation.objects.filter(
                    name=name, latitude=lat, longitude=lon
                ).exists()

                if exists:
                    skipped_count += 1
                    continue

                CheckInLocation.objects.create(
                    name=name,
                    zone=current_zone,
                    latitude=lat,
                    longitude=lon,
                    default_radius_meters=50.0,
                    is_active=True,
                )
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Hoàn tất! Đã tạo {created_count} địa điểm mới, bỏ qua {skipped_count} đã tồn tại."
            )
        )
