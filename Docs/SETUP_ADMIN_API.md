# Administration API Setup & Quick Start

## What Was Built

A complete, production-ready **Administration API** app that exposes all admin functionality via REST endpoints **without exposing Django's built-in admin interface**. Your frontend can now:

- ✅ Manage users (create, edit, deactivate, promote to staff)
- ✅ Manage universities, faculties, departments
- ✅ Manage courses (create, edit, delete)
- ✅ Manage enrollments (single and bulk)
- ✅ Manage course materials (upload, list, filter)
- ✅ View ratings and study sessions (audit)
- ✅ Search and filter on all resources
- ✅ Perform custom actions (approve, deactivate, etc.)

---

## Files Created

```
apps/administration/
├── __init__.py                       # Empty init
├── apps.py                           # App config
├── models.py                         # Empty (uses existing models)
├── permissions.py                   # IsStaffUser, IsAdminUser, IsStaffOrAdmin
├── serializers.py                   # All model serializers with nested relations
├── viewsets.py                       # CRUD viewsets + custom actions
├── urls.py                           # DRF router + URL patterns
└── admin.py                          # Empty (API-only, no Django admin)

Updated Files:
├── Acadexis_backend/settings/base.py # Added "apps.administration" to INSTALLED_APPS
├── Acadexis_backend/urls.py          # Added /api/admin/ namespace

Documentation:
├── Docs/ADMINISTRATION_API.md        # Complete API reference
└── Docs/SETUP_ADMIN_API.md          # This file
```

---

## How It Works

### Architecture
```
Your Frontend Admin Dashboard
        ↓ (HTTPS + JWT Token)
        ↓
GET /api/admin/users/               (List with filters)
POST /api/admin/users/              (Create new user)
PATCH /api/admin/users/{id}/        (Edit user)
POST /api/admin/users/{id}/deactivate/  (Custom action)
        ↓
Django REST Framework Viewsets
        ↓
IsStaffUser Permission Check (JWT + is_staff=True)
        ↓
Django ORM
        ↓
PostgreSQL Database
```

### Key Points

1. **Staff-Only Access:** Only users with `is_staff=True` can access `/api/admin/*`
2. **JWT Protected:** Every request requires `Authorization: Bearer <token>` header
3. **No Django Admin Exposed:** The built-in `/admin/` can be disabled/hidden from users
4. **Full CRUD:** Create, read, update, delete all resources
5. **Pagination:** 20 results per page (configurable)
6. **Search & Filtering:** Advanced query capabilities on all list endpoints

---

## Quick Setup

### 1. Run Migrations (if needed)
Since the `administration` app uses existing models, no new migrations are required.

```bash
python manage.py migrate
```

### 2. Create a Staff User (if you don't have one)

```bash
python manage.py createsuperuser
# Email: admin@example.com
# Password: yourpassword

# Or via shell:
python manage.py shell
>>> from apps.accounts.models import User
>>> user = User.objects.create_superuser(
...     email='admin@example.com',
...     password='yourpassword',
...     first_name='Admin',
...     last_name='User'
... )
>>> user.is_staff = True
>>> user.save()
```

### 3. Start the Dev Server

```bash
python manage.py runserver
```

### 4. Get an Access Token

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "yourpassword"}'
```

**Response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": { ... }
}
```

### 5. Test the API

```bash
# Replace YOUR_TOKEN with the access token from step 4

# List all users
curl -X GET http://localhost:8000/api/admin/users/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# List all courses
curl -X GET http://localhost:8000/api/admin/courses/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# Create a university
curl -X POST http://localhost:8000/api/admin/universities/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Harvard University"}'
```

---

## API Endpoints Summary

| Resource | List | Create | Detail | Update | Delete | Custom Actions |
|----------|------|--------|--------|--------|--------|-----------------|
| **Users** | ✅ | ✅ | ✅ | ✅ | ❌ | deactivate, activate, promote_to_staff, demote_from_staff |
| **Universities** | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **Faculties** | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **Departments** | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **Courses** | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **Enrollments** | ✅ | ✅ | ✅ | ✅ | ✅ | bulk_enroll |
| **Materials** | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **Ratings** | ✅ | ❌ | ✅ | ❌ | ✅ | — |
| **Study Sessions** | ✅ | ❌ | ✅ | ❌ | ❌ | — |

