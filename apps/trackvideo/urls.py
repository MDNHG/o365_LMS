from django.urls import path

from . import views

app_name = 'trackvideo'

urlpatterns = [
    # Dashboard xem tiến độ video (Tránh lỗi 404 khi vào /trackvideo/)
    path('', views.video_dashboard, name='dashboard'),
    
    # API phục vụ trình phát video YouTube
    path('heartbeat/', views.heartbeat, name='heartbeat'),
    path('sync-duration/', views.sync_duration, name='sync_duration'),
    path('event/', views.log_event, name='log_event'),
]
