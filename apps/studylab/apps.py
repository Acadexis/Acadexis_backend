from django.apps import AppConfig


class StudylabConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.studylab'
    verbose_name = "Studylab"

    def ready(self):
        import apps.analytics.signals  # noqa: F401 — register analytics signals

        # Initialize the RAG AI pipeline on Django startup.
        # Non-fatal: if API keys are missing the platform still works (keyword fallback).
        from django.conf import settings
        if getattr(settings, "GOOGLE_API_KEY", "") and getattr(settings, "PINECONE_API_KEY", ""):
            try:
                from rag.startup import initialize_rag
                initialize_rag()
            except Exception as exc:
                import logging
                logging.getLogger("rag").warning(
                    "RAG startup skipped: %s", exc
                )
