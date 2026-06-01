from .models import Notification


def push_notification(user, title, body, notification_type, data=None):
    return Notification.create_and_push(
        user=user,
        title=title,
        body=body,
        notification_type=notification_type,
        data=data or {},
    )
