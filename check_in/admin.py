import os
from django.contrib import admin
from django.utils.html import format_html
from .models import CheckInRecord, CheckInLocation


@admin.register(CheckInLocation)
class CheckInLocationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "zone", "latitude", "longitude", "default_radius_meters", "is_active", "created_by", "created_at")
    list_filter = ("is_active", "zone")
    search_fields = ("name", "zone")
    list_editable = ("is_active", "default_radius_meters")
    list_per_page = 50


@admin.register(CheckInRecord)
class CheckInRecordAdmin(admin.ModelAdmin):
    # Các cột hiển thị trên danh sách bảng admin
    list_display = (
        "id",
        "display_user",
        "status_badge",
        "distance_meters",
        "allowed_radius_meters",
        "accuracy_meters",
        "has_photo_icon",
        "created_at",
        "view_on_map",
    )

    # Bộ lọc nhanh ở thanh bên phải
    list_filter = ("is_valid", "created_at", "location")

    # Thanh tìm kiếm theo tên tài khoản hoặc thông báo
    search_fields = ("user__username", "user__email", "message")

    # Các trường chỉ đọc (tránh việc sửa đổi dữ liệu log đã ghi)
    readonly_fields = (
        "user",
        "user_latitude",
        "user_longitude",
        "accuracy_meters",
        "target_latitude",
        "target_longitude",
        "distance_meters",
        "allowed_radius_meters",
        "is_valid",
        "message",
        "photo",
        "location",
        "created_at",
    )

    # Số bản ghi trên mỗi trang
    list_per_page = 25

    actions = ["export_to_excel", "delete_selected_records"]

    @admin.action(description="📊 Xuất danh sách đã chọn ra file Excel (.xlsx)")
    def export_to_excel(self, request, queryset):
        from .views import generate_excel_response
        return generate_excel_response(queryset, filename="danh_sach_diem_danh_admin.xlsx")

    @admin.action(description="🗑️ Xóa các bản ghi điểm danh đã chọn (kèm dọn dẹp file ảnh)")
    def delete_selected_records(self, request, queryset):
        count = queryset.count()
        for obj in queryset:
            if bool(obj.photo) and obj.photo.name:
                try:
                    if hasattr(obj.photo, "path") and os.path.exists(obj.photo.path):
                        os.remove(obj.photo.path)
                except Exception:
                    pass
        queryset.delete()
        self.message_user(
            request,
            f"Đã xóa thành công {count} bản ghi điểm danh và các file ảnh liên quan."
        )

    # Phân nhóm giao diện khi xem chi tiết 1 bản ghi
    fieldsets = (
        (
            "Thông tin người dùng & Kết quả",
            {
                "fields": (
                    "user",
                    "is_valid",
                    "message",
                    "distance_meters",
                    "allowed_radius_meters",
                    "location",
                    "created_at",
                )
            },
        ),
        (
            "Dữ liệu Tọa độ & Độ chính xác",
            {
                "fields": (
                    "user_latitude",
                    "user_longitude",
                    "accuracy_meters",
                    "target_latitude",
                    "target_longitude",
                )
            },
        ),
        (
            "Ảnh minh chứng",
            {
                "fields": ("photo",),
            },
        ),
    )

    # Hiển thị tên người dùng hoặc "Khách ẩn danh"
    @admin.display(description="Người điểm danh", ordering="user__username")
    def display_user(self, obj):
        if not obj.user:
            return "Khách ẩn danh"
        full_name = obj.user.get_full_name()
        return f"{full_name} ({obj.user.username})" if full_name else obj.user.username

    # Hiển thị icon/màu sắc trực quan cho trạng thái
    @admin.display(description="Trạng thái", ordering="is_valid")
    def status_badge(self, obj):
        if obj.is_valid:
            return format_html(
                '<span style="color: white; background-color: #28a745; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
                "Hợp lệ",
            )
        return format_html(
            '<span style="color: white; background-color: #dc3545; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
            "Không hợp lệ",
        )

    # Hiển thị icon ảnh
    @admin.display(description="Ảnh", boolean=True)
    def has_photo_icon(self, obj):
        return bool(obj.photo)

    # Tạo đường link xem vị trí người dùng trên Google Maps
    @admin.display(description="Bản đồ")
    def view_on_map(self, obj):
        if obj.user_latitude is None or obj.user_longitude is None:
            return "-"
        url = f"https://www.google.com/maps?q={obj.user_latitude:.6f},{obj.user_longitude:.6f}"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer" style="color: #007bff; text-decoration: underline;">{}</a>',
            url,
            "Xem vị trí",
        )
