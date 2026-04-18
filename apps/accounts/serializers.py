from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import transaction
from .models import User, Profile
from apps.institutions.models import University, Department

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["first_name", "last_name", "identification_number",
                  "level", "department", "avatar"]

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    class Meta:
        model = User
        fields = ["id", "email", "role", "university", "profile"]

class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    role = serializers.ChoiceField(choices=User.Role.choices)
    university = serializers.PrimaryKeyRelatedField(queryset=University.objects.all())
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    identification_number = serializers.CharField()
    level = serializers.CharField(required=False, allow_blank=True)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())

    def create(self, validated):
        with transaction.atomic():
            user = User.objects.create_user(
                email=validated["email"],
                password=validated["password"],
                role=validated["role"],
                university=validated["university"],
            )
            Profile.objects.create(
                user=user,
                first_name=validated["first_name"],
                last_name=validated["last_name"],
                identification_number=validated["identification_number"],
                level=validated.get("level", ""),
                department=validated["department"],
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
        data["user"] = UserSerializer(self.user).data
        return data