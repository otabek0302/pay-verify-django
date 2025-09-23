#!/usr/bin/env bash
set -euo pipefail

echo "🚀 PayVerify - Automated Deployment Script (v3.0.0)"
echo "=================================================="
echo "✨ Flexible deployment for any server with auto IP detection"

# Use Docker Compose v2
COMPOSE="docker compose"

# Get script directory
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# 1) Check prerequisites
log_info "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed. Please install Docker first."
    echo "Ubuntu/Debian: sudo apt update && sudo apt install -y docker.io docker-compose"
    echo "Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    log_error "Docker Compose is not installed. Please install Docker Compose first."
    echo "Ubuntu/Debian: sudo apt install -y docker-compose"
    echo "Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

log_success "Docker and Docker Compose are installed"

# 2) Detect host IP
log_info "Detecting host IP address..."

DETECTED_IP=""
# Try multiple methods to detect IP
if command -v ip &> /dev/null; then
    DETECTED_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '/src/ {print $7; exit}')" || true
fi

if [ -z "$DETECTED_IP" ]; then
    # macOS compatibility
    if command -v ifconfig &> /dev/null; then
        DETECTED_IP="$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)" || true
    else
        DETECTED_IP="$(hostname -I | awk '{print $1}')" || true
    fi
fi

if [ -z "$DETECTED_IP" ]; then
    DETECTED_IP="$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)" || true
fi

if [ -z "$DETECTED_IP" ]; then
    log_error "Could not detect host IP automatically."
    echo "Please set HOST_IP manually in .env file"
    exit 1
fi

log_success "Detected host IP: $DETECTED_IP"

# 3) Prepare .env file
log_info "Preparing environment configuration..."

if [ -f .env ]; then
    log_warning ".env already exists, backing up to .env.bak"
    cp .env .env.bak
fi

if [ ! -f .env.template ]; then
    log_error ".env.template not found. Please ensure it exists in the repository."
    exit 1
fi

# Copy template and fill with detected IP
cp .env.template .env

# Update .env with detected IP (macOS compatible)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS sed
    sed -i '' "s/^HOST_IP=.*$/HOST_IP=${DETECTED_IP}/" .env
    sed -i '' "s/^ALLOWED_HOSTS=.*$/ALLOWED_HOSTS=${DETECTED_IP},localhost,127.0.0.1/" .env
    sed -i '' "s|^CSRF_TRUSTED_ORIGINS=.*$|CSRF_TRUSTED_ORIGINS=http://${DETECTED_IP},https://${DETECTED_IP}|" .env
    sed -i '' "s|^CORS_ALLOWED_ORIGINS=.*$|CORS_ALLOWED_ORIGINS=https://mis.dmed.uz,https://${DETECTED_IP},http://${DETECTED_IP},chrome-extension://peifjgpicbnlpobobglipjgbmpkmcafh|" .env
else
    # Linux sed
    sed -i "s/^HOST_IP=.*$/HOST_IP=${DETECTED_IP}/" .env
    sed -i "s/^ALLOWED_HOSTS=.*$/ALLOWED_HOSTS=${DETECTED_IP},localhost,127.0.0.1/" .env
    sed -i "s|^CSRF_TRUSTED_ORIGINS=.*$|CSRF_TRUSTED_ORIGINS=http://${DETECTED_IP},https://${DETECTED_IP}|" .env
    sed -i "s|^CORS_ALLOWED_ORIGINS=.*$|CORS_ALLOWED_ORIGINS=https://mis.dmed.uz,https://${DETECTED_IP},http://${DETECTED_IP},chrome-extension://peifjgpicbnlpobobglipjgbmpkmcafh|" .env
fi

log_success "Environment configured for IP: $DETECTED_IP"

# 4) Verify nginx config exists
log_info "Checking Nginx configuration..."

if [ ! -f nginx/default.conf ]; then
    log_error "Nginx configuration not found at nginx/default.conf"
    exit 1
fi

log_success "Nginx configuration found"

# 5) Ensure SSL certificates directory exists
log_info "Preparing SSL certificates directory..."
mkdir -p nginx/certs

if [ ! -f nginx/certs/fullchain.pem ] || [ ! -f nginx/certs/privkey.pem ]; then
    log_warning "No TLS certificates found in nginx/certs/"
    log_info "Generating self-signed certificates for development..."
    
    # Generate self-signed certificates
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx/certs/privkey.pem \
        -out nginx/certs/fullchain.pem \
        -subj "/C=US/ST=State/L=City/O=PayVerify/CN=${DETECTED_IP}" 2>/dev/null || {
        log_warning "Could not generate self-signed certificates. HTTPS may not work."
        log_info "For production, add valid certificates to nginx/certs/"
    }
fi

