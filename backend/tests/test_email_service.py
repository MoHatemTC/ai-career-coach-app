import pytest
from backend.models.schemas import JobSchema, ProfileSchema
from backend.services.email_service import EmailSenderStub

# 1. اختبار أن دالة إرسال الإيميل تعمل بشكل صحيح بناءً على الإعدادات
def test_send_email_enabled_disabled(monkeypatch):
    # تجربة الإرسال عندما يكون الإيميل مفعل
    monkeypatch.setenv("EMAIL_ENABLED", "True")
    monkeypatch.setenv("SENDER_EMAIL", "test@example.com")
    # أضفنا القوسين () بعد EmailSenderStub لتجنب الـ TypeError
    assert EmailSenderStub().send_email("recipient@example.com", "Subject", "Body") is True

    # تجربة الإرسال عندما يكون الإيميل معطل
    monkeypatch.setenv("EMAIL_ENABLED", "False")
    assert EmailSenderStub().send_email("recipient@example.com", "Subject", "Body") is False

# 2. اختبار أن الـ Schema تقبل البيانات الصحيحة وتطابق الحقول الفعلية
def test_job_schema_valid_payload():
    # الحقول هنا مطابقة تماماً للـ JobSchema في ملفschemas.py الخاص بكِ
    valid_data = {
        "id": "job_001",
        "title": "Software Engineer",
        "description": "Develop amazing Python applications",
        "location": "Cairo, Egypt",
        "work_type": "Full-time",
        "salary": 15000.0
    }
    job = JobSchema(**valid_data)
    assert job.title == "Software Engineer"
    assert job.salary == 15000.0

# 3. اختبار إضافي للتأكد من صحة إدخال الإيميل في الـ ProfileSchema
def test_profile_schema_valid_email():
    valid_profile = {
        "id": "prof_001",
        "user_id": "user_100",
        "name": "Sarah Basem",
        "email": "sarah@example.com", # حقل EmailStr للتأكد من عمل المراجعة التلقائية للإيميل
        "location": "Cairo",
        "salary_expectation": 18000.0
    }
    profile = ProfileSchema(**valid_profile)
    assert profile.email == "sarah@example.com"