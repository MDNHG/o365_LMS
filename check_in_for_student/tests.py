import json
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse, NoReverseMatch
from django.contrib.admin.sites import AdminSite
from check_in.models import CheckInRecord
from .models import StudentCheckInRecord
from .admin import StudentCheckInRecordAdmin
from .check_in_location import Coordinates, haversine_distance, verify_check_in

User = get_user_model()


class StudentCoordinatesAndDistanceTests(TestCase):
    def test_haversine_distance_same_location(self):
        dist = haversine_distance(21.0049, 105.8433, 21.0049, 105.8433)
        self.assertAlmostEqual(dist, 0.0, places=2)

    def test_haversine_distance_known_points(self):
        dist = haversine_distance(21.0000, 105.0000, 21.0010, 105.0000)
        self.assertTrue(100.0 < dist < 120.0)

    def test_coordinates_valid(self):
        coords = Coordinates(latitude=21.0049, longitude=105.8433)
        self.assertEqual(coords.latitude, 21.0049)
        self.assertEqual(coords.longitude, 105.8433)
        self.assertEqual(coords.to_tuple(), (21.0049, 105.8433))

    def test_coordinates_invalid_bounds(self):
        with self.assertRaises(ValueError):
            Coordinates(latitude=95.0, longitude=100.0)
        with self.assertRaises(ValueError):
            Coordinates(latitude=20.0, longitude=200.0)


class StudentVerifyCheckInTests(TestCase):
    def test_verify_check_in_success(self):
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

    def test_verify_check_in_too_far(self):
        result = verify_check_in(
            user_latitude=21.050000,
            user_longitude=105.843300,
            target_latitude=21.004900,
            target_longitude=105.843300,
            max_radius_meters=50.0,
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(result.distance_meters > 1000)


class StudentCheckInViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username="student_user",
            password="password123",
            first_name="Học Viên",
            last_name="Test",
            role="student",
            student_id="20269999",
        )

    def test_student_check_in_page_get(self):
        url = reverse("check_in_for_student:student_check_in_page")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "check_in_for_student/interface.html")
        self.assertContains(response, "CỔNG ĐIỂM DANH SINH VIÊN")
        # Ensure that no database export buttons/links are in the student interface
        self.assertNotContains(response, "XUẤT FILE EXCEL")
        self.assertNotContains(response, "export_checkin_excel")
        self.assertNotContains(response, "export_checkin_csv")
        self.assertNotContains(response, ".xlsx")

    def test_student_check_in_api_empty_body(self):
        url = reverse("check_in_for_student:student_check_in_api")
        response = self.client.post(url, data="", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])

    def test_student_check_in_api_invalid_json(self):
        url = reverse("check_in_for_student:student_check_in_api")
        response = self.client.post(url, data="invalid-json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_student_check_in_api_missing_coordinates(self):
        url = reverse("check_in_for_student:student_check_in_api")
        response = self.client.post(url, data=json.dumps({"latitude": 21.0}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_student_check_in_api_success_authenticated(self):
        url = reverse("check_in_for_student:student_check_in_api")
        self.client.force_login(self.student)
        payload = {
            "latitude": 21.004900,
            "longitude": 105.843300,
            "accuracy": 8.0,
        }
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIsNotNone(data.get("record_id"))
        self.assertEqual(data["student_info"]["student_id"], "20269999")

        # Verify record exists in database
        record = CheckInRecord.objects.get(id=data["record_id"])
        self.assertEqual(record.user, self.student)
        self.assertTrue(record.is_valid)

    def test_student_check_in_api_failure_too_far(self):
        url = reverse("check_in_for_student:student_check_in_api")
        self.client.force_login(self.student)
        payload = {
            "latitude": 20.000000,
            "longitude": 105.000000,
            "accuracy": 10.0,
        }
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIsNotNone(data.get("record_id"))

        record = CheckInRecord.objects.get(id=data["record_id"])
        self.assertEqual(record.user, self.student)
        self.assertFalse(record.is_valid)

    def test_student_check_in_api_guest_with_mssv(self):
        url = reverse("check_in_for_student:student_check_in_api")
        payload = {
            "latitude": 21.004900,
            "longitude": 105.843300,
            "accuracy": 5.0,
            "student_id": "20211234",
            "student_name": "Tran Van B",
        }
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["student_info"]["student_id"], "20211234")

        record = CheckInRecord.objects.get(id=data["record_id"])
        self.assertIn("20211234", record.message)

    def test_no_database_release_urls(self):
        # Assert that check_in_for_student has NO reverse matches for export-excel or export-csv
        with self.assertRaises(NoReverseMatch):
            reverse("check_in_for_student:export_checkin_excel")
        with self.assertRaises(NoReverseMatch):
            reverse("check_in_for_student:export_checkin_csv")

    def test_student_my_status_api(self):
        url = reverse("check_in_for_student:student_my_status_api")
        # Unauthenticated: 401
        res = self.client.get(url)
        self.assertEqual(res.status_code, 401)

        # Authenticated with no check-in yet
        self.client.force_login(self.student)
        res2 = self.client.get(url)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2["authenticated"])
        self.assertFalse(data2["has_checkin"])

        # Authenticated with check-in
        CheckInRecord.objects.create(
            user=self.student,
            user_latitude=21.0049,
            user_longitude=105.8433,
            target_latitude=21.0049,
            target_longitude=105.8433,
            distance_meters=0.0,
            is_valid=True,
            message="Điểm danh thành công!",
        )
        res3 = self.client.get(url)
        self.assertEqual(res3.status_code, 200)
        data3 = res3.json()
        self.assertTrue(data3["has_checkin"])
        self.assertTrue(data3["latest_checkin"]["is_valid"])


class StudentAdminTests(TestCase):
    def test_student_admin_no_export_actions(self):
        rf = RequestFactory()
        request = rf.get("/admin/")
        request.user = User.objects.create_superuser(username="admin_test", password="password123")
        admin_instance = StudentCheckInRecordAdmin(StudentCheckInRecord, AdminSite())
        actions = admin_instance.get_actions(request)
        self.assertNotIn("export_to_excel", actions)
        self.assertFalse(admin_instance.has_add_permission(request))
        self.assertFalse(admin_instance.has_delete_permission(request))
