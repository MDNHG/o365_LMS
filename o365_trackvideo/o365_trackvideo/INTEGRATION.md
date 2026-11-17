# Tích hợp app `tracking`

1. Chép `apps/trackvideo/`, `templates/trackvideo/`, `static/js/tracker.js`, `static/css/tracker.css` vào dự án.
2. settings.py -> INSTALLED_APPS, thêm sau 'apps.courses.apps.CoursesConfig':
       'apps.trackvideo.apps.TrackVideoConfig',
3. config/urls.py -> thêm TRƯỚC dòng path('', include('apps.courses.urls')):
       path('trackvideo/', include('apps.trackvideo.urls')),
4. templates/courses/lesson_detail.html -> xem hướng dẫn trong tin nhắn (load trackvideo_tags + {% video_tracker lesson %}).
5. python manage.py makemigrations trackvideo && python manage.py migrate
6. python manage.py test apps.trackvideo
