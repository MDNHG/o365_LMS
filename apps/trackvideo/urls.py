from django.urls import path

from . import views

app_name = 'trackvideo'

urlpatterns = [
    path('heartbeat/', views.heartbeat, name='heartbeat'),
    path('sync-duration/', views.sync_duration, name='sync_duration'),
    path('event/', views.log_event, name='log_event'),
]
