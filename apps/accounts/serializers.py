from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import transaction
import os

from .models import User, Profile
from apps.institutions.models import University, Faculty, Department


class ProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), allow_null=True, required=False
    )
    identification_number = serializers.CharField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            "first_name",
            "last_name",
            "identification_number",
            "level",
            "department",
            "avatar",
            "avatar_url",
        ]

    def get_avatar(self, obj):
        if obj.avatar:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

    def get_avatar_url(self, obj):
        return self.get_avatar(obj)

    def validate_avatar(self, value):
        allowed_extensions = [".jpg", ".jpeg", ".png", ".webp"]
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                "Unsupported file type. Allowed: jpg, jpeg, png, webp."
            )
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Avatar file size must be under 10 MB.")
        return value


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    university = serializers.PrimaryKeyRelatedField(read_only=True)
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "role", "university", "name", "profile"]
        read_only_fields = ["id", "role", "university", "name"]

    def get_name(self, obj):
        profile = getattr(obj, "profile", None)
        if profile:
            full = f"{profile.first_name} {profile.last_name}".strip()
            return full if full else obj.email
        return obj.email


class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email"]

    def validate(self, attrs):
        if "role" in attrs:
            raise serializers.ValidationError({"role": "Role cannot be changed via this endpoint."})
        return attrs

    def validate_email(self, value):
        user = self.context["request"].user
        if User.objects.exclude(pk=user.pk).filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    role = serializers.ChoiceField(choices=User.Role.choices)
    university = serializers.PrimaryKeyRelatedField(queryset=University.objects.all())
    faculty = serializers.PrimaryKeyRelatedField(queryset=Faculty.objects.all())
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    identification_number = serializers.CharField(required=False, allow_blank=True)
    level = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        role = attrs.get("role")
        faculty = attrs.get("faculty")
        department = attrs.get("department")
        university = attrs.get("university")
        identification_number = attrs.get("identification_number", "").strip()
        level = attrs.get("level", "").strip()

        if department and department.faculty != faculty:
            raise serializers.ValidationError(
                {"department": "Department must belong to the selected faculty."}
            )

        if faculty and faculty.university != university:
            raise serializers.ValidationError(
                {"faculty": "Faculty must belong to the selected university."}
            )

        if role == User.Role.STUDENT:
            if not identification_number:
                raise serializers.ValidationError(
                    {"identification_number": "This field is required for students."}
                )
            if not level:
                raise serializers.ValidationError(
                    {"level": "This field is required for students."}
                )
        else:
            attrs["identification_number"] = identification_number
            attrs["level"] = level

        return attrs

    def create(self, validated):
        with transaction.atomic():
            user = User.objects.create_user(
                email=validated["email"],
                password=validated["password"],
                role=validated["role"],
                university=validated["university"],
            )
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    "first_name": validated["first_name"],
                    "last_name": validated["last_name"],
                    "identification_number": validated.get("identification_number", ""),
                    "level": validated.get("level", ""),
                    "department": validated["department"],
                },
            )
        return user


class CustomTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["email"] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user, context=self.context).data
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)
