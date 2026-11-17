from django.urls import path
from .views import (
    student_check_in_page_view,
    student_check_in_api_view,
    student_my_status_api_view,
)

app_name = "check_in_for_student"

urlpatterns = [
    path("", student_check_in_page_view, name="student_check_in_page"),
    path("api/", student_check_in_api_view, name="student_check_in_api"),
    path("my-status/", student_my_status_api_view, name="student_my_status_api"),
]
