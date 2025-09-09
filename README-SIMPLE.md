# PayVerify - Simple Deployment

This is a simplified version of PayVerify that works on any server with minimal configuration.

## 🚀 Quick Start

### 1. Clone and Deploy
```bash
git clone https://github.com/otabek0302/pay-verify-django.git
cd pay-verify-django
./deploy.sh
```

### 2. Test Everything
```bash
./test.sh
```

That's it! The script automatically detects your server IP and configures everything.

## 📱 Terminal Configuration

After deployment, configure your Hikvision terminal with:

- **Event Alarm IP**: (Your server IP - shown after deployment)
- **URL**: `/medical_access/hik/events/`
- **Port**: `80`
- **Protocol**: `HTTP`

## 🔧 Management Commands

```bash
# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Stop services
docker-compose -f docker-compose.prod.yml down

# Restart services
docker-compose -f docker-compose.prod.yml restart

# Test everything
./test.sh
```

## 📁 Files

- `deploy.sh` - One-click deployment script
- `test.sh` - Test if everything is working
- `env.simple` - Environment configuration (auto-updated with your IP)
- `docker-compose.prod.yml` - Docker configuration
- `nginx/nginx.conf` - Nginx proxy configuration

## 🌐 Access

- **Web Interface**: `http://YOUR_SERVER_IP`
- **Terminal Events**: `http://YOUR_SERVER_IP/medical_access/hik/events/`

## 🆘 Troubleshooting

If something doesn't work:

1. Check if Docker is running: `docker ps`
2. Check logs: `docker-compose -f docker-compose.prod.yml logs`
3. Restart: `docker-compose -f docker-compose.prod.yml restart`
4. Run test: `./test.sh`

## 🔄 Updating

To update to the latest version:

```bash
git pull origin main
./deploy.sh
```

That's it! No complex configuration needed.
