from rest_framework.test import APITestCase
from apps.accounts.models import User
from apps.institutions.models import University, Faculty, Department
from .models import Course

class CourseAPITests(APITestCase):
    def setUp(self):
        u = University.objects.create(name="UCT")
        f = Faculty.objects.create(name="Eng", university=u)
        self.dept = Department.objects.create(name="CS", faculty=f)
        self.lect = User.objects.create_user("l@x.com", "pass12345",
                                             role="lecturer", university=u)
        self.client.force_authenticate(self.lect)

    def test_create_course(self):
        r = self.client.post("/api/courses/", {
            "title": "ML", "code": "CS1", "description": "x",
            "department": str(self.dept.id), "lecturer": str(self.lect.id),
        })
        self.assertEqual(r.status_code, 201)

    def test_retrieve_course(self):
        # First create a course
        r = self.client.post("/api/courses/", {
            "title": "ML", "code": "CS1", "description": "x",
            "department": str(self.dept.id), "lecturer": str(self.lect.id),
        })
        self.assertEqual(r.status_code, 201)
        
        course = Course.objects.get(code="CS1")
        course_id = course.id

        # Retrieve the course
        r_get = self.client.get(f"/api/courses/{course_id}/")
        self.assertEqual(r_get.status_code, 200)
        self.assertEqual(str(r_get.data["department"]), str(self.dept.id))