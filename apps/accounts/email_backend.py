import json
import urllib.request
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage
from django.conf import settings


class ResendEmailBackend(BaseEmailBackend):
    """Send email through the Resend API."""

    api_url = "https://api.resend.com/emails"

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            if self._send_message(message):
                sent_count += 1
        return sent_count

    def _send_message(self, message: EmailMessage):
        recipients = [addr for addr in message.to or []]
        if not recipients:
            return False

        payload = {
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": recipients,
            "subject": message.subject,
            "text": message.body,
        }

        if getattr(message, "alternatives", None):
            for content, mime_type in message.alternatives:
                if mime_type == "text/html":
                    payload["html"] = content
                    break

        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        }

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.api_url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return 200 <= response.status < 300
        except Exception:
            if not self.fail_silently:
                raise
            return False
