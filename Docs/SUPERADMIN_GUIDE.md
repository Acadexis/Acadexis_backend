# Superadmin Guide for Acadexis Backend

This guide covers all API endpoints, models, and recommendations for building a custom admin interface in your Next.js frontend.

---

## Table of Contents

1. [Authentication](#authentication)
2. [All API Endpoints](#all-api-endpoints)
3. [Models Reference](#models-reference)
4. [Admin-Specific Endpoints](#admin-specific-endpoints)
5. [Recommendations for Next.js](#recommendations-for-nextjs)
6. [Customization Ideas](#customization-ideas)

---

## Authentication

### Login
```
POST /api/auth/login/
Body: { "email": "admin@example.com", "password": "yourpassword" }
Response: { "access": "...", "refresh": "..." }
```

### Get Current User
```
GET /api/auth/me/
Headers: Authorization: Bearer <access_token>
Response: { "id": "...", "email": "...", "role": "admin", ... }
```

### Refresh Token
```
POST /api/auth/token/refresh/
Body: { "refresh": "..." }
Response: { "access": "..." }
```

---

## All API Endpoints

### Accounts (`/api/auth/`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/register/` | Register new user | No |
| POST | `/login/` | Login user | No |
| POST | `/logout/` | Logout user | Yes |
| POST | `/token/refresh/` | Refresh JWT token | No |
| GET | `/me/` | Get current user | Yes |
| GET/PUT | `/profile/` | Get/Update user profile | Yes |
| POST | `/forgot-password/` | Request password reset | No |
| POST | `/reset-password/` | Reset password with token | No |
| POST | `/change-password/` | Change password | Yes |

### Institutions (`/api/`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET/POST | `/universities/` | List/Create universities | Yes |
| GET/PUT/DELETE | `/universities/<uuid>/` | Retrieve/Update/Delete university | Yes |
| GET/POST | `/faculties/` | List/Create faculties | Yes |
| GET/PUT/DELETE | `/faculties/<uuid>/` | Retrieve/Update/Delete faculty | Yes |
| GET/POST | `/departments/` | List/Create departments | Yes |
| GET/PUT/DELETE | `/departments/<uuid>/` | Retrieve/Update/Delete department | Yes |

### Courses (`/api/`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET/POST | `/courses/` | List/Create courses | Yes |
| GET/PUT/DELETE | `/courses/<uuid>/` | Retrieve/Update/Delete course | Yes |
| GET/POST | `/modules/` | List/Create course modules | Yes |
| GET/PUT/DELETE | `/modules/<uuid>/` | Retrieve/Update/Delete module | Yes |
| GET | `/recommendations/` | Get AI recommendations | Yes |
| GET/POST | `/materials/` | List/Create course materials | Yes |
| GET/PUT/DELETE | `/materials/<uuid>/` | Retrieve/Update/Delete material | Yes |

### StudyLab (`/api/`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET/POST | `/sessions/` | List/Create study sessions | Yes |
| GET/PUT/DELETE | `/sessions/<uuid>/` | Retrieve/Update/Delete session | Yes |

### Analytics (`/api/`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/heatmap/` | Get study heatmap data | Yes |
| GET | `/bookmarks/` | List bookmarks | Yes |
| POST | `/bookmarks/` | Create bookmark | Yes |
| DELETE | `/bookmarks/<uuid>/` | Delete bookmark | Yes |

### Notifications (`/api/`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/notifications/` | List user notifications | Yes |
| GET | `/notifications/unread-count/` | Get unread count | Yes |
| POST | `/notifications/mark-all-read/` | Mark all as read | Yes |
| POST | `/notifications/<uuid>/mark-as-read/` | Mark single as read | Yes |

### Support (`/api/support/`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/contact/` | Submit contact message | No |
| POST | `/report/` | Submit issue report | No |
| POST | `/admin-request/` | Request admin privileges | Yes |

---

## Models Reference

### User (accounts)

```javascript
{
  id: "uuid",
  email: "user@example.com",
  role: "student" | "lecturer" | "admin",
  university: University | null,
  is_active: boolean,
  is_staff: boolean,
  date_joined: "datetime"
}
```

### Profile (accounts)

```javascript
{
  id: "uuid",
  user: User,
  first_name: string,
  last_name: string,
  identification_number: string,  // unique
  level: string,                   // e.g., "3rd Year", "Professor"
  department: Department | null,
  avatar: string | null,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### University (institutions)

```javascript
{
  id: "uuid",
  name: string,
  description: string,
  logo: string | null,             // URL to image
  code: string | null,              // e.g., "UNILAG"
  created_at: "datetime",
  updated_at: "datetime"
}
```

### Faculty (institutions)

```javascript
{
  id: "uuid",
  name: string,
  university: University,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### Department (institutions)

```javascript
{
  id: "uuid",
  name: string,
  code: string,
  faculty: Faculty,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### Course (courses)

```javascript
{
  id: "uuid",
  title: string,
  code: string,                     // unique, e.g., "CS101"
  description: string,
  department: Department | null,
  lecturer: User | null,
  thumbnail: string | null,
  level: string,                    // e.g., "100 Level"
  lecturer_remark: string,
  materials_count: number,           // computed property
  students_enrolled: number,         // computed property
  created_at: "datetime",
  updated_at: "datetime"
}
```

### CourseMaterial (courses)

```javascript
{
  id: "uuid",
  course: Course,
  file: string,                      // URL to file
  file_name: string,
  file_type: "pdf" | "docx" | "pptx",
  file_size: number,                 // bytes
  page_count: number | null,
  status: "processing" | "ready" | "failed",
  uploaded_by: User | null,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### CourseModule (courses)

```javascript
{
  id: "uuid",
  course: Course,
  title: string,
  description: string,
  order: number,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### Enrollment (courses)

```javascript
{
  id: "uuid",
  student: User,
  course: Course,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### StudySession (studylab)

```javascript
{
  id: "uuid",
  user: User,
  course: Course,
  title: string,
  description: string,
  confidence_score: number,          // 0.0 - 1.0
  created_at: "datetime",
  updated_at: "datetime"
}
```

### ChatMessage (studylab)

```javascript
{
  id: "uuid",
  session: StudySession,
  role: "user" | "assistant",
  content: string,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### Notification (notifications)

```javascript
{
  id: "uuid",
  user: User,
  title: string,
  body: string,
  read: boolean,
  notification_type: "info" | "success" | "warning" | "course",
  data: object,                      // custom JSON data
  created_at: "datetime",
  updated_at: "datetime"
}
```

### TopicStruggle (analytics)

```javascript
{
  id: "uuid",
  course: Course,
  topic: string,
  questions_asked: number,
  avg_confidence: number,
  struggling_students: number,
  updated_at: "datetime"
}
```

### Bookmark (analytics)

```javascript
{
  id: "uuid",
  user: User,
  kind: "snippet" | "answer",
  title: string,
  content: string,
  material: CourseMaterial | null,
  page: number | null,
  message: ChatMessage | null,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### ContactMessage (support)

```javascript
{
  id: "uuid",
  user: User | null,
  subject: string,
  body: string,
  email: string,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### IssueReport (support)

```javascript
{
  id: "uuid",
  user: User | null,
  title: string,
  description: string,
  severity: "low" | "medium" | "high" | "critical",
  resolved: boolean,
  created_at: "datetime",
  updated_at: "datetime"
}
```

### AdminRequest (support)

```javascript
{
  id: "uuid",
  user: User,
  reason: string,
  document_proof: string | null,
  status: "pending" | "approved" | "rejected",
  created_at: "datetime",
  updated_at: "datetime"
}
```

---

## Admin-Specific Endpoints

Since the default Django admin is not styled, you'll want to build custom admin endpoints in your Next.js frontend. Here are the operations you need:

### User Management

```javascript
// Get all users (paginated)
GET /api/auth/register/  // Actually this is for registration, not admin listing

// For admin user management, you'll need to add custom endpoints
// Recommended: GET /api/admin/users/
//             PUT /api/admin/users/<id>/role/
//             POST /api/admin/users/<id>/activate/
//             POST /api/admin/users/<id>/deactivate/
```

### Recommended Custom Admin Endpoints

Add these to your backend for full admin control:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/users/` | List all users (with filters) |
| GET | `/api/admin/users/<id>/` | Get user details |
| PUT | `/api/admin/users/<id>/` | Update user |
| PUT | `/api/admin/users/<id>/role/` | Change user role |
| POST | `/api/admin/users/<id>/activate/` | Activate user |
| POST | `/api/admin/users/<id>/deactivate/` | Deactivate user |
| GET | `/api/admin/statistics/` | Dashboard statistics |
| GET | `/api/admin/analytics/overview/` | Analytics overview |
| GET | `/api/admin/support/contacts/` | List contact messages |
| GET | `/api/admin/support/reports/` | List issue reports |
| PUT | `/api/admin/support/reports/<id>/resolve/` | Resolve issue report |
| GET | `/api/admin/support/admin-requests/` | List admin requests |
| PUT | `/api/admin/support/admin-requests/<id>/approve/` | Approve admin request |
| PUT | `/api/admin/support/admin-requests/<id>/reject/` | Reject admin request |
| POST | `/api/admin/courses/<id>/enroll-student/` | Enroll student |
| DELETE | `/api/admin/courses/<id>/unenroll-student/` | Unenroll student |
| GET | `/api/admin/courses/<id>/enrollments/` | List enrollments |

---

## Recommendations for Next.js

### 1. Authentication Flow

```javascript
// Store tokens
localStorage.setItem('access_token', access);
localStorage.setItem('refresh_token', refresh);

// Include in requests
const headers = {
  'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
  'Content-Type': 'application/json',
};
```

### 2. Protected Routes

```javascript
// Check admin role
const isAdmin = user?.role === 'admin';

if (!isAdmin) {
  router.push('/unauthorized');
}
```

### 3. API Service Pattern

```javascript
// lib/api.js
const API_BASE = process.env.NEXT_PUBLIC_API_URL;

async function fetchAPI(endpoint, options = {}) {
  const token = localStorage.getItem('access_token');
  
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  
  if (res.status === 401) {
    // Try refresh token
    // If fails, redirect to login
  }
  
  return res.json();
}

// Usage
const users = await fetchAPI('/admin/users/');
const courses = await fetchAPI('/courses/');
```

### 4. Real-time Notifications

Use WebSocket for real-time notifications:

```javascript
// Connect to WebSocket
const ws = new WebSocket(`wss://your-domain/ws/notifications/`);

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  // Add to notification list
  toast(notification.title);
};
```

### 5. File Upload

```javascript
async function uploadMaterial(file, courseId) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('course', courseId);
  
  const token = localStorage.getItem('access_token');
  
  const res = await fetch(`${API_BASE}/materials/`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
    body: formData,
  });
  
  return res.json();
}
```

### 6. Pagination & Filtering

Most list endpoints support pagination:

```javascript
// Pagination
GET /api/admin/users/?page=2&page_size=20

// Filtering
GET /api/admin/users/?role=student&university=<uuid>
GET /api/courses/?department=<uuid>&level=100

// Search
GET /api/admin/users/?search=john
GET /api/courses/?search=algorithm

// Ordering
GET /api/admin/users/?ordering=created_at
GET /api/courses/?ordering=-created_at
```

---

## Customization Ideas

### 1. Dashboard Cards

- Total Users (by role)
- Total Courses
- Total Enrollments
- Active Study Sessions
- Issue Reports (unresolved)
- Admin Requests (pending)

### 2. User Management Features

- Search/filter users by email, role, university
- Bulk role assignment
- Export users to CSV
- View user activity log

### 3. Course Management Features

- Upload materials with drag-and-drop
- View enrollment analytics
- Track material processing status
- Manage course modules (ordering)

### 4. Analytics Dashboard

- Study heatmap visualization
- Topic struggle charts
- Course popularity rankings
- Student engagement metrics

### 5. Support Queue

- Contact message inbox
- Issue report triage
- Admin request approval workflow

### 6. Notification System

- Send broadcasts to all users
- Send targeted notifications (by role, department, course)
- Schedule notifications

---

## Environment Variables Required

Ensure your Next.js app has:

```env
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

---

## Need More Endpoints?

If you need additional admin endpoints, let me know and I can add them to the backend. Common additions include:

- Bulk operations (delete, activate, deactivate)
- Export functionality (CSV, JSON)
- Advanced analytics
- Content moderation tools