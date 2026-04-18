from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import StudySession, ChatMessage, SessionFeedback
from .serializers import (StudySessionSerializer, ChatMessageSerializer,
                          FeedbackSerializer)
from .services import answer_question

class StudySessionViewSet(viewsets.ModelViewSet):
    serializer_class = StudySessionSerializer
    def get_queryset(self):
        return StudySession.objects.filter(user=self.request.user).order_by("-created_at")
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        msgs = ChatMessage.objects.filter(session_id=pk).prefetch_related("sources")
        return Response(ChatMessageSerializer(msgs, many=True).data)

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        session = self.get_object()
        question = request.data.get("message", "").strip()
        if not question:
            return Response({"detail": "Empty"}, status=400)
        user_msg = ChatMessage.objects.create(session=session, role="user", content=question)
        assistant_msg = answer_question(session, question)
        return Response({
            "user": ChatMessageSerializer(user_msg).data,
            "assistant": ChatMessageSerializer(assistant_msg).data,
        })

    @action(detail=True, methods=["post"])
    def feedback(self, request, pk=None):
        s = FeedbackSerializer(data={**request.data, "session": pk})
        s.is_valid(raise_exception=True); s.save()
        return Response({"success": True})