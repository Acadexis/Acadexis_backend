"""
rag/ — Acadexis RAG AI & Security pipeline.

This package is the AI team's integration layer. It is imported by:
  - apps/studylab/services.py  → answer_question()
  - apps/courses/tasks.py      → process_material()
  - apps/studylab/apps.py      → StudylabConfig.ready()

Do not import Django models or apps directly from this package.
All Django DB interaction stays in services.py and tasks.py.
"""
