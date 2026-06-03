# Acadexis Backend — Frontend Developer Handover Guide

> **For Next.js Frontend Development**
> 
> This is a comprehensive technical handover document that describes the Acadexis Django REST API, its structure, authentication, endpoints, data models, and integration patterns for Next.js frontend development.

**Last Updated:** May 27, 2026  
**Backend Version:** Django 5.1.7 + DRF 3.16.1  
**Target Frontend:** Next.js with React

---

## 📋 Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Tech Stack & Dependencies](#2-tech-stack--dependencies)
3. [API Base Configuration](#3-api-base-configuration)
4. [Authentication (JWT + Role-Based Access)](#4-authentication-jwt--role-based-access)
5. [Data Models & Relationships](#5-data-models--relationships)
6. [API Endpoints Reference](#6-api-endpoints-reference)
7. [Real-Time Features (WebSockets)](#7-real-time-features-websockets)
8. [File Upload & Storage](#8-file-upload--storage)
9. [AI/RAG Chat System](#9-airag-chat-system)
10. [Error Handling & Status Codes](#10-error-handling--status-codes)
11. [Rate Limiting & Pagination](#11-rate-limiting--pagination)
12. [CORS Configuration](#12-cors-configuration)
13. [Frontend Integration Examples](#13-frontend-integration-examples)
14. [Deployment & Environment Variables](#14-deployment--environment-variables)
15. [Common Troubleshooting](#15-common-troubleshooting)

---

## 1. Architecture Overview

The Acadexis backend is a **Django REST Framework (DRF)** API with a modular, app-based architecture. It serves a Next.js frontend with REST endpoints, real-time WebSocket capabilities, and AI-powered RAG (Retrieval-Augmented Generation) chat.

### High-Level Flow

```
Next.js Frontend
    ↓ (HTTP REST + WebSocket)
    ↓
Django REST API (Port 8000)
    ↓
PostgreSQL DB + pgvector
Redis (Celery + WebSocket broker)
OpenAI API (LLM + Embeddings)
AWS S3 (Media storage, prod only)
```

### Core Features

| Feature | Tech | Purpose |
|---------|------|---------|
| **Authentication** | JWT (SimpleJWT) | Stateless token-based auth |
| **API Framework** | Django REST Framework | RESTful API structure |
| **Database** | PostgreSQL + pgvector | Relational + vector storage |
| **Async Tasks** | Celery + Redis | PDF processing, background jobs |
| **Real-Time** | Django Channels + Redis | WebSocket notifications |
| **AI/RAG** | OpenAI Embeddings + GPT-4o-mini | Intelligent tutoring |
| **File Storage** | S3 (prod) / Local (dev) | Media & PDF uploads |

---

## 2. Tech Stack & Dependencies

### Backend Stack

```
Framework:           Django 5.1.7
API:                 Django REST Framework 3.16.1
Authentication:      djangorestframework-simplejwt 5.5.1
Database:            PostgreSQL 16 + pgvector 0.2.5
Async:               Celery 5.3.6 + Redis 5.0.1
Real-Time:           Django Channels 4.1.0 + channels-redis 4.2.0
Web Server (Prod):   Daphne 4.1.2 / Gunicorn 22.0.0
CORS:                django-cors-headers 4.9.0
Storage:             django-storages 1.14.3 (S3 support)
PDF Processing:      pypdf 4.2.0 + pdfplumber 0.11.0
AI:                  openai 1.30.1
Utilities:           python-decouple, Pillow, python-multipart
```

### Key Library Versions (Critical for Compatibility)

- **PostgreSQL**: Must have pgvector extension installed
- **Redis**: Required for Celery and WebSocket message broker
- **OpenAI API Key**: Required for chat + embeddings
- **AWS Credentials**: Required for S3 (production only)

---

## 3. API Base Configuration

### Base URL

```
Development:  http://localhost:8000/api/
Production:   https://api.acadexis.com/api/  (varies by deployment)
```

### API Versioning

Currently **not versioned** (single version). If you need to support multiple versions in the future, consider adding `/api/v1/` prefix.

### Request/Response Format

All requests and responses use **JSON** with UTF-8 encoding.

```javascript
// Request
POST /api/courses/
Content-Type: application/json
Authorization: Bearer {access_token}

{
  "title": "Introduction to Python",
  "code": "CS101",
  "description": "Learn Python basics",
  "department": "uuid-of-department",
  "level": "100"
}

// Response (201 Created)
{
  "id": "uuid",
  "title": "Introduction to Python",
  "code": "CS101",
  "description": "Learn Python basics",
  "department": "uuid-of-department",
  "lecturer": "uuid-of-lecturer",
  "level": "100",
  "created_at": "2024-05-27T10:30:00Z",
  "updated_at": "2024-05-27T10:30:00Z"
}
```

### HTTP Headers (Required)

```javascript
{
  "Content-Type": "application/json",
  "Authorization": "Bearer {access_token}",  // For authenticated endpoints
  "Accept": "application/json"
}
```

---

## 4. Authentication (JWT + Role-Based Access)

### Overview

Acadexis uses **JWT (JSON Web Tokens)** with role-based access control. Every user has a **role** (student, lecturer, or admin) encoded in the token.

### JWT Token Structure

```javascript
// Access Token (60 minutes default)
{
  "token_type": "access",
  "exp": 1234567890,          // Unix timestamp (60 min from issue)
  "iat": 1234567890,          // Issued at
  "jti": "...",
  "user_id": "uuid",
  "email": "student@uni.edu",
  "role": "student"           // ← Critical for frontend routing
}

// Refresh Token (7 days default)
{
  "token_type": "refresh",
  "exp": 1234567890,
  "iat": 1234567890,
  "jti": "...",
  "user_id": "uuid"
}
```

### Endpoint: Register

**POST** `/api/auth/register/`

```javascript
// Request
{
  "email": "john.doe@university.edu",
  "password": "SecurePass123!",      // Min 8 chars
  "role": "student",                  // "student" | "lecturer" | "admin"
  "university": "uuid",               // Get from /api/universities/
  "first_name": "John",
  "last_name": "Doe",
  "identification_number": "STU2024001",  // Unique per institution
  "level": "3rd Year",                // Or "Professor", etc.
  "department": "uuid"                // Get from /api/departments/
}

// Response (201 Created)
{
  "success": true,
  "user": {
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
}
```

### Endpoint: Login

**POST** `/api/auth/login/`

```javascript
// Request
{
  "email": "john.doe@university.edu",
  "password": "SecurePass123!"
}

// Response (200 OK)
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": "uuid",
    "email": "john.doe@university.edu",
    "role": "student",
    "university": "uuid",
    "profile": { ... }
  }
}
```

### Endpoint: Refresh Token

**POST** `/api/auth/token/refresh/`

```javascript
// Request
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}

// Response (200 OK)
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."  // Rotated
}
```

### Endpoint: Get Current User

**GET** `/api/auth/me/`

```javascript
// Response (200 OK)
{
  "id": "uuid",
  "email": "john.doe@university.edu",
  "role": "student",
  "university": "uuid",
  "profile": { ... }
}
```

### Endpoint: Update Current User

**PATCH** `/api/auth/me/`

```javascript
// Request (any subset of fields)
{
  "email": "new.email@university.edu"
}

// Response (200 OK)
{
  "id": "uuid",
  "email": "new.email@university.edu",
  ...
}
```

### Endpoint: Get/Update Profile

**GET** `/api/auth/profile/`  
**PATCH** `/api/auth/profile/`

```javascript
// GET Response
{
  "first_name": "John",
  "last_name": "Doe",
  "identification_number": "STU2024001",
  "level": "3rd Year",
  "department": "uuid",
  "avatar": "https://s3.amazonaws.com/...avatar.jpg"
}

// PATCH Request (with file upload)
{
  "first_name": "Johnny",
  "last_name": "Smith",
  "avatar": <File>  // Multipart form data
}
```

### Token Storage (Frontend Recommendation)

```javascript
// For Web (SPA)
// ✅ Best: httpOnly cookie (automatic, secure)
// ⚠️ Fallback: localStorage (if CORS prevents cookies)

localStorage.setItem('access_token', response.access);
localStorage.setItem('refresh_token', response.refresh);

// ❌ Do NOT store in sessionStorage (lost on tab close)
// ❌ Do NOT store in memory (lost on page refresh)
```

### Refresh Token Rotation

When you call `/api/auth/token/refresh/`, you get a **new refresh token** (security best practice). Always replace the old one:

```javascript
const refreshTokens = async (refreshToken) => {
  const response = await fetch('/api/auth/token/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh: refreshToken })
  });
  const data = await response.json();
  localStorage.setItem('access_token', data.access);
  localStorage.setItem('refresh_token', data.refresh);  // ← New token
  return data;
};
```

### Role-Based Access Control (RBAC)

The backend enforces roles at the API level. Your frontend **should reflect this**:

| Role | Permissions |
|------|-------------|
| **student** | View courses, enroll, ask questions in chat, bookmark snippets, view analytics |
| **lecturer** | Create/edit courses, upload materials, view class analytics, moderate reports |
| **admin** | Full access, user management, institution management, system settings |

**Frontend Implementation:**

```typescript
// pages/_app.tsx (or layout.tsx in Next.js 13+)
const useAuth = () => {
  const [user, setUser] = useState(null);
  
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      // Decode JWT to get role
      const decoded = JSON.parse(atob(token.split('.')[1]));
      setUser({ role: decoded.role, email: decoded.email });
    }
  }, []);
  
  return user;
};

export default function App() {
  const user = useAuth();
  
  return (
    <Router>
      {user?.role === 'student' && <StudentLayout />}
      {user?.role === 'lecturer' && <LecturerLayout />}
      {user?.role === 'admin' && <AdminLayout />}
    </Router>
  );
}
```

---

## 5. Data Models & Relationships

### User Model

```
User (accounts.User)
├── id: UUID (primary key)
├── email: Email (unique)
├── password: Hashed
├── role: Choice("student", "lecturer", "admin")
├── is_active: Boolean
├── is_staff: Boolean
├── is_superuser: Boolean
├── university: FK → University
├── first_name: String
├── last_name: String
├── created_at: DateTime
├── updated_at: DateTime
└── profile: OneToOne → Profile
    ├── first_name: String
    ├── last_name: String
    ├── identification_number: String (unique)
    ├── level: String ("3rd Year", "Professor", etc.)
    ├── department: FK → Department
    └── avatar: Image (nullable)
```

### Institution Hierarchy

```
University
├── id: UUID
├── name: String
├── description: Text
├── logo: Image
├── code: String (unique)
└── faculties: Reverse FK
    └── Faculty
        ├── id: UUID
        ├── name: String
        ├── university: FK
        └── departments: Reverse FK
            └── Department
                ├── id: UUID
                ├── name: String
                ├── code: String
                ├── faculty: FK
                └── courses: Reverse FK
```

### Course Ecosystem

```
Course
├── id: UUID
├── title: String
├── code: String (unique, e.g., "CS101")
├── description: Text
├── department: FK → Department
├── lecturer: FK → User (lecturer role)
├── thumbnail: Image (nullable)
├── level: String
├── lecturer_remark: Text
├── created_at: DateTime
├── updated_at: DateTime
├── enrollments: Reverse FK → Enrollment
├── materials: Reverse FK → CourseMaterial
├── sessions: Reverse FK → StudySession
├── struggles: Reverse FK → TopicStruggle
└── ratings: Reverse FK → CourseRating
    ├── score: Integer (1-5)
    ├── reaction: String ("up", "down")
    └── user: FK → User

Enrollment
├── id: UUID
├── student: FK → User
├── course: FK → Course
├── created_at: DateTime
└── unique_together: (student, course)

CourseMaterial
├── id: UUID
├── course: FK → Course
├── file: File (PDF)
├── file_name: String
├── file_type: String ("pdf", "docx", etc.)
├── file_size: BigInteger (bytes)
├── page_count: Integer (nullable, set after processing)
├── status: Choice("processing", "ready", "failed")
├── uploaded_by: FK → User
├── created_at: DateTime
├── chunks: Reverse FK → MaterialChunk
    ├── page: Integer
    ├── content: Text (800 chars)
    └── embedding: Vector (1536-dim, pgvector)

CourseRating
├── user: FK → User
├── course: FK → Course
├── score: Integer (1-5)
├── reaction: String ("up", "down")
└── unique_together: (user, course)
```

### Study Lab (AI Chat)

```
StudySession
├── id: UUID
├── user: FK → User
├── course: FK → Course
├── title: String ("How to solve ODEs")
├── description: Text
├── confidence_score: Float (0.0 - 1.0)
├── created_at: DateTime
├── messages: Reverse FK → ChatMessage
└── feedback: Reverse FK → SessionFeedback

ChatMessage
├── id: UUID
├── session: FK → StudySession
├── role: Choice("user", "assistant")
├── content: Text (user question or AI answer)
├── created_at: DateTime
└── sources: Reverse FK → MessageSource
    ├── material: FK → CourseMaterial
    ├── page: Integer
    └── snippet: Text (first 240 chars)

SessionFeedback
├── id: UUID
├── session: FK → StudySession
├── rating: Integer (1-5)
├── note: Text (optional feedback)
└── created_at: DateTime
```

### Analytics

```
TopicStruggle
├── id: UUID
├── course: FK → Course
├── topic: String
├── questions_asked: Integer (aggregated)
├── avg_confidence: Float (0.0 - 1.0)
├── struggling_students: Integer (count)
└── updated_at: DateTime

Bookmark
├── id: UUID
├── user: FK → User
├── kind: Choice("snippet", "answer")
├── title: String
├── content: Text
├── material: FK → CourseMaterial (nullable)
├── page: Integer (nullable)
├── message: FK → ChatMessage (nullable)
└── created_at: DateTime
```

### Notifications

```
Notification
├── id: UUID
├── user: FK → User
├── title: String
├── body: Text
├── notification_type: String (e.g., "material_ready", "new_enrollment")
├── read: Boolean
├── created_at: DateTime
└── data: JSON (optional extra context)
```

### Support

```
ContactMessage
├── id: UUID
├── user: FK → User (nullable, anonymous allowed)
├── email: Email
├── subject: String
├── body: Text
└── created_at: DateTime

IssueReport
├── id: UUID
├── user: FK → User (nullable)
├── title: String
├── description: Text
├── severity: Choice("low", "medium", "high", "critical")
├── resolved: Boolean
└── created_at: DateTime

AdminRequest
├── id: UUID
├── user: FK → User
├── reason: Text
├── document_proof: File (nullable)
├── status: Choice("pending", "approved", "rejected")
└── created_at: DateTime
```

---

## 6. API Endpoints Reference

### Organization

Endpoints are organized by **app** and registered via Django REST Framework's `DefaultRouter`. All REST endpoints follow REST conventions.

### 6.1 Authentication Endpoints

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/api/auth/register/` | None | Create new user |
| POST | `/api/auth/login/` | None | Get access + refresh tokens |
| POST | `/api/auth/token/refresh/` | None | Refresh access token |
| GET | `/api/auth/me/` | Required | Get current user |
| PATCH | `/api/auth/me/` | Required | Update current user |
| GET | `/api/auth/profile/` | Required | Get user profile |
| PATCH | `/api/auth/profile/` | Required | Update profile (with avatar) |

### 6.2 Institutions Endpoints

**Universities**

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/universities/` | Yes | List universities (paginated, 20 per page) |
| GET | `/api/universities/{id}/` | Yes | Get single university |
| POST | `/api/universities/` | Admin | Create university |
| PATCH | `/api/universities/{id}/` | Admin | Update university |
| DELETE | `/api/universities/{id}/` | Admin | Delete university |

**Query Parameters:**
```
GET /api/universities/?page=1&search=MIT
GET /api/universities/?ordering=-created_at
```

**Faculties**

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/faculties/` | Yes | List faculties |
| GET | `/api/faculties/{id}/` | Yes | Get single faculty |
| POST | `/api/faculties/` | Admin | Create faculty |

**Departments**

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/departments/` | Yes | List departments (filterable) |
| GET | `/api/departments/{id}/` | Yes | Get single department |
| POST | `/api/departments/` | Lecturer+ | Create department |

**Query Parameters:**
```
GET /api/departments/?university=uuid&faculty=uuid
```

### 6.3 Courses Endpoints

**List & Create**

```
GET    /api/courses/                    # List all courses (paginated)
POST   /api/courses/                    # Create new course (lecturer only)
GET    /api/courses/{id}/               # Get course detail
PATCH  /api/courses/{id}/               # Update course (lecturer only)
DELETE /api/courses/{id}/               # Delete course (lecturer only)
```

**Query Parameters (Filtering & Search):**

```javascript
GET /api/courses/?page=1                          // Page 1
GET /api/courses/?department=uuid                 // By department
GET /api/courses/?lecturer=uuid                   // By lecturer
GET /api/courses/?level=200                       // By level
GET /api/courses/?search=Python                   // Search title/code/description
GET /api/courses/?ordering=-created_at            // Sort (- = desc)
```

**Custom Actions**

```
GET    /api/courses/mine/                         # Courses user teaches (lecturer) or enrolled in (student)
POST   /api/courses/{id}/enroll/                  # Student enrolls in course
POST   /api/courses/{id}/rate/                    # Rate a course (1-5 stars + reaction)
GET    /api/courses/{id}/sessions/                # Get all study sessions for course
```

**Enroll Request:**
```javascript
POST /api/courses/{id}/enroll/
// Response: { "success": true }
```

**Rate Request:**
```javascript
POST /api/courses/{id}/rate/
{
  "score": 5,
  "reaction": "up"  // "up" or "down"
}
// Response: { "success": true }
```

### 6.4 Materials Endpoints

```
GET    /api/materials/                   # List materials (filterable)
POST   /api/materials/                   # Upload new material (multipart/form-data)
GET    /api/materials/{id}/              # Get material detail
PATCH  /api/materials/{id}/              # Update material metadata
DELETE /api/materials/{id}/              # Delete material
```

**Query Parameters:**
```javascript
GET /api/materials/?course=uuid
GET /api/materials/?status=ready  // "processing", "ready", "failed"
GET /api/materials/?page=1
```

**Upload Material (POST):**

```javascript
// Use FormData for file upload
const formData = new FormData();
formData.append('course', courseUUID);
formData.append('file', pdfFile);  // <input type="file">

const response = await fetch('/api/materials/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    // DO NOT set Content-Type, browser will set it to multipart/form-data
  },
  body: formData
});

// Response (201 Created)
{
  "id": "uuid",
  "course": "uuid",
  "file": "https://s3.amazonaws.com/materials/...",
  "file_name": "lecture01.pdf",
  "file_type": "pdf",
  "file_size": 2048576,
  "page_count": null,  // Set after processing
  "status": "processing",  // Will change to "ready" after Celery task completes
  "uploaded_by": "uuid",
  "created_at": "2024-05-27T10:30:00Z"
}
```

**Processing Status Flow:**

```
1. User uploads PDF
   ↓ (status: "processing")
2. Celery task triggered
   ├── Extract text from PDF
   ├── Split into 800-char chunks (100-char overlap)
   ├── Embed chunks with OpenAI text-embedding-3-small
   └── Store vectors in PostgreSQL pgvector column
3. Task completes
   ↓ (status: "ready")
   ✓ Material available for RAG chat
4. If task fails
   ↓ (status: "failed")
   ✗ User can delete and retry
```

**Frontend Polling Strategy:**

```javascript
// Check material status periodically
const checkMaterialStatus = async (materialId) => {
  const response = await fetch(`/api/materials/${materialId}/`, {
    headers: { 'Authorization': `Bearer ${accessToken}` }
  });
  const material = await response.json();
  
  if (material.status === 'ready') {
    console.log(`Material ready! ${material.page_count} pages.`);
    // Enable chat with this material
  } else if (material.status === 'failed') {
    console.error('Processing failed, try uploading again');
  }
};

// Poll every 5 seconds until ready
const pollInterval = setInterval(() => {
  checkMaterialStatus(materialId);
}, 5000);
```

### 6.5 Study Sessions (AI Chat) Endpoints

```
GET    /api/sessions/                    # List user's study sessions
POST   /api/sessions/                    # Create new study session
GET    /api/sessions/{id}/               # Get session detail
PATCH  /api/sessions/{id}/               # Update session
DELETE /api/sessions/{id}/               # Delete session
```

**Custom Actions**

```
GET    /api/sessions/{id}/messages/      # Get all messages in session
POST   /api/sessions/{id}/ask/           # Ask a question (triggers RAG)
POST   /api/sessions/{id}/feedback/      # Submit session feedback (1-5 rating)
```

**Create Study Session:**

```javascript
POST /api/sessions/
{
  "course": "uuid-of-course",
  "title": "Help with Differential Equations",
  "description": "Understanding separation of variables"
}

// Response (201)
{
  "id": "uuid",
  "user": "uuid",
  "course": "uuid",
  "title": "Help with Differential Equations",
  "description": "Understanding separation of variables",
  "confidence_score": 0.0,
  "created_at": "2024-05-27T10:30:00Z"
}
```

**Ask a Question (RAG Chat):**

```javascript
POST /api/sessions/{sessionId}/ask/
{
  "message": "What is the method of separation of variables?"
}

// Response (200)
{
  "user": {
    "id": "uuid",
    "session": "uuid",
    "role": "user",
    "content": "What is the method of separation of variables?",
    "created_at": "2024-05-27T10:30:05Z"
  },
  "assistant": {
    "id": "uuid",
    "session": "uuid",
    "role": "assistant",
    "content": "The separation of variables is a method for solving PDEs by assuming the solution can be written as a product of functions, each depending on one variable only...",
    "created_at": "2024-05-27T10:30:10Z",
    "sources": [
      {
        "id": "uuid",
        "message": "uuid",
        "material": { "id": "uuid", "file_name": "Chapter_3.pdf", ... },
        "page": 45,
        "snippet": "The separation of variables is a fundamental technique in solving partial differential equations..."
      }
    ]
  }
}
```

**Get Messages in Session:**

```javascript
GET /api/sessions/{sessionId}/messages/

// Response (200)
[
  {
    "id": "uuid",
    "session": "uuid",
    "role": "user",
    "content": "What is separation of variables?",
    "sources": [],
    "created_at": "..."
  },
  {
    "id": "uuid",
    "session": "uuid",
    "role": "assistant",
    "content": "It's a method for solving PDEs...",
    "sources": [
      {
        "material": { "file_name": "Chapter_3.pdf", ... },
        "page": 45,
        "snippet": "..."
      }
    ],
    "created_at": "..."
  }
]
```

**Submit Session Feedback:**

```javascript
POST /api/sessions/{sessionId}/feedback/
{
  "rating": 4,
  "note": "Very helpful, but more examples would be great"
}

// Response
{ "success": true }
```

### 6.6 Analytics Endpoints

**Heatmap (Topic Struggles)**

```
GET    /api/heatmap/                     # Get topic struggle data (for all courses taught)
```

**Query Parameters:**

```javascript
GET /api/heatmap/?course=uuid             // For specific course
```

**Response:**

```javascript
{
  "count": 15,
  "results": [
    {
      "id": "uuid",
      "course": "uuid",
      "topic": "Differential Equations",
      "questions_asked": 45,
      "avg_confidence": 0.62,
      "struggling_students": 12
    },
    {
      "id": "uuid",
      "course": "uuid",
      "topic": "Integration Techniques",
      "questions_asked": 28,
      "avg_confidence": 0.74,
      "struggling_students": 7
    }
  ]
}
```

**Bookmarks**

```
GET    /api/bookmarks/                   # List user's bookmarks (paginated)
POST   /api/bookmarks/                   # Create bookmark
GET    /api/bookmarks/{id}/              # Get bookmark detail
PATCH  /api/bookmarks/{id}/              # Update bookmark
DELETE /api/bookmarks/{id}/              # Delete bookmark
```

**Create Bookmark:**

```javascript
POST /api/bookmarks/
{
  "kind": "snippet",              // "snippet" or "answer"
  "title": "Separation of Variables Formula",
  "content": "y(x,t) = X(x) * T(t)",
  "material": "uuid",             // If kind is "snippet"
  "page": 45                      // If kind is "snippet"
}

// Or for answer bookmarks:
{
  "kind": "answer",
  "title": "How to solve separable PDEs",
  "content": "First identify if PDE is separable...",
  "message": "uuid"               // Reference to chat message
}
```

### 6.7 Notifications Endpoints

```
GET    /api/notifications/               # Get user's notifications (paginated)
POST   /api/notifications/{id}/mark-as-read/  # Mark notification as read
```

**Response:**

```javascript
{
  "count": 42,
  "results": [
    {
      "id": "uuid",
      "user": "uuid",
      "title": "Material Ready",
      "body": "Chapter_3.pdf has been processed and is ready for study",
      "notification_type": "material_ready",
      "read": false,
      "created_at": "2024-05-27T10:30:00Z",
      "data": {
        "material_id": "uuid",
        "course_id": "uuid"
      }
    }
  ]
}
```

### 6.8 Support Endpoints

**Contact (Public)**

```
POST   /api/support/contact/             # Send contact message (no auth required)
```

```javascript
POST /api/support/contact/
{
  "email": "user@example.com",
  "subject": "Technical Issue",
  "body": "The PDF upload feature is not working for me..."
}

// Response (201)
{ "success": true }
```

**Report Issue**

```
POST   /api/support/report/              # Report a bug/issue (auth required)
```

```javascript
POST /api/support/report/
{
  "title": "Chat response missing sources",
  "description": "When I ask a question, the AI response doesn't show where it got the information from",
  "severity": "medium"  // "low", "medium", "high", "critical"
}

// Response (201)
{ "success": true }
```

**Request Admin Elevation**

```
POST   /api/support/admin-request/       # Request admin/lecturer role (auth required)
```

```javascript
POST /api/support/admin-request/
{
  "reason": "I am a lecturer and would like to create courses",
  "document_proof": <File>  // Proof document (optional)
}

// Response (201)
{ "success": true }
```

---

## 7. Real-Time Features (WebSockets)

### WebSocket Endpoint

```
ws://localhost:8000/ws/notifications/    # Development
wss://api.acadexis.com/ws/notifications/ # Production (SSL)
```

### Connection Handshake

```javascript
const token = localStorage.getItem('access_token');

const ws = new WebSocket(
  `ws://localhost:8000/ws/notifications/?token=${token}`
);

ws.onopen = (event) => {
  console.log('Connected to notifications');
};

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  console.log('Received:', notification);
  // {
  //   "id": "uuid",
  //   "title": "Material Ready",
  //   "body": "...",
  //   "notification_type": "material_ready",
  //   "data": { "material_id": "uuid" }
  // }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = (event) => {
  console.log('Disconnected from notifications');
  // Implement auto-reconnect logic
};
```

### Notification Types

| Type | When | Payload |
|------|------|---------|
| `material_ready` | PDF processing completed | `{ material_id, course_id }` |
| `new_enrollment` | Student enrolls in course | `{ course_id, student_id }` |
| `course_announcement` | Lecturer posts announcement | `{ course_id, message }` |
| `admin_request_approved` | Admin role request approved | `{ request_id }` |

### Auto-Reconnect Strategy

```javascript
class NotificationManager {
  constructor(token) {
    this.token = token;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // 1 second
    this.connect();
  }

  connect() {
    this.ws = new WebSocket(
      `ws://localhost:8000/ws/notifications/?token=${this.token}`
    );

    this.ws.onopen = () => {
      console.log('Connected');
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1000;
    };

    this.ws.onmessage = (event) => {
      const notification = JSON.parse(event.data);
      this.handleNotification(notification);
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('Disconnected, attempting to reconnect...');
      this.reconnect();
    };
  }

  reconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    setTimeout(() => this.connect(), this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000); // Exponential backoff, max 30s
  }

  handleNotification(notification) {
    // Update UI based on notification type
    if (notification.notification_type === 'material_ready') {
      // Refresh materials list
      // Show toast: "Material is ready!"
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

export default NotificationManager;
```

### Frontend State Management Example

```typescript
// hooks/useNotifications.ts
import { useEffect, useState, useCallback } from 'react';
import NotificationManager from '@/services/NotificationManager';

export const useNotifications = () => {
  const [notifications, setNotifications] = useState([]);
  const [manager, setManager] = useState<NotificationManager | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    const nm = new NotificationManager(token);
    nm.handleNotification = (notification) => {
      setNotifications((prev) => [notification, ...prev]);
    };
    setManager(nm);

    return () => nm.disconnect();
  }, []);

  return { notifications, manager };
};
```

---

## 8. File Upload & Storage

### File Types & Limits

| Type | Max Size | Allowed Extensions |
|------|----------|-------------------|
| PDF (Material) | 100 MB | `.pdf` |
| Avatar (Image) | 10 MB | `.jpg`, `.jpeg`, `.png`, `.webp` |
| Proof (Support) | 25 MB | `.pdf`, `.jpg`, `.png`, `.docx` |

### Upload Endpoint: Course Material (PDF)

Already covered in [Section 6.4](#64-materials-endpoints).

### Upload Endpoint: Profile Avatar

**PATCH** `/api/auth/profile/` with `avatar` file

```javascript
const formData = new FormData();
formData.append('first_name', 'John');
formData.append('avatar', avatarFile);  // <input type="file" accept="image/*">

const response = await fetch('/api/auth/profile/', {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    // DO NOT set Content-Type
  },
  body: formData
});

// Response
{
  "first_name": "John",
  "avatar": "https://s3.amazonaws.com/avatars/uuid/avatar.jpg"
}
```

### Storage Backend

**Development:**
- Files stored in local directory: `media/`
- URLs: `/media/avatars/...`, `/media/materials/...`

**Production:**
- Files stored in AWS S3
- URLs: `https://s3.amazonaws.com/acadexis-media/...` (or custom CloudFront distribution)

### File URL Format

```javascript
// Local (dev)
avatar: "/media/avatars/uuid/avatar.jpg"

// S3 (prod)
avatar: "https://s3.amazonaws.com/acadexis-media/avatars/uuid/avatar.jpg"
```

### Download File

To download a file (e.g., material PDF):

```javascript
const url = material.file;  // Already a full URL
const a = document.createElement('a');
a.href = url;
a.download = material.file_name;
a.click();
```

---

## 9. AI/RAG Chat System

### How It Works (Architecture)

```
1. Student asks question in StudySession
   ↓
2. Question embedded using OpenAI text-embedding-3-small (1536 dimensions)
   ↓
3. Cosine similarity search against MaterialChunk vectors
   ↓
4. Top-5 chunks retrieved from PostgreSQL pgvector
   ↓
5. Chunks used as context in GPT-4o-mini prompt
   ↓
6. AI generates answer with citations
   ↓
7. MessageSource records created linking answer to source materials
```

### Key Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Embedding Model | `text-embedding-3-small` | 1536-dim vectors |
| LLM Model | `gpt-4o-mini` | Fast, cost-effective |
| Top-K Chunks | 5 | Retrieved for context |
| Chunk Size | 800 characters | With 100-char overlap |
| Temperature | 0.2 | More deterministic |

### System Prompt

```
You are Acadexis, an academic AI tutor.
ONLY answer using the provided course context. Cite page numbers.
If the context lacks the answer, say so plainly.
```

### Example Chat Flow

```javascript
// 1. Create session
POST /api/sessions/
{
  "course": "uuid",
  "title": "Linear Algebra Help",
  "description": ""
}
// Response: { id: "session-123", ... }

// 2. Ask question
POST /api/sessions/session-123/ask/
{
  "message": "What is an eigenvector?"
}

// Backend flow:
// ✓ Embed question
// ✓ Search pgvector for top-5 chunks
// ✓ Call GPT-4o-mini with context
// ✓ Create ChatMessage (assistant)
// ✓ Create MessageSource records (citations)

// Response:
{
  "user": {
    "id": "msg-1",
    "role": "user",
    "content": "What is an eigenvector?",
    "sources": [],
    "created_at": "..."
  },
  "assistant": {
    "id": "msg-2",
    "role": "assistant",
    "content": "An eigenvector is a non-zero vector that, when multiplied by a square matrix, yields a scalar multiple of itself...",
    "sources": [
      {
        "material": {
          "id": "mat-456",
          "file_name": "Linear_Algebra_Chapter2.pdf",
          "course": "uuid"
        },
        "page": 23,
        "snippet": "An eigenvector v of a matrix A is a non-zero vector such that A*v = λ*v for some scalar λ..."
      },
      {
        "material": { ... },
        "page": 31,
        "snippet": "..."
      }
    ],
    "created_at": "..."
  }
}

// 3. Get conversation history
GET /api/sessions/session-123/messages/
// Returns all messages and sources in chronological order

// 4. Submit feedback
POST /api/sessions/session-123/feedback/
{
  "rating": 5,
  "note": "Excellent explanation!"
}
// Updates analytics about teaching effectiveness
```

### Frontend Chat UI Implementation

```typescript
// components/ChatInterface.tsx
'use client';

import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ChatMessage as ChatMessageType } from '@/types';

export const ChatInterface = ({ sessionId }: { sessionId: string }) => {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [input, setInput] = useState('');

  // Fetch existing messages
  const { data: existingMessages } = useQuery({
    queryKey: ['messages', sessionId],
    queryFn: async () => {
      const res = await fetch(`/api/sessions/${sessionId}/messages/`, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
      });
      return res.json();
    }
  });

  // Ask question mutation
  const askMutation = useMutation({
    mutationFn: async (message: string) => {
      const res = await fetch(`/api/sessions/${sessionId}/ask/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({ message })
      });
      if (!res.ok) throw new Error('Failed to ask question');
      return res.json();
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        data.user,
        data.assistant
      ]);
      setInput('');
    }
  });

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.role}`}>
            <p>{msg.content}</p>
            {msg.sources?.length > 0 && (
              <details>
                <summary>Sources ({msg.sources.length})</summary>
                <ul>
                  {msg.sources.map((src) => (
                    <li key={src.id}>
                      <a href={src.material.file}>
                        {src.material.file_name} (p. {src.page})
                      </a>
                      <p className="snippet">{src.snippet}...</p>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
      </div>

      <form onSubmit={(e) => {
        e.preventDefault();
        askMutation.mutate(input);
      }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={askMutation.isPending}
          placeholder="Ask a question..."
        />
        <button type="submit" disabled={askMutation.isPending}>
          {askMutation.isPending ? 'Waiting for AI...' : 'Send'}
        </button>
      </form>
    </div>
  );
};
```

### Cost Optimization Notes

- **Embeddings:** ~$0.02 per 1M tokens → $0.02 per 1000 files (assuming ~500 tokens/file)
- **LLM:** ~$0.15 per 1M input tokens + $0.60 per 1M output tokens
- **Batching:** Chunks are embedded in batches of 100 to reduce API calls
- **Caching:** Consider caching embeddings in Redis for frequently asked questions

---

## 10. Error Handling & Status Codes

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| **200** | OK | GET successful, response in body |
| **201** | Created | POST successful, new resource created |
| **204** | No Content | DELETE successful, no response body |
| **400** | Bad Request | Invalid input data |
| **401** | Unauthorized | Missing/invalid token |
| **403** | Forbidden | User lacks permission (role-based) |
| **404** | Not Found | Resource doesn't exist |
| **409** | Conflict | Unique constraint violation |
| **429** | Too Many Requests | Rate limit exceeded |
| **500** | Internal Server Error | Backend error, log it and retry |

### Error Response Format

```javascript
// 400 Bad Request
{
  "detail": "Invalid email address"
  // OR for multiple fields:
  // "email": ["Invalid email address"],
  // "password": ["Password too short"]
}

// 401 Unauthorized
{
  "detail": "Authentication credentials were not provided."
}

// 403 Forbidden
{
  "detail": "You do not have permission to perform this action."
}

// 404 Not Found
{
  "detail": "Not found."
}

// 429 Too Many Requests
{
  "detail": "Request was throttled. Expected available in 3600 seconds."
}
```

### Common Errors

**Registration fails: "User already exists"**
- Status: 400
- Solution: User already has account, direct to login

**Upload fails: "file size exceeds maximum"**
- Status: 400
- Solution: File too large, show max size to user

**Chat fails: "No materials found for this course"**
- Status: 400
- Solution: Lecturer hasn't uploaded materials yet

**Material status is "failed"**
- Status: 200 (but check `status` field)
- Solution: PDF processing failed, user should delete and retry

### Frontend Error Handling

```typescript
// services/api.ts
export async function apiCall(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };

  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  const response = await fetch(url, { ...options, headers });

  // Handle token expiration
  if (response.status === 401) {
    const refreshToken = localStorage.getItem('refresh_token');
    if (refreshToken) {
      // Try to refresh
      const refreshResponse = await fetch('/api/auth/token/refresh/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: refreshToken })
      });

      if (refreshResponse.ok) {
        const data = await refreshResponse.json();
        localStorage.setItem('access_token', data.access);
        localStorage.setItem('refresh_token', data.refresh);

        // Retry original request
        return apiCall(url, options);
      } else {
        // Refresh failed, redirect to login
        window.location.href = '/login';
      }
    }
  }

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(JSON.stringify(errorData));
  }

  return response;
}
```

---

## 11. Rate Limiting & Pagination

### Rate Limiting

Backend enforces rate limiting per user:

| User Type | Limit | Window |
|-----------|-------|--------|
| Authenticated | 1,000 requests | 24 hours |
| Anonymous | 100 requests | 24 hours |

**Response Headers When Throttled:**

```
HTTP/1.1 429 Too Many Requests

X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1234567890  (Unix timestamp)

{
  "detail": "Request was throttled. Expected available in 3600 seconds."
}
```

**Frontend Handling:**

```javascript
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function apiCallWithRetry(url, options) {
  try {
    const response = await fetch(url, options);
    
    if (response.status === 429) {
      const retryAfter = parseInt(response.headers.get('X-RateLimit-Reset')) * 1000 - Date.now();
      console.log(`Rate limited, retrying in ${retryAfter}ms`);
      await sleep(retryAfter + 1000);
      return apiCallWithRetry(url, options);  // Retry
    }
    
    return response;
  } catch (error) {
    console.error('API call failed:', error);
    throw error;
  }
}
```

### Pagination

**Default Page Size:** 20 items per page

**Query Parameters:**

```javascript
GET /api/courses/?page=1
GET /api/courses/?page=2
GET /api/courses/?page=3
```

**Response Format:**

```javascript
{
  "count": 247,              // Total items across all pages
  "next": "http://...?page=2",  // URL for next page (null if last page)
  "previous": null,             // URL for previous page (null if first page)
  "results": [
    { ... },
    { ... },
    // ... 20 items per page
  ]
}
```

**Frontend Pagination Implementation:**

```typescript
// hooks/usePagination.ts
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

export const usePagination = (baseUrl: string) => {
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery({
    queryKey: [baseUrl, page],
    queryFn: async () => {
      const url = new URL(baseUrl);
      url.searchParams.append('page', page.toString());
      
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
      });
      
      if (!response.ok) throw new Error('Fetch failed');
      return response.json();
    }
  });

  return {
    items: data?.results || [],
    hasNext: !!data?.next,
    hasPrevious: !!data?.previous,
    totalCount: data?.count || 0,
    page,
    setPage,
    isLoading,
    error
  };
};

// Usage
export const CourseList = () => {
  const { items, hasNext, hasPrevious, page, setPage } = usePagination('/api/courses/');

  return (
    <div>
      {items.map(course => <CourseCard key={course.id} course={course} />)}
      
      <div className="pagination">
        <button onClick={() => setPage(p => p - 1)} disabled={!hasPrevious}>
          Previous
        </button>
        <span>Page {page}</span>
        <button onClick={() => setPage(p => p + 1)} disabled={!hasNext}>
          Next
        </button>
      </div>
    </div>
  );
};
```

---

## 12. CORS Configuration

### Allowed Origins

The backend allows CORS requests from whitelisted origins. In **development**, all origins are typically allowed. In **production**, specific frontend URLs are whitelisted.

**Development (.env):**
```
CORS_ALLOWED_ORIGINS=*  # or http://localhost:3000
```

**Production (.env):**
```
CORS_ALLOWED_ORIGINS=https://acadexis.com,https://app.acadexis.com
```

### Credentials

**CORS with credentials is enabled.** This allows:
- Sending cookies (if applicable)
- Sending/receiving auth headers

**Frontend must include credentials:**

```javascript
const response = await fetch('/api/courses/', {
  method: 'GET',
  credentials: 'include',  // ← Include credentials
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
```

### Preflight Requests

For requests with custom headers (e.g., `Authorization`), the browser sends an **OPTIONS preflight request**. The backend automatically handles these — you don't need to do anything.

---

## 13. Frontend Integration Examples

### Setup: Authentication Context

```typescript
// contexts/AuthContext.tsx
'use client';

import { createContext, useContext, useState, useEffect } from 'react';

interface User {
  id: string;
  email: string;
  role: 'student' | 'lecturer' | 'admin';
  profile: {
    first_name: string;
    last_name: string;
    avatar: string | null;
  };
}

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Restore from localStorage
    const token = localStorage.getItem('access_token');
    if (token) {
      const decoded = JSON.parse(atob(token.split('.')[1]));
      setUser({
        id: decoded.user_id,
        email: decoded.email,
        role: decoded.role,
        profile: { first_name: '', last_name: '', avatar: null }
      });
      setAccessToken(token);
    }
    setLoading(false);
  }, []);

  const login = async (email: string, password: string) => {
    const response = await fetch('/api/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    if (!response.ok) throw new Error('Login failed');

    const data = await response.json();
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);
    setAccessToken(data.access);
    setUser(data.user);
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setAccessToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, accessToken, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};
```

### Setup: API Client

```typescript
// services/apiClient.ts
import { useAuth } from '@/contexts/AuthContext';

export class APIClient {
  private baseURL: string;
  private accessToken: string | null = null;

  constructor(baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') {
    this.baseURL = baseURL;
  }

  setAccessToken(token: string | null) {
    this.accessToken = token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = new URL(endpoint, this.baseURL);
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    } as Record<string, string>;

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const response = await fetch(url, { ...options, headers });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(JSON.stringify(error));
    }

    // 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // Courses
  getCourses(params?: Record<string, any>) {
    const url = new URL('/api/courses/', this.baseURL);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, String(value));
      });
    }
    return this.request<{ results: Course[]; count: number }>(`/api/courses/`);
  }

  enrollCourse(courseId: string) {
    return this.request(`/api/courses/${courseId}/enroll/`, { method: 'POST' });
  }

  // Study Sessions
  createSession(data: { course: string; title: string; description?: string }) {
    return this.request('/api/sessions/', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  askQuestion(sessionId: string, message: string) {
    return this.request(`/api/sessions/${sessionId}/ask/`, {
      method: 'POST',
      body: JSON.stringify({ message })
    });
  }

  // Materials
  uploadMaterial(courseId: string, file: File) {
    const formData = new FormData();
    formData.append('course', courseId);
    formData.append('file', file);

    return this.request('/api/materials/', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${this.accessToken}` },
      body: formData
    });
  }

  getMaterial(materialId: string) {
    return this.request(`/api/materials/${materialId}/`);
  }
}

