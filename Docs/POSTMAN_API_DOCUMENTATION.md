# Acadexis Backend API Postman Documentation

This document explains how to use the Postman collection for the Acadexis backend.
It includes the complete API structure, endpoint usage, authentication workflow, and sample payloads.

## Postman Collection

Import the JSON file located at:

- `Docs/POSTMAN_COLLECTION.json`

This collection contains grouped requests for:
- Auth
- Institutions
- Courses
- Study sessions
- Analytics
- Notifications
- Support
- Admin APIs

## Environment Setup

Create a Postman environment with these variables:

- `base_url` = `http://localhost:8000/api`
- `token` = ``
- `refresh_token` = ``
- `university_id` = ``
- `faculty_id` = ``
- `department_id` = ``
- `course_id` = ``
- `material_id` = ``
- `module_id` = ``
- `session_id` = ``
- `user_id` = ``
- `student_id` = ``
- `notification_id` = ``
- `student1_id` = ``
- `student2_id` = ``

Use `{{base_url}}` in request URLs, and set `Authorization: Bearer {{token}}` for protected requests.

## Authentication

### Register

- `POST {{base_url}}/auth/register/`
- Public endpoint
- Payload example for a student:

```json
{
  "email": "student@example.com",
  "password": "Password123!",
  "role": "student",
  "university": "{{university_id}}",
  "faculty": "{{faculty_id}}",
  "department": "{{department_id}}",
  "first_name": "Jane",
  "last_name": "Doe",
  "identification_number": "STU2026001",
  "level": "3rd Year"
}
```

### Login

- `POST {{base_url}}/auth/login/`
- Returns access and refresh tokens

