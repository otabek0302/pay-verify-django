#!/bin/bash

echo "🔍 PayVerify Diagnostic Script"
echo "=============================="

echo ""
echo "1. Checking Docker status..."
if command -v docker &> /dev/null; then
    echo "✅ Docker is installed"
    if docker info &> /dev/null; then
        echo "✅ Docker is running"
    else
        echo "❌ Docker is not running. Please start Docker first."
        exit 1
    fi
else
    echo "❌ Docker is not installed"
    exit 1
fi

echo ""
echo "2. Checking container status..."
docker-compose ps

echo ""
echo "3. Checking nginx configuration..."
if docker-compose exec nginx nginx -t 2>/dev/null; then
    echo "✅ Nginx configuration is valid"
else
    echo "❌ Nginx configuration has errors"
fi

echo ""
echo "4. Testing Django app internally..."
if docker-compose exec web curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "✅ Django app is responding internally"
else
    echo "❌ Django app is not responding internally"
fi

echo ""
echo "5. Testing nginx to Django connection..."
if docker-compose exec nginx curl -s http://web:8000/ > /dev/null 2>&1; then
    echo "✅ Nginx can reach Django app"
else
    echo "❌ Nginx cannot reach Django app"
fi

echo ""
echo "6. Checking nginx config file..."
echo "Current nginx config:"
docker-compose exec nginx cat /etc/nginx/conf.d/default.conf | head -10

echo ""
echo "7. Testing external access..."
echo "Try accessing:"
echo "  - http://localhost"
echo "  - http://192.168.100.133"
echo "  - http://localhost/ping (should return 'OK')"

echo ""
echo "8. Recent logs (last 10 lines):"
echo "=== Web Container ==="
docker-compose logs web --tail=5
echo ""
echo "=== Nginx Container ==="
docker-compose logs nginx --tail=5

echo ""
echo "Diagnostic complete!"
