from rest_framework.test import APITestCase
from apps.accounts.models import User
from apps.institutions.models import University, Faculty, Department
from apps.courses.models import Course
from apps.studylab.models import StudySession

class StudySessionAPITests(APITestCase):
    def setUp(self):
        u = University.objects.create(name="UCT")
        f = Faculty.objects.create(name="Eng", university=u)
        self.dept = Department.objects.create(name="CS", faculty=f)
        self.student = User.objects.create_user("student@x.com", "pass12345",
                                                role="student", university=u)
        # Create student profile manually since there's no auto signal
        from apps.accounts.models import Profile
        Profile.objects.create(
            user=self.student,
            first_name="Student",
            last_name="Test",
            identification_number="STU12345",
            department=self.dept
        )
        
        self.course = Course.objects.create(
            title="ML", code="CS1", description="Intro to ML",
            department=self.dept, level="100"
        )
        self.client.force_authenticate(self.student)

    def test_create_study_session_returns_full_data(self):
        response = self.client.post("/api/sessions/", {
            "course": str(self.course.id),
            "title": "New Session",
        })
        self.assertEqual(response.status_code, 201)
        data = response.json()
        
        # Verify that all read-only generated fields are present in the response
        self.assertIn("id", data)
        self.assertIsNotNone(data["id"])
        self.assertIn("created_at", data)
        self.assertIsNotNone(data["created_at"])
        self.assertIn("updated_at", data)
        self.assertIsNotNone(data["updated_at"])
        self.assertIn("confidence_score", data)
        self.assertEqual(data["confidence_score"], 0.0)
        self.assertEqual(data["title"], "New Session")