export const useAPI = () => {
  const { accessToken } = useAuth();
  const client = new APIClient();
  client.setAccessToken(accessToken);
  return client;
};
```

### Example: Course Listing Page

```typescript
// app/courses/page.tsx
'use client';

import { useQuery } from '@tanstack/react-query';
import { useAPI } from '@/services/apiClient';
import { useState } from 'react';

export default function CoursesPage() {
  const api = useAPI();
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery({
    queryKey: ['courses', page],
    queryFn: () => api.getCourses({ page }),
  });

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {String(error)}</div>;

  return (
    <div className="courses-page">
      <h1>Courses</h1>
      
      <div className="course-grid">
        {data?.results.map((course) => (
          <div key={course.id} className="course-card">
            {course.thumbnail && <img src={course.thumbnail} alt={course.title} />}
            <h3>{course.title}</h3>
            <p>{course.code}</p>
            <p>By {course.lecturer.profile.first_name} {course.lecturer.profile.last_name}</p>
            <button onClick={() => api.enrollCourse(course.id)}>
              Enroll
            </button>
          </div>
        ))}
      </div>

      <div className="pagination">
        <button onClick={() => setPage(p => p - 1)} disabled={page === 1}>
          Previous
        </button>
        <span>Page {page}</span>
        <button onClick={() => setPage(p => p + 1)} disabled={!data?.next}>
          Next
        </button>
      </div>
    </div>
  );
}
```

### Example: AI Chat Component

```typescript
// components/StudyChat.tsx
'use client';

