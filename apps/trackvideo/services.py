from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from . import conf
from .intervals import merge_intervals, percent_of, total_seconds
from .models import LessonProgress, WatchedInterval, VideoEventLog


@dataclass
class HeartbeatResult:
    accepted: bool
    reason: str  # ok | no_duration | invalid_interval | gap | rate_limited
    progress: Optional[LessonProgress] = None


def record_heartbeat(user, lesson, start, end, tab_hidden=False, now=None):
    """
    Ghi nhận một khoảng xem [start, end] (giây) của học viên.

    Server không tin hoàn toàn vào client:
      - Khoảng phải nằm trong thời lượng video.
      - Không được bắt đầu quá xa mốc xem xa nhất (chống tua vượt / gửi giả).
      - Độ dài bị giới hạn theo "quỹ giây xem" tích lũy theo thời gian thật.
    """
    now = now or timezone.now()
    duration = lesson.duration_seconds or 0
    if duration <= 0:
        return HeartbeatResult(False, 'no_duration')

    with transaction.atomic():
        progress, _ = LessonProgress.objects.select_for_update().get_or_create(
            user=user, lesson=lesson
        )

        start, end = int(start), int(end)
        if start < 0 or end <= start or start >= duration:
            return HeartbeatResult(False, 'invalid_interval', progress)
        end = min(end, duration)

        if start > progress.furthest_second_reached + conf.SERVER_GAP_TOLERANCE_SECONDS:
            return HeartbeatResult(False, 'gap', progress)

        # Quỹ giây xem: cộng theo thời gian thật kể từ heartbeat trước.
        if progress.last_heartbeat_at:
            elapsed = max(0.0, (now - progress.last_heartbeat_at).total_seconds())
            progress.watch_credit = min(
                conf.MAX_CREDIT, progress.watch_credit + elapsed * conf.MAX_PLAYBACK_RATE
            )
        allowed = int(progress.watch_credit + conf.RATE_SLACK_SECONDS)
        length = min(end - start, conf.MAX_INTERVAL_SECONDS, allowed)
        progress.last_heartbeat_at = now

        if length <= 0:
            progress.save(update_fields=['last_heartbeat_at', 'watch_credit', 'last_accessed_at'])
            return HeartbeatResult(False, 'rate_limited', progress)

        end = start + length
        progress.watch_credit = max(0.0, progress.watch_credit - length)
        if tab_hidden:
            progress.hidden_tab_seconds += length

        existing = list(progress.intervals.values_list('start_sec', 'end_sec'))
        merged = merge_intervals(existing + [(start, end)])
        if merged != sorted(existing):
            progress.intervals.all().delete()
            WatchedInterval.objects.bulk_create(
                [WatchedInterval(progress=progress, start_sec=s, end_sec=e) for s, e in merged]
            )

        progress.unique_watched_seconds = total_seconds(merged, duration)
        progress.completion_percentage = percent_of(progress.unique_watched_seconds, duration)
        progress.furthest_second_reached = max(progress.furthest_second_reached, end)
        if not progress.is_completed and progress.completion_percentage >= lesson.min_watch_percent:
            progress.is_completed = True
            progress.completed_at = now
        progress.save()
        return HeartbeatResult(True, 'ok', progress)


def recompute_lesson(lesson):
    """Tính lại % của mọi học viên sau khi thời lượng video của bài thay đổi (không thu hồi hoàn thành)."""
    duration = lesson.duration_seconds or 0
    if duration <= 0:
        return 0
    count = 0
    now = timezone.now()
    for p in LessonProgress.objects.filter(lesson=lesson).prefetch_related('intervals'):
        merged = merge_intervals([(i.start_sec, i.end_sec) for i in p.intervals.all()])
        p.unique_watched_seconds = total_seconds(merged, duration)
        p.completion_percentage = percent_of(p.unique_watched_seconds, duration)
        p.furthest_second_reached = min(p.furthest_second_reached, duration)
        if not p.is_completed and p.completion_percentage >= lesson.min_watch_percent:
            p.is_completed = True
            p.completed_at = now
        p.save()
        count += 1
    return count


def record_event(user, lesson, event_type, video_time=0.0, extra_data=None):
    """
    Ghi nhật ký một sự kiện tương tác video của học viên và cập nhật các chỉ số đánh giá.
    """
    valid_events = dict(VideoEventLog.EVENT_CHOICES)
    if event_type not in valid_events:
        return None

    extra = extra_data if isinstance(extra_data, dict) else {}
    try:
        video_time = max(0.0, float(video_time or 0.0))
    except (ValueError, TypeError):
        video_time = 0.0

    with transaction.atomic():
        progress, _ = LessonProgress.objects.select_for_update().get_or_create(
            user=user, lesson=lesson
        )

        update_fields = ['last_accessed_at']
        if event_type == 'inactivity_prompt':
            progress.inactivity_prompts_count += 1
            update_fields.append('inactivity_prompts_count')
        elif event_type == 'inactivity_timeout':
            progress.inactivity_timeouts_count += 1
            update_fields.append('inactivity_timeouts_count')
        elif event_type in ('seek_forward', 'seek_backward') and extra.get('suspicious'):
            progress.suspicious_seeks_count += 1
            update_fields.append('suspicious_seeks_count')

        progress.save(update_fields=update_fields)

        event_log = VideoEventLog.objects.create(
            progress=progress,
            event_type=event_type,
            video_time=video_time,
            extra_data=extra,
        )
        return event_log
