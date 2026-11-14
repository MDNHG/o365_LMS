import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import CheckInRecord
from .check_in_location import Coordinates, haversine_distance, verify_check_in
from .admin import CheckInRecordAdmin
from django.contrib.admin.sites import AdminSite

User = get_user_model()


class CoordinatesAndDistanceTests(TestCase):
    def test_haversine_distance_same_location(self):
        dist = haversine_distance(21.0049, 105.8433, 21.0049, 105.8433)
        self.assertAlmostEqual(dist, 0.0, places=2)

    def test_haversine_distance_known_points(self):
        # Khoảng cách giữa 2 điểm gần nhau (~111m cho 0.001 độ vĩ độ)
        dist = haversine_distance(21.0000, 105.0000, 21.0010, 105.0000)
        self.assertTrue(100.0 < dist < 120.0)

    def test_haversine_antipodal_does_not_crash(self):
        # Điểm đối cực có thể gây a >= 1.0 do sai số dấu phẩy động
        try:
            dist = haversine_distance(90.0, 0.0, -90.0, 0.0)
            self.assertTrue(dist > 0)
        except ValueError:
            self.fail("haversine_distance raised ValueError on extreme coordinates")

    def test_coordinates_valid(self):
        coords = Coordinates(latitude=21.0049, longitude=105.8433)
        self.assertEqual(coords.latitude, 21.0049)
        self.assertEqual(coords.longitude, 105.8433)
        self.assertEqual(coords.to_tuple(), (21.0049, 105.8433))
        self.assertIn("21.004900,105.843300", coords.to_google_maps_url())

    def test_coordinates_invalid_bounds(self):
        with self.assertRaises(ValueError):
            Coordinates(latitude=91.0, longitude=100.0)
        with self.assertRaises(ValueError):
            Coordinates(latitude=-91.0, longitude=100.0)
        with self.assertRaises(ValueError):
            Coordinates(latitude=20.0, longitude=181.0)
        with self.assertRaises(ValueError):
            Coordinates(latitude=20.0, longitude=-181.0)
        with self.assertRaises(ValueError):
            Coordinates(latitude=float("nan"), longitude=100.0)
        with self.assertRaises(ValueError):
            Coordinates(latitude="abc", longitude=100.0)


