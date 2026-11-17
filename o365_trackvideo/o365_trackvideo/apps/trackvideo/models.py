from django.conf import settings
from django.db import models


class LessonProgress(models.Model):
    """Tiến độ xem video của một học viên trong một bài học."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='progresses'
    )
    lesson = models.ForeignKey(
        'courses.Lesson', on_delete=models.CASCADE, related_name='user_progresses'
    )

    furthest_second_reached = models.PositiveIntegerField(
        default=0, help_text='Mốc thời gian xem xa nhất (dùng để chặn tua vượt)'
    )
    unique_watched_seconds = models.PositiveIntegerField(
        default=0, help_text='Tổng số giây xem thực tế, không tính trùng'
    )
    completion_percentage = models.FloatField(default=0.0)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(auto_now=True)

    # --- Phục vụ chống gian lận / kiểm tra ---
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    watch_credit = models.FloatField(
        default=120.0, help_text='Quỹ giây xem còn lại (giới hạn tốc độ báo cáo)'
    )
    hidden_tab_seconds = models.PositiveIntegerField(
        default=0, help_text='Số giây đã báo cáo khi tab trình duyệt bị ẩn'
    )
    inactivity_prompts_count = models.PositiveIntegerField(
        default=0, help_text='Số lần xuất hiện popup Bạn có còn đang xem không?'
    )
    inactivity_timeouts_count = models.PositiveIntegerField(
        default=0, help_text='Số lần hết thời gian chờ không phản hồi (treo máy)'
    )
    suspicious_seeks_count = models.PositiveIntegerField(
        default=0, help_text='Số lần cố tình tua vượt hoặc vi phạm quy định'
    )

    class Meta:
        unique_together = ('user', 'lesson')
        verbose_name = 'Tiến độ bài học'
        verbose_name_plural = 'Tiến độ bài học'

    def __str__(self):
        return f'{self.user} - {self.lesson} ({self.completion_percentage:.0f}%)'

    @property
    def is_flagged(self):
        """Cảnh báo nghi vấn nếu treo máy >= 2 lần hoặc thời gian ẩn tab quá 35% tổng xem."""
        if self.inactivity_timeouts_count >= 2:
            return True
        if self.unique_watched_seconds > 30 and (self.hidden_tab_seconds / self.unique_watched_seconds) > 0.35:
            return True
        return False

    @property
    def integrity_score(self):
        """Điểm tin cậy (thang 100): Giảm khi bị timeout không phản hồi, tua phạm quy, ẩn tab."""
        score = 100.0
        score -= self.inactivity_timeouts_count * 20.0
        score -= self.suspicious_seeks_count * 5.0
        if self.unique_watched_seconds > 0:
            hidden_ratio = min(1.0, self.hidden_tab_seconds / self.unique_watched_seconds)
            score -= hidden_ratio * 30.0
        return max(0.0, round(score, 1))

    @property
    def assessment_summary(self):
        """Đánh giá tổng hợp độ hoàn thiện và tính chuyên cần."""
        if not self.is_completed:
            return {
                'status': 'in_progress',
                'label': 'Chưa hoàn thành',
                'passed': False,
                'score': self.integrity_score,
            }
        if self.is_flagged or self.integrity_score < 60.0:
            return {
                'status': 'flagged',
                'label': 'Cần kiểm tra nghi vấn (Treo máy / Ẩn tab nhiều)',
                'passed': False,
                'score': self.integrity_score,
            }
        return {
            'status': 'passed',
            'label': 'Đạt chuẩn hoàn thành trung thực',
            'passed': True,
            'score': self.integrity_score,
        }


class WatchedInterval(models.Model):
    """Các khoảng xem hợp lệ [start_sec, end_sec], luôn được gom gọn sau mỗi heartbeat."""

    progress = models.ForeignKey(
        LessonProgress, on_delete=models.CASCADE, related_name='intervals'
    )
    start_sec = models.PositiveIntegerField()
    end_sec = models.PositiveIntegerField()

    class Meta:
        ordering = ['start_sec']
        verbose_name = 'Khoảng đã xem'
        verbose_name_plural = 'Các khoảng đã xem'

    def __str__(self):
        return f'{self.start_sec}-{self.end_sec}s'


class VideoEventLog(models.Model):
    """Nhật ký chi tiết các sự kiện tương tác của học viên đối với video bài học."""

    EVENT_CHOICES = (
        ('play', 'Bắt đầu / Tiếp tục phát'),
        ('pause', 'Tạm dừng'),
        ('stop', 'Kết thúc video'),
        ('seek_forward', 'Tua tiến'),
        ('seek_backward', 'Tua lùi'),
        ('speed_change', 'Đổi tốc độ phát'),
        ('tab_hidden', 'Ẩn tab trình duyệt'),
        ('tab_visible', 'Quay lại tab'),
        ('inactivity_prompt', 'Hiện popup Bạn có còn đang xem?'),
        ('inactivity_confirmed', 'Xác nhận Tôi vẫn đang xem'),
        ('inactivity_timeout', 'Treo máy (hết thời gian chờ)'),
    )

    progress = models.ForeignKey(
        LessonProgress, on_delete=models.CASCADE, related_name='event_logs'
    )
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES, verbose_name="Loại sự kiện")
    video_time = models.FloatField(default=0.0, verbose_name="Thời điểm trên video (giây)")
    extra_data = models.JSONField(default=dict, blank=True, verbose_name="Dữ liệu chi tiết")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian ghi nhận")

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Nhật ký sự kiện video'
        verbose_name_plural = 'Nhật ký sự kiện video'
        indexes = [
            models.Index(fields=['progress', 'event_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'[{self.created_at.strftime("%H:%M:%S")}] {self.progress.user} - {self.get_event_type_display()} ({self.video_time:.1f}s)'
