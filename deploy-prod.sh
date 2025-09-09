#!/bin/bash

# PayVerify Production Deployment Script
# This script sets up and starts the production environment

set -e

echo "🚀 Starting PayVerify Production Deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose is not installed. Please install it and try again."
    exit 1
fi

# Stop any existing containers
print_status "Stopping existing containers..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Build the application
print_status "Building PayVerify application..."
docker-compose -f docker-compose.prod.yml build --no-cache

# Start the services
print_status "Starting production services..."
docker-compose -f docker-compose.prod.yml --env-file production.env up -d

# Wait for services to be healthy
print_status "Waiting for services to be ready..."
sleep 30

# Check if services are running
if docker-compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    print_success "PayVerify is now running in production mode!"
    echo ""
    echo "🌐 Access your application at:"
    echo "   • Local: http://localhost"
    echo "   • Network: http://192.168.1.108"
    echo ""
    echo "📊 Service Status:"
    docker-compose -f docker-compose.prod.yml ps
    echo ""
    echo "📝 Logs:"
    echo "   docker-compose -f docker-compose.prod.yml logs -f"
    echo ""
    echo "🛑 Stop services:"
    echo "   docker-compose -f docker-compose.prod.yml down"
else
    print_error "Failed to start services. Check logs with:"
    echo "docker-compose -f docker-compose.prod.yml logs"
    exit 1
fi
