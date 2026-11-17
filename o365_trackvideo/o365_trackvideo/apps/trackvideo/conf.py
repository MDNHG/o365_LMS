"""
Cấu hình của app tracking. Có thể ghi đè trong settings.py bằng các biến TRACKVIDEO_*.
"""
from django.conf import settings


def _get(name, default):
    return getattr(settings, 'TRACKVIDEO_' + name, default)


# --- Phía trình duyệt (đưa xuống tracker.js qua data-attribute) ---
HEARTBEAT_SECONDS = _get('HEARTBEAT_SECONDS', 30)          # chu kỳ gửi heartbeat khi đang phát
SEEK_TOLERANCE_SECONDS = _get('SEEK_TOLERANCE_SECONDS', 3)  # cho phép lệch tối đa so với mốc xa nhất
IDLE_MINUTES = _get('IDLE_MINUTES', 15)                     # không tương tác bao lâu thì hỏi "còn xem không"
IDLE_COUNTDOWN_SECONDS = _get('IDLE_COUNTDOWN_SECONDS', 60)  # thời gian chờ học viên bấm xác nhận

# --- Phía server (chống gian lận) ---
# Interval mới được phép bắt đầu tối đa bao nhiêu giây phía sau mốc xem xa nhất.
SERVER_GAP_TOLERANCE_SECONDS = _get('SERVER_GAP_TOLERANCE_SECONDS', 10)
# Một heartbeat không được báo quá số giây này.
MAX_INTERVAL_SECONDS = _get('MAX_INTERVAL_SECONDS', 180)
# Tốc độ phát tối đa được chấp nhận (YouTube cho tối đa 2x).
MAX_PLAYBACK_RATE = _get('MAX_PLAYBACK_RATE', 2.0)
# "Quỹ giây xem": mỗi giây thật cộng MAX_PLAYBACK_RATE giây, tối đa MAX_CREDIT.
# Chặn việc gửi dồn dập nhiều heartbeat giả để "xem" cả video trong vài giây.
MAX_CREDIT = _get('MAX_CREDIT', 300.0)
RATE_SLACK_SECONDS = _get('RATE_SLACK_SECONDS', 5)
