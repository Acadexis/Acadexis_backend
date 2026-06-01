import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.group_name = f"notifications_{user.id}"

        # Join private notification group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(f"WebSocket connected: {user.email} → {self.group_name}")

        # Send unread notification count immediately on connect
        unread_count = await self._get_unread_count(user)
        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "unread_count": unread_count,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"WebSocket disconnected: group={self.group_name}, code={close_code}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get("action")

            if action == "mark_read":
                notification_id = data.get("notification_id")
                if notification_id:
                    await self._mark_notification_read(notification_id)
                    await self.send(text_data=json.dumps({
                        "type": "notification_marked_read",
                        "notification_id": notification_id,
                    }))

            elif action == "mark_all_read":
                count = await self._mark_all_read()
                await self.send(text_data=json.dumps({
                    "type": "all_notifications_marked_read",
                    "marked": count,
                }))

        except json.JSONDecodeError:
            pass

    async def send_notification(self, event):
        await self.send(text_data=json.dumps({
            "id": event["id"],
            "title": event["title"],
            "body": event["body"],
            "notification_type": event["notification_type"],
            "read": event["read"],
            "created_at": event["created_at"],
            "data": event.get("data", {}),
        }))

    @database_sync_to_async
    def _get_unread_count(self, user):
        from apps.notifications.models import Notification
        return Notification.objects.filter(user=user, read=False).count()

    @database_sync_to_async
    def _mark_notification_read(self, notification_id):
        from apps.notifications.models import Notification
        user = self.scope["user"]
        Notification.objects.filter(id=notification_id, user=user).update(read=True)

    @database_sync_to_async
    def _mark_all_read(self):
        from apps.notifications.models import Notification
        user = self.scope["user"]
        return Notification.objects.filter(user=user, read=False).update(read=True)