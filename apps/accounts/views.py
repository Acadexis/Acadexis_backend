from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator

from rest_framework import generics, permissions, parsers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PasswordResetToken, User, Profile
from .serializers import (
    RegisterSerializer,
    CustomTokenSerializer,
    UserSerializer,
    UpdateUserSerializer,
    ProfileSerializer,
    LogoutSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer,
)

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        
        import random
        from django.db import transaction
        from .models import EmailVerificationCode
        from .tasks import send_verification_email
        
        code = f"{random.randint(100000, 999999)}"
        EmailVerificationCode.objects.create(user=user, code=code)
        
        try:
            transaction.on_commit(lambda: send_verification_email.delay(str(user.id), code))
        except Exception:
            pass
            
        return Response(
            {"success": True, "user": UserSerializer(user, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )

class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenSerializer


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Logged out successfully."})


class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return UpdateUserSerializer
        return UserSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = UpdateUserSerializer(
            instance,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(instance, context={"request": request}).data)


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_object(self):
        profile, _ = Profile.objects.get_or_create(
            user=self.request.user,
            defaults={
                "first_name": "",
                "last_name": "",
                "identification_number": str(self.request.user.id),
                "level": "",
                "department": None,
            },
        )
        return profile

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        if user:
            token = password_reset_token_generator.make_token(user)
            PasswordResetToken.objects.create(user=user, token=token)
            try:
                from .tasks import send_password_reset_email
                from django.db import transaction
                transaction.on_commit(lambda: send_password_reset_email.delay(str(user.id), token))
            except Exception:
                print(f"[password reset] email={user.email} token={token}")

        return Response({"message": "If that email is registered, a reset link has been sent."})


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]
        reset_record = PasswordResetToken.objects.filter(token=token, used=False).first()

        if not reset_record:
            return Response({"detail": "Invalid or expired reset token."}, status=status.HTTP_400_BAD_REQUEST)

        if reset_record.is_expired() or not password_reset_token_generator.check_token(reset_record.user, token):
            return Response({"detail": "Invalid or expired reset token."}, status=status.HTTP_400_BAD_REQUEST)

        user = reset_record.user
        user.set_password(new_password)
        user.save()

        reset_record.used = True
        reset_record.save()

        try:
            from .tasks import send_password_changed_email
            from django.db import transaction
            transaction.on_commit(lambda: send_password_changed_email.delay(str(user.id)))
        except Exception:
            pass

        return Response({"message": "Password has been reset successfully."})


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"message": "Password changed successfully."})


class CSRFTokenView(APIView):
    """
    Dedicated endpoint to fetch CSRF token.
    This ensures the CSRF cookie is set for cross-origin requests.
    Use this before making POST requests to Django admin or other endpoints
    that require CSRF protection.
    """
    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"CSRF token request from origin: {request.headers.get('origin')}")
        return Response({"message": "CSRF cookie set"})


class AdminLoginView(APIView):
    """
    Custom admin login endpoint that uses DRF authentication.
    This is an alternative to Django admin's built-in login which has
    CSRF issues with cross-origin requests.

    Note: This User model uses email as the username field (USERNAME_FIELD = "email")
    """
    permission_classes = [permissions.AllowAny]
    parser_classes = [parsers.FormParser, parsers.JSONParser]

    def post(self, request, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)

        # Support both "username" (for backward compat) and "email" in the payload
        email = request.data.get("email") or request.data.get("username")
        password = request.data.get("password")

        logger.info(f"Admin login attempt for email: {email}")

        if not email or not password:
            return Response(
                {"detail": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find user by email
        from .models import User
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            logger.warning(f"User not found: {email}")
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except User.MultipleObjectsReturned:
            logger.error(f"Multiple users found: {email}")
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check password
        if not user.check_password(password):
            logger.warning(f"Invalid password for: {email}")
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check if user is admin (is_staff or is_superuser)
        if not user.is_staff and not user.is_superuser:
            logger.warning(f"Non-admin user attempted login: {email}")
            return Response(
                {"detail": "Access denied. Admin credentials required."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Generate tokens
        refresh = RefreshToken.for_user(user)

        logger.info(f"Admin login successful for: {email}")
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": "admin",
                "name": user.get_full_name() or user.email.split('@')[0],
                "profile": {},
            }
        })


import re
import urllib.parse
import requests
from django.db import transaction
from django.conf import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

class GoogleAuthUrlView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        client_id = settings.GOOGLE_CLIENT_ID
        redirect_uri = settings.GOOGLE_REDIRECT_URI
        
        # Serialize the state query params
        role = request.query_params.get("role", "")
        state_data = {}
        if role:
            state_data["role"] = role
        
        # We can pass state as URL-encoded JSON or simple key-value pairs
        state_str = urllib.parse.urlencode(state_data)
        
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "consent",
            "state": state_str,
        }
        
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        return Response({"url": url})


class GoogleAuthCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def validate_student_email(self, email):
        email = email.lower()
        domain = email.split("@")[1] if "@" in email else ""
        
        # Suffix/domain check
        # 1. No free emails allowed
        is_free_email = re.match(r"^(gmail|yahoo|outlook|hotmail|aol|protonmail|icloud)\.(com|co\.|net|org)$", domain)
        if is_free_email:
            return False
            
        # 2. Check for academic domain patterns or indicator terms
        academic_patterns = re.compile(r"\.(edu|ac\.|edu\.[a-z]{2}|co\.[a-z]{2}|org\.[a-z]{2})$", re.IGNORECASE)
        has_academic_indicators = any(term in email for term in ["student", "staff", "faculty", "lecturer", "prof", "alumni"])
        
        return bool(academic_patterns.search(domain) or has_academic_indicators)

    def post(self, request, *args, **kwargs):
        code = request.data.get("code")
        if not code:
            return Response(
                {"detail": "Authorization code is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Exchange code for Google tokens
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        
        token_response = requests.post(token_url, data=payload)
        if not token_response.ok:
            return Response(
                {"detail": f"Failed to exchange Google authorization code: {token_response.text}"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        tokens = token_response.json()
        id_token_str = tokens.get("id_token")
        if not id_token_str:
            return Response(
                {"detail": "Google did not return an ID token."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Verify Google ID token
        try:
            id_info = id_token.verify_oauth2_token(
                id_token_str,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
            if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
        except Exception as e:
            return Response(
                {"detail": f"Invalid ID token: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        email = id_info.get("email")
        first_name = id_info.get("given_name", "")
        last_name = id_info.get("family_name", "")

        if not email:
            return Response(
                {"detail": "Email is missing from Google account info."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate that email is an institutional/student email
        if not self.validate_student_email(email):
            return Response(
                {"detail": "Access restricted. You must sign in with a valid University email account (e.g. @university.edu)."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Find user or handle registration
        user = User.objects.filter(email__iexact=email).first()
        
        if not user:
            # Check if this is the initial exchange or the registration completion request
            role = request.data.get("role")
            if not role:
                # User does not exist, return detail so frontend prompts them to complete sign up
                return Response({
                    "registered": False,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "message": "Valid institutional email. Please complete registration details."
                }, status=status.HTTP_200_OK)

            # Complete registration
            university_id = request.data.get("university")
            faculty_id = request.data.get("faculty")
            department_id = request.data.get("department")
            identification_number = request.data.get("identification_number")
            level = request.data.get("level", "")

            if not university_id or not department_id:
                return Response(
                    {"detail": "University and department are required to complete registration."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate student specifics
            if role == User.Role.STUDENT:
                if not identification_number:
                    return Response(
                        {"detail": "Matric number is required for students."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if not level:
                    return Response(
                        {"detail": "Level is required for students."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            try:
                from apps.institutions.models import University, Department
                university = University.objects.get(id=university_id)
                department = Department.objects.get(id=department_id)
            except (University.DoesNotExist, Department.DoesNotExist):
                return Response(
                    {"detail": "Selected university or department does not exist."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create the user and profile
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    role=role,
                    university=university,
                    password=None
                )
                Profile.objects.update_or_create(
                    user=user,
                    defaults={
                        "first_name": first_name or request.data.get("first_name", ""),
                        "last_name": last_name or request.data.get("last_name", ""),
                        "identification_number": identification_number or str(user.id),
                        "level": level,
                        "department": department,
                    }
                )

        # Generate tokens
        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["email"] = user.email
        profile = getattr(user, "profile", None)
        if profile:
            refresh["first_name"] = profile.first_name
            refresh["last_name"] = profile.last_name
            refresh["identification_number"] = profile.identification_number
            refresh["level"] = profile.level
            refresh["department"] = str(profile.department.id) if profile.department else None
            refresh["department_name"] = profile.department.name if profile.department else None
            if profile.department and profile.department.faculty:
                refresh["faculty"] = str(profile.department.faculty.id)
                refresh["faculty_name"] = profile.department.faculty.name
                if profile.department.faculty.university:
                    refresh["university"] = str(profile.department.faculty.university.id)
                    refresh["university_name"] = profile.department.faculty.university.name

        return Response({
            "registered": True,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user, context={"request": request}).data
        }, status=status.HTTP_200_OK)


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get("email")
        code_str = request.data.get("code")

        if not email or not code_str:
            return Response(
                {"detail": "Email and verification code are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response(
                {"detail": "User with this email does not exist."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user.is_active:
            return Response(
                {"detail": "This email address is already verified. Please log in."},
                status=status.HTTP_400_BAD_REQUEST
            )

        verification_record = user.verification_codes.filter(code=code_str, used=False).first()
        if not verification_record:
            return Response(
                {"detail": "Invalid verification code."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if verification_record.is_expired():
            return Response(
                {"detail": "Verification code has expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            verification_record.used = True
            verification_record.save()
            user.is_active = True
            user.save()

        try:
            from .tasks import send_welcome_email
            transaction.on_commit(lambda: send_welcome_email.delay(str(user.id)))
        except Exception:
            pass

        return Response({"success": True, "message": "Email address verified successfully!"})


class ResendVerificationCodeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get("email")

        if not email:
            return Response(
                {"detail": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response(
                {"detail": "User with this email does not exist."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user.is_active:
            return Response(
                {"detail": "This email address is already verified. Please log in."},
                status=status.HTTP_400_BAD_REQUEST
            )

        import random
        from .models import EmailVerificationCode
        from .tasks import send_verification_email

        code = f"{random.randint(100000, 999999)}"
        EmailVerificationCode.objects.create(user=user, code=code)

        try:
            transaction.on_commit(lambda: send_verification_email.delay(str(user.id), code))
        except Exception:
            pass

        return Response({"success": True, "message": "A new verification code has been sent to your email."})