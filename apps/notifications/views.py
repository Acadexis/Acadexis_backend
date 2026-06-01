from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        read = self.request.query_params.get("read")
        if read is not None:
            qs = qs.filter(read=read.lower() == "true")
        return qs


class NotificationMarkReadView(generics.UpdateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def post(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.read = True
        notification.save(update_fields=["read"])
        serializer = NotificationSerializer(notification)
        return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    count = Notification.objects.filter(user=request.user, read=False).update(read=True)
    return Response({"marked": count})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_count(request):
    count = Notification.objects.filter(user=request.user, read=False).count()
    return Response({"unread_count": count})