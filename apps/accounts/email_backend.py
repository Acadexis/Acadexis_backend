import json
import base64
import logging
import urllib.request
import urllib.error
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage
from django.conf import settings

logger = logging.getLogger(__name__)


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

        from_email = message.from_email or settings.DEFAULT_FROM_EMAIL

        payload = {
            "from": from_email,
            "to": recipients,
            "subject": message.subject,
            "text": message.body,
        }

        # Support cc, bcc, and reply_to
        if getattr(message, "cc", None):
            payload["cc"] = [addr for addr in message.cc]
        if getattr(message, "bcc", None):
            payload["bcc"] = [addr for addr in message.bcc]
        if getattr(message, "reply_to", None):
            payload["reply_to"] = [addr for addr in message.reply_to]

        # Support html alternatives
        if getattr(message, "alternatives", None):
            for content, mime_type in message.alternatives:
                if mime_type == "text/html":
                    payload["html"] = content
                    break

        # Support attachments
        if getattr(message, "attachments", None):
            attachments_payload = []
            for attachment in message.attachments:
                if isinstance(attachment, tuple):
                    filename, content, mimetype = attachment
                    if isinstance(content, str):
                        content_bytes = content.encode("utf-8")
                    else:
                        content_bytes = content
                    content_b64 = base64.b64encode(content_bytes).decode("utf-8")
                    attachments_payload.append({
                        "filename": filename,
                        "content": content_b64,
                    })
            if attachments_payload:
                payload["attachments"] = attachments_payload

        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.api_url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return 200 <= response.status < 300
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
                error_json = json.loads(error_body)
                logger.error(
                    "Resend API Error: Code %s, Message: %s, Type: %s, Details: %s",
                    e.code,
                    error_json.get("message"),
                    error_json.get("type"),
                    error_body,
                )
            except Exception:
                logger.error("Resend API HTTP Error: Code %s, Reason: %s", e.code, e.reason)
            if not self.fail_silently:
                raise
            return False
        except Exception as e:
            logger.exception("Unexpected error in ResendEmailBackend: %s", str(e))
            if not self.fail_silently:
                raise
            return False
