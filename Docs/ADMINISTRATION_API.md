# Administration API Documentation

## Overview

The **Administration API** (`/api/admin/`) is a comprehensive, staff-only REST API that manages all resources in the Acadexis backend without exposing the Django admin interface. This API is designed to be consumed by your frontend admin dashboard.

---

## Architecture

```
Frontend Admin Dashboard
        ↓ (JWT + Staff Auth)
/api/admin/* REST Endpoints
        ↓
Django DRF Viewsets (IsStaffUser Permission)
        ↓
Django ORM Models
```

### Key Features
- **Staff-only access:** `IsStaffUser` permission enforces `is_staff=True` + JWT authentication.
- **Full CRUD:** Create, Read, Update, Delete for all admin-manageable resources.
- **Search & Filtering:** Advanced filtering, search, and ordering on all endpoints.
- **Bulk Actions:** Endpoints for bulk enrollments, deactivations, etc.
- **Custom Actions:** Special endpoints like `/deactivate/`, `/activate/`, `/promote_to_staff/`, etc.
- **Pagination:** Default 20 items per page (configurable).
- **OpenAPI Schema:** Swagger docs at `/api/docs/swagger/`

---

## Authentication

All admin endpoints require:
1. **JWT Bearer Token** in `Authorization` header: `Authorization: Bearer <access_token>`
2. **Staff Status:** The token's user must have `is_staff=True`

### Example Request

```bash
curl -X GET "http://localhost:8000/api/admin/users/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

### Obtaining a Token

Use the auth endpoints (same as user auth):
```bash
POST /api/auth/login/
{
  "email": "admin@example.com",
  "password": "yourpassword"
}

Response:
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": { ... }
}
```

---

## Endpoints

### 1. **Users** (`/api/admin/users/`)

Manage user accounts, roles, and activation status.

#### LIST - Get all users
```
GET /api/admin/users/
```

**Query Parameters:**
- `role`: Filter by role (student, lecturer, admin)
- `is_active`: Filter by active status (true/false)
- `university`: Filter by university UUID
- `search`: Search by email, first_name, or last_name
- `ordering`: Order by field (e.g., `-created_at`, `email`)
- `page`: Pagination (default 20 per page)

**Example:**
```bash
GET /api/admin/users/?role=lecturer&is_active=true&search=john&ordering=-created_at
```

**Response:**
```json
{
  "count": 150,
  "next": "http://localhost:8000/api/admin/users/?page=2",
  "previous": null,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "role": "lecturer",
      "is_active": true,
      "university_name": "MIT",
      "date_joined": "2024-01-15T10:30:00Z"
    },
    ...
  ]
}
```

#### RETRIEVE - Get user detail
```
GET /api/admin/users/{id}/
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "role": "lecturer",
  "is_active": true,
  "is_staff": true,
  "is_superuser": false,
  "university": "550e8400-e29b-41d4-a716-446655440001",
  "university_name": "MIT",
  "profile": {
    "id": "550e8400-e29b-41d4-a716-446655440002",
    "first_name": "John",
    "last_name": "Doe",
    "identification_number": "12345",
    "level": "Professor",
    "department": "550e8400-e29b-41d4-a716-446655440003",
    "avatar": "https://...",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-20T14:22:00Z"
  },
  "date_joined": "2024-01-15T10:30:00Z",
  "last_login": "2024-01-25T09:15:00Z"
}
```

#### CREATE - Add new user
```
POST /api/admin/users/
Content-Type: application/json

{
  "email": "newuser@example.com",
  "first_name": "Jane",
  "last_name": "Smith",
  "role": "student",
  "university": "550e8400-e29b-41d4-a716-446655440001"
}
```

#### UPDATE - Edit user
```
PATCH /api/admin/users/{id}/
Content-Type: application/json

{
  "first_name": "Janet",
  "role": "lecturer"
}
```

#### CUSTOM ACTIONS

**Deactivate User:**
```
POST /api/admin/users/{id}/deactivate/
```

**Activate User:**
```
POST /api/admin/users/{id}/activate/
```

**Promote to Staff:**
```
POST /api/admin/users/{id}/promote_to_staff/
```

**Demote from Staff:**
```
POST /api/admin/users/{id}/demote_from_staff/
```

---

### 2. **Universities** (`/api/admin/universities/`)

Manage university records.

#### LIST
```
GET /api/admin/universities/?search=MIT&ordering=name
```

#### CREATE
```
POST /api/admin/universities/

{
  "name": "Massachusetts Institute of Technology"
}
```

---

### 3. **Faculties** (`/api/admin/faculties/`)

Manage faculty records.

#### LIST with filtering
```
GET /api/admin/faculties/?university={university_id}&search=engineering
```

#### CREATE
```
POST /api/admin/faculties/

{
  "name": "Engineering Faculty",
  "university": "550e8400-e29b-41d4-a716-446655440001"
}
```

---

### 4. **Departments** (`/api/admin/departments/`)

Manage department records.

#### LIST with filtering
```
GET /api/admin/departments/?faculty={faculty_id}&search=computer
```

#### CREATE
```
POST /api/admin/departments/

{
  "name": "Computer Science",
  "faculty": "550e8400-e29b-41d4-a716-446655440005"
}
```

---

### 5. **Courses** (`/api/admin/courses/`)

Manage courses.

#### LIST with filters
```
GET /api/admin/courses/?department={dept_id}&lecturer={lecturer_id}&level=200&search=programming
```

**Response includes:**
- `enrollment_count`: Number of enrolled students
- `material_count`: Number of uploaded materials

#### CREATE
```
POST /api/admin/courses/

