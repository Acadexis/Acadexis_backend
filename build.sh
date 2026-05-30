#!/bin/bash
set -e

echo "Running Acadexis Backend Build Script..."

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Run migrations
echo "Running migrations..."
python manage.py migrate

echo "Build complete!"
