from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification
from .serializers import NotificationSerializer

def push_notification(user, **kwargs):
    n = Notification.objects.create(user=user, **kwargs)
    async_to_sync(get_channel_layer().group_send)(
        f"user_{user.id}",
        {"type": "notify", "payload": NotificationSerializer(n).data},
    )
    return n