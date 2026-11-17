from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('check-in/', include('check_in.urls')),
    path('trackvideo/', include('apps.trackvideo.urls')),
    path('check-in-student/', include('check_in_for_student.urls')),
    path('', include('apps.courses.urls')),
]