import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAPI } from '@/services/apiClient';

interface Props {
  sessionId: string;
}

export const StudyChat = ({ sessionId }: Props) => {
  const api = useAPI();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');

  const { data: existingMessages } = useQuery({
    queryKey: ['session-messages', sessionId],
    queryFn: () => api.getMessages(sessionId),
    onSuccess: (data) => setMessages(data),
  });

  const askMutation = useMutation({
    mutationFn: (message: string) => api.askQuestion(sessionId, message),
    onSuccess: (response) => {
      setMessages((prev) => [
        ...prev,
        response.user,
        response.assistant,
      ]);
      setInput('');
    },
  });

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.role}`}>
            <div className="content">{msg.content}</div>
            {msg.sources && msg.sources.length > 0 && (
              <div className="sources">
                <summary>Sources ({msg.sources.length})</summary>
                <ul>
                  {msg.sources.map((source, idx) => (
                    <li key={idx}>
                      <a href={source.material.file} target="_blank">
                        {source.material.file_name} (p. {source.page})
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) {
            askMutation.mutate(input);
          }
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={askMutation.isPending}
          placeholder="Ask a question..."
        />
        <button type="submit" disabled={askMutation.isPending || !input.trim()}>
          {askMutation.isPending ? 'Waiting...' : 'Send'}
        </button>
      </form>
    </div>
  );
};
```

