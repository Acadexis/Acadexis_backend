from django.test import TestCase, override_settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from unittest.mock import patch, MagicMock
import urllib.error
import urllib.request
import io
import json

from apps.accounts.email_backend import ResendEmailBackend
from apps.accounts.models import User


class EmailBackendTestCase(TestCase):
    @patch("urllib.request.urlopen")
    @override_settings(RESEND_API_KEY="test_key", DEFAULT_FROM_EMAIL="default@test.com")
    def test_send_message_full_payload(self, mock_urlopen):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Create email message with cc, bcc, reply_to, html, and attachments
        email = EmailMultiAlternatives(
            subject="Test Subject",
            body="Test Text Body",
            from_email="custom@test.com",
            to=["to@test.com"],
            cc=["cc@test.com"],
            bcc=["bcc@test.com"],
            reply_to=["reply@test.com"],
        )
        email.attach_alternative("<p>Test HTML Body</p>", "text/html")
        email.attach("test_file.txt", "Attachment content", "text/plain")

        backend = ResendEmailBackend()
        sent = backend.send_messages([email])

        self.assertEqual(sent, 1)
        mock_urlopen.assert_called_once()
        
        # Verify the request payload sent to Resend
        called_req = mock_urlopen.call_args[0][0]
        self.assertIsInstance(called_req, urllib.request.Request)
        self.assertEqual(called_req.get_header("Authorization"), "Bearer test_key")
        self.assertEqual(called_req.get_header("Content-type"), "application/json")
        
        payload = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(payload["from"], "custom@test.com")
        self.assertEqual(payload["to"], ["to@test.com"])
        self.assertEqual(payload["cc"], ["cc@test.com"])
        self.assertEqual(payload["bcc"], ["bcc@test.com"])
        self.assertEqual(payload["reply_to"], ["reply@test.com"])
        self.assertEqual(payload["text"], "Test Text Body")
        self.assertEqual(payload["html"], "<p>Test HTML Body</p>")
        self.assertEqual(len(payload["attachments"]), 1)
        self.assertEqual(payload["attachments"][0]["filename"], "test_file.txt")
        self.assertEqual(payload["attachments"][0]["content"], "QXR0YWNobWVudCBjb250ZW50") # base64 of 'Attachment content'

    @patch("urllib.request.urlopen")
    @patch("apps.accounts.email_backend.logger")
    @override_settings(RESEND_API_KEY="test_key")
    def test_send_message_api_error_logging(self, mock_logger, mock_urlopen):
        # Mock HTTPError 400 with detailed JSON body
        error_json = {"message": "Domain not verified", "type": "validation_error"}
        error_body = json.dumps(error_json).encode("utf-8")
        
        # HTTPError arguments: url, code, msg, hdrs, fp
        http_error = urllib.error.HTTPError(
            url="https://api.resend.com/emails",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(error_body)
        )
        mock_urlopen.side_effect = http_error

        email = EmailMessage(
            subject="Test Subject",
            body="Test Body",
            to=["to@test.com"],
        )

        backend = ResendEmailBackend(fail_silently=True)
        sent = backend.send_messages([email])

        self.assertEqual(sent, 0)
        # Verify error logger was called with Resend error details
        mock_logger.error.assert_any_call(
            "Resend API Error: Code %s, Message: %s, Type: %s, Details: %s",
            400,
            "Domain not verified",
            "validation_error",
            error_body.decode("utf-8"),
        )


class EmailTasksTestCase(TestCase):
    @patch("apps.accounts.tasks.send_email")
    def test_send_welcome_email_task(self, mock_send_email):
        # Create a user
        user = User.objects.create_user(email="testuser@test.com", password="password123")
        
        # Call the task synchronously
        from apps.accounts.tasks import send_welcome_email
        send_welcome_email(str(user.id))
        
        # Verify send_email was called with correct context
        mock_send_email.assert_called_once()
        args, kwargs = mock_send_email.call_args
        self.assertEqual(args[0], "Welcome to Acadexis")
        self.assertIn("Welcome to the family! ✨", kwargs["html_message"])
        self.assertEqual(args[2], ["testuser@test.com"])


