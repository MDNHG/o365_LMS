import json
import logging
import base64
from django.shortcuts import render
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.files.base import ContentFile
from .check_in_location import verify_check_in
from .models import CheckInRecord
from check_in.hust_data import get_current_active_location

logger = logging.getLogger(__name__)

# Tọa độ mốc cần điểm danh (mặc định ĐHBK Hà Nội, có thể cấu hình qua settings)
DEFAULT_TARGET_LATITUDE = getattr(settings, "CHECK_IN_TARGET_LATITUDE", 21.004900)
DEFAULT_TARGET_LONGITUDE = getattr(settings, "CHECK_IN_TARGET_LONGITUDE", 105.843300)
DEFAULT_MAX_RADIUS_METERS = getattr(settings, "CHECK_IN_MAX_RADIUS_METERS", 50.0)
TARGET_LOCATION_NAME = getattr(settings, "CHECK_IN_TARGET_NAME", "Đại học Bách Khoa Hà Nội")


def student_check_in_page_view(request: HttpRequest):
    """
    Giao diện điểm danh dành riêng cho Sinh viên — GPS + Camera.
    Tự động đồng bộ với địa điểm mốc do Giảng viên vừa chọn.
    """
    active_loc = get_current_active_location()
    target_lat = active_loc.latitude if active_loc else DEFAULT_TARGET_LATITUDE
    target_lon = active_loc.longitude if active_loc else DEFAULT_TARGET_LONGITUDE
    max_radius = active_loc.default_radius_meters if active_loc else DEFAULT_MAX_RADIUS_METERS
    target_name = active_loc.name if active_loc else TARGET_LOCATION_NAME

    user = request.user if request.user.is_authenticated else None
    student_info = {
        "is_authenticated": request.user.is_authenticated,
        "username": user.username if user else "",
        "full_name": user.get_full_name() if user else "",
        "student_id": getattr(user, "student_id", "") if user else "",
        "class_name": getattr(user, "class_name", "") if user else "",
    }

    context = {
        "target_latitude": target_lat,
        "target_longitude": target_lon,
        "max_radius_meters": max_radius,
        "target_location_name": target_name,
        "student_info": student_info,
    }
    return render(request, "check_in_for_student/interface.html", context)


@csrf_exempt
@require_http_methods(["POST"])
def student_check_in_api_view(request: HttpRequest) -> JsonResponse:
    """
    API tiếp nhận tọa độ GPS + ảnh camera từ trình duyệt sinh viên.
    Tự động xác thực với địa điểm mốc do Giảng viên kích hoạt.
    """
    active_loc = get_current_active_location()
    target_lat = active_loc.latitude if active_loc else DEFAULT_TARGET_LATITUDE
    target_lon = active_loc.longitude if active_loc else DEFAULT_TARGET_LONGITUDE
    max_radius = active_loc.default_radius_meters if active_loc else DEFAULT_MAX_RADIUS_METERS

    # 1. Parse JSON body
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
                {"success": False, "error": "Thiếu thông tin tọa độ 'latitude' hoặc 'longitude'."},
                status=400,
            )

        user_lat = float(lat_val)
        user_lon = float(lon_val)

        accuracy_raw = payload.get("accuracy")
        accuracy = None
        if accuracy_raw not in (None, ""):
            try:
                accuracy = float(accuracy_raw)
            except (ValueError, TypeError):
                accuracy = None

        # Verify coordinates using check_in_location
        result = verify_check_in(
            user_latitude=user_lat,
            user_longitude=user_lon,
            target_latitude=target_lat,
            target_longitude=target_lon,
            max_radius_meters=max_radius,
            accuracy_meters=accuracy,
            allow_accuracy_buffer=True,
        )
    except (ValueError, TypeError) as e:
        return JsonResponse(
            {"success": False, "error": f"Tọa độ không hợp lệ: {str(e)}"},
            status=400,
        )
    except Exception as e:
        logger.exception("Lỗi bất ngờ khi tính toán check-in sinh viên")
        return JsonResponse(
            {"success": False, "error": f"Lỗi xử lý điểm danh: {str(e)}"},
            status=500,
        )

    # 3. Process camera photo (base64 encoded)
    photo_file = None
    photo_b64 = payload.get("photo")
    if photo_b64 and isinstance(photo_b64, str):
        try:
            if "," in photo_b64:
                photo_b64 = photo_b64.split(",", 1)[1]
            photo_bytes = base64.b64decode(photo_b64)
            if len(photo_bytes) > 0:
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                username = request.user.username if request.user.is_authenticated else "guest"
                filename = f"student_{username}_{ts}.jpg"
                photo_file = ContentFile(photo_bytes, name=filename)
        except Exception as e:
            logger.warning(f"Không thể decode ảnh camera sinh viên: {e}")

    # 4. Lưu bản ghi vào cơ sở dữ liệu
    user = request.user if request.user.is_authenticated else None

    # Gắn thêm định danh sinh viên vào message nếu là khách nhập tay
    guest_mssv = str(payload.get("student_id", "")).strip()
    guest_name = str(payload.get("student_name", "")).strip()

    final_message = result.message
    if not user and (guest_mssv or guest_name):
        identifier = f"[{guest_mssv} - {guest_name}]" if (guest_mssv and guest_name) else f"[{guest_mssv or guest_name}]"
        final_message = f"{identifier} {result.message}"

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
            message=final_message,
            photo=photo_file,
        )
        record_id = record.id
    except Exception as e:
        logger.exception("Không thể lưu bản ghi điểm danh sinh viên vào database")
        record_id = None

    response_data = result.to_dict()
    response_data["record_id"] = record_id
    response_data["has_photo"] = photo_file is not None
    response_data["student_info"] = {
        "is_authenticated": user is not None,
        "student_id": getattr(user, "student_id", None) or guest_mssv or None,
        "full_name": user.get_full_name() if user else (guest_name or None),
    }

    # 200 khi hợp lệ, 400 khi ngoài bán kính
    status_code = 200 if result.is_valid else 400
    return JsonResponse(response_data, status=status_code)


@require_http_methods(["GET"])
def student_my_status_api_view(request: HttpRequest) -> JsonResponse:
    """
    API cho phép sinh viên đã đăng nhập tra cứu bản ghi điểm danh gần nhất CỦA CHÍNH MÌNH.
    """
    if not request.user.is_authenticated:
        return JsonResponse(
            {"authenticated": False, "message": "Bạn chưa đăng nhập."},
            status=401,
        )

    latest = (
        CheckInRecord.objects.filter(user=request.user)
        .order_by("-created_at")
        .first()
    )

    if not latest:
        return JsonResponse(
            {
                "authenticated": True,
                "has_checkin": False,
                "message": "Bạn chưa có bản ghi điểm danh nào.",
            }
        )

    return JsonResponse(
        {
            "authenticated": True,
            "has_checkin": True,
            "latest_checkin": {
                "id": latest.id,
                "is_valid": latest.is_valid,
                "distance_meters": round(latest.distance_meters, 1) if latest.distance_meters is not None else None,
                "created_at": latest.created_at.strftime("%H:%M:%S %d/%m/%Y") if latest.created_at else None,
                "message": latest.message,
                "has_photo": bool(latest.photo),
            },
        }
    )