---

## 14. Deployment & Environment Variables

### Environment Variables (Backend `.env`)

```env
# Django
DEBUG=False
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=api.acadexis.com,localhost

# Database
DATABASE_URL=postgres://user:password@host:5432/acadexis_prod

# Redis & Celery
REDIS_URL=redis://localhost:6379/0

# JWT
ACCESS_TOKEN_LIFETIME_MINUTES=60
REFRESH_TOKEN_LIFETIME_DAYS=7

# OpenAI
OPENAI_API_KEY=sk-...

# AWS S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=acadexis-media
AWS_S3_REGION_NAME=us-east-1

# CORS
CORS_ALLOWED_ORIGINS=https://acadexis.com,https://app.acadexis.com

# Email (optional, for notifications)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=app-password
```

### Environment Variables (Frontend `.env.local`)

```env
NEXT_PUBLIC_API_URL=https://api.acadexis.com
NEXT_PUBLIC_WS_URL=wss://api.acadexis.com
NEXT_PUBLIC_APP_NAME=Acadexis
```

### Docker Compose (Local Development)

```yaml
version: '3.9'

services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: acadexis
      POSTGRES_PASSWORD: acadexis
      POSTGRES_DB: acadexis_dev
    ports:
      - '5432:5432'
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - '6379:6379'

  backend:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    environment:
      - DATABASE_URL=postgres://acadexis:acadexis@db:5432/acadexis_dev
      - REDIS_URL=redis://redis:6379/0
      - DEBUG=True
    ports:
      - '8000:8000'
    depends_on:
      - db
      - redis
    volumes:
      - .:/app

  celery:
    build: .
    command: celery -A Acadexis_backend worker -l info
    environment:
      - DATABASE_URL=postgres://acadexis:acadexis@db:5432/acadexis_dev
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - .:/app

volumes:
  postgres_data:
```

