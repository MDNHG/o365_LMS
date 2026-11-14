import csv
import json
import logging
from django.shortcuts import render
from django.http import HttpRequest, JsonResponse, HttpResponse
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


def generate_excel_response(records, filename: str = "danh_sach_diem_danh.xlsx") -> HttpResponse:
    """
    Tạo file Excel (.xlsx) định dạng chuẩn, có tiêu đề tô màu, border, tự co giãn cột.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

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

    for idx, r in enumerate(records, start=1):
        if r.user:
            username = r.user.username
            full_name = r.user.get_full_name() or r.user.username
        else:
            username = "Khách (Chưa đăng nhập)"
            full_name = "N/A"

        thoi_gian = getattr(r, "created_at", None) or getattr(r, "timestamp", None)
        thoi_gian_str = thoi_gian.strftime("%Y-%m-%d %H:%M:%S") if thoi_gian else "N/A"

        accuracy_val = round(r.accuracy_meters, 2) if r.accuracy_meters is not None else ""
        distance_val = round(r.distance_meters, 2) if r.distance_meters is not None else ""
        status_text = "Hợp lệ" if r.is_valid else "Không hợp lệ"

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
            r.message,
        ]
        ws.append(row_data)
        row_num = idx + 1
        ws.row_dimensions[row_num].height = 22

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.font = default_font
            cell.border = thin_border
            if col_num in [1, 2, 5, 8, 9, 10, 11]:
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
        max_len = 0
        col_letter = get_column_letter(col[0].column)
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
    """
    Xuất toàn bộ lịch sử điểm danh từ bảng CheckInRecord ra file Excel (.xlsx).
    """
    records = CheckInRecord.objects.select_related("user").all().order_by("-id")
    return generate_excel_response(records, filename="danh_sach_diem_danh.xlsx")


@require_http_methods(["GET"])
def export_checkin_csv(request: HttpRequest) -> HttpResponse:
    """
    Xuất toàn bộ lịch sử điểm danh từ bảng CheckInRecord ra file CSV (tương thích Excel).
    """
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
        "Chi tiết thông báo",
    ])

    records = CheckInRecord.objects.select_related("user").all().order_by("-id")

    for r in records:
        if r.user:
            username = r.user.username
            full_name = r.user.get_full_name() or r.user.username
        else:
            username = "Khách (Chưa đăng nhập)"
            full_name = "N/A"

        thoi_gian = getattr(r, "created_at", None) or getattr(r, "timestamp", None)
        thoi_gian_str = thoi_gian.strftime("%Y-%m-%d %H:%M:%S") if thoi_gian else "N/A"

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
            r.message,
        ])

    return response
