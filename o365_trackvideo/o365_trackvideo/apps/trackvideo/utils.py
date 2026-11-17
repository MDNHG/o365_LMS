import re
from urllib.parse import parse_qs, urlparse

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')
_YT_HOSTS = {
    'youtube.com', 'www.youtube.com', 'm.youtube.com',
    'music.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com',
}


def extract_youtube_id(value):
    """Rút ID video từ ID trần hoặc các dạng liên kết YouTube phổ biến. Trả về '' nếu không hợp lệ."""
    value = (value or '').strip()
    if not value:
        return ''
    if _ID_RE.match(value):
        return value
    try:
        url = urlparse(value if '//' in value else '//' + value)
    except ValueError:
        return ''
    host = (url.hostname or '').lower()
    candidate = ''
    if host == 'youtu.be':
        candidate = url.path.lstrip('/').split('/')[0]
    elif host in _YT_HOSTS:
        parts = [p for p in url.path.split('/') if p]
        if parts and parts[0] == 'watch':
            candidate = (parse_qs(url.query).get('v') or [''])[0]
        elif len(parts) >= 2 and parts[0] in ('embed', 'shorts', 'live', 'v'):
            candidate = parts[1]
    return candidate if _ID_RE.match(candidate) else ''


def get_lesson_video_id(lesson):
    """Lấy video ID từ Lesson (hỗ trợ cả `external_id` lẫn `raw_url`)."""
    # Lesson.save() đã tự rút external_id từ raw_url; chỉ tin external_id khi provider là YouTube.
    if getattr(lesson, 'provider', 'youtube') == 'youtube':
        vid = extract_youtube_id(getattr(lesson, 'external_id', '') or '')
        if vid:
            return vid
    return extract_youtube_id(getattr(lesson, 'raw_url', '') or '')


def can_manage_lesson(user, lesson):
    """Admin hoặc giảng viên được phân vào khóa học của bài này."""
    if not user.is_authenticated:
        return False
    role = getattr(user, 'role', None)
    if user.is_superuser or role == 'admin':
        return True
    return role == 'teacher' and lesson.course.instructors.filter(pk=user.pk).exists()