### Deployment Checklist

- [ ] Set `DEBUG=False` in production
- [ ] Generate strong `SECRET_KEY`
- [ ] Configure database backups
- [ ] Set up SSL certificate (HTTPS)
- [ ] Configure CORS for frontend domain
- [ ] Set up OpenAI API key securely (AWS Secrets Manager, etc.)
- [ ] Configure S3 for media storage
- [ ] Set up email for notifications
- [ ] Configure logging and error tracking (Sentry, etc.)
- [ ] Set up monitoring and alerts
- [ ] Configure rate limiting if needed
- [ ] Run Django migrations on production: `python manage.py migrate --noinput`
- [ ] Collect static files: `python manage.py collectstatic --noinput`

### Running Celery Workers

```bash
# Local development
celery -A Acadexis_backend worker -l info

# Production with multiple workers
celery -A Acadexis_backend worker -l info --concurrency=4
celery -A Acadexis_backend worker -l info --queue=materials --concurrency=2
```

### Database Migrations

```bash
# Create migrations (dev)
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migration status
python manage.py showmigrations

# Fake a migration (if needed)
python manage.py migrate --fake apps.courses 0001_initial
```

---

## 15. Common Troubleshooting

### Issue: "Authentication credentials were not provided"

**Cause:** Missing or invalid JWT token in header

