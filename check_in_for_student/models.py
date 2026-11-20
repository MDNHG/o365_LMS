"""
Models for check_in_for_student.
Reuses the shared CheckInRecord from check_in.models to maintain a single central
attendance database, while keeping student interactions isolated and non-exportable.
"""
from django.db import models
from check_in.models import CheckInRecord


class StudentCheckInRecord(CheckInRecord):
    """
    Proxy model representing attendance records created by students.
    Shares the underlying table with CheckInRecord.
    """

    class Meta:
        proxy = True
        verbose_name = "Điểm danh Sinh viên"
        verbose_name_plural = "Danh sách Điểm danh Sinh viên"


__all__ = ["CheckInRecord", "StudentCheckInRecord"]
