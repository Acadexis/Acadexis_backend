from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import User, Profile, AdminRequest
from .serializers import RegisterSerializer, UserSerializer, ProfileSerializer, AdminRequestSerializer
from .permissions import IsLecturer



class RegisterView(generics.CreateAPIView):
    """
    Handles Student and Lecturer registration.
    """
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

class UserProfileViewSet(viewsets.ModelViewSet):
    """
    Handles retrieving and updating the authenticated user's profile.
    """
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Profile.objects.filter(user=self.request.user)

    def get_object(self):
        return self.request.user.profile


class AdminRequestCreateView(generics.CreateAPIView):
    """
    Allows a verified Lecturer to request Institutional Admin status.
    """
    queryset = AdminRequest.objects.all()
    serializer_class = AdminRequestSerializer
    permission_classes = [IsLecturer]

    def perform_create(self, serializer):
        # Check if the user already has a pending request to prevent spam
        if AdminRequest.objects.filter(user=self.request.user, status='pending').exists():
            raise serializers.ValidationError("You already have a pending admin request.")
        serializer.save()