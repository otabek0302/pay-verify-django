

#!/bin/bash

set -e

echo "🚀 Starting PayVerify deployment..."

# Stop old containers
docker-compose down

# Build and start containers
docker-compose build
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate --noinput

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

echo "✅ Deployment complete! App running on http://localhost:8000"