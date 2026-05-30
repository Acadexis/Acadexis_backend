from django.core.management.base import BaseCommand
from apps.institutions.models import University, Faculty, Department


class Command(BaseCommand):
    help = "Seed universities, faculties, and departments with sample data"

    def handle(self, *args, **kwargs):
        uni, _ = University.objects.get_or_create(
            code="UNILAG",
            defaults={
                "name": "University of Lagos",
                "description": "A top Nigerian university",
            },
        )
        fac, _ = Faculty.objects.get_or_create(
            name="Faculty of Science",
            university=uni,
        )
        Department.objects.get_or_create(
            name="Computer Science",
            faculty=fac,
            defaults={"code": "CS"},
        )
        Department.objects.get_or_create(
            name="Mathematics",
            faculty=fac,
            defaults={"code": "MTH"},
        )
        self.stdout.write(self.style.SUCCESS("Institutions seeded successfully."))
