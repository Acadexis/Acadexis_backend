"""
Management command to create a superuser from environment variables.
Only creates if SUPERUSER_EMAIL and SUPERUSER_PASSWORD are set.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.auth import get_user_model
from decouple import config


class Command(BaseCommand):
    help = 'Create superuser from environment variables if not exists'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreate superuser even if exists',
        )

    def handle(self, *args, **options):
        User = get_user_model()

        email = config('SUPERUSER_EMAIL', default=None)
        password = config('SUPERUSER_PASSWORD', default=None)

        if not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    'SUPERUSER_EMAIL and SUPERUSER_PASSWORD not set. '
                    'Skipping superuser creation.'
                )
            )
            return

        # Check if user exists
        if User.objects.filter(email=email).exists():
            if options.get('force'):
                self.stdout.write(f'Force recreating superuser: {email}')
                User.objects.filter(email=email).delete()
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'Superuser already exists: {email}')
                )
                return

        # Create superuser
        user = User.objects.create_superuser(
            email=email,
            password=password,
            first_name=config('SUPERUSER_FIRST_NAME', default='Admin'),
            last_name=config('SUPERUSER_LAST_NAME', default='User'),
        )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created superuser: {email}')
        )