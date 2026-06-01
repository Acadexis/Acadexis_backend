from django.core.management.base import BaseCommand
from apps.courses.models import Course
from apps.analytics.models import TopicStruggle


class Command(BaseCommand):
    help = "Seeds TopicStruggle records with sample analytics data for development."

    SAMPLE_TOPICS = [
        ("Differential Equations", 45, 0.42, 12),
        ("Integration Techniques", 28, 0.74, 7),
        ("Linear Algebra Basics", 33, 0.58, 10),
        ("Probability Theory", 19, 0.81, 3),
        ("Fourier Transforms", 52, 0.35, 18),
        ("Vector Calculus", 17, 0.69, 5),
        ("Complex Analysis", 41, 0.44, 14),
        ("Numerical Methods", 23, 0.77, 4),
    ]

    def handle(self, *args, **options):
        courses = Course.objects.all()
        if not courses.exists():
            self.stdout.write(self.style.WARNING(
                "No courses found. Run seed_institutions and create courses first."
            ))
            return

        count = 0
        for course in courses:
            for topic, q, conf, struggling in self.SAMPLE_TOPICS:
                TopicStruggle.objects.update_or_create(
                    course=course,
                    topic=topic,
                    defaults={
                        "questions_asked": q,
                        "avg_confidence": conf,
                        "struggling_students": struggling,
                    },
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {count} TopicStruggle records across {courses.count()} courses."
        ))