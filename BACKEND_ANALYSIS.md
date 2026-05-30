# Acadexis Django Backend - Comprehensive Analysis

## Executive Summary

Acadexis is an **Institutional AI Knowledge Grounding SaaS** built with **Django 5 + Django REST Framework + PostgreSQL + pgvector + Celery + Django Channels**. The backend implements an AI-powered study platform that connects students with course materials, provides AI-assisted tutoring via RAG (Retrieval-Augmented Generation), tracks learning analytics, and delivers real-time notifications.

---

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [Project Architecture](#project-architecture)
3. [Authentication & Authorization](#authentication--authorization)
4. [Domain Models & Data Structure](#domain-models--data-structure)
5. [API Endpoints](#api-endpoints)
6. [View Logic & Business Logic](#view-logic--business-logic)
7. [Serialization Strategy](#serialization-strategy)
8. [Background Tasks & Async Operations](#background-tasks--async-operations)
9. [WebSocket & Real-time Features](#websocket--real-time-features)
10. [Vector Search & RAG Pipeline](#vector-search--rag-pipeline)
11. [Permissions & Access Control](#permissions--access-control)
12. [File Handling & Storage](#file-handling--storage)
13. [Third-Party Integrations](#third-party-integrations)

---

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Framework** | Django | 5.1.7 |
| **API Framework** | Django REST Framework | 3.16.1 |
| **Authentication** | djangorestframework-simplejwt | 5.5.1 |
| **Database** | PostgreSQL | 16+ (via psycopg) |
| **Vector DB** | pgvector | 0.2.5 |
| **Task Queue** | Celery | 5.3.6 |
| **Message Broker** | Redis | 5.0.1 |
| **Real-time** | Django Channels | 4.1.0 |
| **WebSocket Layer** | channels-redis | 4.2.0 |
| **ASGI Server** | Daphne | 4.1.2 |
| **PDF Processing** | pdfplumber, pypdf | 0.11.0, 4.2.0 |
| **LLM Integration** | OpenAI SDK | 1.30.1 |
| **File Storage** | django-storages (S3) | 1.14.3 |
| **CORS** | django-cors-headers | 4.9.0 |
| **App Server** | gunicorn | 22.0.0 |

### Key Dependencies
- **Image Handling**: Pillow ≥10.4.0
- **Config Management**: python-decouple 3.8
- **DB URL Parsing**: dj-database-url 3.1.2
- **Filtering**: django-filter 24.2
- **Rate Limiting**: Built-in DRF throttling

---

## Project Architecture

### Directory Structure

```
Acadexis_backend/
├── Acadexis_backend/                 # Project root config
│   ├── __init__.py
│   ├── asgi.py                       # Channels routing
│   ├── celery.py                     # Celery config
│   ├── settings.py
│   ├── urls.py                       # Main URL routing
│   ├── wsgi.py                       # Production server
│   └── settings/
│       ├── base.py                   # Shared settings
│       ├── development.py            # Dev-specific
│       └── production.py             # Prod-specific
├── apps/
│   ├── accounts/                     # User auth & profiles
│   ├── institutions/                 # University hierarchy
│   ├── courses/                      # Course materials & enrollment
│   ├── studylab/                     # AI chat & study sessions
│   ├── analytics/                    # Learning heatmap & bookmarks
│   ├── notifications/                # Real-time notifications
│   └── support/                      # Help tickets & admin requests
├── manage.py
├── requirements.txt
├── db.sqlite3                        # Dev database
├── Dockerfile                        # Container config
├── docker-compose.yml                # Local services
├── Pipfile                           # Pipenv config
├── Docs/
│   └── BACKEND_GUIDE.md              # Implementation guide
└── media/                            # Local uploads
```

### Core Settings (`settings/base.py`)

**Installed Apps**:
- Django defaults (admin, auth, contenttypes, sessions, messages, staticfiles)
- Third-party: rest_framework, simplejwt, corsheaders, django_filters, channels, storages
- Local: accounts, institutions, courses, studylab, analytics, notifications, support

**Middleware Stack**:
- CORS headers (before Django's SecurityMiddleware)
- Session & CSRF handling
- Auth & messages

**REST Framework Config**:
```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": "1000/day", "anon": "100/day"},
}
```

**JWT Configuration**:
```python
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),  # configurable via env
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),     # configurable via env
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": True,
}
```

**CORS** (Development):
```
Allowed Origins: http://localhost:3000, http://127.0.0.1:3000
Headers: accept, authorization, content-type, origin, user-agent, x-csrftoken, etc.
```

**Channels** (Real-time):
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": ["redis://localhost:6379/0"]},
    }
}
```

**Celery** (Background Jobs):
```
BROKER_URL: redis://localhost:6379/0
RESULT_BACKEND: redis://localhost:6379/0
```

---

## Authentication & Authorization

### User Model & Roles

**Custom User Model** (`apps/accounts/models.py`):
```
User (extends AbstractUser)
├── id: UUIDField (primary key)
├── email: EmailField (unique, USERNAME_FIELD)
├── role: CharField (Student | Lecturer | Admin)
├── university: ForeignKey → University
├── password: managed by AbstractUser
└── is_active, is_staff, is_superuser: inherited

Profile (OneToOne with User)
├── user: OneToOneField → User
├── first_name: CharField
├── last_name: CharField
├── identification_number: CharField (unique)
├── level: CharField (e.g., "3rd Year", "Professor")
├── department: ForeignKey → Department
└── avatar: ImageField
```

**Role System**:
- **STUDENT**: Default role, can enroll in courses, use study lab
- **LECTURER**: Can create courses, upload materials, view analytics
- **ADMIN**: Full access (managed via Django admin)

### JWT Authentication Flow

1. **Registration** (`POST /api/auth/register/`):
   - Email, password, role, university, profile info
   - Creates User + Profile atomically
   - Returns user object (no tokens)

2. **Login** (`POST /api/auth/login/`):
   - Email, password
   - Issues **access token** + **refresh token**
   - Returns user data + tokens
   - Custom JWT includes `role` and `email` claims

3. **Token Refresh** (`POST /api/auth/refresh/`):
   - Takes refresh token
   - Issues new access token
   - `ROTATE_REFRESH_TOKENS=True` → new refresh token issued

4. **Protected Endpoints**:
   - Require `Authorization: Bearer <access_token>` header
   - Verified by `JWTAuthentication`

### Permission Classes

**`apps/accounts/permissions.py`**:
```python
IsStudent: role == "student"
IsLecturer: role == "lecturer"
IsOwner: obj.user == request.user  # object-level permission
```

**`apps/courses/permissions.py`**:
```python
IsLecturerOrReadOnly:
  - Safe methods (GET, HEAD, OPTIONS) → AllowAny
  - Write methods → requires role="lecturer"
  - Object-level: obj.lecturer == request.user
```

---

## Domain Models & Data Structure

### App 1: Accounts

**User** (Custom Django User):
- Primary key: UUID
- Username field: email
- Roles: student, lecturer, admin
- Foreign key: university (set to NULL if deleted)

**Profile** (OneToOne with User):
- Links to User, Department
- Stores: first_name, last_name, identification_number, level, avatar
- Timestamps: created_at, updated_at

### App 2: Institutions

**University** (TimestampedModel):
- id: UUID
- name: CharField (unique)
- Relationships: ← Faculty (many), ← User (many via foreign key)

**Faculty** (TimestampedModel):
- id: UUID
- name: CharField
- university: ForeignKey → University
- Unique constraint: (name, university)
- Relationships: ← Department (many)

**Department** (TimestampedModel):
- id: UUID
- name: CharField
- faculty: ForeignKey → Faculty
- Unique constraint: (name, faculty)
- Relationships: ← Course (many), ← Profile (many)

**TimestampedModel** (Abstract Base):
- id: UUIDField (primary key)
- created_at: DateTimeField (auto_now_add)
- updated_at: DateTimeField (auto_now)

### App 3: Courses

**Course** (TimestampedModel):
- id: UUID
- title, code (unique), description
- department: ForeignKey → Department
- lecturer: ForeignKey → User (role="lecturer")
- thumbnail: ImageField (optional)
- level: CharField (optional, e.g., "200-level")
- lecturer_remark: TextField (optional)
- Relationships:
  - ← Enrollment (many students)
  - ← CourseMaterial (many)
  - ← CourseRating (many)
  - ← StudySession (many)

**Enrollment** (TimestampedModel):
- id: UUID
- student: ForeignKey → User
- course: ForeignKey → Course
- Unique constraint: (student, course)
- Created at: timestamp

**CourseMaterial** (TimestampedModel):
- id: UUID
- course: ForeignKey → Course
- file: FileField (uploaded PDF/document)
- file_name, file_type: CharField
- file_size: BigIntegerField (bytes)
- page_count: IntegerField (null initially, set after processing)
- status: CharField (processing | ready | failed)
- uploaded_by: ForeignKey → User (nullable)
- Relationships:
  - ← MaterialChunk (many vector embeddings)
  - ← Bookmark (many)

**MaterialChunk** (TimestampedModel, Vector-aware):
- id: UUID
- material: ForeignKey → CourseMaterial
- page: IntegerField (page number in document)
- content: TextField (text snippet, max 800 chars)
- embedding: VectorField (pgvector, dimensions=1536, text-embedding-3-small)
- Used for: RAG similarity search

**CourseRating** (TimestampedModel):
- id: UUID
- course: ForeignKey → Course
- user: ForeignKey → User
- score: PositiveSmallIntegerField (1-5)
- reaction: CharField (optional, "up"/"down")
- Unique constraint: (course, user)

### App 4: StudyLab (AI Tutoring)

**StudySession** (TimestampedModel):
- id: UUID
- user: ForeignKey → User
- course: ForeignKey → Course
- title: CharField (e.g., "Chapter 3 Questions")
- description: TextField (optional)
- confidence_score: FloatField (0.0-1.0, updated from feedback)
- Relationships:
  - ← ChatMessage (many messages in session)
  - ← SessionFeedback (many feedback records)

**ChatMessage** (TimestampedModel):
- id: UUID
- session: ForeignKey → StudySession
- role: CharField (user | assistant)
- content: TextField (question or AI response)
- Relationships:
  - ← MessageSource (many citations)
  - Indexed for search

**MessageSource** (TimestampedModel):
- id: UUID (auto increment)
- message: ForeignKey → ChatMessage
- material: ForeignKey → CourseMaterial (cited reference)
- page: IntegerField (page number)
- snippet: TextField (extracted quote, max 240 chars)

**SessionFeedback** (TimestampedModel):
- id: UUID
- session: ForeignKey → StudySession
- rating: PositiveSmallIntegerField (1-5)
- note: TextField (optional, user notes)

### App 5: Analytics

**TopicStruggle** (TimestampedModel):
- id: UUID
- course: ForeignKey → Course
- topic: CharField (extracted keyword/phrase)
- questions_asked: IntegerField (count)
- avg_confidence: FloatField (0-1)
- struggling_students: IntegerField (count)
- Purpose: Heatmap visualization

**Bookmark** (TimestampedModel):
- id: UUID
- user: ForeignKey → User
- kind: CharField (snippet | answer)
- title: CharField
- content: TextField
- material: ForeignKey → CourseMaterial (optional)
- page: IntegerField (optional)
- message: ForeignKey → ChatMessage (optional, if bookmarked from chat)

### App 6: Notifications

**Notification** (TimestampedModel):
- id: UUID
- user: ForeignKey → User
- title: CharField
- message: TextField
- type: CharField (info | success | warning | course)
- read: BooleanField (default=False)
- Sent via: WebSocket in real-time

### App 7: Support

**ContactMessage** (TimestampedModel):
- id: UUID
- user: ForeignKey → User (nullable, for anonymous)
- subject: CharField
- body: TextField
- email: EmailField
- Purpose: General contact form

**IssueReport** (TimestampedModel):
- id: UUID
- user: ForeignKey → User (nullable)
- title, description: CharField/TextField
- severity: CharField (low | medium | high | critical)
- resolved: BooleanField (default=False)
- Purpose: Bug/issue tracking

**AdminRequest** (TimestampedModel):
- id: UUID
- user: ForeignKey → User (CASCADE)
- reason: TextField
- document_proof: FileField (optional)
- status: CharField (pending | approved | rejected)
- Purpose: Lecturer/admin elevation requests

---

## API Endpoints

### Main URL Router (`Acadexis_backend/urls.py`)

```python
# DefaultRouter registration
router.register("universities", UniversityViewSet)
router.register("faculties", FacultyViewSet)
router.register("departments", DepartmentViewSet)
router.register("courses", CourseViewSet)
router.register("materials", MaterialViewSet)
router.register("sessions", StudySessionViewSet, basename="sessions")
router.register("heatmap", HeatmapViewSet, basename="heatmap")
router.register("bookmarks", BookmarkViewSet, basename="bookmarks")
router.register("notifications", NotificationViewSet, basename="notifications")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include(router.urls)),
    path("api/support/contact/", ContactView.as_view()),
    path("api/support/report/", ReportView.as_view()),
    path("api/support/admin-request/", AdminRequestView.as_view()),
]
```

### Authentication Endpoints (`/api/auth/`)

| Method | Endpoint | Auth | Input | Output |
|--------|----------|------|-------|--------|
| POST | `/register/` | AllowAny | email, password, role, university, profile | {success, user} |
| POST | `/login/` | AllowAny | email, password | {access, refresh, user} |
| POST | `/refresh/` | AllowAny | refresh_token | {access, refresh} |
| GET | `/me/` | Required | - | User object |
| PUT/PATCH | `/me/` | Required | user fields | Updated user |
| GET | `/profile/` | Required | - | Profile object |
| PUT/PATCH | `/profile/` | Required | profile fields | Updated profile |

### Institutions Endpoints

| Method | Endpoint | Auth | Perm | Action |
|--------|----------|------|------|--------|
| GET | `/universities/` | AllowAny | - | List universities |
| GET | `/universities/{id}/` | AllowAny | - | Retrieve university |
| GET | `/universities/{id}/faculties/` | AllowAny | - | List faculties in university |
| GET | `/faculties/` | AllowAny | - | List all faculties |
| GET | `/faculties/{id}/` | AllowAny | - | Retrieve faculty |
| GET | `/faculties/{id}/departments/` | AllowAny | - | List departments in faculty |
| GET | `/departments/` | AllowAny | - | List all departments |
| GET | `/departments/{id}/` | AllowAny | - | Retrieve department |

### Courses Endpoints

| Method | Endpoint | Auth | Perm | Action |
|--------|----------|------|------|--------|
| GET | `/courses/` | Required | - | List courses (filterable) |
| POST | `/courses/` | Required | IsLecturer | Create course |
| GET | `/courses/{id}/` | Required | - | Retrieve course |
| PUT/PATCH | `/courses/{id}/` | Required | IsLecturerOrReadOnly | Update course |
| DELETE | `/courses/{id}/` | Required | IsLecturerOrReadOnly | Delete course |
| GET | `/courses/mine/` | Required | - | My courses (student enrollments or lecturer's courses) |
| POST | `/courses/{id}/enroll/` | Required | - | Enroll in course |
| POST | `/courses/{id}/rate/` | Required | - | Rate course (score, reaction) |
| POST | `/materials/` | Required | IsLecturer | Upload course material (PDF) |
| GET | `/materials/` | Required | - | List materials |
| GET | `/materials/{id}/` | Required | - | Retrieve material metadata |

**Query Parameters**:
- Courses: `department`, `lecturer`, `level`, `search`, `ordering`
- Materials: `course`, `status`
- Pagination: `page`, default size=20

### StudyLab Endpoints

| Method | Endpoint | Auth | Action |
|--------|----------|------|--------|
| GET | `/sessions/` | Required | List user's study sessions |
| POST | `/sessions/` | Required | Create new session |
| GET | `/sessions/{id}/` | Required | Retrieve session details |
| PUT/PATCH | `/sessions/{id}/` | Required | Update session |
| DELETE | `/sessions/{id}/` | Required | Delete session |
| GET | `/sessions/{id}/messages/` | Required | Get all messages in session |
| POST | `/sessions/{id}/ask/` | Required | Send question, get AI response |
| POST | `/sessions/{id}/feedback/` | Required | Submit session feedback (rating, note) |

**Chat Request Format**:
```json
POST /sessions/{id}/ask/
{
  "message": "What is photosynthesis?"
}
```

**Chat Response**:
```json
{
  "user": {
    "id": "uuid",
    "role": "user",
    "content": "What is photosynthesis?",
    "sources": [],
    "timestamp": "ISO8601"
  },
  "assistant": {
    "id": "uuid",
    "role": "assistant",
    "content": "Photosynthesis is...",
    "sources": [
      {
        "page": 45,
        "snippet": "...",
        "material_name": "Chapter5.pdf"
      }
    ],
    "timestamp": "ISO8601"
  }
}
```

### Analytics Endpoints

| Method | Endpoint | Auth | Action |
|--------|----------|------|--------|
| GET | `/heatmap/` | Required | Get topic struggle heatmap (filterable by course) |
| GET | `/bookmarks/` | Required | List user's bookmarks |
| POST | `/bookmarks/` | Required | Create bookmark (snippet or answer) |
| GET | `/bookmarks/{id}/` | Required | Retrieve bookmark |
| PUT/PATCH | `/bookmarks/{id}/` | Required | Update bookmark |
| DELETE | `/bookmarks/{id}/` | Required | Delete bookmark |

**Heatmap Response**:
```json
[
  {
    "topic": "Quantum Mechanics",
    "questions_asked": 42,
    "avg_confidence": 0.68,
    "struggling_students": 12
  }
]
```

### Notifications Endpoints

| Method | Endpoint | Auth | Action |
|--------|----------|------|--------|
| GET | `/notifications/` | Required | List user's notifications |
| GET | `/notifications/{id}/` | Required | Retrieve notification |
| POST | `/notifications/{id}/read/` | Required | Mark as read |
| POST | `/notifications/read_all/` | Required | Mark all as read |

**WebSocket** (Real-time):
```
ws://localhost:8000/ws/notifications/
Connected users receive notifications pushed in real-time
```

### Support Endpoints

| Method | Endpoint | Auth | Action |
|--------|----------|------|--------|
| POST | `/support/contact/` | AllowAny | Submit contact form |
| POST | `/support/report/` | Required | Report issue (severity: low/medium/high/critical) |
| POST | `/support/admin-request/` | Required | Request admin/lecturer role (with proof document) |

---

## View Logic & Business Logic

### Accounts App Views

**RegisterView** (CreateAPIView):
- Permission: AllowAny
- Creates User + Profile in atomic transaction
- Returns success flag + user serialized data

**LoginView** (TokenObtainPairView):
- Permission: AllowAny
- Custom serializer adds `role` and `email` to JWT token
- Returns access token, refresh token, and user object

**MeView** (RetrieveUpdateAPIView):
- Permission: IsAuthenticated
- Endpoint: GET/PUT/PATCH /api/auth/me/
- Returns current user or updates user info

**ProfileView** (RetrieveUpdateAPIView):
- Permission: IsAuthenticated
- Endpoint: GET/PUT/PATCH /api/auth/profile/
- Returns or updates user's profile (first_name, last_name, etc.)

### Institutions App Views

**UniversityViewSet** (ReadOnlyModelViewSet):
- Permission: AllowAny
- Endpoints: LIST, RETRIEVE
- Custom action: `/universities/{id}/faculties/` → list faculties

**FacultyViewSet** (ReadOnlyModelViewSet):
- Permission: AllowAny
- Endpoints: LIST, RETRIEVE
- Custom action: `/faculties/{id}/departments/` → list departments

**DepartmentViewSet** (ReadOnlyModelViewSet):
- Permission: AllowAny
- Endpoints: LIST, RETRIEVE
- No custom actions

### Courses App Views

**CourseViewSet** (ModelViewSet):
- Permission: IsAuthenticated + IsLecturerOrReadOnly
- Queryset: Course.objects.select_related("lecturer", "department").all()
- Filters: department, lecturer, level
- Search: title, code, description
- Ordering: any field

**Custom Actions**:

1. **`GET /courses/mine/`** (list action):
   - Students: courses they're enrolled in
   - Lecturers: courses they teach
   - Assistants: returns QuerySet of Enrollment→Course or Course where lecturer=user

2. **`POST /courses/{id}/enroll/`** (detail action):
   - Students enroll in course
   - `get_or_create(student=request.user, course=course)`
   - Returns: {success: true}

3. **`POST /courses/{id}/rate/`** (detail action):
   - Students rate course (score 1-5, optional reaction)
   - Uses `update_or_create(user=request.user, course=course, defaults={...})`
   - Returns: {success: true}

**perform_create()**: Sets `lecturer=request.user` automatically

**MaterialViewSet** (ModelViewSet):
- Permission: IsAuthenticated (no explicit permission check on upload)
- Queryset: CourseMaterial.objects.all()
- Filters: course, status
- Parser: MultiPartParser, FormParser (for file upload)

**Custom Action: `POST /materials/`**:
- Receives: file (PDF), course_id
- Automatically extracts:
  - file_name, file_type, file_size from request.FILES["file"]
- Sets status to "processing"
- **Triggers Celery task**: `process_material.delay(str(material.id))`
  - Task runs asynchronously to extract text, chunk, embed, store vectors

### StudyLab Views

**StudySessionViewSet** (ModelViewSet):
- Permission: IsAuthenticated
- Queryset: StudySession.objects.filter(user=request.user).order_by("-created_at")
- perform_create(): sets `user=request.user`

**Custom Actions**:

1. **`GET /sessions/{id}/messages/`**:
   - Returns all ChatMessage objects for session (ordered by creation)
   - Includes prefetched `sources` (MessageSource relations)
   - Serialized with sources expanded

2. **`POST /sessions/{id}/ask/`**:
   - Request body: `{"message": "user question"}`
   - Logic:
     ```
     1. Create ChatMessage(session, role="user", content=question)
     2. Call answer_question(session, question)
        → Retrieves 5 most similar MaterialChunk vectors
        → Builds context string from chunks
        → Calls OpenAI GPT-4o-mini with system prompt + context
        → Creates ChatMessage(session, role="assistant", content=answer)
        → Creates MessageSource records linking response to citations
     3. Return both messages as JSON
     ```
   - Response includes sources with material_name, page, snippet

3. **`POST /sessions/{id}/feedback/`**:
   - Request: `{"rating": 1-5, "note": "optional text"}`
   - Saves SessionFeedback
   - Could trigger heatmap recomputation (currently not automated)

### Analytics Views

**HeatmapViewSet** (ViewSet):
- Permission: IsAuthenticated
- Query params: `course` (filter by course_id)
- Returns: list of TopicStruggle objects
- Data shows: topic, questions_asked, avg_confidence, struggling_students

**BookmarkViewSet** (ModelViewSet):
- Permission: IsAuthenticated
- Queryset: filtered to `user=request.user`
- Standard CRUD: CREATE, READ, UPDATE, DELETE
- perform_create(): sets `user=request.user`

### Notifications Views

**NotificationViewSet** (ModelViewSet):
- Permission: IsAuthenticated
- Queryset: Notification.objects.filter(user=request.user).order_by("-created_at")

**Custom Actions**:

1. **`POST /notifications/{id}/read/`**:
   - Sets `read=True` on notification
   - Returns: {success: true}

2. **`POST /notifications/read_all/`**:
   - Bulk update: `self.get_queryset().update(read=True)`
   - Returns: {success: true}

### Support Views

**ContactView** (CreateAPIView):
- Permission: AllowAny
- Creates ContactMessage (can be anonymous)
- Returns: {success: true}

**ReportView** (CreateAPIView):
- Permission: IsAuthenticated
- perform_create(): sets `user=request.user`
- Creates IssueReport

**AdminRequestView** (CreateAPIView):
- Permission: IsAuthenticated
- Parser: MultiPartParser, FormParser (file upload)
- perform_create(): sets `user=request.user`, status=PENDING
- Creates AdminRequest with optional proof document

---

## Serialization Strategy

### Accounts App Serializers

**UserSerializer**:
```
Serializes: User model
Fields: id, email, role, university, profile (nested)
Profile is read_only nested ProfileSerializer
```

**ProfileSerializer**:
```
Serializes: Profile model
Fields: first_name, last_name, identification_number, level, department, avatar
```

**RegisterSerializer**:
```
Input-only serializer (create method)
Fields: email, password (write_only), role, university, first_name, last_name,
        identification_number, level, department
Creates both User and Profile atomically
```

**CustomTokenSerializer** (extends TokenObtainPairSerializer):
```
Adds custom claims to JWT:
- token["role"] = user.role
- token["email"] = user.email
Returns: {access, refresh, user: UserSerializer(self.user)}
```

### Institutions Serializers

**UniversitySerializer**:
```
Fields: id, name
```

**FacultySerializer**:
```
Fields: id, name, university
```

**DepartmentSerializer**:
```
Fields: id, name, faculty
```

### Courses Serializers

**CourseSerializer**:
```
Fields: id, title, code, description, department, lecturer, lecturer_name,
        thumbnail, level, lecturer_remark, materials_count, students_enrolled, created_at

SerializerMethodField:
- lecturer_name: formatted as "FirstName LastName" from Profile
- materials_count: MaterialChunk.count()
- students_enrolled: Enrollment.count()
```

**CourseMaterialSerializer**:
```
Fields: id, course, file, file_name, file_type, file_size, page_count, status, created_at
Read-only: status, page_count, file_size, file_type (set by Celery task)
```

**CourseRatingSerializer**:
```
Fields: id, course, score, reaction
```

### StudyLab Serializers

**StudySessionSerializer**:
```
Fields: id, user, course, title, description, confidence_score, created_at
Read-only: user, confidence_score
```

**ChatMessageSerializer**:
```
Fields: id, role, content, sources, timestamp
Nested: sources (MessageSourceSerializer many=True, read_only)
SerializerMethodField: timestamp = created_at
```

**MessageSourceSerializer**:
```
Fields: page, snippet, material_name
SerializerMethodField: material_name = material.file_name
```

**FeedbackSerializer**:
```
Fields: session, rating, note
```

### Analytics Serializers

**HeatmapSerializer**:
```
Fields: topic, questions_asked, avg_confidence, struggling_students
```

**BookmarkSerializer**:
```
Fields: id, kind, title, content, material, page, message, created_at
```

### Notifications Serializer

**NotificationSerializer**:
```
Fields: id, user, title, message, type, read, created_at
```

### Support Serializers

**ContactSerializer**:
```
Fields: subject, body, email
```

**ReportSerializer**:
```
Fields: title, description, severity
```

**AdminRequestSerializer**:
```
Fields: reason, document_proof, status
Read-only: status (set by admin)
```

---

## Background Tasks & Async Operations

### Celery Configuration (`Acadexis_backend/celery.py`)

```python
app = Celery("acadexis")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

**Settings** (from `settings/development.py`):
```
CELERY_BROKER_URL = redis://localhost:6379/0
CELERY_RESULT_BACKEND = redis://localhost:6379/0
```

### Courses App: Material Processing Task (`apps/courses/tasks.py`)

**`process_material(material_id: str)`** (@shared_task):

**Trigger**: When MaterialViewSet receives POST /materials/ with PDF file

**Flow**:
1. Fetch CourseMaterial by ID
2. Open PDF with `pdfplumber`
3. Extract text from each page
4. **Chunk Strategy**:
   - CHUNK_SIZE = 800 characters
   - CHUNK_OVERLAP = 100 characters
   - Prevents losing context at boundaries

5. **Embedding**:
   - For each chunk, call OpenAI text-embedding-3-small
   - Batch process: 100 chunks at a time (to manage API costs)
   - Get 1536-dimensional vectors

6. **Storage**:
   - Bulk create MaterialChunk records
   - Each chunk: `(page, content, embedding)`

7. **Status Management**:
   - Success: `status = "ready"`
   - Failure: `status = "failed"`
   - Max retries: 3 (with 30-second countdown between retries)

**Error Handling**: Celery auto-retry with exponential backoff

### Analytics App: Heatmap Recomputation (`apps/analytics/tasks.py`)

**`recompute_heatmap(course_id)`** (@shared_task):

**Logic**:
1. Query all ChatMessage objects where role="user" in course_id
2. Extract "topic" from first 3 words of each question (naive implementation)
3. Group by topic key
4. Count:
   - questions_asked: total questions on topic
   - struggling_students: unique students asking about topic
   - avg_confidence: placeholder (0.5)

5. Delete old TopicStruggle records for course
6. Bulk create new TopicStruggle records

**Note**: Currently not auto-triggered; would need manual call or scheduling

---

## WebSocket & Real-time Features

### Channels Configuration (`Acadexis_backend/asgi.py`)

```python
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
```

- HTTP requests → standard Django ASGI
- WebSocket connections → authenticated via AuthMiddlewareStack
- Routed through `websocket_urlpatterns` from notifications.routing

### Notifications Consumer (`apps/notifications/consumers.py`)

**NotificationConsumer** (AsyncJsonWebsocketConsumer):

**connect()**:
```
1. Check if user is anonymous → close connection
2. Create group name: f"user_{user.id}"
3. Add channel to group: channel_layer.group_add(group, channel_name)
4. Accept connection
```

**disconnect(code)**:
```
Remove channel from group: channel_layer.group_discard(group, channel_name)
```

**async notify(event)**:
```
Handler for group messages
Receives event["payload"] and sends as JSON to WebSocket
```

### Notifications Routing (`apps/notifications/routing.py`)

```python
websocket_urlpatterns = [
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi())
]
```

**Client Connection**:
```
ws://localhost:8000/ws/notifications/
```

### How Notifications Are Sent

1. When notification needs to be sent (e.g., new course assignment):
   ```python
   from channels.layers import get_channel_layer
   import asyncio
   
   channel_layer = get_channel_layer()
   asyncio.run(channel_layer.group_send(
       f"user_{user_id}",
       {
           "type": "notify",  # Maps to notify() method
           "payload": {
               "title": "New Assignment",
               "message": "You have a new assignment in Course XYZ",
               "type": "course"
           }
       }
   ))
   ```

2. Consumer receives via group and sends to connected WebSocket client

**Note**: Notifications are also stored in DB (Notification model) for persistence

---

## Vector Search & RAG Pipeline

### pgvector Integration

**Database**:
- PostgreSQL with pgvector extension
- VectorField from pgvector.django

### Material Chunking Strategy

**In `apps/courses/tasks.py`**:

```python
def chunk_text(text: str):
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + CHUNK_SIZE])
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks
```

- Chunk size: 800 characters
- Overlap: 100 characters
- Purpose: Provide context without excessive redundancy

### Embedding Generation

**OpenAI text-embedding-3-small**:
- Model: "text-embedding-3-small"
- Dimensions: 1536
- Batching: 100 chunks per API call (cost optimization)

### RAG Query Flow (`apps/studylab/services.py`)

**`answer_question(session, question: str) -> ChatMessage`**:

1. **Retrieval** (`retrieve(course_id, question, k=5)`):
   ```python
   # Embed the question
   qvec = client.embeddings.create(
       model="text-embedding-3-small",
       input=[question]
   ).data[0].embedding
   
   # Vector similarity search
   chunks = MaterialChunk.objects \
       .filter(material__course_id=course_id, material__status="ready") \
       .annotate(distance=CosineDistance("embedding", qvec)) \
       .order_by("distance")[:k] \
       .select_related("material")
   ```
   - Uses cosine distance (pgvector CosineDistance)
   - Returns top-5 most relevant chunks

2. **Context Building**:
   ```python
   context = "\n\n".join(
       f"[{chunk.material.file_name} p.{chunk.page}]\n{chunk.content}"
       for chunk in chunks
   )
   ```
   - Format: `[Filename p.PageNum]\nContent`
   - Each chunk separated by 2 newlines

3. **LLM Completion** (GPT-4o-mini):
   ```python
   completion = client.chat.completions.create(
       model="gpt-4o-mini",
       messages=[
           {"role": "system", "content": SYSTEM_PROMPT},
           {
               "role": "user",
               "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"
           }
       ],
       temperature=0.2,  # Lower = more deterministic
   )
   answer = completion.choices[0].message.content
   ```

   **System Prompt**:
   ```
   "You are Acadexis, an academic AI tutor.
   ONLY answer using the provided course context. Cite page numbers.
   If the context lacks the answer, say so plainly."
   ```

4. **Store Response & Citations**:
   ```python
   msg = ChatMessage.objects.create(
       session=session,
       role="assistant",
       content=answer
   )
   MessageSource.objects.bulk_create([
       MessageSource(
           message=msg,
           material=chunk.material,
           page=chunk.page,
           snippet=chunk.content[:240]
       )
       for chunk in chunks
   ])
   ```

### Indexing Strategy

**Explicit**:
- Vectors are computed and stored at upload time via Celery task
- No automatic background indexing

**Performance**:
- pgvector's cosine distance is natively optimized
- Batch operations for bulk_create (100 chunks per operation)

---

## Permissions & Access Control

### DRF Default Permissions

**Base** (`settings/base.py`):
```
DEFAULT_PERMISSION_CLASSES = ("rest_framework.permissions.IsAuthenticated",)
```

Most endpoints require authentication by default.

### Custom Permission Classes

#### `apps/accounts/permissions.py`

**IsStudent**:
```python
def has_permission(self, request, view):
    return request.user.is_authenticated and request.user.role == "student"
```

**IsLecturer**:
```python
def has_permission(self, request, view):
    return request.user.is_authenticated and request.user.role == "lecturer"
```

**IsOwner** (object-level):
```python
def has_object_permission(self, request, view, obj):
    return getattr(obj, "user", None) == request.user
```

#### `apps/courses/permissions.py`

**IsLecturerOrReadOnly**:
```python
def has_permission(self, request, view):
    if request.method in permissions.SAFE_METHODS: return True
    return request.user.is_authenticated and request.user.role == "lecturer"

def has_object_permission(self, request, view, obj):
    if request.method in permissions.SAFE_METHODS: return True
    return obj.lecturer == request.user
```

### Permission Application by Endpoint

| Resource | GET (List/Retrieve) | POST (Create) | PUT/PATCH (Update) | DELETE |
|----------|-----|-----|-----|-----|
| **Universities, Faculties, Departments** | AllowAny | - | - | - |
| **Courses** | IsAuthenticated | IsLecturer | IsLecturerOrReadOnly | IsLecturerOrReadOnly |
| **Enrollments** | IsAuthenticated | IsStudent | - | - |
| **Materials** | IsAuthenticated | IsLecturer | IsLecturer | IsLecturer |
| **StudySessions** | IsAuthenticated | IsAuthenticated | IsAuthenticated | IsAuthenticated |
| **Messages/Chat** | IsAuthenticated | IsAuthenticated | - | - |
| **Bookmarks** | IsAuthenticated | IsAuthenticated | IsAuthenticated | IsAuthenticated |
| **Notifications** | IsAuthenticated | - | IsAuthenticated | - |
| **Support (Contact)** | - | AllowAny | - | - |
| **Support (Report)** | - | IsAuthenticated | - | - |
| **Support (AdminRequest)** | - | IsAuthenticated | - | - |

### User Scope Filtering

**Automatic filtering** in viewsets:

```python
# StudySession
def get_queryset(self):
    return StudySession.objects.filter(user=self.request.user)

# Bookmark
def get_queryset(self):
    return Bookmark.objects.filter(user=self.request.user)

# Notification
def get_queryset(self):
    return Notification.objects.filter(user=self.request.user)
```

Users can only see their own data.

### Admin & Superuser

- Django admin: `/admin/`
- Managed via `is_staff` and `is_superuser` flags
- Lecturers can be promoted via AdminRequest model (admin approval required)

---

## File Handling & Storage

### Local Development (`settings/development.py`)

```
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

Files served locally from `media/` directory.

**URL mapping** in `urls.py`:
```python
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### Production (`settings/production.py`)

Would use django-storages with S3:
```python
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME")
```

### File Types Handled

**Course Materials**:
- PDFs (primary)
- Extracted via pdfplumber
- Stored in: `media/materials/`

**User Avatars**:
- Images
- Stored in: `media/avatars/`

**Admin Proofs**:
- For admin requests
- Stored in: `media/admin_proofs/`

### Upload Parsers

```python
from rest_framework.parsers import MultiPartParser, FormParser

# In MaterialViewSet, AdminRequestView
parser_classes = [MultiPartParser, FormParser]
```

Enables form-data with file uploads.

---

## Third-Party Integrations

### OpenAI Integration (`apps/studylab/services.py`, `apps/courses/tasks.py`)

**Embeddings**:
- Model: `text-embedding-3-small`
- Dimensions: 1536
- Used for: Chunking and storing vectors for RAG

**Chat Completion** (RAG):
- Model: `gpt-4o-mini`
- Temperature: 0.2 (deterministic)
- System prompt: Academic tutor with citation requirement
- Context: Top-5 relevant course materials

**Configuration**:
```python
from openai import OpenAI
from django.conf import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)
```

**API Key**:
- Source: `OPENAI_API_KEY` from environment
- Must be set for embeddings and chat to work

### Django Channels & Redis

**Real-time Notifications**:
- Channel layers: `channels_redis.core.RedisChannelLayer`
- Broker: Redis (same instance as Celery)
- Protocol: WebSocket

### django-cors-headers

**Configuration**:
```
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # Next.js dev server
    "http://127.0.0.1:3000",
]
```

**Headers**:
```
accept, authorization, content-type, origin, user-agent, x-csrftoken, etc.
```

### django-filter

**Filterable fields**:
- Courses: department, lecturer, level
- Materials: course, status
- Query params: `?course=uuid&status=ready`

### django-storages

**S3 Integration** (production):
- boto3 backend
- Used for avatars, materials, admin proofs
- Not active in development (uses local filesystem)

---

## Key Design Patterns & Architectural Insights

### 1. **App-Based Modular Design**
Each app is independent:
- Accounts: authentication
- Institutions: organizational hierarchy
- Courses: curriculum management
- StudyLab: AI tutoring engine
- Analytics: learner analytics
- Notifications: real-time alerts
- Support: user support

**Benefit**: Easy to scale, test, and maintain independently.

### 2. **RAG (Retrieval-Augmented Generation) Architecture**
- **Retrieval**: Vector similarity search on material chunks
- **Augmentation**: Context fed to LLM
- **Generation**: LLM answers grounded in course materials
- **Citations**: Automatic source attribution

**Key Insight**: Prevents hallucinations by limiting LLM to course context only.

### 3. **Async PDF Processing Pipeline**
- Upload → Celery task
- Task: Extract → Chunk → Embed → Store
- Batched embeddings (100 at a time) for cost efficiency
- Automatic retry on failure

**Benefit**: Non-blocking uploads; users don't wait for processing.

### 4. **Role-Based Access Control (RBAC)**
- Three roles: Student, Lecturer, Admin
- JWT tokens include role claim
- Custom permissions enforce role rules
- Automatic user-scope filtering

### 5. **Real-time Notification System**
- WebSocket consumer per user
- Redis-backed group messaging
- Persistent DB fallback (Notification model)
- Push on-demand via group_send()

### 6. **Multi-environment Configuration**
- `settings/base.py`: shared config
- `settings/development.py`: SQLite, local Redis, console email
- `settings/production.py`: PostgreSQL, S3 storage, SendGrid email

**Benefit**: One codebase, multiple deployment targets.

### 7. **Atomic Transaction Safety**
- User + Profile creation: `transaction.atomic()`
- Prevents inconsistent state if one fails

### 8. **Pagination & Throttling**
- Default page size: 20
- User throttle: 1000 requests/day
- Anonymous throttle: 100 requests/day
- Prevents abuse and manages load

### 9. **Vector Semantics**
- pgvector for persistence
- Cosine distance for similarity
- Batched embedding calls for efficiency
- Overlap strategy prevents context loss

### 10. **Audit Trail & Timestamps**
- All TimestampedModels have created_at, updated_at
- User tracking: who uploaded, who requested
- Enables compliance and debugging

---

## Summary Table: Apps & Key Components

| App | Models | Views | Tasks | Consumers | Key Feature |
|-----|--------|-------|-------|-----------|-------------|
| **accounts** | User, Profile | Register, Login, Me, Profile | - | - | JWT auth, role-based |
| **institutions** | University, Faculty, Department | ReadOnly ViewSets | - | - | Org hierarchy |
| **courses** | Course, Enrollment, CourseMaterial, MaterialChunk, CourseRating | Course, Material ViewSets | process_material | - | PDF upload + embedding |
| **studylab** | StudySession, ChatMessage, MessageSource, SessionFeedback | StudySession ViewSet | - | - | AI RAG chat, citations |
| **analytics** | TopicStruggle, Bookmark | Heatmap, Bookmark ViewSets | recompute_heatmap | - | Learning analytics |
| **notifications** | Notification | NotificationViewSet | - | NotificationConsumer | Real-time push |
| **support** | ContactMessage, IssueReport, AdminRequest | Contact, Report, AdminRequest Views | - | - | User support |

---

## Deployment Considerations

### Environment Variables Required

```bash
DEBUG=False
SECRET_KEY=<strong-random-key>
DJANGO_SETTINGS_MODULE=Acadexis_backend.settings.production
DATABASE_URL=postgres://<user>:<pass>@<host>:5432/<db>
REDIS_URL=redis://<host>:6379/0
OPENAI_API_KEY=sk-<key>
AWS_ACCESS_KEY_ID=<id>
AWS_SECRET_ACCESS_KEY=<key>
AWS_STORAGE_BUCKET_NAME=<bucket>
FRONTEND_ORIGIN=https://acadexis.example.com
```

### Production Servers

- **ASGI**: Daphne (handles WebSockets)
- **WSGI**: gunicorn (traditional HTTP)
- **Task Worker**: Celery with Redis broker
- **Database**: PostgreSQL 16+ with pgvector extension

### Docker

Provided Dockerfile and docker-compose.yml for containerization.

---

## Security Considerations

1. **JWT Expiry**: 60 minutes (configurable)
2. **Token Rotation**: Refresh tokens rotate on use
3. **HTTPS**: Should be enforced in production
4. **CSRF**: Built-in Django protection
5. **Rate Limiting**: 1000 requests/day per user
6. **File Validation**: Filename/type extracted, but no explicit validation
7. **LLM Constraints**: System prompt enforces citation requirement

---

## Next Steps & Potential Enhancements

1. **File Validation**: Add size limits and mime-type validation
2. **WebSocket Auth**: Implement per-message auth refresh
3. **Caching**: Redis caching for frequently accessed queries
4. **Search**: Full-text search (PostgreSQL FTS or Elasticsearch)
5. **Pagination**: Cursor-based pagination for large datasets
6. **Audit Logging**: Store all API calls for compliance
7. **Analytics Dashboard**: Internal admin views for system monitoring
8. **Scheduling**: Automated heatmap recomputation (Celery beat)
9. **Multi-tenancy**: Support for multiple institutions
10. **API Documentation**: Swagger/OpenAPI generation

