import json

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.courses.models import Enrollment, Lesson

from . import services
from .utils import can_manage_lesson
from .models import LessonProgress

MAX_VIDEO_SECONDS = 4 * 60 * 60


def _error(code, status):
    return JsonResponse({'ok': False, 'error': code}, status=status)


def _json_body(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _serialize(result):
    p = result.progress
    return {
        'ok': True,
        'tracked': True,
        'accepted': result.accepted,
        'reason': result.reason,
        'furthest': p.furthest_second_reached if p else 0,
        'watched_seconds': p.unique_watched_seconds if p else 0,
        'completion_percentage': p.completion_percentage if p else 0.0,
        'is_completed': p.is_completed if p else False,
    }


@require_POST
def heartbeat(request):
    """
    POST JSON: {"lesson_id": 12, "interval": [120, 150], "current_time": 150,
                "tab_hidden": false, "reason": "heartbeat"}
    """
    user = request.user
    if not user.is_authenticated:
        return _error('unauthenticated', 401)

    data = _json_body(request)
    if data is None:
        return _error('bad_request', 400)
    try:
        lesson_id = int(data['lesson_id'])
        start, end = data['interval']
        start, end = int(start), int(end)
    except (KeyError, TypeError, ValueError):
        return _error('bad_request', 400)

    lesson = (
        Lesson.objects.select_related('course')
        .filter(pk=lesson_id, is_published=True, lesson_type='video')
        .first()
    )
    if lesson is None:
        return _error('lesson_not_found', 404)

    # Chỉ học viên mới được ghi tiến độ; giảng viên/admin xem thử thì bỏ qua.
    if getattr(user, 'role', 'student') != 'student':
        return JsonResponse({'ok': True, 'tracked': False})

    if not Enrollment.objects.filter(user=user, course_id=lesson.course_id).exists():
        return _error('not_enrolled', 403)

    result = services.record_heartbeat(
        user, lesson, start, end, tab_hidden=bool(data.get('tab_hidden'))
    )
    return JsonResponse(_serialize(result))


@require_POST
def sync_duration(request):
    """
    Giảng viên/admin xem thử bài học → trình phát báo thời lượng thật của video.
    POST JSON: {"lesson_id": 12, "duration": 213}
    """
    user = request.user
    if not user.is_authenticated:
        return _error('unauthenticated', 401)

    data = _json_body(request)
    if data is None:
        return _error('bad_request', 400)
    try:
        lesson_id = int(data['lesson_id'])
        duration = int(data['duration'])
    except (KeyError, TypeError, ValueError):
        return _error('bad_request', 400)
    if not 1 <= duration <= MAX_VIDEO_SECONDS:
        return _error('bad_duration', 400)

    lesson = Lesson.objects.select_related('course').filter(pk=lesson_id).first()
    if lesson is None:
        return _error('lesson_not_found', 404)
    if not can_manage_lesson(user, lesson):
        return _error('forbidden', 403)

    changed = lesson.duration_seconds != duration
    if changed:
        lesson.duration_seconds = duration
        lesson.save(update_fields=['duration_seconds'])
        services.recompute_lesson(lesson)
    return JsonResponse({'ok': True, 'duration': duration, 'changed': changed})


@require_POST
def log_event(request):
    """
    Ghi nhận một sự kiện tương tác video từ client (play, pause, stop, seek, tab visibility, inactivity).
    POST JSON: {"lesson_id": 12, "event_type": "pause", "video_time": 45.2, "extra_data": {...}}
    """
    user = request.user
    if not user.is_authenticated:
        return _error('unauthenticated', 401)

    data = _json_body(request)
    if data is None:
        return _error('bad_request', 400)

    try:
        lesson_id = int(data['lesson_id'])
        event_type = str(data['event_type'])
        video_time = float(data.get('video_time', 0.0))
        extra_data = data.get('extra_data', {})
    except (KeyError, TypeError, ValueError):
        return _error('bad_request', 400)

    lesson = (
        Lesson.objects.select_related('course')
        .filter(pk=lesson_id, is_published=True, lesson_type='video')
        .first()
    )
    if lesson is None:
        return _error('lesson_not_found', 404)

    # Chỉ học viên mới được ghi log tương tác
    if getattr(user, 'role', 'student') != 'student':
        return JsonResponse({'ok': True, 'tracked': False})

    if not Enrollment.objects.filter(user=user, course_id=lesson.course_id).exists():
        return _error('not_enrolled', 403)

    log_entry = services.record_event(
        user=user,
        lesson=lesson,
        event_type=event_type,
        video_time=video_time,
        extra_data=extra_data if isinstance(extra_data, dict) else {},
    )
    if log_entry is None:
        return _error('invalid_event_type', 400)

    progress = log_entry.progress
    return JsonResponse({
        'ok': True,
        'event_id': log_entry.pk,
        'event_type': log_entry.event_type,
        'inactivity_prompts': progress.inactivity_prompts_count,
        'inactivity_timeouts': progress.inactivity_timeouts_count,
        'suspicious_seeks': progress.suspicious_seeks_count,
        'assessment': progress.assessment_summary,
    })


def video_dashboard(request):
    """
    Trang tổng quan theo dõi tiến độ xem video:
    - Nếu là Giảng viên / Admin: Thống kê tiến độ video của toàn bộ sinh viên.
    - Nếu là Học viên: Xem các bài video mình đang học và % tiến độ đã hoàn thành.
    """
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    user = request.user
    is_teacher_or_admin = getattr(user, 'is_teacher_or_admin', False) or user.is_staff or getattr(user, 'role', '') in ('teacher', 'admin')

    video_lessons = Lesson.objects.filter(lesson_type='video', is_published=True).select_related('course').order_by('course__code', 'order')

    if is_teacher_or_admin:
        progress_records = LessonProgress.objects.select_related('user', 'lesson', 'lesson__course').order_by('-last_accessed_at')[:50]
        total_students_tracked = LessonProgress.objects.values('user').distinct().count()
        total_completed = LessonProgress.objects.filter(is_completed=True).count()
        context = {
            'is_teacher': True,
            'video_lessons': video_lessons,
            'progress_records': progress_records,
            'total_students_tracked': total_students_tracked,
            'total_completed': total_completed,
        }
    else:
        user_progresses = {
            p.lesson_id: p
            for p in LessonProgress.objects.filter(user=user)
        }
        lessons_data = []
        for l in video_lessons:
            p = user_progresses.get(l.id)
            lessons_data.append({
                'lesson': l,
                'progress': p,
                'percent': p.completion_percentage if p else 0.0,
                'is_completed': p.is_completed if p else False,
            })
        context = {
            'is_teacher': False,
            'lessons_data': lessons_data,
        }

    return render(request, 'trackvideo/dashboard.html', context)

