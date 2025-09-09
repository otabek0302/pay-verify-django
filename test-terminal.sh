#!/bin/bash

# PayVerify Terminal Request Test Script
# This script tests if terminal requests are working through the Nginx proxy

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
BASE_URL="http://$PC_IP"

print_status "Testing PayVerify Terminal Requests..."
print_status "PC IP: $PC_IP"
print_status "Base URL: $BASE_URL"

# Test 1: Basic connectivity
print_status "Test 1: Basic connectivity to $BASE_URL"
if curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/" | grep -q "200\|302"; then
    print_success "Basic connectivity working"
else
    print_error "Basic connectivity failed"
    exit 1
fi

# Test 2: Health check
print_status "Test 2: Health check endpoint"
if curl -s "$BASE_URL/health/" | grep -q "healthy"; then
    print_success "Health check working"
else
    print_warning "Health check failed or not available"
fi

# Test 3: Login page
print_status "Test 3: Login page accessibility"
if curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/medical_access/login/" | grep -q "200"; then
    print_success "Login page accessible"
else
    print_warning "Login page not accessible (might require authentication)"
fi

# Test 4: Terminal endpoints (if they exist)
print_status "Test 4: Terminal endpoints"
if curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/medical_access/terminal/" | grep -q "200\|404"; then
    print_success "Terminal endpoints responding"
else
    print_warning "Terminal endpoints not responding"
fi

# Test 5: Check if Nginx is running
print_status "Test 5: Nginx proxy status"
if docker ps | grep -q "payverify_nginx_prod"; then
    print_success "Nginx proxy is running"
else
    print_error "Nginx proxy is not running"
fi

# Test 6: Check if Django app is running
print_status "Test 6: Django app status"
if docker ps | grep -q "payverify_web_prod"; then
    print_success "Django app is running"
else
    print_error "Django app is not running"
fi

# Test 7: Check port 80 accessibility
print_status "Test 7: Port 80 accessibility"
if nc -z $PC_IP 80; then
    print_success "Port 80 is open and accessible"
else
    print_error "Port 80 is not accessible"
fi

echo ""
print_status "Terminal Request Testing Summary:"
echo "   • Access URL: $BASE_URL"
echo "   • Direct app access: $BASE_URL:8000 (if enabled)"
echo ""
print_status "If terminal requests are still not working:"
echo "   1. Check if terminals are configured with the correct URL: $BASE_URL"
echo "   2. Verify network connectivity between terminals and PC"
echo "   3. Check firewall settings on PC"
echo "   4. Check Nginx logs: docker-compose -f docker-compose.prod.yml logs nginx"
echo "   5. Check Django logs: docker-compose -f docker-compose.prod.yml logs web"
