from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def get_frontend_url():
    return getattr(settings, "FRONTEND_URL", None) or getattr(settings, "FRONTEND_ORIGIN", "http://localhost:3000")


def get_default_from_email():
    return getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost")


def build_password_reset_url(token: str) -> str:
    frontend_url = get_frontend_url().rstrip("/")
    return f"{frontend_url}/reset-password?token={token}"


def render_email_templates(template_name: str, context: dict):
    text_template = f"accounts/emails/{template_name}.txt"
    html_template = f"accounts/emails/{template_name}.html"
    text = render_to_string(text_template, context).strip()
    html = render_to_string(html_template, context).strip()
    return text, html


def send_email(subject: str, body: str, recipient_list: list, html_message: str = None, from_email: str = None, fail_silently: bool = False):
    from_email = from_email or get_default_from_email()
    return send_mail(
        subject=subject,
        message=body,
        from_email=from_email,
        recipient_list=recipient_list,
        html_message=html_message,
        fail_silently=fail_silently,
    )


def build_welcome_message(user):
    subject = "Welcome to Acadexis"
    context = {"user": user, "frontend_url": get_frontend_url()}
    text, html = render_email_templates("welcome_email", context)
    return subject, text, html


def build_password_reset_message(user, token: str):
    subject = "Acadexis Password Reset"
    context = {"user": user, "reset_url": build_password_reset_url(token)}
    text, html = render_email_templates("password_reset_email", context)
    return subject, text, html


def build_password_changed_message(user):
    subject = "Your Acadexis password was changed"
    context = {"user": user}
    text, html = render_email_templates("password_changed_email", context)
    return subject, text, html
