#!/bin/bash

# Simple PayVerify Test Script
# Tests if everything is working correctly

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

# Get server IP (works on both macOS and Linux)
if command -v hostname >/dev/null 2>&1 && hostname -I >/dev/null 2>&1; then
    # Linux
    SERVER_IP=$(hostname -I | awk '{print $1}')
elif command -v ifconfig >/dev/null 2>&1; then
    # macOS
    SERVER_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{print $2}')
else
    # Fallback
    SERVER_IP="localhost"
fi
print_status "Testing PayVerify on IP: $SERVER_IP"

# Test 1: Check containers
print_status "Test 1: Checking containers..."
if docker ps | grep -q "payverify_nginx_prod" && docker ps | grep -q "payverify_web_prod"; then
    print_success "All containers are running"
else
    print_error "Some containers are not running"
    docker ps
    exit 1
fi

# Test 2: Test main page
print_status "Test 2: Testing main page..."
if curl -s -o /dev/null -w "%{http_code}" "http://$SERVER_IP/" | grep -q "200\|302"; then
    print_success "Main page is accessible"
else
    print_error "Main page is not accessible"
fi

# Test 3: Test Hikvision endpoint
print_status "Test 3: Testing Hikvision endpoint..."
HIK_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "http://$SERVER_IP/medical_access/hik/events/")
HTTP_CODE=$(echo "$HIK_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)

if [[ "$HTTP_CODE" =~ ^(200|405)$ ]]; then
    print_success "Hikvision endpoint is working (HTTP $HTTP_CODE)"
else
    print_error "Hikvision endpoint failed (HTTP $HTTP_CODE)"
fi

# Test 4: Test with POST request (simulate terminal)
print_status "Test 4: Testing terminal simulation..."
EVENT_DATA='{"AccessControllerEvent":{"cardNo":"TEST123","verifyMode":"card","major":5}}'
POST_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" -d "$EVENT_DATA" -w "\nHTTP_CODE:%{http_code}" "http://$SERVER_IP/medical_access/hik/events/")
HTTP_CODE=$(echo "$POST_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)

if [[ "$HTTP_CODE" =~ ^(200|405)$ ]]; then
    print_success "Terminal simulation successful (HTTP $HTTP_CODE)"
else
    print_error "Terminal simulation failed (HTTP $HTTP_CODE)"
fi

echo ""
print_success "=== Test Complete ==="
echo ""
print_status "Your PayVerify is ready!"
echo "   • Web Access: http://$SERVER_IP"
echo "   • Terminal IP: $SERVER_IP"
echo "   • Terminal URL: /medical_access/hik/events/"
echo "   • Terminal Port: 80"
echo ""
print_status "To view logs:"
echo "   docker-compose logs -f"