class VerifyCheckInTests(TestCase):
    def test_verify_check_in_success_exact(self):
        target_lat = 21.004900
        target_lon = 105.843300
        result = verify_check_in(
            user_latitude=target_lat,
            user_longitude=target_lon,
            target_latitude=target_lat,
            target_longitude=target_lon,
            max_radius_meters=50.0,
        )
        self.assertTrue(result.is_valid)
        self.assertAlmostEqual(result.distance_meters, 0.0, places=1)
        self.assertIn("thành công", result.message.lower())

    def test_verify_check_in_failure_too_far(self):
        result = verify_check_in(
            user_latitude=21.050000,
            user_longitude=105.843300,
            target_latitude=21.004900,
            target_longitude=105.843300,
            max_radius_meters=50.0,
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(result.distance_meters > 1000)
        self.assertIn("thất bại", result.message.lower())

    def test_verify_check_in_invalid_radius(self):
        with self.assertRaises(ValueError):
            verify_check_in(21.0, 105.0, 21.0, 105.0, max_radius_meters=0.0)

    def test_verify_check_in_accuracy_buffer(self):
        # Cách khoảng 60m, nhưng bán kính 50m và sai số GPS ±20m
        # 0.00054 độ vĩ độ ~ 60 mét
        target_lat = 21.000000
        target_lon = 105.000000
        user_lat = 21.000540
        user_lon = 105.000000

        # Không cho buffer -> thất bại
        res_no_buffer = verify_check_in(
            user_lat, user_lon, target_lat, target_lon,
            max_radius_meters=50.0, accuracy_meters=20.0, allow_accuracy_buffer=False
        )
        self.assertFalse(res_no_buffer.is_valid)

        # Cho buffer -> thành công
        res_buffer = verify_check_in(
            user_lat, user_lon, target_lat, target_lon,
            max_radius_meters=50.0, accuracy_meters=20.0, allow_accuracy_buffer=True
        )
        self.assertTrue(res_buffer.is_valid)
        self.assertIn("bù sai số gps", res_buffer.message.lower())

    def test_accuracy_buffer_cannot_bypass_far_distance(self):
        # Cách xa 5km với accuracy 10km không thể được duyệt
        target_lat = 21.000000
        target_lon = 105.000000
        user_lat = 21.050000
        user_lon = 105.000000
        result = verify_check_in(
            user_lat, user_lon, target_lat, target_lon,
            max_radius_meters=50.0, accuracy_meters=10000.0, allow_accuracy_buffer=True
        )
        self.assertFalse(result.is_valid)


class CheckInRecordModelTests(TestCase):
    def test_str_representation_unsaved(self):
        # Kiểm tra __str__ không bị crash khi created_at là None
        record = CheckInRecord(
            user=None,
            user_latitude=21.0,
            user_longitude=105.0,
            target_latitude=21.0,
            target_longitude=105.0,
            distance_meters=10.5,
            is_valid=True,
        )
        s = str(record)
        self.assertIn("[Thành công] Ẩn danh - 10.5m", s)

    def test_str_representation_saved_with_user(self):
        user = User.objects.create_user(username="testuser", password="password123")
        record = CheckInRecord.objects.create(
            user=user,
            user_latitude=21.0,
            user_longitude=105.0,
            target_latitude=21.0,
            target_longitude=105.0,
            distance_meters=5.0,
            is_valid=True,
        )
        s = str(record)
        self.assertIn("[Thành công] testuser - 5.0m", s)


class CheckInViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="student1", password="password123")

    def test_check_in_page_get(self):
        url = reverse("check_in:check_in_page")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "check_in/interface.html")
        self.assertContains(response, "Điểm Danh Sự Kiện")

    def test_check_in_api_empty_body(self):
        url = reverse("check_in:check_in_api")
        response = self.client.post(url, data="", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])

    def test_check_in_api_invalid_json(self):
        url = reverse("check_in:check_in_api")
        response = self.client.post(url, data="bad-json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_check_in_api_json_list(self):
        url = reverse("check_in:check_in_api")
        response = self.client.post(url, data=json.dumps([1, 2, 3]), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_check_in_api_missing_coordinates(self):
        url = reverse("check_in:check_in_api")
        response = self.client.post(url, data=json.dumps({"latitude": 21.0}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_check_in_api_invalid_latitude_bounds(self):
        url = reverse("check_in:check_in_api")
        response = self.client.post(
            url,
            data=json.dumps({"latitude": 999.0, "longitude": 105.0}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_check_in_api_success_and_persisted(self):
        url = reverse("check_in:check_in_api")
        self.client.force_login(self.user)
        payload = {
            "latitude": 21.004900,
            "longitude": 105.843300,
            "accuracy": 10.0,
        }
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIsNotNone(data.get("record_id"))

        # Kiểm tra bản ghi đã được lưu vào CSDL
        record = CheckInRecord.objects.get(id=data["record_id"])
        self.assertEqual(record.user, self.user)
        self.assertTrue(record.is_valid)
        self.assertAlmostEqual(record.user_latitude, 21.004900)

    def test_check_in_api_failure_and_persisted(self):
        url = reverse("check_in:check_in_api")
        payload = {
            "latitude": 20.000000,
            "longitude": 105.000000,
            "accuracy": 15.0,
        }
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIsNotNone(data.get("record_id"))

        record = CheckInRecord.objects.get(id=data["record_id"])
        self.assertIsNone(record.user)
        self.assertFalse(record.is_valid)

    def test_export_checkin_excel(self):
        # Create sample records
        CheckInRecord.objects.create(
            user=self.user,
            user_latitude=21.0049,
            user_longitude=105.8433,
            target_latitude=21.0049,
            target_longitude=105.8433,
            distance_meters=0.0,
            is_valid=True,
            message="Thành công",
        )
        url = reverse("check_in:export_checkin_excel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("danh_sach_diem_danh.xlsx", response["Content-Disposition"])
        # Verify it is valid excel content
        import io, openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        self.assertIn("Lịch sử Điểm danh", wb.sheetnames)
        ws = wb["Lịch sử Điểm danh"]
        self.assertEqual(ws.cell(row=1, column=1).value, "STT")
        self.assertEqual(ws.cell(row=2, column=3).value, self.user.username)

    def test_export_checkin_csv(self):
        CheckInRecord.objects.create(
            user=self.user,
            user_latitude=21.0049,
            user_longitude=105.8433,
            target_latitude=21.0049,
            target_longitude=105.8433,
            distance_meters=0.0,
            is_valid=True,
            message="Thành công",
        )
        url = reverse("check_in:export_checkin_csv")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("danh_sach_diem_danh.csv", response["Content-Disposition"])
        self.assertIn(self.user.username.encode("utf-8"), response.content)


class AdminTests(TestCase):
    def test_admin_helpers(self):
        admin_instance = CheckInRecordAdmin(CheckInRecord, AdminSite())

        # Test display_user anonymous
        rec_anon = CheckInRecord(user=None, user_latitude=21.0, user_longitude=105.0)
        self.assertEqual(admin_instance.display_user(rec_anon), "Khách ẩn danh")

        # Test display_user with user
        user = User.objects.create_user(username="test_admin_user", first_name="Nguyen", last_name="Van A")
        rec_user = CheckInRecord(user=user, user_latitude=21.0, user_longitude=105.0)
        self.assertIn("Nguyen Van A", admin_instance.display_user(rec_user))

        # Test status_badge
        rec_valid = CheckInRecord(is_valid=True)
        rec_invalid = CheckInRecord(is_valid=False)
        self.assertIn("Hợp lệ", str(admin_instance.status_badge(rec_valid)))
        self.assertIn("Không hợp lệ", str(admin_instance.status_badge(rec_invalid)))

        # Test view_on_map
        self.assertIn("google.com/maps", str(admin_instance.view_on_map(rec_user)))
        rec_empty_coords = CheckInRecord(user_latitude=None, user_longitude=None)
        self.assertEqual(admin_instance.view_on_map(rec_empty_coords), "-")