**Solution:**
```javascript
// ✅ Correct
headers: {
  'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGc...'
}

// ❌ Wrong
headers: {
  'Authorization': 'eyJ0eXAiOiJKV1QiLCJhbGc...'  // Missing "Bearer"
}

// ❌ Wrong
// No Authorization header at all
```

### Issue: "Token is invalid or expired"

**Cause:** Access token expired or refresh token invalid

**Solution:**
```javascript
const refreshAccessToken = async () => {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) {
    // Redirect to login
    window.location.href = '/login';
    return;
  }

  const response = await fetch('/api/auth/token/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh: refreshToken })
  });

  if (response.ok) {
    const data = await response.json();
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);
    // Retry failed request
  } else {
    // Refresh token invalid, redirect to login
    window.location.href = '/login';
  }
};
```

### Issue: "CORS blocked this request"

**Cause:** Frontend origin not in `CORS_ALLOWED_ORIGINS`

**Solution:** Add frontend URL to backend `.env`:
```
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.acadexis.com
```

Then restart Django.

### Issue: "File upload fails with 413 Payload Too Large"

**Cause:** File exceeds size limit

**Solution:** Check max file sizes:
```
PDF materials: 100 MB
Avatars: 10 MB
Proof documents: 25 MB
```

Compress file before uploading.

