from celery import shared_task
from collections import defaultdict
from apps.studylab.models import ChatMessage, SessionFeedback
from .models import TopicStruggle

@shared_task
def recompute_heatmap(course_id):
    # Simple heuristic: group user questions by keyword & average rating
    qs = ChatMessage.objects.filter(role="user", session__course_id=course_id)
    buckets = defaultdict(lambda: {"q": 0, "students": set(), "ratings": []})
    for m in qs.select_related("session"):
        topic = m.content.split()[0:3]  # replace with NLP topic extractor
        key = " ".join(topic).lower()
        buckets[key]["q"] += 1
        buckets[key]["students"].add(m.session.user_id)
    TopicStruggle.objects.filter(course_id=course_id).delete()
    TopicStruggle.objects.bulk_create([
        TopicStruggle(course_id=course_id, topic=k,
                      questions_asked=v["q"],
                      avg_confidence=0.5,
                      struggling_students=len(v["students"]))
        for k, v in buckets.items()
    ])