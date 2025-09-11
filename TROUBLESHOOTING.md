# PayVerify Troubleshooting Guide

## Issue: Getting "Welcome to nginx!" instead of Django app

### Step 1: Check Container Status
```bash
# Check if all containers are running
docker-compose ps

# Check container logs
docker-compose logs web
docker-compose logs nginx
docker-compose logs db
```

### Step 2: Verify Nginx Configuration
```bash
# Check if nginx is using the correct config
docker-compose exec nginx cat /etc/nginx/conf.d/default.conf

# Test nginx configuration
docker-compose exec nginx nginx -t
```

### Step 3: Test Django App Directly
```bash
# Test if Django app is running inside the container
docker-compose exec web curl http://localhost:8000/

# Check if Django app responds
docker-compose exec web python manage.py check
```

### Step 4: Check Network Connectivity
```bash
# Test if nginx can reach Django app
docker-compose exec nginx curl http://web:8000/

# Check if the upstream is working
docker-compose exec nginx nslookup web
```

## Common Solutions

### Solution 1: Restart All Containers
```bash
# Stop all containers
docker-compose down

# Remove containers and rebuild
docker-compose down --remove-orphans
docker-compose build --no-cache
docker-compose up -d

# Check logs
docker-compose logs -f
```

### Solution 2: Check File Permissions
```bash
# Make sure nginx config is readable
ls -la nginx/nginx.conf

# Check if staticfiles directory exists
ls -la staticfiles/
```

### Solution 3: Verify Environment Variables
```bash
# Check if .env file exists and has correct values
cat .env

# Check Django settings
docker-compose exec web python manage.py diffsettings
```

### Solution 4: Manual Nginx Test
```bash
# Test nginx configuration manually
docker-compose exec nginx nginx -t

# Reload nginx configuration
docker-compose exec nginx nginx -s reload
```

## Expected Results

### Working Setup Should Show:
1. **All containers running and healthy**
2. **Django app accessible at http://web:8000 inside nginx container**
3. **Nginx serving Django app at http://localhost**
4. **No "Welcome to nginx!" page**

### If Still Not Working:
1. Check if there are any error messages in the logs
2. Verify that the nginx configuration file is being mounted correctly
3. Ensure the Django app is actually running and responding
4. Check if there are any port conflicts

## Quick Fix Commands

```bash
# Complete reset and restart
docker-compose down -v
docker system prune -f
./setup.sh

# Or manual restart
docker-compose down
docker-compose up -d --build
docker-compose logs -f
```