### Issue: "Material status stays on 'processing'"

**Cause:** Celery task failed or not running

**Solution:**
```bash
# Check Celery is running
celery -A Acadexis_backend worker -l info

# Check Redis is running
redis-cli ping
# Should respond: PONG

# Check logs for errors
tail -f logs/celery.log
```

### Issue: "WebSocket connection keeps disconnecting"

**Cause:** Connection timeout or server issue

**Solution:** Implement exponential backoff reconnection (see [Section 7](#7-real-time-features-websockets))

### Issue: "Chat returns error: 'No materials found'"

**Cause:** Course has no materials, or materials haven't finished processing

**Solution:**
1. Lecturer uploads material
2. Wait for material status to be "ready"
3. Then students can ask questions

### Issue: "Can't upload material, getting 400 error"

**Cause:** Missing required fields or incorrect format

**Check:**
```javascript
// ✅ Correct
const formData = new FormData();
formData.append('course', courseUUID);  // Required
formData.append('file', pdfFile);       // Required, must be File object

// ❌ Wrong
const formData = new FormData();
formData.append('file', pdfFile);  // Missing course
```

---

## Conclusion

This handover document provides the essential information for Next.js frontend developers to integrate with the Acadexis Django backend. Key takeaways:

1. **Authentication:** Use JWT tokens stored in localStorage (or secure cookies)
2. **API Structure:** REST endpoints with pagination, filtering, sorting
3. **Real-Time:** WebSockets for notifications
4. **AI/RAG:** Chat system uses pgvector + OpenAI embeddings + GPT-4o-mini
5. **File Upload:** FormData for multipart requests
6. **Error Handling:** Implement token refresh logic and proper error responses
7. **Rate Limiting:** 1,000 req/day for authenticated users
8. **Roles:** Frontend should reflect RBAC (student/lecturer/admin)

For detailed API examples, use the [API Endpoints Reference](#6-api-endpoints-reference) and [Frontend Integration Examples](#13-frontend-integration-examples) sections.

**Questions or issues?** Refer to the [Common Troubleshooting](#15-common-troubleshooting) section or review the backend code directly.

---

**Backend Repository:** `c:\Users\Abiola John\Documents\OVERSIGHT\Acadexis_backend`  
**Framework:** Django 5.1.7 + DRF 3.16.1  
**Generated:** May 27, 2026
