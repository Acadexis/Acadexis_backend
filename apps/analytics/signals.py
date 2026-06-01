import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="studylab.StudySession")
def update_heatmap_on_session_save(sender, instance, **kwargs):
    try:
        from apps.analytics.models import TopicStruggle

        TopicStruggle.recalculate_for_topic(
            course=instance.course,
            topic=instance.title.strip(),
        )
    except Exception as e:
        logger.warning(f"update_heatmap_on_session_save: {e}")


@receiver(post_save, sender="studylab.SessionFeedback")
def update_heatmap_on_feedback(sender, instance, **kwargs):
    try:
        from apps.analytics.models import TopicStruggle

        TopicStruggle.recalculate_for_topic(
            course=instance.session.course,
            topic=instance.session.title.strip(),
        )
    except Exception as e:
        logger.warning(f"update_heatmap_on_feedback: {e}")


@receiver(post_save, sender="studylab.ChatMessage")
def update_heatmap_on_message(sender, instance, **kwargs):
    if instance.role != "user":
        return
    try:
        from apps.analytics.models import TopicStruggle

        TopicStruggle.recalculate_for_topic(
            course=instance.session.course,
            topic=instance.session.title.strip(),
        )
    except Exception as e:
        logger.warning(f"update_heatmap_on_message: {e}")
