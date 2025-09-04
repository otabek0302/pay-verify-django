# Docker Setup for PayVerify Django

## Quick Start

1. **Copy environment file:**
   ```bash
   cp env.example .env
   ```

2. **Edit environment variables in `.env`:**
   ```bash
   # Generate a new secret key
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

3. **Build and run with Docker Compose:**
   ```bash
   docker-compose up --build
   ```

4. **Access the application:**
   - Web: http://localhost:8000
   - Admin: http://localhost:8000/admin

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | payverify | Database name |
| `POSTGRES_USER` | payverify | Database user |
| `POSTGRES_PASSWORD` | payverify | Database password |
| `POSTGRES_HOST` | db | Database host |
| `POSTGRES_PORT` | 5432 | Database port |
| `SECRET_KEY` | (generated) | Django secret key |
| `DEBUG` | False | Debug mode |
| `ALLOWED_HOSTS` | localhost,127.0.0.1,0.0.0.0 | Allowed hosts |
| `HIK_VISITOR_EMPLOYEE_NO` | VISITOR | Hikvision visitor employee number |

## Commands

### Development
```bash
# Start services
docker-compose up

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic

# Access Django shell
docker-compose exec web python manage.py shell
```

### Production
```bash
# Build and start in detached mode
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## Services

- **web**: Django application (port 8000)
- **db**: PostgreSQL database (port 5432)

## Volumes

- `pgdata`: PostgreSQL data persistence
- `static_volume`: Static files for production

## Security Notes

- Change default passwords in production
- Use strong secret keys
- Set DEBUG=False in production
- Configure proper ALLOWED_HOSTS
