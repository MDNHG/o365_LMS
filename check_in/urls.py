from django.urls import path
from .views import (
    check_in_page_view,
    check_in_api_view,
    export_checkin_excel,
    export_checkin_csv,
)

app_name = "check_in"

urlpatterns = [
    path("", check_in_page_view, name="check_in_page"),
    path("api/", check_in_api_view, name="check_in_api"),
    path("export-excel/", export_checkin_excel, name="export_checkin_excel"),
    path("export-csv/", export_checkin_csv, name="export_checkin_csv"),
]
