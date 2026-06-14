from rest_framework.test import APITestCase
from rest_framework import status
from apps.accounts.models import User
from apps.institutions.models import University, Faculty, Department
from apps.courses.models import Course

class AdministrationScopingTests(APITestCase):
    def setUp(self):
        # Create Universities
        self.univ1 = University.objects.create(name="University of Science", code="UNIV1")
        self.univ2 = University.objects.create(name="State College", code="UNIV2")

        # Create Admins (Staff)
        self.admin1 = User.objects.create_user(
            email="admin1@science.edu", password="password123",
            role="admin", university=self.univ1, is_staff=True
        )
        self.admin2 = User.objects.create_user(
            email="admin2@state.edu", password="password123",
            role="admin", university=self.univ2, is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            email="superuser@platform.com", password="password123"
        )

        # Create Faculties
        self.fac1 = Faculty.objects.create(name="Engineering", university=self.univ1)
        self.fac2 = Faculty.objects.create(name="Arts", university=self.univ2)

        # Create Departments
        self.dept1 = Department.objects.create(name="Computer Science", faculty=self.fac1)
        self.dept2 = Department.objects.create(name="History", faculty=self.fac2)

        # Create Courses
        self.course1 = Course.objects.create(
            title="Introduction to Programming", code="CS101",
            department=self.dept1, level="100"
        )
        self.course2 = Course.objects.create(
            title="World History", code="HIS101",
            department=self.dept2, level="100"
        )

        # Create extra users for each university
        self.student1 = User.objects.create_user(
            email="student1@science.edu", password="password123",
            role="student", university=self.univ1
        )
        self.student2 = User.objects.create_user(
            email="student2@state.edu", password="password123",
            role="student", university=self.univ2
        )

    def test_admin_only_sees_own_university_users(self):
        self.client.force_authenticate(self.admin1)
        response = self.client.get("/api/admin/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        emails = [u["email"] for u in results]
        self.assertIn(self.admin1.email, emails)
        self.assertIn(self.student1.email, emails)
        self.assertNotIn(self.admin2.email, emails)
        self.assertNotIn(self.student2.email, emails)

    def test_admin_only_sees_own_university_faculties(self):
        self.client.force_authenticate(self.admin1)
        response = self.client.get("/api/admin/faculties/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        names = [f["name"] for f in results]
        self.assertIn("Engineering", names)
        self.assertNotIn("Arts", names)

    def test_admin_only_sees_own_university_departments(self):
        self.client.force_authenticate(self.admin1)
        response = self.client.get("/api/admin/departments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        names = [d["name"] for d in results]
        self.assertIn("Computer Science", names)
        self.assertNotIn("History", names)

    def test_admin_only_sees_own_university_courses(self):
        self.client.force_authenticate(self.admin1)
        response = self.client.get("/api/admin/courses/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        titles = [c["title"] for c in results]
        self.assertIn("Introduction to Programming", titles)
        self.assertNotIn("World History", titles)

    def test_superuser_sees_everything(self):
        self.client.force_authenticate(self.superuser)
        
        # Superuser sees all users
        response = self.client.get("/api/admin/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertGreaterEqual(len(results), 4) # admin1, admin2, student1, student2

        # Superuser sees all universities
        response = self.client.get("/api/admin/universities/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        names = [u["name"] for u in results]
        self.assertIn("University of Science", names)
        self.assertIn("State College", names)

    def test_non_staff_admin_access(self):
        # Create an admin user with role='admin' but is_staff=False
        non_staff_admin = User.objects.create_user(
            email="nonstaffadmin@science.edu", password="password123",
            role="admin", university=self.univ1, is_staff=False
        )
        self.client.force_authenticate(non_staff_admin)
        
        # Test that this user can successfully list users, courses, etc.
        response = self.client.get("/api/admin/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response = self.client.get("/api/admin/courses/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

