# Copilot Prompt — Acadexis Backend: User / Profile Endpoint Fixes

---

## Context

This is the Django REST Framework backend (`Django 5.1.7`, `djangorestframework-simplejwt 5.5.1`) for **Acadexis**. The relevant Django app is `accounts`. A contract audit has revealed gaps between what the frontend expects from user/profile endpoints and what the backend currently provides or is structured to return.

The files in scope are:
- `accounts/models.py` — User and Profile models
- `accounts/serializers.py` — DRF serializers
- `accounts/views.py` — views for user/profile endpoints
- `accounts/urls.py` — URL routing (already fixed to live under `/api/auth/` from the auth prompt)

Do not change anything already working. Only address the items listed below.

---

## The agreed data model

The backend has two related models. Confirm they match this exact structure before touching serializers or views:

```
User (accounts.User)
├── id: UUID (primary key, auto-generated)
├── email: EmailField (unique) — used as USERNAME_FIELD
├── password: (hashed, managed by Django)
├── role: CharField, choices=["student", "lecturer", "admin"]
├── is_active: BooleanField (default True)
├── is_staff: BooleanField (default False)
├── is_superuser: BooleanField (default False)
├── university: ForeignKey → institutions.University (nullable=False on creation)
├── first_name: CharField
├── last_name: CharField
├── created_at: DateTimeField (auto_now_add)
└── updated_at: DateTimeField (auto_now)

Profile (accounts.Profile)
├── user: OneToOneField → User (related_name="profile", cascade on delete)
├── first_name: CharField
├── last_name: CharField
├── identification_number: CharField (unique)
├── level: CharField (e.g. "3rd Year", "Professor", "PhD Candidate")
├── department: ForeignKey → institutions.Department (nullable=True)
└── avatar: ImageField (upload_to="avatars/", nullable=True, blank=True)
```

If `first_name` and `last_name` exist on both `User` and `Profile`, that is intentional — `User` holds them for Django's built-in auth machinery, `Profile` is the editable copy exposed to the API. Keep both.

If a `Profile` record does not auto-create when a `User` is created, add a `post_save` signal in `accounts/signals.py` to create it:

```python
# accounts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, Profile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
```

Register this signal in `accounts/apps.py`:

```python
class AccountsConfig(AppConfig):
    ...
    def ready(self):
        import accounts.signals  # noqa
```

---

## Fix 1: `UserSerializer` — the canonical user response shape

Create or update a `UserSerializer` in `accounts/serializers.py` that produces this exact output. This shape is used by login, register, `GET /api/auth/me/`, and anywhere a full user object is returned:

```json
{
  "id": "uuid",
  "email": "john.doe@university.edu",
  "role": "student",
  "university": "uuid",
  "profile": {
    "first_name": "John",
    "last_name": "Doe",
    "identification_number": "STU2024001",
    "level": "3rd Year",
    "department": "uuid",
    "avatar": "https://s3.amazonaws.com/avatars/uuid/avatar.jpg"
  }
}
```

Rules:
- `university` must serialize as the UUID string, not a nested object
- `profile.department` must serialize as the UUID string, not a nested object
- `profile.avatar` must return an absolute URL (use `serializers.SerializerMethodField` and `request.build_absolute_uri` if needed)
- `id`, `email`, `role`, and `university` are **read-only** in this serializer
- Do **not** include `password`, `is_staff`, `is_superuser`, `created_at`, or `updated_at` in the output

```python
# accounts/serializers.py

class ProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Profile
        fields = ["first_name", "last_name", "identification_number", "level", "department", "avatar"]

    def get_avatar(self, obj):
        if obj.avatar:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    university = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "role", "university", "profile"]
        read_only_fields = ["id", "role", "university"]
```

---

## Fix 2: `GET /api/auth/me/` — return the full user object

**View:** `CurrentUserView` in `accounts/views.py`
**Permission:** `IsAuthenticated`

```python
class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context
```

Expected `GET` response (200):

```json
{
  "id": "uuid",
  "email": "john.doe@university.edu",
  "role": "student",
  "university": "uuid",
  "profile": {
    "first_name": "John",
    "last_name": "Doe",
    "identification_number": "STU2024001",
    "level": "3rd Year",
    "department": "uuid",
    "avatar": null
  }
}
```

---

## Fix 3: `PATCH /api/auth/me/` — update email only

The `PATCH /api/auth/me/` endpoint allows the user to update only their `email`. Profile fields (name, avatar, level, department) are updated via `PATCH /api/auth/profile/` instead (Fix 4).

Create a separate write serializer to prevent accidental field exposure:

```python
class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email"]

    def validate_email(self, value):
        user = self.context["request"].user
        if User.objects.exclude(pk=user.pk).filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
```

In the `CurrentUserView`, use `UserSerializer` for GET and `UpdateUserSerializer` for PATCH:

```python
def get_serializer_class(self):
    if self.request.method in ("PATCH", "PUT"):
        return UpdateUserSerializer
    return UserSerializer
```

After a successful PATCH, return the full user object using `UserSerializer`, not just the updated field:

