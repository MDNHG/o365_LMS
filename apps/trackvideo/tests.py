import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.courses.models import Course, Enrollment, Lesson

from .intervals import merge_intervals, percent_of, total_seconds
from .models import LessonProgress, WatchedInterval
from .utils import extract_youtube_id

User = get_user_model()


class IntervalTests(SimpleTestCase):
    def test_merge_overlap_and_touching(self):
        self.assertEqual(merge_intervals([(0, 30), (20, 50), (50, 60)]), [(0, 60)])

    def test_merge_keeps_gaps(self):
        self.assertEqual(merge_intervals([(60, 90), (0, 30)]), [(0, 30), (60, 90)])

    def test_merge_tolerates_one_second_gap(self):
        self.assertEqual(merge_intervals([(0, 30), (31, 60)]), [(0, 60)])

    def test_ignores_empty_intervals(self):
        self.assertEqual(merge_intervals([(5, 5), (9, 3)]), [])

    def test_total_and_percent(self):
        merged = merge_intervals([(0, 100), (50, 150)])
        self.assertEqual(total_seconds(merged), 150)
        self.assertEqual(total_seconds(merged, duration=120), 120)
        self.assertEqual(percent_of(150, 600), 25.0)
        self.assertEqual(percent_of(10, 0), 0.0)


class YoutubeIdTests(SimpleTestCase):
    def test_variants(self):
        vid = 'dQw4w9WgXcQ'
        for value in [
            vid,
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s',
            'https://youtu.be/dQw4w9WgXcQ',
            'https://www.youtube.com/embed/dQw4w9WgXcQ',
            'https://www.youtube.com/shorts/dQw4w9WgXcQ',
        ]:
            self.assertEqual(extract_youtube_id(value), vid, value)

    def test_rejects_other_hosts(self):
        self.assertEqual(extract_youtube_id('https://evil.com/watch?v=dQw4w9WgXcQ'), '')
        self.assertEqual(extract_youtube_id(''), '')


class HeartbeatApiTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user('sv', password='x', role='student')
        self.other = User.objects.create_user('sv2', password='x', role='student')
        self.teacher = User.objects.create_user('gv', password='x', role='teacher')
        self.course = Course.objects.create(code='WORD', title='Word')
        self.course.instructors.add(self.teacher)
        self.lesson = Lesson.objects.create(
            course=self.course, order=1, title='Bài 1', lesson_type='video',
            raw_url='https://youtu.be/dQw4w9WgXcQ', duration_seconds=600,
            min_watch_percent=80, is_published=True,
        )
        Enrollment.objects.create(user=self.student, course=self.course)
        self.url = reverse('trackvideo:heartbeat')

    def hb(self, start, end, **extra):
        payload = {'lesson_id': self.lesson.pk, 'interval': [start, end],
                   'current_time': end, **extra}
        return self.client.post(self.url, json.dumps(payload), content_type='application/json')

    def test_requires_login(self):
        self.assertEqual(self.hb(0, 30).status_code, 401)

    def test_not_enrolled(self):
        self.client.force_login(self.other)
        self.assertEqual(self.hb(0, 30).status_code, 403)

    def test_teacher_is_not_tracked(self):
        self.client.force_login(self.teacher)
        res = self.hb(0, 30)
        self.assertFalse(res.json()['tracked'])
        self.assertFalse(LessonProgress.objects.exists())

    def test_accepts_and_merges(self):
        self.client.force_login(self.student)
        self.assertTrue(self.hb(0, 30).json()['accepted'])
        res = self.hb(20, 60).json()
        self.assertTrue(res['accepted'])
        self.assertEqual(res['watched_seconds'], 60)
        self.assertEqual(res['furthest'], 60)
        self.assertEqual(WatchedInterval.objects.count(), 1)

    def test_rewatching_does_not_inflate_progress(self):
        self.client.force_login(self.student)
        self.hb(0, 60)
        res = self.hb(0, 60).json()
        self.assertEqual(res['watched_seconds'], 60)

    def test_rejects_skip_ahead(self):
        self.client.force_login(self.student)
        self.hb(0, 30)
        res = self.hb(300, 330).json()
        self.assertFalse(res['accepted'])
        self.assertEqual(res['reason'], 'gap')
        self.assertEqual(res['furthest'], 30)

    def test_rate_limit_clamps_burst(self):
        self.client.force_login(self.student)
        self.assertTrue(self.hb(0, 100).json()['accepted'])
        res = self.hb(100, 200).json()   # gửi ngay lập tức: chỉ còn rất ít quỹ giây
        self.assertLessEqual(res['watched_seconds'], 130)

    def test_completion_threshold(self):
        self.client.force_login(self.student)
        LessonProgress.objects.create(
            user=self.student, lesson=self.lesson, furthest_second_reached=470,
            watch_credit=1000,
        )
        p = LessonProgress.objects.get()
        WatchedInterval.objects.create(progress=p, start_sec=0, end_sec=470)
        res = self.hb(470, 490).json()          # 490/600 = 81.7% >= 80%
        self.assertTrue(res['is_completed'])
        self.assertIsNotNone(LessonProgress.objects.get().completed_at)

    def test_clamps_to_duration(self):
        self.client.force_login(self.student)
        LessonProgress.objects.create(
            user=self.student, lesson=self.lesson, furthest_second_reached=590, watch_credit=300,
        )
        res = self.hb(590, 700).json()
        self.assertTrue(res['accepted'])
        self.assertEqual(res['furthest'], 600)

    def test_bad_payload(self):
        self.client.force_login(self.student)
        res = self.client.post(self.url, 'not json', content_type='application/json')
        self.assertEqual(res.status_code, 400)


class SyncDurationTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user('gv', password='x', role='teacher')
        self.student = User.objects.create_user('sv', password='x', role='student')
        self.course = Course.objects.create(code='EXCEL', title='Excel')
        self.course.instructors.add(self.teacher)
        self.lesson = Lesson.objects.create(
            course=self.course, order=1, title='B1', lesson_type='video',
            raw_url='https://youtu.be/dQw4w9WgXcQ', duration_seconds=360,
            min_watch_percent=80, is_published=True,
        )
        self.url = reverse('trackvideo:sync_duration')

    def post(self, duration):
        return self.client.post(
            self.url, json.dumps({'lesson_id': self.lesson.pk, 'duration': duration}),
            content_type='application/json',
        )

    def test_teacher_can_sync(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.post(213).status_code, 200)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.duration_seconds, 213)

    def test_student_cannot_sync(self):
        self.client.force_login(self.student)
        self.assertEqual(self.post(10).status_code, 403)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.duration_seconds, 360)


class LogEventApiTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user('sv_log', password='x', role='student')
        self.other = User.objects.create_user('sv_other', password='x', role='student')
        self.course = Course.objects.create(code='WORD', title='Word Course')
        self.lesson = Lesson.objects.create(
            course=self.course, order=1, title='Bài 1', lesson_type='video',
            raw_url='https://youtu.be/dQw4w9WgXcQ', duration_seconds=600,
            min_watch_percent=80, is_published=True,
            allow_seek_policy='backward_only', allow_speed_change=True, max_playback_rate=1.5
        )
        Enrollment.objects.create(user=self.student, course=self.course)
        self.url = reverse('trackvideo:log_event')

    def post_event(self, event_type, video_time=0.0, extra_data=None):
        payload = {
            'lesson_id': self.lesson.pk,
            'event_type': event_type,
            'video_time': video_time,
            'extra_data': extra_data or {}
        }
        return self.client.post(self.url, json.dumps(payload), content_type='application/json')

    def test_requires_login(self):
        res = self.post_event('pause', 10.0)
        self.assertEqual(res.status_code, 401)

    def test_not_enrolled_cannot_log(self):
        self.client.force_login(self.other)
        res = self.post_event('pause', 10.0)
        self.assertEqual(res.status_code, 403)

    def test_student_can_log_events(self):
        self.client.force_login(self.student)
        res = self.post_event('play', 0.0)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['ok'])

        res = self.post_event('tab_hidden', 35.0)
        self.assertEqual(res.status_code, 200)

        res = self.post_event('tab_visible', 40.0)
        self.assertEqual(res.status_code, 200)

        p = LessonProgress.objects.get(user=self.student, lesson=self.lesson)
        self.assertEqual(p.event_logs.count(), 3)

    def test_inactivity_metrics_and_assessment(self):
        self.client.force_login(self.student)
        # Gửi prompt
        res = self.post_event('inactivity_prompt', 120.0).json()
        self.assertEqual(res['inactivity_prompts'], 1)

        # Gửi timeout (treo máy)
        res = self.post_event('inactivity_timeout', 120.0).json()
        self.assertEqual(res['inactivity_timeouts'], 1)

        p = LessonProgress.objects.get(user=self.student, lesson=self.lesson)
        self.assertEqual(p.inactivity_timeouts_count, 1)
        # Điểm trừ 20 vì có 1 timeout
        self.assertEqual(p.integrity_score, 80.0)

    def test_suspicious_seek_increases_count(self):
        self.client.force_login(self.student)
        res = self.post_event('seek_forward', 300.0, extra_data={'suspicious': True}).json()
        self.assertEqual(res['suspicious_seeks'], 1)
        p = LessonProgress.objects.get(user=self.student, lesson=self.lesson)
        self.assertEqual(p.suspicious_seeks_count, 1)
