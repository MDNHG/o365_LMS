from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    
    # Phân hệ Điểm danh: Sinh viên dùng /check-in/, Giảng viên quản lý tại /check-in/manage/
    path('check-in/manage/', include('check_in.urls')),
    path('check-in/', include('check_in_for_student.urls')),
    
    # Phân hệ Theo dõi tiến độ video (có cả Dashboard & API)
    path('trackvideo/', include('apps.trackvideo.urls')),
    
    # Phân hệ Khóa học & Trang chủ
    path('', include('apps.courses.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
