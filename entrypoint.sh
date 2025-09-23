#!/bin/bash

set -e

echo "🚀 PayVerify - Starting Application"
echo "===================================="

# Wait for database to be ready
echo "⏳ Waiting for database..."
while ! nc -z db 5432; do
  echo "   Database not ready, waiting..."
  sleep 2
done
echo "✅ Database is ready!"

# Run migrations
echo "🔄 Running database migrations..."
python manage.py migrate --noinput

# Collect static files (cleaned up)
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput --clear

# Create superuser if it doesn't exist
echo "👤 Ensuring superuser exists..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('✅ Superuser created: admin/admin123')
else:
    print('✅ Superuser already exists')
"

# Create initial integration if it doesn't exist
echo "🔗 Ensuring integration exists..."
python manage.py shell -c "
from medical_access.models import Integration
if not Integration.objects.filter(name='Default').exists():
    Integration.objects.create(name='Default', is_active=True)
    print('✅ Default integration created')
else:
    print('✅ Integration already exists')
"

echo ""
echo "🎉 Application setup complete!"
echo "🌐 Starting Gunicorn server..."

# Start Gunicorn with optimized settings
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --worker-class sync \
    --worker-connections 1000 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout 120 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    controller.wsgi:application