{
  "title": "Introduction to Python",
  "code": "CS101",
  "description": "Learn Python basics...",
  "department": "550e8400-e29b-41d4-a716-446655440005",
  "lecturer": "550e8400-e29b-41d4-a716-446655440000",
  "level": "100",
  "lecturer_remark": "Core course for all CS students"
}
```

---

### 6. **Enrollments** (`/api/admin/enrollments/`)

Manage student enrollments.

#### LIST
```
GET /api/admin/enrollments/?student={student_id}&course={course_id}
```

#### CREATE - Manually enroll
```
POST /api/admin/enrollments/

{
  "student": "550e8400-e29b-41d4-a716-446655440010",
  "course": "550e8400-e29b-41d4-a716-446655440020"
}
```

#### BULK ENROLL - Enroll multiple students
```
POST /api/admin/enrollments/bulk_enroll/

{
  "course_id": "550e8400-e29b-41d4-a716-446655440020",
  "student_ids": [
    "550e8400-e29b-41d4-a716-446655440010",
    "550e8400-e29b-41d4-a716-446655440011",
    "550e8400-e29b-41d4-a716-446655440012"
  ]
}

Response:
{
  "detail": "Enrolled 3 students in Introduction to Python.",
  "enrolled_count": 3
}
```

#### DELETE - Unenroll student
```
DELETE /api/admin/enrollments/{id}/
```

---

### 7. **Course Materials** (`/api/admin/materials/`)

Manage course materials (PDFs, documents).

#### LIST
```
GET /api/admin/materials/?course={course_id}&status=ready&search=lecture
```

**Statuses:** `processing`, `ready`, `failed`

#### CREATE - Upload material
```
POST /api/admin/materials/
Content-Type: multipart/form-data

{
  "course": "550e8400-e29b-41d4-a716-446655440020",
  "file": <binary file>,
  "file_name": "Chapter 1 - Fundamentals",
  "file_type": "pdf",
  "uploaded_by": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### RETRIEVE - Get material with file URL
```
GET /api/admin/materials/{id}/
```

---

### 8. **Course Ratings** (`/api/admin/ratings/`)

View and manage course ratings (read-only + delete).

#### LIST
```
GET /api/admin/ratings/?course={course_id}&score=5
```

#### DELETE
```
DELETE /api/admin/ratings/{id}/
```

---

### 9. **Study Sessions** (`/api/admin/study-sessions/`)

Monitor study sessions (read-only for audit purposes).

#### LIST
```
GET /api/admin/study-sessions/?user={user_id}&course={course_id}
```

**Response includes:**
- `message_count`: Number of chat messages in session
- Timestamps and confidence scores

#### RETRIEVE - Get session with chat history
```
GET /api/admin/study-sessions/{id}/
```

---

## Pagination

All list endpoints return paginated results (20 per page by default).

```json
{
  "count": 500,
  "next": "http://localhost:8000/api/admin/users/?page=2",
  "previous": null,
  "results": [...]
}
```

**Navigate with:**
- `?page=1`
- `?page=2`
- etc.

---

## Filtering & Search

### Filter by field
```
GET /api/admin/users/?role=lecturer&is_active=true
```

### Search across multiple fields
```
GET /api/admin/users/?search=john
```
Searches: `email`, `first_name`, `last_name`

### Order results
```
GET /api/admin/courses/?ordering=-created_at
GET /api/admin/courses/?ordering=title
```

Reverse order with `-` prefix.

---

## Error Responses

### 401 Unauthorized (Missing/Invalid JWT)
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden (Not staff)
```json
{
  "detail": "Only staff users can access this resource."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

### 400 Bad Request
```json
{
  "field_name": ["Error message"]
}
```

---

## Security Considerations

1. **JWT Authentication:** Every request requires a valid access token with `is_staff=True`.
2. **Rate Limiting:** Default DRF throttling applies (1000 req/day for staff, 100 for anon).
3. **Read-Only Endpoints:** Some endpoints (ratings, study sessions) are read-only or delete-only for safety.
4. **Secret Key:** Use environment variables in production; never commit `SECRET_KEY`.
5. **HTTPS:** Always use HTTPS in production (`SECURE_SSL_REDIRECT=True`).
6. **Audit Trail:** Log admin actions for compliance (consider adding a new `AdminAuditLog` model).

---

## Frontend Integration Example

```javascript
// Example: React Hook for fetching admin users

const useAdminUsers = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const token = localStorage.getItem("access_token");

  const fetchUsers = async (role, page = 1) => {
    setLoading(true);
    try {
      const response = await fetch(
        `http://localhost:8000/api/admin/users/?role=${role}&page=${page}`,
        {
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
          }
        }
      );
      const data = await response.json();
      setUsers(data.results);
    } catch (error) {
      console.error("Failed to fetch users:", error);
    } finally {
      setLoading(false);
    }
  };

  return { users, loading, fetchUsers };
};
```

---

## Testing the API

### Using cURL

```bash
# Get all courses
curl -X GET "http://localhost:8000/api/admin/courses/" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Create a university
curl -X POST "http://localhost:8000/api/admin/universities/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Stanford University"}'

# Deactivate a user
curl -X POST "http://localhost:8000/api/admin/users/{user_id}/deactivate/" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Using Postman

1. Import the OpenAPI schema from `/api/schema/`
2. Set up an `Authorization` header with Bearer token
3. Start making requests to `/api/admin/*` endpoints

---

## Future Enhancements

1. **Audit Logging:** Track who changed what and when.
2. **Admin Actions:** Batch delete, approve/reject enrollments, etc.
3. **Reports:** CSV export for users, enrollments, course analytics.
4. **2FA for Admin:** Require two-factor authentication for staff users.
5. **Role-Based Access:** Fine-grained permissions (e.g., department heads can only manage their dept).
6. **Notifications:** Alert admins of unusual activity or pending approvals.
