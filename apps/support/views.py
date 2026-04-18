from rest_framework import generics, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import ContactSerializer, ReportSerializer, AdminRequestSerializer

class ContactView(generics.CreateAPIView):
    serializer_class = ContactSerializer
    permission_classes = [permissions.AllowAny]

class ReportView(generics.CreateAPIView):
    serializer_class = ReportSerializer
    def perform_create(self, s): s.save(user=self.request.user)

class AdminRequestView(generics.CreateAPIView):
    serializer_class = AdminRequestSerializer
    parser_classes = [MultiPartParser, FormParser]
    def perform_create(self, s): s.save(user=self.request.user)