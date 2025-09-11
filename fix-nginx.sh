#!/bin/bash

echo "🔧 Fixing Nginx Container Issue"
echo "==============================="

echo ""
echo "1. Stopping all containers..."
docker-compose down

echo ""
echo "2. Checking nginx configuration..."
if [ -f nginx/nginx.conf ]; then
    echo "✅ nginx.conf exists"
    echo "Configuration preview:"
    head -10 nginx/nginx.conf
else
    echo "❌ nginx.conf not found!"
    exit 1
fi

echo ""
echo "3. Starting containers in order..."
echo "Starting database..."
docker-compose up -d db

echo "Waiting for database to be ready..."
sleep 10

echo "Starting web application..."
docker-compose up -d web

echo "Waiting for web app to be ready..."
sleep 10

echo "Starting nginx..."
docker-compose up -d nginx

echo ""
echo "4. Checking container status..."
docker-compose ps

echo ""
echo "5. Testing nginx configuration..."
if docker-compose exec nginx nginx -t 2>/dev/null; then
    echo "✅ Nginx configuration is valid"
else
    echo "❌ Nginx configuration has errors:"
    docker-compose exec nginx nginx -t
fi

echo ""
echo "6. Testing connections..."
echo "Testing Django app internally..."
if docker-compose exec web curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "✅ Django app is responding"
else
    echo "❌ Django app is not responding"
fi

echo "Testing nginx to Django connection..."
if docker-compose exec nginx curl -s http://web:8000/ > /dev/null 2>&1; then
    echo "✅ Nginx can reach Django app"
else
    echo "❌ Nginx cannot reach Django app"
fi

echo ""
echo "7. Testing external access..."
echo "Try accessing:"
echo "  - http://localhost"
echo "  - http://192.168.100.133"
echo "  - http://localhost/ping"

echo ""
echo "Fix complete! Check the results above."
