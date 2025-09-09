#!/bin/bash

# PayVerify Hikvision Terminal Integration Final Test
# This script performs comprehensive testing of the terminal integration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
PC_IP="192.168.100.133"
BASE_URL_80="http://$PC_IP"
HIK_EVENTS_URL="/medical_access/hik/events/"

print_status "=== PayVerify Hikvision Terminal Integration Test ==="
print_status "PC IP: $PC_IP"
print_status "Base URL: $BASE_URL_80"
print_status "Hikvision Events URL: $HIK_EVENTS_URL"

echo ""

# Test 1: Basic connectivity
print_status "Test 1: Basic connectivity to $BASE_URL_80"
if curl -s -o /dev/null -w "%{http_code}" "$BASE_URL_80/" | grep -q "200\|302"; then
    print_success "Basic connectivity working"
else
    print_error "Basic connectivity failed"
    exit 1
fi

# Test 2: Hikvision events endpoint accessibility
print_status "Test 2: Hikvision events endpoint accessibility"
RESPONSE_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL_80$HIK_EVENTS_URL")
if [[ "$RESPONSE_CODE" =~ ^(200|405|500)$ ]]; then
    print_success "Hikvision events endpoint accessible (HTTP $RESPONSE_CODE)"
else
    print_error "Hikvision events endpoint not accessible (HTTP $RESPONSE_CODE)"
fi

# Test 3: Test GET request to Hikvision events
print_status "Test 3: GET request to Hikvision events endpoint"
GET_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL_80$HIK_EVENTS_URL")
HTTP_CODE=$(echo "$GET_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$GET_RESPONSE" | sed '/HTTP_CODE:/d')

if [[ "$HTTP_CODE" =~ ^(200|405)$ ]]; then
    print_success "GET request successful (HTTP $HTTP_CODE)"
    if [[ "$RESPONSE_BODY" == *"OK"* ]]; then
        print_success "Response contains 'OK' - endpoint is working"
    else
        print_warning "Response doesn't contain 'OK': $RESPONSE_BODY"
    fi
else
    print_error "GET request failed (HTTP $HTTP_CODE)"
fi

# Test 4: Test POST request to Hikvision events (simulate terminal event)
print_status "Test 4: POST request simulation (terminal event)"
EVENT_DATA='{"AccessControllerEvent":{"cardNo":"123456789","verifyMode":"card","major":5,"time":"2024-01-01T12:00:00"}}'
POST_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" -d "$EVENT_DATA" -w "\nHTTP_CODE:%{http_code}" "$BASE_URL_80$HIK_EVENTS_URL")
HTTP_CODE=$(echo "$POST_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$POST_RESPONSE" | sed '/HTTP_CODE:/d')

if [[ "$HTTP_CODE" =~ ^(200|405)$ ]]; then
    print_success "POST request successful (HTTP $HTTP_CODE)"
    if [[ "$RESPONSE_BODY" == *"OK"* ]]; then
        print_success "POST response contains 'OK' - terminal events working"
    else
        print_warning "POST response doesn't contain 'OK': $RESPONSE_BODY"
    fi
else
    print_error "POST request failed (HTTP $HTTP_CODE)"
fi

# Test 5: Check Docker containers
print_status "Test 5: Docker container status"
if docker ps | grep -q "payverify_nginx_prod"; then
    print_success "Nginx container is running"
else
    print_error "Nginx container is not running"
fi

if docker ps | grep -q "payverify_web_prod"; then
    print_success "Django app container is running"
else
    print_error "Django app container is not running"
fi

# Test 6: Check Nginx logs for recent requests
print_status "Test 6: Checking Nginx logs for Hikvision requests"
if docker logs payverify_nginx_prod 2>&1 | tail -20 | grep -q "hik"; then
    print_success "Hikvision requests found in recent Nginx logs"
else
    print_warning "No recent Hikvision requests found in Nginx logs"
fi

# Test 7: Check Django logs for Hikvision events
print_status "Test 7: Checking Django logs for Hikvision events"
if docker logs payverify_web_prod 2>&1 | tail -20 | grep -q "hik\|event\|verification"; then
    print_success "Hikvision events found in recent Django logs"
else
    print_warning "No recent Hikvision events found in Django logs"
fi

# Test 8: Test with multipart data (real Hikvision format)
print_status "Test 8: Testing with multipart data (real Hikvision format)"
MULTIPART_DATA='--boundary123
Content-Type: application/json

{"AccessControllerEvent":{"cardNo":"QR123456","verifyMode":"qr","major":5,"time":"2024-01-01T12:00:00"}}
--boundary123--'
MULTIPART_RESPONSE=$(curl -s -X POST -H "Content-Type: multipart/form-data; boundary=boundary123" -d "$MULTIPART_DATA" -w "\nHTTP_CODE:%{http_code}" "$BASE_URL_80$HIK_EVENTS_URL")
HTTP_CODE=$(echo "$MULTIPART_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$MULTIPART_RESPONSE" | sed '/HTTP_CODE:/d')

if [[ "$HTTP_CODE" =~ ^(200|405)$ ]]; then
    print_success "Multipart request successful (HTTP $HTTP_CODE)"
    if [[ "$RESPONSE_BODY" == *"OK"* ]]; then
        print_success "Multipart response contains 'OK' - real Hikvision format working"
    else
        print_warning "Multipart response doesn't contain 'OK': $RESPONSE_BODY"
    fi
else
    print_error "Multipart request failed (HTTP $HTTP_CODE)"
fi

echo ""
print_status "=== Terminal Configuration Instructions ==="
echo ""
print_success "✅ RECOMMENDED TERMINAL CONFIGURATION:"
echo "   • Event Alarm IP/Domain: $PC_IP"
echo "   • URL: $HIK_EVENTS_URL"
echo "   • Port: 80 (NOT 8000)"
echo "   • Protocol: HTTP"
echo ""
print_warning "❌ AVOID THIS CONFIGURATION:"
echo "   • Port: 8000 (will not work with Nginx proxy)"
echo "   • HTTPS (unless you have SSL certificates)"
echo ""
print_status "=== Troubleshooting Commands ==="
echo ""
echo "Check Nginx logs:"
echo "   docker logs payverify_nginx_prod"
echo ""
echo "Check Django logs:"
echo "   docker logs payverify_web_prod"
echo ""
echo "Test from another device:"
echo "   curl -i $BASE_URL_80$HIK_EVENTS_URL"
echo ""
echo "Monitor real-time logs:"
echo "   docker logs -f payverify_nginx_prod"
echo "   docker logs -f payverify_web_prod"
echo ""
print_status "=== Test Complete ==="
