# PayVerify Deployment Guide

## Quick Start (New Machine)

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd payverify_django
   ```

2. **Run the setup script:**
   ```bash
   ./setup.sh
   ```

3. **Edit the .env file** (if prompted) with your server IP address

4. **Access the application:**
   - Main app: http://localhost
   - Admin panel: http://localhost/admin (admin/admin123)

## Manual Setup

If the setup script doesn't work, follow these steps:

### 1. Prerequisites
- Docker and Docker Compose installed
- Git installed

### 2. Environment Setup
```bash
# Copy the environment template
cp env.template .env

# Edit the .env file with your settings
nano .env
```

**Important:** Update these values in `.env`:
- `ALLOWED_HOSTS`: Add your server's IP address
- `CSRF_TRUSTED_ORIGINS`: Add your server's URL
- `SECRET_KEY`: Generate a new secret key for production

### 3. Deploy
```bash
# Make scripts executable
chmod +x deploy.sh entrypoint.sh

# Deploy the application
./deploy.sh
```

## Troubleshooting

### Common Issues

1. **"Error in Container payverify_web_prod"**
   - **Cause**: Missing `.env` file
   - **Solution**: Run `cp env.template .env` and edit the file

2. **Database connection errors**
   - **Cause**: Database container not ready
   - **Solution**: Wait a few minutes for database to initialize

3. **Permission denied errors**
   - **Cause**: Scripts not executable
   - **Solution**: Run `chmod +x *.sh`

4. **Port already in use**
   - **Cause**: Another service using port 80
   - **Solution**: Stop other services or change nginx port in docker-compose.yml

### Check Container Status
```bash
# View all containers
docker-compose ps

# View logs
docker-compose logs web
docker-compose logs db
docker-compose logs nginx

# Restart containers
docker-compose restart
```

### Reset Everything
```bash
# Stop and remove all containers
docker-compose down

# Remove volumes (WARNING: This deletes all data)
docker-compose down -v

# Remove images
docker rmi payverify_django-web:latest

# Start fresh
./deploy.sh
```

## Production Deployment

For production deployment:

1. **Update environment variables:**
   - Set `DEBUG=False`
   - Use a strong `SECRET_KEY`
   - Set proper `ALLOWED_HOSTS`
   - Use strong database passwords

2. **SSL/HTTPS:**
   - Place SSL certificates in `nginx/ssl/`
   - Update nginx configuration for HTTPS

3. **Backup:**
   - Regular database backups
   - Backup media files

## File Structure
```
payverify_django/
├── .env                 # Environment variables (create from env.template)
├── env.template         # Environment template
├── setup.sh            # Automated setup script
├── deploy.sh           # Deployment script
├── docker-compose.yml  # Docker services
├── Dockerfile         # Web container image
└── nginx/             # Nginx configuration
```

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. View container logs: `docker-compose logs`
3. Ensure all prerequisites are installed
4. Verify the `.env` file is properly configured