# 6) Stop existing containers
log_info "Stopping existing containers..."
$COMPOSE down -v --remove-orphans || true

# 7) Fix host permissions and create directories
log_info "Setting up host directories and permissions..."
mkdir -p staticfiles
sudo chown -R 1000:1000 staticfiles || true

# 8) Build and start containers
log_info "Building Docker images..."
$COMPOSE build --no-cache

log_info "Starting containers..."
$COMPOSE up -d

# 8) Wait for services to be ready
log_info "Waiting for services to be ready..."
sleep 15

# 9) Run Django setup
log_info "Running Django migrations..."
docker-compose exec -T web python manage.py migrate --noinput

log_info "Creating superuser..."
docker-compose exec -T web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('✅ Superuser created: admin/admin123')
else:
    print('✅ Superuser already exists')
" || true

log_info "Collecting static files..."
docker-compose exec -T web python manage.py collectstatic --noinput --clear

# 10) Health checks
log_info "Running health checks..."

echo ""
log_info "Testing HTTP health endpoint (should redirect to HTTPS)..."
HTTP_RESPONSE=$(curl -s -I "http://${DETECTED_IP}/" | head -1)
if echo "$HTTP_RESPONSE" | grep -q "301"; then
    log_success "HTTP endpoint correctly redirects to HTTPS: $HTTP_RESPONSE"
else
    log_warning "HTTP endpoint response: $HTTP_RESPONSE"
fi

echo ""
log_info "Testing events endpoint (should NOT redirect)..."
EVENTS_RESPONSE=$(curl -s -i -X POST "http://${DETECTED_IP}/medical_access/hik/events/" \
    -H "Content-Type: application/json" -d '{"selftest":"ok"}' | head -1)
if echo "$EVENTS_RESPONSE" | grep -q "200"; then
    log_success "Events endpoint responding correctly: $EVENTS_RESPONSE"
elif echo "$EVENTS_RESPONSE" | grep -q "301"; then
    log_error "Events endpoint is redirecting (should not): $EVENTS_RESPONSE"
else
    log_warning "Events endpoint response: $EVENTS_RESPONSE"
fi

echo ""
log_info "Testing health check endpoint..."
HEALTH_RESPONSE=$(curl -s -I "http://${DETECTED_IP}/medical_access/health" | head -1)
if echo "$HEALTH_RESPONSE" | grep -q "200"; then
    log_success "Health check endpoint responding: $HEALTH_RESPONSE"
else
    log_warning "Health check endpoint response: $HEALTH_RESPONSE"
fi

# 11) Show container status
echo ""
log_info "Container status:"
$COMPOSE ps

# 12) Final instructions
echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Next steps:"
echo "  1. Configure Hikvision terminals:"
echo "     - Protocol: HTTP"
echo "     - IP/Domain: ${DETECTED_IP}"
echo "     - Port: 80"
echo "     - URL: /medical_access/hik/events/"
echo "     - Enable: Access Controller Events"
echo "     - Disable: Upload Historical Events"
echo "     - Set NTP: pool.ntp.org"
echo ""
echo "  2. Access the application:"
echo "     - Main app: http://${DETECTED_IP}/ (redirects to HTTPS)"
echo "     - Admin panel: https://${DETECTED_IP}/admin/ (admin/admin123)"
echo "     - Medical Admin: https://${DETECTED_IP}/medical_admin/"
echo "     - Health check: http://${DETECTED_IP}/medical_access/health"
echo ""
echo "  3. Monitor logs:"
echo "     - View logs: docker-compose logs -f"
echo "     - Stop app: $COMPOSE down -v --remove-orphans"
echo "     - Restart: docker-compose restart"
echo ""
echo "🔧 Troubleshooting:"
echo "   - Check container health: $COMPOSE ps"
echo "   - View logs: docker-compose logs -f web"
echo "   - Test events: curl -X POST http://${DETECTED_IP}/medical_access/hik/events/ -H 'Content-Type: application/json' -d '{\"test\":\"data\"}'"
echo "   - Test redirect: curl -I http://${DETECTED_IP}/"
# 13) Configure auto-start
echo ""
log_info "Configuring auto-start..."
if command -v systemctl &> /dev/null; then
    # Create systemd service for auto-start
    sudo tee /etc/systemd/system/payverify.service > /dev/null <<EOF
[Unit]
Description=PayVerify Docker Containers
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$REPO_ROOT
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF
    
    # Enable and start service
    sudo systemctl enable payverify.service
    sudo systemctl start payverify.service
    
    log_success "Auto-start configured! PayVerify will start automatically after PC restart."
else
    log_warning "systemctl not available - auto-start not configured"
fi

echo ""
log_success "PayVerify v3.0.0 is ready for production!"