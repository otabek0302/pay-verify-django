#!/bin/bash

# PayVerify Deployment Test Script
# Tests if the deployment is working correctly

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Configuration
SERVER_IP="192.168.100.145"
BASE_URL="http://$SERVER_IP"

print_status "Testing PayVerify deployment on $SERVER_IP"
echo ""

# Test 1: Check if containers are running
print_status "1. Checking if containers are running..."
if docker ps | grep -q "payverify_nginx_prod"; then
    print_success "Nginx container is running"
else
    print_error "Nginx container is not running"
    exit 1
fi

if docker ps | grep -q "payverify_web_prod"; then
    print_success "Django web container is running"
else
    print_error "Django web container is not running"
    exit 1
fi

if docker ps | grep -q "payverify_db_prod"; then
    print_success "PostgreSQL database container is running"
else
    print_error "PostgreSQL database container is not running"
    exit 1
fi

# Test 2: Check if web application is accessible
print_status "2. Testing web application accessibility..."
if curl -s -f "$BASE_URL/" > /dev/null; then
    print_success "Web application is accessible at $BASE_URL"
else
    print_error "Web application is not accessible at $BASE_URL"
    print_warning "Check if port 80 is open and nginx is running"
fi

# Test 3: Check if Hikvision endpoint is accessible
print_status "3. Testing Hikvision terminal endpoint..."
if curl -s -f "$BASE_URL/medical_access/hik/events/" > /dev/null; then
    print_success "Hikvision endpoint is accessible"
else
    print_warning "Hikvision endpoint test failed (this is normal for GET requests)"
fi

# Test 4: Check if static files are served
print_status "4. Testing static files..."
if curl -s -f "$BASE_URL/static/admin/css/base.css" > /dev/null; then
    print_success "Static files are being served correctly"
else
    print_warning "Static files test failed"
fi

# Test 5: Check database connectivity
print_status "5. Testing database connectivity..."
if docker exec payverify_web_prod python manage.py check --database default > /dev/null 2>&1; then
    print_success "Database connectivity is working"
else
    print_error "Database connectivity test failed"
fi

# Test 6: Check if admin interface is accessible
print_status "6. Testing admin interface..."
if curl -s -f "$BASE_URL/admin/" > /dev/null; then
    print_success "Admin interface is accessible"
else
    print_warning "Admin interface test failed"
fi

echo ""
print_success "Deployment test completed!"
echo ""
echo "🌐 Your PayVerify application is running at:"
echo "   • Main Application: $BASE_URL"
echo "   • Admin Interface: $BASE_URL/admin/"
echo "   • Medical Dashboard: $BASE_URL/medical_access/"
echo ""
echo "📱 Terminal Configuration:"
echo "   • Event Alarm IP: $SERVER_IP"
echo "   • URL: /medical_access/hik/events/"
echo "   • Port: 80"
echo "   • Protocol: HTTP"
echo ""
echo "🔧 Management Commands:"
echo "   • View logs: docker-compose logs -f"
echo "   • Stop: docker-compose down"
echo "   • Restart: docker-compose restart"
echo "   • Test again: ./test_deployment.sh"
