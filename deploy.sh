#!/bin/bash

# Simple PayVerify Deployment Script
# Works on any server - automatically detects IP

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

# Get the server IP automatically (works on both macOS and Linux)
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
print_status "Detected server IP: $SERVER_IP"

# Update the environment file with the detected IP
print_status "Updating environment file with IP: $SERVER_IP"
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s/ALLOWED_HOSTS=.*/ALLOWED_HOSTS=$SERVER_IP,192.168.1.108,192.168.1.100,localhost,127.0.0.1,0.0.0.0,*/" env.simple
else
    # Linux
    sed -i "s/ALLOWED_HOSTS=.*/ALLOWED_HOSTS=$SERVER_IP,192.168.1.108,192.168.1.100,localhost,127.0.0.1,0.0.0.0,*/" env.simple
fi

# Stop any existing containers
print_status "Stopping existing containers..."
docker-compose down 2>/dev/null || true

# Start the services
print_status "Starting PayVerify services..."
docker-compose --env-file env.simple up -d

# Wait for services to start
print_status "Waiting for services to start..."
sleep 30

# Check if services are running
if docker ps | grep -q "payverify_nginx_prod"; then
    print_success "PayVerify is running!"
    echo ""
    echo "🌐 Access your application at:"
    echo "   • http://$SERVER_IP"
    echo "   • http://$SERVER_IP:8000 (alternative)"
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
    echo "   • Test: ./test.sh"
else
    print_error "Failed to start services. Check logs:"
    echo "docker-compose logs"
    exit 1
fi
