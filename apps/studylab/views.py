import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import StudySession, ChatMessage, SessionFeedback
from .serializers import (
    StudySessionSerializer,
    StudySessionCreateSerializer,
    ChatMessageSerializer,
    SessionFeedbackSerializer,
)
from .services import answer_question

logger = logging.getLogger(__name__)


class StudySessionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Users can only access their own sessions
        qs = StudySession.objects.filter(user=self.request.user)
        # Support filtering by course
        course_id = self.request.query_params.get("course")
        if course_id:
            qs = qs.filter(course__id=course_id)
        return qs.select_related("course", "user").prefetch_related("messages__sources")

    def get_serializer_class(self):
        if self.action == "create":
            return StudySessionCreateSerializer
        return StudySessionSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # ── GET /api/sessions/{id}/messages/ ─────────────────────────────────────
    @action(detail=True, methods=["get"], url_path="messages")
    def messages(self, request, pk=None):
        """Returns all chat messages in this session in chronological order."""
        session = self.get_object()
        qs = session.messages.prefetch_related("sources__material").order_by("created_at")
        serializer = ChatMessageSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    # ── POST /api/sessions/{id}/ask/ ─────────────────────────────────────────
    @action(detail=True, methods=["post"], url_path="ask")
    def ask(self, request, pk=None):
        """
        Accepts a question, creates the user message, invokes the RAG pipeline,
        creates the assistant message + sources, and returns both.
        """
        session = self.get_object()
        message_text = request.data.get("message", "").strip()

        if not message_text:
            return Response(
                {"detail": "message field is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check course has ready materials — give a clear error if not
        ready_materials = session.course.materials.filter(status="ready")
        if not ready_materials.exists():
            return Response(
                {"detail": "No processed materials found for this course. "
                           "Ask your lecturer to upload and process course materials first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Persist the user's message
        user_message = ChatMessage.objects.create(
            session=session,
            role="user",
            content=message_text,
        )

        # 2. Invoke RAG pipeline (or stub)
        try:
            assistant_message = answer_question(session, message_text)
        except Exception as e:
            logger.error(f"RAG pipeline failed: {e}")
            # Create a fallback assistant message
            assistant_message = ChatMessage.objects.create(
                session=session,
                role="assistant",
                content="I'm sorry, I encountered an error processing your question. Please try again.",
            )

        # 3. Return both messages
        ctx = {"request": request}
        return Response({
            "user": ChatMessageSerializer(user_message, context=ctx).data,
            "assistant": ChatMessageSerializer(assistant_message, context=ctx).data,
        })

    # ── POST /api/sessions/{id}/feedback/ ───────────────────────────────────
    @action(detail=True, methods=["post"], url_path="feedback")
    def feedback(self, request, pk=None):
        """Accepts a 1–5 rating and optional note. One feedback per session."""
        session = self.get_object()

        # Prevent duplicate feedback
        if hasattr(session, "feedback"):
            return Response(
                {"detail": "Feedback already submitted for this session."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SessionFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(session=session)
        return Response({"success": True})