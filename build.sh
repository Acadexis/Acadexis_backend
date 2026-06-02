#!/bin/bash
set -e

echo "Running Acadexis Backend Build Script..."

echo "Installing Python dependencies..."
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Enable pgvector extension (required for vector embeddings)
echo "Enabling pgvector extension..."
python manage.py enable_pgvector

# Run migrations
echo "Running migrations..."
python manage.py migrate

# Create superuser if credentials are provided
echo "Creating superuser..."
python manage.py createsuperuser_if_not_exists

echo "Build complete!"