---

## Connecting Your Frontend

Your React/Vue frontend can now consume this API:

### JavaScript/Fetch Example

```javascript
// utils/adminApi.js
const API_BASE_URL = "http://localhost:8000/api/admin";

export const adminApi = {
  // Get all users
  getUsers: async (token, filters = {}) => {
    const query = new URLSearchParams(filters).toString();
    const response = await fetch(`${API_BASE_URL}/users/?${query}`, {
      headers: { "Authorization": `Bearer ${token}` }
    });
    return response.json();
  },

  // Create a course
  createCourse: async (token, courseData) => {
    const response = await fetch(`${API_BASE_URL}/courses/`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(courseData)
    });
    return response.json();
  },

  // Bulk enroll students
  bulkEnroll: async (token, courseId, studentIds) => {
    const response = await fetch(`${API_BASE_URL}/enrollments/bulk_enroll/`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        course_id: courseId,
        student_ids: studentIds
      })
    });
    return response.json();
  }
};
```

### Using in a React Component

```jsx
import { adminApi } from './utils/adminApi';

function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const token = localStorage.getItem("access_token");

  useEffect(() => {
    const fetchUsers = async () => {
      const data = await adminApi.getUsers(token, { 
        role: "lecturer", 
        ordering: "-created_at" 
      });
      setUsers(data.results);
    };
    fetchUsers();
  }, [token]);

  return (
    <div>
      <h1>Admin Dashboard - Users</h1>
      <table>
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {users.map(user => (
            <tr key={user.id}>
              <td>{user.email}</td>
              <td>{user.role}</td>
              <td>{user.is_active ? "Active" : "Inactive"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

---

## Security Best Practices

1. **Always use HTTPS** in production
2. **JWT tokens should expire** (default: 60 minutes for access)
3. **Require 2FA** for staff users (future enhancement)
4. **Log all admin actions** for compliance (future enhancement)
5. **Rate-limit admin endpoints** (already configured: 1000 req/day)
6. **Rotate secrets regularly** (move `SECRET_KEY` to env vars)
7. **Test staff permissions** before deploying to production

---

## Testing the API Manually

### Option 1: Using cURL

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"yourpassword"}' | jq -r '.access')

# Use token in requests
curl -X GET http://localhost:8000/api/admin/users/ \
  -H "Authorization: Bearer $TOKEN"
```

### Option 2: Using Postman

1. **Create a new Postman collection**
2. **Set up Authorization:**
   - Go to Collection → Authorization
   - Type: Bearer Token
   - Token: `{{access_token}}`
3. **Import the OpenAPI schema:**
   - GET `http://localhost:8000/api/schema/` to get schema
   - Import into Postman
4. **Start testing endpoints**

### Option 3: Using Swagger UI

Visit: `http://localhost:8000/api/docs/swagger/`
- Click "Authorize" button
- Paste your JWT token
- Start making requests from the UI

---

## Troubleshooting

### 401 Unauthorized
- **Cause:** Missing or invalid JWT token
- **Fix:** Get a new token via `/api/auth/login/`

### 403 Forbidden
- **Cause:** User is not staff (`is_staff=False`)
- **Fix:** Set `is_staff=True` on your user account

### 404 Not Found
- **Cause:** App not registered or URL not configured
- **Fix:** Check that `"apps.administration"` is in `INSTALLED_APPS` in `settings/base.py`

### Import Errors
- **Cause:** Missing models or circular imports
- **Fix:** Run `python manage.py check` to validate

---

## Next Steps

1. **Integrate with your frontend:** Use the API endpoints in your React/Vue app
2. **Add audit logging:** Track who made what changes (create `AdminAuditLog` model)
3. **Implement bulk actions:** CSV export, batch approvals, etc.
4. **Add 2FA:** Use `django-two-factor-auth` for staff users
5. **Set up alerting:** Notify admins of suspicious activity
6. **Harden production:** Use environment variables for secrets, enable HTTPS

---

## Support

For more details, see:
- **Complete API Reference:** `Docs/ADMINISTRATION_API.md`
- **Backend Analysis:** `Docs/BACKEND_ANALYSIS.md`
- **OpenAPI Docs:** `http://localhost:8000/api/docs/swagger/`
