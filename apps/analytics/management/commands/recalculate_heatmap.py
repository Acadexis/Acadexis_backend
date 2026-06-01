from django.core.management.base import BaseCommand
from apps.studylab.models import StudySession
from apps.analytics.models import TopicStruggle
from apps.courses.models import Course


class Command(BaseCommand):
    help = "Recalculates all TopicStruggle records from existing StudySession data."

    def handle(self, *args, **options):
        # Get all unique (course, topic) pairs from existing sessions
        pairs = StudySession.objects.values("course", "title").distinct()

        count = 0
        for pair in pairs:
            try:
                course = Course.objects.get(id=pair["course"])
                topic = pair["title"].strip()
                if topic:
                    TopicStruggle.recalculate_for_topic(course=course, topic=topic)
                    count += 1
            except Course.DoesNotExist:
                continue

        self.stdout.write(
            self.style.SUCCESS(f"Recalculated {count} topic struggle records.")
        )