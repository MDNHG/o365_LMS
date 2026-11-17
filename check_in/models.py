from django.db import models
from django.conf import settings


class CheckInLocation(models.Model):
    """
    Địa điểm mốc điểm danh — giảng viên có thể chọn / thay đổi.
    Các vị trí mặc định được nạp từ hust_gps_coordinates.md.
    """
    name = models.CharField(max_length=120, verbose_name="Tên địa điểm")
    zone = models.CharField(
        max_length=60, blank=True, default="",
        verbose_name="Khu vực (VD: C zone, D zone)",
    )
    latitude = models.FloatField(verbose_name="Vĩ độ")
    longitude = models.FloatField(verbose_name="Kinh độ")
    default_radius_meters = models.FloatField(
        default=50.0,
        verbose_name="Bán kính mặc định (m)",
    )
    is_active = models.BooleanField(default=True, verbose_name="Đang sử dụng")
    is_current = models.BooleanField(default=False, verbose_name="Đang là mốc điểm danh hiện tại")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="created_locations",
        verbose_name="Người tạo",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Địa điểm điểm danh"
        verbose_name_plural = "Danh sách địa điểm điểm danh"
        ordering = ["zone", "name"]

    def __str__(self):
        return f"{self.name} ({self.latitude:.5f}, {self.longitude:.5f})"


class CheckInRecord(models.Model):
    # Người dùng (nếu có đăng nhập, để null nếu check-in khách)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Người điểm danh",
    )
    # Tọa độ gửi từ thiết bị
    user_latitude = models.FloatField(verbose_name="Vĩ độ người dùng")
    user_longitude = models.FloatField(verbose_name="Kinh độ người dùng")
    accuracy_meters = models.FloatField(
        null=True, blank=True, verbose_name="Độ chính xác GPS (m)"
    )

    # Tọa độ sự kiện/phòng học mốc
    target_latitude = models.FloatField(verbose_name="Vĩ độ mục tiêu")
    target_longitude = models.FloatField(verbose_name="Kinh độ mục tiêu")

    # Liên kết với địa điểm đã chọn (nếu có)
    location = models.ForeignKey(
        CheckInLocation,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Địa điểm mốc",
    )

    # Kết quả tính toán
    distance_meters = models.FloatField(verbose_name="Khoảng cách thực tế (m)")
    allowed_radius_meters = models.FloatField(
        default=50.0, verbose_name="Bán kính cho phép (m)"
    )
    is_valid = models.BooleanField(
        default=False, verbose_name="Điểm danh hợp lệ"
    )
    message = models.CharField(
        max_length=255, blank=True, verbose_name="Thông báo kết quả"
    )

    # Ảnh chụp camera minh chứng
    photo = models.ImageField(
        upload_to="check_in_photos/%Y/%m/%d/",
        null=True, blank=True,
        verbose_name="Ảnh minh chứng",
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Thời gian check-in"
    )

    class Meta:
        verbose_name = "Bản ghi điểm danh"
        verbose_name_plural = "Danh sách bản ghi điểm danh"
        ordering = ["-created_at"]

    def __str__(self):
        status = "Thành công" if self.is_valid else "Thất bại"
        user_name = self.user.username if self.user else "Ẩn danh"
        dist = f"{self.distance_meters:.1f}m" if self.distance_meters is not None else "N/A"
        time_str = self.created_at.strftime('%H:%M %d/%m/%Y') if self.created_at else "Chưa lưu"
        return f"[{status}] {user_name} - {dist} ({time_str})"
