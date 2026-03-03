from rest_framework import serializers
from .models import User, Profile, AdminRequest
from core.models import University, Department

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['first_name', 'last_name', 'bio', 'department', 'identification_number', 'level', 'avatar']

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'role', 'university', 'profile']

class RegisterSerializer(serializers.ModelSerializer):
    # Define only the allowed roles for public signup
    PUBLIC_ROLES = (
        (User.Role.LECTURER, 'Lecturer'),
        (User.Role.STUDENT, 'Student'),
    )
    
    role = serializers.ChoiceField(choices=PUBLIC_ROLES)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'role', 'university', 'first_name', 'last_name']

    def create(self, validated_data):
        # The logic remains the same, but 'admin' is no longer an option
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data['role'],
            university=validated_data.get('university')
        )
        
        profile = user.profile
        profile.first_name = first_name
        profile.last_name = last_name
        profile.save()
        
        return user

class AdminRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminRequest
        fields = ['id', 'user', 'reason', 'document_proof', 'status', 'created_at']
        read_only_fields = ['user', 'status', 'created_at']

    def create(self, validated_data):
        # Automatically associate the request with the logged-in user
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)