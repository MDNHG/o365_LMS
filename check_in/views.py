import json
import logging
from django.shortcuts import render
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .check_in_location import verify_check_in
from .models import CheckInRecord

logger = logging.getLogger(__name__)

# Tọa độ mốc cần điểm danh (mặc định ĐHBK Hà Nội, có thể cấu hình qua settings)
DEFAULT_TARGET_LATITUDE = getattr(settings, "CHECK_IN_TARGET_LATITUDE", 21.004900)
DEFAULT_TARGET_LONGITUDE = getattr(settings, "CHECK_IN_TARGET_LONGITUDE", 105.843300)
DEFAULT_MAX_RADIUS_METERS = getattr(settings, "CHECK_IN_MAX_RADIUS_METERS", 50.0)
TARGET_LOCATION_NAME = getattr(settings, "CHECK_IN_TARGET_NAME", "Đại học Bách Khoa Hà Nội")


def check_in_page_view(request: HttpRequest):
    context = {
        "target_latitude": DEFAULT_TARGET_LATITUDE,
        "target_longitude": DEFAULT_TARGET_LONGITUDE,
        "max_radius_meters": DEFAULT_MAX_RADIUS_METERS,
        "target_location_name": TARGET_LOCATION_NAME,
    }
    return render(request, "check_in/interface.html", context)


@csrf_exempt
@require_http_methods(["POST"])
def check_in_api_view(request: HttpRequest) -> JsonResponse:
    # 1. Parse JSON body safely
    try:
        body_text = request.body.decode("utf-8").strip()
        if not body_text:
            return JsonResponse(
                {"success": False, "error": "Dữ liệu yêu cầu không được để trống."},
                status=400,
            )
        payload = json.loads(body_text)
        if not isinstance(payload, dict):
            return JsonResponse(
                {"success": False, "error": "Dữ liệu JSON phải là object."},
                status=400,
            )
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return JsonResponse(
            {"success": False, "error": f"Định dạng JSON không hợp lệ: {str(e)}"},
            status=400,
        )

    # 2. Extract and validate coordinates
    try:
        lat_val = payload.get("latitude")
        lon_val = payload.get("longitude")
        if lat_val is None or lon_val is None:
            return JsonResponse(
                {"success": False, "error": "Thiếu thông tin 'latitude' hoặc 'longitude'."},
                status=400,
            )

        user_lat = float(lat_val)
        user_lon = float(lon_val)

        accuracy_raw = payload.get("accuracy")
        accuracy = float(accuracy_raw) if accuracy_raw is not None else None

        # Verify coordinates using check_in_location
        result = verify_check_in(
            user_latitude=user_lat,
            user_longitude=user_lon,
            target_latitude=DEFAULT_TARGET_LATITUDE,
            target_longitude=DEFAULT_TARGET_LONGITUDE,
            max_radius_meters=DEFAULT_MAX_RADIUS_METERS,
            accuracy_meters=accuracy,
            allow_accuracy_buffer=True,
        )
    except (ValueError, TypeError) as e:
        return JsonResponse(
            {"success": False, "error": f"Tọa độ không hợp lệ: {str(e)}"},
            status=400,
        )
    except Exception as e:
        logger.exception("Lỗi bất ngờ khi tính toán check-in")
        return JsonResponse(
            {"success": False, "error": f"Lỗi xử lý điểm danh: {str(e)}"},
            status=500,
        )

    # 3. Persist record into Database
    user = request.user if request.user.is_authenticated else None
    try:
        record = CheckInRecord.objects.create(
            user=user,
            user_latitude=result.user_coordinates.latitude,
            user_longitude=result.user_coordinates.longitude,
            accuracy_meters=accuracy,
            target_latitude=DEFAULT_TARGET_LATITUDE,
            target_longitude=DEFAULT_TARGET_LONGITUDE,
            distance_meters=result.distance_meters,
            allowed_radius_meters=DEFAULT_MAX_RADIUS_METERS,
            is_valid=result.is_valid,
            message=result.message,
        )
        record_id = record.id
    except Exception as e:
        logger.exception("Không thể lưu bản ghi điểm danh vào cơ sở dữ liệu")
        record_id = None

    response_data = result.to_dict()
    response_data["record_id"] = record_id

    # Return 200 on successful check-in, or 400 when outside allowed radius
    status_code = 200 if result.is_valid else 400
    return JsonResponse(response_data, status=status_code)
