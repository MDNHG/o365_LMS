from django import template
from django.middleware.csrf import get_token
from django.urls import reverse

from .. import conf
from ..models import LessonProgress
from ..utils import can_manage_lesson, get_lesson_video_id

register = template.Library()


@register.inclusion_tag('trackvideo/video_player.html', takes_context=True)
def video_tracker(context, lesson):
    """
    Dùng trong lesson_detail.html:
        {% load trackvideo_tags %}
        {% if lesson.lesson_type == 'video' %}{% video_tracker lesson %}{% endif %}
    Mọi số được chuyển thành chuỗi để không bị định dạng theo locale (vd "12,5").
    """
    request = context['request']
    user = request.user
    is_student = user.is_authenticated and getattr(user, 'role', 'student') == 'student'

    progress = None
    if is_student:
        progress = LessonProgress.objects.filter(user=user, lesson=lesson).first()

    cfg = {
        'lesson_id': str(lesson.pk),
        'video_id': get_lesson_video_id(lesson),
        'mode': 'student' if is_student else 'preview',
        'can_sync': '1' if (not is_student and can_manage_lesson(user, lesson)) else '0',
        'duration': str(lesson.duration_seconds or 0),
        'threshold': str(lesson.min_watch_percent),
        'furthest': str(progress.furthest_second_reached if progress else 0),
        'percent': '%.2f' % (progress.completion_percentage if progress else 0.0),
        'completed': '1' if (progress and progress.is_completed) else '0',
        'heartbeat_url': reverse('trackvideo:heartbeat'),
        'sync_url': reverse('trackvideo:sync_duration'),
        'event_url': reverse('trackvideo:log_event'),
        'csrf': get_token(request),
        'heartbeat_seconds': str(conf.HEARTBEAT_SECONDS),
        'seek_tolerance': str(conf.SEEK_TOLERANCE_SECONDS),
        'idle_minutes': str(conf.IDLE_MINUTES),
        'countdown_seconds': str(conf.IDLE_COUNTDOWN_SECONDS),
        'seek_policy': getattr(lesson, 'allow_seek_policy', 'backward_only'),
        'allow_speed': '1' if getattr(lesson, 'allow_speed_change', True) else '0',
        'max_speed': str(getattr(lesson, 'max_playback_rate', 2.0)),
    }
    return {'cfg': cfg, 'lesson': lesson, 'is_student': is_student, 'progress': progress}
