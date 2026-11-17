from django.contrib import admin
from django.utils.html import format_html

from .models import LessonProgress, VideoEventLog, WatchedInterval


class WatchedIntervalInline(admin.TabularInline):
    model = WatchedInterval
    extra = 0
    can_delete = False
    readonly_fields = ('start_sec', 'end_sec')

    def has_add_permission(self, request, obj=None):
        return False


class VideoEventLogInline(admin.TabularInline):
    model = VideoEventLog
    extra = 0
    can_delete = False
    readonly_fields = ('created_at', 'event_type', 'video_time', 'extra_data')
    ordering = ('-created_at',)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'lesson', 'completion_percentage', 'is_completed',
        'display_assessment', 'inactivity_timeouts_count', 'suspicious_seeks_count',
        'furthest_second_reached', 'last_accessed_at',
    )
    list_filter = ('is_completed', 'lesson__course')
    search_fields = ('user__username', 'user__student_id', 'user__email', 'lesson__title')
    readonly_fields = (
        'user', 'lesson', 'furthest_second_reached', 'unique_watched_seconds',
        'completion_percentage', 'is_completed', 'completed_at', 'last_accessed_at',
        'last_heartbeat_at', 'watch_credit', 'hidden_tab_seconds',
        'inactivity_prompts_count', 'inactivity_timeouts_count', 'suspicious_seeks_count',
        'display_assessment',
    )
    inlines = [WatchedIntervalInline, VideoEventLogInline]

    @admin.display(description="Đánh giá chuyên cần")
    def display_assessment(self, obj):
        summary = obj.assessment_summary
        if summary['status'] == 'passed':
            return format_html(
                '<span style="color: #16a34a; font-weight: bold;">✔ Đạt (Điểm: {}/100)</span>',
                summary['score']
            )
        elif summary['status'] == 'flagged':
            return format_html(
                '<span style="color: #dc2626; font-weight: bold;">⚠ Nghi vấn (Điểm: {}/100)</span>',
                summary['score']
            )
        return format_html('<span style="color: #64748b;">Đang học ({}%)</span>', obj.completion_percentage)


@admin.register(VideoEventLog)
class VideoEventLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user_name', 'lesson_title', 'event_type', 'video_time', 'extra_data')
    list_filter = ('event_type', 'progress__lesson__course')
    search_fields = (
        'progress__user__username', 'progress__user__student_id',
        'progress__lesson__title'
    )
    readonly_fields = ('progress', 'event_type', 'video_time', 'extra_data', 'created_at')

    @admin.display(description="Học viên")
    def user_name(self, obj):
        return obj.progress.user.username

    @admin.display(description="Bài học")
    def lesson_title(self, obj):
        return obj.progress.lesson.title

    def has_add_permission(self, request):
        return False