from rest_framework.test import APITransactionTestCase
from apps.accounts.models import EmailVerificationCode
from apps.institutions.models import University, Faculty, Department
from django.utils import timezone
from datetime import timedelta

class EmailVerificationTests(APITransactionTestCase):
    def setUp(self):
        self.u = University.objects.create(name="UCT")
        self.f = Faculty.objects.create(name="Eng", university=self.u)
        self.dept = Department.objects.create(name="CS", faculty=self.f)

    @patch("apps.accounts.tasks.send_verification_email.delay")
    def test_registration_flow_creates_inactive_user_and_code(self, mock_send_email):
        response = self.client.post("/api/auth/register/", {
            "email": "student@university.edu",
            "password": "Password123",
            "role": "student",
            "university": str(self.u.id),
            "faculty": str(self.f.id),
            "department": str(self.dept.id),
            "first_name": "John",
            "last_name": "Doe",
            "identification_number": "STU123",
            "level": "100",
        })
        self.assertEqual(response.status_code, 201)
        
        # Verify user is inactive
        user = User.objects.get(email="student@university.edu")
        self.assertFalse(user.is_active)
        
        # Verify verification code is created
        code_record = EmailVerificationCode.objects.filter(user=user).first()
        self.assertIsNotNone(code_record)
        self.assertEqual(len(code_record.code), 6)
        
        # Verify celery task was queued
        mock_send_email.assert_called_once_with(str(user.id), code_record.code)

    @patch("apps.accounts.tasks.send_welcome_email.delay")
    def test_verify_email_success(self, mock_welcome):
        user = User.objects.create_user(
            email="student@university.edu",
            password="Password123",
            role="student",
            university=self.u,
            is_active=False
        )
        code_record = EmailVerificationCode.objects.create(user=user, code="123456")
        
        response = self.client.post("/api/auth/verify-email/", {
            "email": "student@university.edu",
            "code": "123456"
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        
        # Verify user is now active
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        
        # Verify code is marked used
        code_record.refresh_from_db()
        self.assertTrue(code_record.used)
        
        # Verify welcome email queued
        mock_welcome.assert_called_once_with(str(user.id))

    def test_verify_email_invalid_code(self):
        user = User.objects.create_user(
            email="student@university.edu",
            password="Password123",
            role="student",
            university=self.u,
            is_active=False
        )
        EmailVerificationCode.objects.create(user=user, code="123456")
        
        response = self.client.post("/api/auth/verify-email/", {
            "email": "student@university.edu",
            "code": "654321"
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid verification code", response.data["detail"])
        
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_verify_email_expired_code(self):
        user = User.objects.create_user(
            email="student@university.edu",
            password="Password123",
            role="student",
            university=self.u,
            is_active=False
        )
        # Create an expired code (e.g. 20 minutes ago)
        code_record = EmailVerificationCode.objects.create(user=user, code="123456")
        code_record.created_at = timezone.now() - timedelta(minutes=20)
        code_record.save()
        
        response = self.client.post("/api/auth/verify-email/", {
            "email": "student@university.edu",
            "code": "123456"
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("expired", response.data["detail"])

    @patch("apps.accounts.tasks.send_verification_email.delay")
    def test_resend_verification_code(self, mock_send):
        user = User.objects.create_user(
            email="student@university.edu",
            password="Password123",
            role="student",
            university=self.u,
            is_active=False
        )
        
        response = self.client.post("/api/auth/resend-verification/", {
            "email": "student@university.edu"
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        
        # Verify new code is created
        code_record = EmailVerificationCode.objects.filter(user=user).first()
        self.assertIsNotNone(code_record)
        mock_send.assert_called_once_with(str(user.id), code_record.code)

    def test_login_requires_verified_email(self):
        User.objects.create_user(
            email="student@university.edu",
            password="Password123",
            role="student",
            university=self.u,
            is_active=False
        )
        
        response = self.client.post("/api/auth/login/", {
            "email": "student@university.edu",
            "password": "Password123"
        })
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.data["email_verification_required"])
