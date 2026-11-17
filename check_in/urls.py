from django.urls import path
from .views import (
    check_in_page_view,
    check_in_api_view,
    export_checkin_excel,
    export_checkin_csv,
    list_locations_api,
    update_location_api,
    set_active_location_api,
    clear_checkin_history_api,
)

app_name = "check_in"

urlpatterns = [
    path("", check_in_page_view, name="check_in_page"),
    path("api/", check_in_api_view, name="check_in_api"),
    path("export-excel/", export_checkin_excel, name="export_checkin_excel"),
    path("export-csv/", export_checkin_csv, name="export_checkin_csv"),
    path("api/locations/", list_locations_api, name="list_locations_api"),
    path("api/locations/update/", update_location_api, name="update_location_api"),
    path("api/locations/set-active/", set_active_location_api, name="set_active_location_api"),
    path("api/clear-history/", clear_checkin_history_api, name="clear_checkin_history_api"),
]
