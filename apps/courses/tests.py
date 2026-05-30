from rest_framework.test import APITestCase
from apps.accounts.models import User
from apps.institutions.models import University, Faculty, Department

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