```python
def partial_update(self, request, *args, **kwargs):
    instance = self.get_object()
    serializer = UpdateUserSerializer(instance, data=request.data, partial=True, context={"request": request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(UserSerializer(instance, context={"request": request}).data)
```

---

## Fix 4: `GET /api/auth/profile/` and `PATCH /api/auth/profile/`

This endpoint manages the `Profile` model directly. It must support:
- `GET` — returns the profile fields only (not the full user object)
- `PATCH` — partial update, accepts `first_name`, `last_name`, `level`, `department` (UUID), and `avatar` (file)

```python
class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # Required for file upload

    def get_object(self):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
```

Expected `GET /api/auth/profile/` response (200):

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "identification_number": "STU2024001",
  "level": "3rd Year",
  "department": "uuid",
  "avatar": "http://localhost:8000/media/avatars/uuid/avatar.jpg"
}
```

Expected `PATCH /api/auth/profile/` request (multipart/form-data):

```
first_name: "Johnny"
last_name: "Smith"
level: "4th Year"
department: "uuid-of-department"
avatar: <image file>
```

Expected `PATCH` response (200): same shape as GET with updated values.

Avatar upload rules:
- Allowed extensions: `.jpg`, `.jpeg`, `.png`, `.webp`
- Max file size: 10 MB
- Validate both in the serializer's `validate_avatar` method

```python
def validate_avatar(self, value):
    allowed_extensions = [".jpg", ".jpeg", ".png", ".webp"]
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in allowed_extensions:
        raise serializers.ValidationError("Unsupported file type. Allowed: jpg, jpeg, png, webp.")
    if value.size > 10 * 1024 * 1024:
        raise serializers.ValidationError("Avatar file size must be under 10 MB.")
    return value
```

---

## Fix 5: `identification_number` must not be updatable via `PATCH /api/auth/profile/`

Once set on registration, `identification_number` is read-only. Enforce this in the `ProfileSerializer`:

```python
class ProfileSerializer(serializers.ModelSerializer):
    identification_number = serializers.CharField(read_only=True)
    ...
```

If `identification_number` has not been set yet (empty string), allow it to be set once but not changed after that. Add a custom `validate_identification_number` method if this logic is needed.

---

## Fix 6: `name` field — provide a computed `name` on the user object

The frontend's `apiService.ts` references a `name` field on the user object (used in header/navbar display). Add it as a computed read-only field in `UserSerializer`:

```python
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
```

---

## Fix 7: `avatarUrl` alias — add it to the profile response

The frontend references both `avatar` and `avatarUrl` in different places. Include both in the `ProfileSerializer` to avoid breaking either reference:

```python
class ProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()  # alias

    def get_avatar(self, obj):
        # ... same logic as before

    def get_avatar_url(self, obj):
        return self.get_avatar(obj)  # identical value, different key name

    class Meta:
        model = Profile
        fields = [
            "first_name", "last_name", "identification_number",
            "level", "department", "avatar", "avatar_url"
        ]
```

---

## Fix 8: Ensure all user/profile endpoints are in `accounts/urls.py`

After all fixes, the following URL entries must exist under the `/api/auth/` prefix (set in the root `urls.py`). These complement the auth-specific routes from the previous prompt:

```python
# accounts/urls.py (user/profile additions)
urlpatterns = [
    ...  # auth routes from previous prompt
    path("me/",       views.CurrentUserView.as_view(),  name="auth-me"),
    path("profile/",  views.ProfileView.as_view(),      name="auth-profile"),
]
```

Confirm these are not duplicated — if they were added in the previous auth prompt already, verify they point to the corrected views described here.

---

## Fix 9: Role-based field restrictions

- A `student` must not be able to change their own `role` field under any circumstances via any endpoint.
- A `lecturer` must not be able to change their `role` to `admin`.
- Only a user with `role = "admin"` (or `is_superuser = True`) may change roles, and only via the Django admin or a dedicated admin endpoint (not in scope here).

Enforce this in `UpdateUserSerializer`:

```python
def validate(self, attrs):
    if "role" in attrs:
        raise serializers.ValidationError({"role": "Role cannot be changed via this endpoint."})
    return attrs
```

---

## Fix 10: Error response shapes

All validation errors from user/profile endpoints must return in DRF's standard field-error format:

```json
// 400 — email already taken
{ "email": ["A user with this email already exists."] }

// 400 — avatar too large
{ "avatar": ["Avatar file size must be under 10 MB."] }

// 400 — unsupported avatar format
{ "avatar": ["Unsupported file type. Allowed: jpg, jpeg, png, webp."] }

// 401 — no token
{ "detail": "Authentication credentials were not provided." }
```

Do not wrap errors in a custom envelope. DRF's default error format is what the frontend expects.

---

## General Rules

- All response field names must be `snake_case`. Never return camelCase from a serializer.
- All endpoints require `Authorization: Bearer <token>`. Return `401` for missing/invalid tokens.
- Pass `request` in serializer context wherever `build_absolute_uri` is needed for avatar URLs.
- Do not modify model migrations unless a new field is being added. If `Profile` already exists, only add signal logic or serializer logic as needed.
- Do not change any course, institution, or other app's models or views.
