from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        n = self.get_object(); n.read = True; n.save()
        return Response({"success": True})

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        self.get_queryset().update(read=True)
        return Response({"success": True})