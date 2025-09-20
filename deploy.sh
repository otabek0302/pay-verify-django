
#!/bin/bash

set -e

echo "🚀 PayVerify - Complete Deployment Script"
echo "========================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    echo "Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from env.simple..."
    cp env.simple .env
    echo "✅ .env file created from env.simple"
    echo "   You can edit .env to customize settings if needed"
fi

# Create logs directory if it doesn't exist
if [ ! -d logs ]; then
    echo "📁 Creating logs directory..."
    mkdir -p logs
    echo "✅ Logs directory created"
fi

# Make scripts executable
chmod +x entrypoint.sh

echo ""
echo "🐳 Starting Docker containers..."

# Stop old containers
echo "Stopping existing containers..."
docker-compose down

# Build and start containers
echo "Building and starting containers..."
docker-compose build
docker-compose up -d

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 15

# Run migrations
echo "Running database migrations..."
docker-compose exec web python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
docker-compose exec web python manage.py collectstatic --noinput

# Create superuser if it doesn't exist
echo "Ensuring superuser exists..."
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('Superuser created: admin/admin123')
else:
    print('Superuser already exists')
"

echo ""
echo "🔍 Checking container status..."
docker-compose ps

echo ""
echo "✅ Deployment complete!"
echo "🌐 Your app is running at:"
echo "   - Main app: http://localhost"
echo "   - Admin panel: http://localhost/admin (admin/admin123)"
echo ""
echo "📋 Quick commands:"
echo "   - View logs: docker-compose logs -f"
echo "   - Stop app: docker-compose down"
echo "   - Restart: docker-compose restart"