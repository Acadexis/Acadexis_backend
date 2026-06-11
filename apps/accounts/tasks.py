import logging
from celery import shared_task
from apps.accounts.services.email_service import (
    build_password_changed_message,
    build_password_reset_message,
    build_welcome_message,
    send_email,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_email_task(self, subject: str, message: str, recipient_list: list, html_message: str = None, from_email: str = None):
    """Generic email sender task."""
    try:
        send_email(
            subject=subject,
            body=message,
            recipient_list=recipient_list,
            html_message=html_message,
            from_email=from_email,
        )
        return True
    except Exception as exc:
        logger.exception("send_email_task failed")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_welcome_email(self, user_id: str):
    from apps.accounts.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("send_welcome_email: user not found %s", user_id)
        return

    subject, text, html = build_welcome_message(user)
    try:
        send_email(subject, text, [user.email], html_message=html)
    except Exception as exc:
        logger.exception("send_welcome_email failed, retrying...")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_password_reset_email(self, user_id: str, token: str):
    from apps.accounts.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("send_password_reset_email: user not found %s", user_id)
        return

    subject, text, html = build_password_reset_message(user, token)
    try:
        send_email(subject, text, [user.email], html_message=html)
    except Exception as exc:
        logger.exception("send_password_reset_email failed, retrying...")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_password_changed_email(self, user_id: str):
    from apps.accounts.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("send_password_changed_email: user not found %s", user_id)
        return

    subject, text, html = build_password_changed_message(user)
    try:
        send_email(subject, text, [user.email], html_message=html)
    except Exception as exc:
        logger.exception("send_password_changed_email failed, retrying...")
        raise self.retry(exc=exc)
