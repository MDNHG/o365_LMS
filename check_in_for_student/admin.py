from django.contrib import admin
from django.utils.html import format_html
from .models import StudentCheckInRecord


@admin.register(StudentCheckInRecord)
class StudentCheckInRecordAdmin(admin.ModelAdmin):
    """
    Read-only view for student check-in records in Django admin.
    Notice: No export-to-excel or CSV actions are registered here.
    """

    list_display = (
        "id",
        "display_user",
        "status_badge",
        "distance_meters",
        "allowed_radius_meters",
        "accuracy_meters",
        "created_at",
        "view_on_map",
    )

    list_filter = ("is_valid", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "message")

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
        "created_at",
    )

    # Disable adding or deleting from student admin portal
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Sinh viên", ordering="user__username")
    def display_user(self, obj):
        if not obj.user:
            return "Sinh viên vãng lai"
        full_name = obj.user.get_full_name()
        student_id = getattr(obj.user, "student_id", None)
        id_part = f"[{student_id}] " if student_id else ""
        return f"{id_part}{full_name or obj.user.username}"

    @admin.display(description="Trạng thái", ordering="is_valid")
    def status_badge(self, obj):
        if obj.is_valid:
            return format_html(
                '<span style="color: white; background-color: #16a34a; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
                "Hợp lệ",
            )
        return format_html(
            '<span style="color: white; background-color: #dc2626; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
            "Không hợp lệ",
        )

    @admin.display(description="Bản đồ")
    def view_on_map(self, obj):
        if obj.user_latitude is not None and obj.user_longitude is not None:
            url = f"https://www.google.com/maps?q={obj.user_latitude:.6f},{obj.user_longitude:.6f}"
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer" style="color: #0284c7; text-decoration: underline;">Xem vị trí</a>',
                url,
            )
        return "-"
