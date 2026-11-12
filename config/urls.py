from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('check-in/', include('checkin.urls')), 
    path('', include('apps.courses.urls')),
]
