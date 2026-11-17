import csv
import json
import logging
import base64
import re
import os
from io import BytesIO
from django.shortcuts import render
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.files.base import ContentFile
from apps.accounts.decorators import teacher_required
from .check_in_location import verify_check_in
from .models import CheckInRecord, CheckInLocation
from .hust_data import seed_hust_locations, get_current_active_location

logger = logging.getLogger(__name__)

# Tọa độ mốc cần điểm danh (mặc định ĐHBK Hà Nội, có thể cấu hình qua settings)
DEFAULT_TARGET_LATITUDE = getattr(settings, "CHECK_IN_TARGET_LATITUDE", 21.004900)
DEFAULT_TARGET_LONGITUDE = getattr(settings, "CHECK_IN_TARGET_LONGITUDE", 105.843300)
DEFAULT_MAX_RADIUS_METERS = getattr(settings, "CHECK_IN_MAX_RADIUS_METERS", 50.0)
TARGET_LOCATION_NAME = getattr(settings, "CHECK_IN_TARGET_NAME", "Đại học Bách Khoa Hà Nội")


def check_in_page_view(request: HttpRequest):
    """Giao diện điểm danh dành cho Giảng viên — có camera + GPS + chọn địa điểm từ hust_gps_coordinates.md."""
    seed_hust_locations()

    current_loc = get_current_active_location()
    target_lat = current_loc.latitude if current_loc else DEFAULT_TARGET_LATITUDE
    target_lon = current_loc.longitude if current_loc else DEFAULT_TARGET_LONGITUDE
    max_radius = current_loc.default_radius_meters if current_loc else DEFAULT_MAX_RADIUS_METERS
    target_name = current_loc.name if current_loc else TARGET_LOCATION_NAME

    locations = list(
        CheckInLocation.objects.filter(is_active=True).order_by("zone", "name").values(
            "id", "name", "zone", "latitude", "longitude", "default_radius_meters", "is_current"
        )
    )

    # Nhóm địa điểm theo khu vực để hiển thị optgroup trên dropdown
    locations_by_zone = {}
    for loc in locations:
        zone = loc.get("zone") or "Khác"
        if zone not in locations_by_zone:
            locations_by_zone[zone] = []
        locations_by_zone[zone].append(loc)

    teacher_info = {
        "is_authenticated": request.user.is_authenticated,
        "username": request.user.username if request.user.is_authenticated else "",
        "full_name": request.user.get_full_name() if request.user.is_authenticated else "",
        "email": getattr(request.user, "email", "") if request.user.is_authenticated else "",
        "role": (
            "Giảng viên phụ trách"
            if getattr(request.user, "is_teacher_or_admin", False)
            else ("Quản trị viên" if getattr(request.user, "is_staff", False) else "Giảng viên / Cán bộ")
        ),
    }

    context = {
        "target_latitude": target_lat,
        "target_longitude": target_lon,
        "max_radius_meters": max_radius,
        "target_location_name": target_name,
        "current_location_id": current_loc.id if current_loc else None,
        "locations": locations,
        "locations_by_zone": locations_by_zone,
        "locations_json": json.dumps(locations, ensure_ascii=False),
        "teacher_info": teacher_info,
        "is_teacher": (
            request.user.is_authenticated
            and getattr(request.user, "is_teacher_or_admin", False)
        ),
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

    # 2. Determine target location — default to active current location
    active_loc = get_current_active_location()
    target_lat = active_loc.latitude if active_loc else DEFAULT_TARGET_LATITUDE
    target_lon = active_loc.longitude if active_loc else DEFAULT_TARGET_LONGITUDE
    max_radius = active_loc.default_radius_meters if active_loc else DEFAULT_MAX_RADIUS_METERS
    location_obj = active_loc

    location_id = payload.get("location_id")
    if location_id:
        try:
            location_obj = CheckInLocation.objects.get(id=int(location_id), is_active=True)
            target_lat = location_obj.latitude
            target_lon = location_obj.longitude
            max_radius = location_obj.default_radius_meters
        except (CheckInLocation.DoesNotExist, ValueError, TypeError):
            pass

    # Allow explicit override from payload (for teacher custom location)
    if payload.get("target_latitude") not in (None, "") and payload.get("target_longitude") not in (None, ""):
        try:
            target_lat = float(payload["target_latitude"])
            target_lon = float(payload["target_longitude"])
        except (ValueError, TypeError):
            pass
    if payload.get("max_radius") not in (None, ""):
        try:
            max_radius = float(payload["max_radius"])
        except (ValueError, TypeError):
            pass

    # 3. Extract and validate user coordinates
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
        logger.exception("Lỗi bất ngờ khi tính toán check-in")
        return JsonResponse(
            {"success": False, "error": f"Lỗi xử lý điểm danh: {str(e)}"},
            status=500,
        )

    # 4. Process camera photo (base64 encoded)
    photo_file = None
    photo_b64 = payload.get("photo")
    if photo_b64 and isinstance(photo_b64, str):
        try:
            # Strip data URL prefix if present
            if "," in photo_b64:
                photo_b64 = photo_b64.split(",", 1)[1]
            photo_bytes = base64.b64decode(photo_b64)
            if len(photo_bytes) > 0:
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                username = request.user.username if request.user.is_authenticated else "guest"
                filename = f"checkin_{username}_{ts}.jpg"
                photo_file = ContentFile(photo_bytes, name=filename)
        except Exception as e:
            logger.warning(f"Không thể decode ảnh camera: {e}")

    # 5. Persist record into Database
    user = request.user if request.user.is_authenticated else None

    # Gắn thêm định danh giảng viên / người điểm danh vào message nếu là khách nhập tay
    guest_id = str(payload.get("teacher_id") or payload.get("student_id") or "").strip()
    guest_name = str(payload.get("teacher_name") or payload.get("student_name") or "").strip()

    final_message = result.message
    if not user and (guest_id or guest_name):
        identifier = f"[{guest_id} - {guest_name}]" if (guest_id and guest_name) else f"[{guest_id or guest_name}]"
        final_message = f"{identifier} {result.message}"

    try:
        record = CheckInRecord.objects.create(
            user=user,
            user_latitude=result.user_coordinates.latitude,
            user_longitude=result.user_coordinates.longitude,
            accuracy_meters=accuracy,
            target_latitude=target_lat,
            target_longitude=target_lon,
            location=location_obj,
            distance_meters=result.distance_meters,
            allowed_radius_meters=max_radius,
            is_valid=result.is_valid,
            message=final_message,
            photo=photo_file,
        )
        record_id = record.id
    except Exception as e:
        logger.exception("Không thể lưu bản ghi điểm danh vào cơ sở dữ liệu")
        record_id = None

    response_data = result.to_dict()
    response_data["record_id"] = record_id
    response_data["has_photo"] = photo_file is not None

    # Return 200 on successful check-in, or 400 when outside allowed radius
    status_code = 200 if result.is_valid else 400
    return JsonResponse(response_data, status=status_code)


# ─── Teacher Location Management APIs ────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
def list_locations_api(request: HttpRequest) -> JsonResponse:
    """Trả về danh sách địa điểm mốc điểm danh."""
    seed_hust_locations()
    locations = list(
        CheckInLocation.objects.filter(is_active=True).order_by("zone", "name").values(
            "id", "name", "zone", "latitude", "longitude", "default_radius_meters", "is_current"
        )
    )
    return JsonResponse({"locations": locations})


@csrf_exempt
@require_http_methods(["POST"])
def set_active_location_api(request: HttpRequest) -> JsonResponse:
    """
    Giảng viên kích hoạt một địa điểm làm mốc điểm danh hiện tại của hệ thống.
    Áp dụng đồng bộ cho cả Giảng viên và Sinh viên.
    """
    is_allowed = (
        settings.DEBUG
        or (
            request.user.is_authenticated
            and (
                getattr(request.user, "is_teacher_or_admin", False)
                or request.user.is_staff
                or request.user.is_superuser
            )
        )
    )
    if not is_allowed:
        return JsonResponse({"success": False, "error": "Bạn không có quyền đổi địa điểm."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "JSON không hợp lệ."}, status=400)

    location_id = payload.get("location_id")
    target_loc = None

    if location_id:
        try:
            target_loc = CheckInLocation.objects.get(id=int(location_id), is_active=True)
        except (CheckInLocation.DoesNotExist, ValueError):
            return JsonResponse({"success": False, "error": "Địa điểm không tồn tại."}, status=404)
    else:
        # Tọa độ trực tiếp / thủ công
        lat = payload.get("latitude")
        lon = payload.get("longitude")
        name = str(payload.get("name", "Vị trí mốc Giảng viên")).strip()
        radius = float(payload.get("radius", 50.0))
        zone = str(payload.get("zone", "Tùy chỉnh")).strip()

        if lat is not None and lon is not None:
            try:
                target_loc = CheckInLocation.objects.create(
                    name=name,
                    latitude=float(lat),
                    longitude=float(lon),
                    default_radius_meters=radius,
                    zone=zone,
                    is_active=True,
                    is_current=True,
                    created_by=request.user if request.user.is_authenticated else None,
                )
            except (ValueError, TypeError) as e:
                return JsonResponse({"success": False, "error": f"Tọa độ không hợp lệ: {e}"}, status=400)

    if not target_loc:
        return JsonResponse({"success": False, "error": "Thiếu thông tin địa điểm."}, status=400)

    # Đặt target_loc thành is_current=True, các địa điểm khác is_current=False
    CheckInLocation.objects.filter(is_current=True).exclude(id=target_loc.id).update(is_current=False)
    target_loc.is_current = True
    target_loc.save(update_fields=["is_current"])

    return JsonResponse({
        "success": True,
        "message": f"Đã chuyển mốc điểm danh toàn hệ thống sang: {target_loc.name}",
        "location": {
            "id": target_loc.id,
            "name": target_loc.name,
            "zone": target_loc.zone,
            "latitude": target_loc.latitude,
            "longitude": target_loc.longitude,
            "default_radius_meters": target_loc.default_radius_meters,
            "is_current": True,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
def update_location_api(request: HttpRequest) -> JsonResponse:
    """
    Giảng viên tạo / cập nhật địa điểm điểm danh.
    Trả về location object đã lưu.
    """
    is_allowed = (
        settings.DEBUG
        or (
            request.user.is_authenticated
            and (
                getattr(request.user, "is_teacher_or_admin", False)
                or request.user.is_staff
                or request.user.is_superuser
            )
        )
    )
    if not is_allowed:
        return JsonResponse({"success": False, "error": "Bạn không có quyền thay đổi địa điểm."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "JSON không hợp lệ."}, status=400)

    loc_id = payload.get("id")
    name = str(payload.get("name", "")).strip()
    lat = payload.get("latitude")
    lon = payload.get("longitude")
    radius = payload.get("radius", 50.0)
    zone = str(payload.get("zone", "")).strip()

    if not name or lat is None or lon is None:
        return JsonResponse({"success": False, "error": "Thiếu tên, vĩ độ hoặc kinh độ."}, status=400)

    try:
        lat = float(lat)
        lon = float(lon)
        radius = float(radius)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Tọa độ / bán kính không hợp lệ."}, status=400)

    if loc_id:
        try:
            location = CheckInLocation.objects.get(id=int(loc_id))
            location.name = name
            location.latitude = lat
            location.longitude = lon
            location.default_radius_meters = radius
            location.zone = zone
            location.save()
        except CheckInLocation.DoesNotExist:
            return JsonResponse({"success": False, "error": "Địa điểm không tồn tại."}, status=404)
    else:
        location = CheckInLocation.objects.create(
            name=name,
            latitude=lat,
            longitude=lon,
            default_radius_meters=radius,
            zone=zone,
            created_by=request.user,
        )

    return JsonResponse({
        "success": True,
        "location": {
            "id": location.id,
            "name": location.name,
            "zone": location.zone,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "default_radius_meters": location.default_radius_meters,
        },
    })


# ─── Excel / CSV Export (unchanged logic, adapted to new model) ──────────────

def generate_excel_response(records, filename: str = "danh_sach_diem_danh.xlsx") -> HttpResponse:
    """
    Tạo file Excel (.xlsx) định dạng chuẩn, có tiêu đề tô màu, border, tự co giãn cột.
    Cột ảnh (cột L) sẽ nhúng trực tiếp hình ảnh chụp người điểm danh từ camera thiết bị.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.drawing.image import Image as OpenpyxlImage
    from PIL import Image as PILImage

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lịch sử Điểm danh"

    headers = [
        "STT",
        "ID",
        "Tài khoản",
        "Họ và Tên",
        "Thời gian điểm danh",
        "Vĩ độ (Lat)",
        "Kinh độ (Lon)",
        "Sai số GPS (m)",
        "Khoảng cách (m)",
        "Bán kính cho phép (m)",
        "Trạng thái",
        "Ảnh người điểm danh",
        "Chi tiết thông báo",
    ]

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    ws.append(headers)
    ws.row_dimensions[1].height = 28

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    valid_font = Font(name="Segoe UI", size=10, bold=True, color="166534")
    valid_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    invalid_font = Font(name="Segoe UI", size=10, bold=True, color="991B1B")
    invalid_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    default_font = Font(name="Segoe UI", size=10)

    # Giữ danh sách buffer để openpyxl không bị đóng stream khi wb.save()
    image_buffers = []

    for idx, r in enumerate(records, start=1):
        if r.user:
            username = r.user.username
            full_name = r.user.get_full_name() or r.user.username
        else:
            m = re.match(r"^\[(.*?)\]", r.message or "")
            if m:
                parts = m.group(1).split(" - ", 1)
                username = parts[0]
                full_name = parts[1] if len(parts) > 1 else parts[0]
            else:
                username = "Khách (Chưa đăng nhập)"
                full_name = "N/A"

        thoi_gian = getattr(r, "created_at", None) or getattr(r, "timestamp", None)
        thoi_gian_str = thoi_gian.strftime("%Y-%m-%d %H:%M:%S") if thoi_gian else "N/A"

        accuracy_val = round(r.accuracy_meters, 2) if r.accuracy_meters is not None else ""
        distance_val = round(r.distance_meters, 2) if r.distance_meters is not None else ""
        status_text = "Hợp lệ" if r.is_valid else "Không hợp lệ"

        row_num = idx + 1
        photo_label = "Không có ảnh"
        openpyxl_img = None
        target_row_height = 24

        # Xử lý nhúng ảnh thực tế của người điểm danh
        if bool(r.photo) and r.photo.name:
            try:
                photo_path = getattr(r.photo, "path", None)
                pil_source = None
                if photo_path and os.path.exists(photo_path):
                    pil_source = photo_path
                elif hasattr(r.photo, "file"):
                    r.photo.file.seek(0)
                    pil_source = r.photo.file

                if pil_source:
                    with PILImage.open(pil_source) as pil_img:
                        pil_img = pil_img.copy()
                        # Thu nhỏ thumbnail vừa vặn ô tính mà vẫn sắc nét
                        pil_img.thumbnail((105, 80), PILImage.Resampling.LANCZOS)
                        buf = BytesIO()
                        if pil_img.mode in ("RGBA", "P"):
                            pil_img.save(buf, format="PNG")
                        else:
                            pil_img.save(buf, format="JPEG", quality=85)
                        buf.seek(0)
                        openpyxl_img = OpenpyxlImage(buf)
                        openpyxl_img.width = pil_img.width
                        openpyxl_img.height = pil_img.height
                        image_buffers.append(buf)
                        photo_label = ""
                        target_row_height = max(65, int(pil_img.height * 0.78) + 8)
            except Exception as exc:
                logger.warning("Không thể xử lý ảnh bản ghi %s: %s", r.id, exc)
                photo_label = "Lỗi đọc ảnh"

        row_data = [
            idx,
            r.id,
            username,
            full_name,
            thoi_gian_str,
            r.user_latitude,
            r.user_longitude,
            accuracy_val,
            distance_val,
            r.allowed_radius_meters,
            status_text,
            photo_label,
            r.message,
        ]
        ws.append(row_data)
        ws.row_dimensions[row_num].height = target_row_height

        # Nếu có ảnh thành công, nhúng vào cột L của dòng này
        if openpyxl_img:
            ws.add_image(openpyxl_img, f"L{row_num}")

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.font = default_font
            cell.border = thin_border
            if col_num in [1, 2, 5, 8, 9, 10, 11, 12]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(vertical="center")

            if col_num == 11:
                if r.is_valid:
                    cell.font = valid_font
                    cell.fill = valid_fill
                else:
                    cell.font = invalid_font
                    cell.fill = invalid_fill

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        if col_letter == "L":
            # Đặt độ rộng cố định cho cột Ảnh để vừa thumbnail 105px
            ws.column_dimensions["L"].width = 18
            continue
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@require_http_methods(["GET"])
def export_checkin_excel(request: HttpRequest) -> HttpResponse:
    records = CheckInRecord.objects.select_related("user").all().order_by("-id")
    return generate_excel_response(records, filename="danh_sach_diem_danh.xlsx")


@require_http_methods(["GET"])
def export_checkin_csv(request: HttpRequest) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="danh_sach_diem_danh.csv"'

    writer = csv.writer(response)

    writer.writerow([
        "ID",
        "Tài khoản",
        "Họ và Tên",
        "Thời gian điểm danh",
        "Vĩ độ User (Lat)",
        "Kinh độ User (Lon)",
        "Sai số GPS (m)",
        "Khoảng cách tới mốc (m)",
        "Bán kính cho phép (m)",
        "Trạng thái",
        "Ảnh minh chứng",
        "Chi tiết thông báo",
    ])

    records = CheckInRecord.objects.select_related("user").all().order_by("-id")

    for r in records:
        if r.user:
            username = r.user.username
            full_name = r.user.get_full_name() or r.user.username
        else:
            m = re.match(r"^\[(.*?)\]", r.message or "")
            if m:
                parts = m.group(1).split(" - ", 1)
                username = parts[0]
                full_name = parts[1] if len(parts) > 1 else parts[0]
            else:
                username = "Khách (Chưa đăng nhập)"
                full_name = "N/A"

        thoi_gian = getattr(r, "created_at", None) or getattr(r, "timestamp", None)
        thoi_gian_str = thoi_gian.strftime("%Y-%m-%d %H:%M:%S") if thoi_gian else "N/A"

        has_photo_text = "Có ảnh" if (bool(r.photo) and r.photo.name) else "Không có ảnh"

        writer.writerow([
            r.id,
            username,
            full_name,
            thoi_gian_str,
            r.user_latitude,
            r.user_longitude,
            round(r.accuracy_meters, 2) if r.accuracy_meters is not None else "",
            round(r.distance_meters, 2) if r.distance_meters is not None else "",
            r.allowed_radius_meters,
            "Hợp lệ" if r.is_valid else "Không hợp lệ",
            has_photo_text,
            r.message,
        ])

    return response


@csrf_exempt
@require_http_methods(["POST"])
def clear_checkin_history_api(request: HttpRequest) -> JsonResponse:
    """
    Xóa lịch sử điểm danh. Chỉ dành cho Giảng viên hoặc Quản trị viên (Admin).
    Hỗ trợ xóa toàn bộ hoặc danh sách ID cụ thể truyền qua JSON payload: {"record_ids": [1, 2, ...]}.
    Đồng thời tự động xóa các file ảnh chụp minh chứng liên quan trên ổ cứng để giải phóng dung lượng.
    """
    is_allowed = (
        settings.DEBUG
        or (
            request.user.is_authenticated
            and (
                getattr(request.user, "is_teacher_or_admin", False)
                or request.user.is_staff
                or request.user.is_superuser
            )
        )
    )
    if not is_allowed:
        return JsonResponse(
            {"success": False, "error": "Chỉ Quản trị viên hoặc Giảng viên mới có quyền xóa lịch sử điểm danh."},
            status=403,
        )

    try:
        payload = {}
        if request.body:
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        record_ids = payload.get("record_ids") if isinstance(payload, dict) else None
        if record_ids and isinstance(record_ids, list):
            records_to_delete = CheckInRecord.objects.filter(id__in=record_ids)
        else:
            records_to_delete = CheckInRecord.objects.all()

        deleted_count = records_to_delete.count()

        # Dọn dẹp các tệp ảnh thực tế trên ổ cứng
        for rec in records_to_delete:
            if bool(rec.photo) and rec.photo.name:
                try:
                    photo_path = getattr(rec.photo, "path", None)
                    if photo_path and os.path.exists(photo_path):
                        os.remove(photo_path)
                except Exception as e:
                    logger.warning("Không thể xóa file ảnh %s: %s", rec.photo.name, e)

        records_to_delete.delete()

        return JsonResponse({
            "success": True,
            "deleted_count": deleted_count,
            "message": f"Đã xóa thành công {deleted_count} bản ghi lịch sử điểm danh.",
        })
    except Exception as exc:
        logger.exception("Lỗi khi xóa lịch sử điểm danh: %s", exc)
        return JsonResponse({"success": False, "error": f"Lỗi máy chủ khi xóa lịch sử: {str(exc)}"}, status=500)