```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

### Admin Login

- `POST {{base_url}}/auth/admin-login/`
- Same as login but intended for admin accounts

### Token Refresh

- `POST {{base_url}}/auth/token/refresh/`

```json
{
  "refresh": "{{refresh_token}}"
}
```

### Current User

- `GET {{base_url}}/auth/me/`
- Requires `Authorization: Bearer {{token}}`

### Profile

- `GET {{base_url}}/auth/profile/`
- Requires `Authorization: Bearer {{token}}`

### Logout

- `POST {{base_url}}/auth/logout/`
- Requires `Authorization: Bearer {{token}}`

```json
{
  "refresh": "{{refresh_token}}"
}
```

### Password Reset and Change

- `POST {{base_url}}/auth/forgot-password/`
- `POST {{base_url}}/auth/reset-password/`
- `POST {{base_url}}/auth/change-password/`

## Institutions

### Public endpoints

- `GET {{base_url}}/universities/`
- `GET {{base_url}}/universities/{{university_id}}/`
- `GET {{base_url}}/faculties/?university={{university_id}}`
- `GET {{base_url}}/faculties/{{faculty_id}}/`
- `GET {{base_url}}/departments/?faculty={{faculty_id}}&university={{university_id}}`
- `GET {{base_url}}/departments/{{department_id}}/`

These are all public reads and can be used by registration forms without auth.

## Courses

Requires `Authorization: Bearer {{token}}` for all course endpoints.

### List courses

- `GET {{base_url}}/courses/?department={{department_id}}&lecturer={{lecturer_id}}&level=400`

### Create course

- `POST {{base_url}}/courses/`
- Sample payload:

```json
{
  "title": "Advanced Physics",
  "code": "PHY401",
  "description": "Physics course for senior students.",
  "department": "{{department_id}}",
  "level": "400",
  "lecturer_remark": "Updated for Q3"
}
```

### Course detail

- `GET {{base_url}}/courses/{{course_id}}/`

### Update course

- `PATCH {{base_url}}/courses/{{course_id}}/`

```json
{
  "description": "Updated course description."
}
```

### Delete course

- `DELETE {{base_url}}/courses/{{course_id}}/`

### My courses

- `GET {{base_url}}/courses/mine/`

### Enroll

- `POST {{base_url}}/courses/{{course_id}}/enroll/`
- Only students can enroll

### Rate course

- `POST {{base_url}}/courses/{{course_id}}/rate/`

```json
{
  "score": 5,
  "reaction": "up"
}
```

## Course Materials

### List materials

- `GET {{base_url}}/materials/?course={{course_id}}&status=ready`

### Upload material

- `POST {{base_url}}/materials/`
- Use `form-data` with:
  - `course` = `{{course_id}}`
  - `file` = select file

### Material detail

- `GET {{base_url}}/materials/{{material_id}}/`

### Rename material

- `PATCH {{base_url}}/materials/{{material_id}}/`

```json
{
  "file_name": "New Document Title.pdf"
}
```

### Delete material

- `DELETE {{base_url}}/materials/{{material_id}}/`

## Modules

- `GET {{base_url}}/modules/?course={{course_id}}`
- `GET {{base_url}}/modules/{{module_id}}/`

## Recommendations

- `GET {{base_url}}/recommendations/`

## Study Sessions

Requires `Authorization: Bearer {{token}}`.

### List sessions

- `GET {{base_url}}/sessions/?course={{course_id}}`

### Create session

- `POST {{base_url}}/sessions/`

```json
{
  "course": "{{course_id}}",
  "title": "Exam Revision Session",
  "description": "Revision for next week"
}
```

### Session detail

- `GET {{base_url}}/sessions/{{session_id}}/`

### Session messages

- `GET {{base_url}}/sessions/{{session_id}}/messages/`

### Ask a question

- `POST {{base_url}}/sessions/{{session_id}}/ask/`

```json
{
  "message": "What is the formula for kinetic energy?"
}
```

### Feedback

- `POST {{base_url}}/sessions/{{session_id}}/feedback/`

```json
{
  "rating": 5,
  "note": "Very helpful session."
}
```

## Analytics

### Heatmap

- `GET {{base_url}}/heatmap/?course={{course_id}}`
- Requires lecturer or admin auth

### Bookmarks

- `GET {{base_url}}/bookmarks/`
- `POST {{base_url}}/bookmarks/`

Sample payload:

```json
{
  "kind": "note",
  "title": "Important concept",
  "content": "Learned about vectors today.",
  "material": "{{material_id}}",
  "page": 12,
  "message": "Revisit this later"
}
```

## Notifications

- `GET {{base_url}}/notifications/?read=false`
- `GET {{base_url}}/notifications/unread-count/`
- `POST {{base_url}}/notifications/mark-all-read/`
- `POST {{base_url}}/notifications/{{notification_id}}/mark-as-read/`

## Support

### Contact

- `POST {{base_url}}/support/contact/`

```json
{
  "subject": "Account question",
  "body": "I need help registering.",
  "email": "user@example.com"
}
```

### Report issue

- `POST {{base_url}}/support/report/`

```json
{
  "title": "Payment page crash",
  "description": "The checkout page fails to load.",
  "severity": "high"
}
```

### Admin request

- `POST {{base_url}}/support/admin-request/`
- Use `form-data` with:
  - `reason`
  - `document_proof` (file)

## Admin API

Admin endpoints are under `/api/admin/` and require staff auth.

### Users

- `GET {{base_url}}/admin/users/?role=student&is_active=true`
- `POST {{base_url}}/admin/users/`
- `GET {{base_url}}/admin/users/{{user_id}}/`
- `POST {{base_url}}/admin/users/{{user_id}}/deactivate/`
- `POST {{base_url}}/admin/users/{{user_id}}/activate/`
- `POST {{base_url}}/admin/users/{{user_id}}/promote_to_staff/`
- `POST {{base_url}}/admin/users/{{user_id}}/demote_from_staff/`

### Universities

- `GET {{base_url}}/admin/universities/`
- `POST {{base_url}}/admin/universities/`

### Faculties

- `GET {{base_url}}/admin/faculties/?university={{university_id}}`
- `POST {{base_url}}/admin/faculties/`

### Departments

- `GET {{base_url}}/admin/departments/?faculty={{faculty_id}}`
- `POST {{base_url}}/admin/departments/`

### Enrollment

- `GET {{base_url}}/admin/enrollments/?student={{student_id}}&course={{course_id}}`
- `POST {{base_url}}/admin/enrollments/`
- `POST {{base_url}}/admin/enrollments/bulk-enroll/`

### Materials

- `GET {{base_url}}/admin/materials/?course={{course_id}}&status=ready`

### Ratings

- `GET {{base_url}}/admin/ratings/?course={{course_id}}&score=5`

### Study Sessions

- `GET {{base_url}}/admin/study-sessions/?user={{user_id}}&course={{course_id}}`

## Notes

- `base_url` is the API root and should include `/api` for local testing.
- Use `Authorization: Bearer {{token}}` for all protected endpoints.
- Institution read endpoints are public and do not require auth.
- Admin endpoints require staff or admin permissions.
- The collection can be imported into Postman as a JSON file.

## Quick start

1. Import `Docs/POSTMAN_COLLECTION.json` into Postman.
2. Set the environment variable `base_url` to your backend address.
3. Run `Auth > Login` and copy `access` into `{{token}}`.
4. Run public institution requests first to get `university_id`, `faculty_id`, and `department_id`.
5. Test protected endpoints using the bearer token.
