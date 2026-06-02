"""
Management command to enable pgvector extension.
Run this before migrations if using vector embeddings.
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Enable pgvector extension for vector embeddings'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Check if extension exists
            cursor.execute("""
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            """)
            exists = cursor.fetchone()

            if not exists:
                self.stdout.write('Creating pgvector extension...')
                cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
                self.stdout.write(
                    self.style.SUCCESS('pgvector extension enabled!')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('pgvector extension already exists.')
                )