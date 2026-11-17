"""Hàm thuần (không phụ thuộc Django) để gom khoảng và tính phần trăm xem."""


def merge_intervals(intervals, gap=1):
    """
    Gom các khoảng [start, end] giao nhau hoặc cách nhau không quá `gap` giây.
    Trả về danh sách tuple (start, end) đã sắp xếp, không chồng lấn.

    >>> merge_intervals([(0, 30), (20, 50), (60, 90)])
    [(0, 50), (60, 90)]
    """
    cleaned = []
    for s, e in intervals:
        s, e = int(s), int(e)
        if e > s:
            cleaned.append((s, e))
    cleaned.sort()
    merged = []
    for s, e in cleaned:
        if merged and s <= merged[-1][1] + gap:
            if e > merged[-1][1]:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def total_seconds(intervals, duration=None):
    """Tổng số giây của các khoảng (đã gom). Nếu có duration thì cắt phần vượt quá."""
    total = 0
    for s, e in intervals:
        if duration is not None:
            s, e = min(s, duration), min(e, duration)
        total += max(0, e - s)
    return total


def percent_of(watched_seconds, duration):
    if not duration or duration <= 0:
        return 0.0
    return round(min(100.0, watched_seconds * 100.0 / duration), 2)
