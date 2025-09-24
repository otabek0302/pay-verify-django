# PayVerify Django Project

A Django-based medical access system with a browser UI, REST API, and Hikvision terminal integration. Ships with Docker, Nginx, HTTPS, and CORS preconfigured.

## Features

- Custom User model with role-based access (Admin, Doctor, Patient)
- JWT authentication using `djangorestframework-simplejwt`
- REST API endpoints
- CORS support for cross-origin requests
- Admin interface for user management

## Project Structure

```
payverify_django/
├── controller/           # Django project settings
│   ├── settings.py      # Project configuration
│   ├── urls.py          # Main URL configuration
│   ├── wsgi.py          # WSGI configuration
│   └── asgi.py          # ASGI configuration
├── medical_access/       # Main Django app
│   ├── models.py        # User model and database schema
│   ├── views.py         # API views
│   ├── urls.py          # App URL patterns
│   ├── admin.py         # Admin interface configuration
│   └── apps.py          # App configuration
├── static/               # Static files directory
├── manage.py            # Django management script
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

## Quick Start (Docker - Recommended)

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd payverify_django
   ```

2. **Run the deployment script:**
   ```bash
   ./deploy.sh
   ```

   What it does:
   - Detects your host IP and creates `.env` from `.env.template`
   - Fills `HOST_IP`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`
   - Builds and starts Docker services (`db`, `web`, `nginx`)
   - Generates development TLS certs in `nginx/certs/`
   - Runs migrations, ensures superuser, collects static

3. **Access the application:**
   - Main app: `https://<your-ip>/`
   - Admin panel: `https://<your-ip>/admin/` (default: admin/admin123)
   - Health check: `http://<your-ip>/medical_access/health`
   - Events endpoint (HTTP allowed): `http://<your-ip>/medical_access/hik/events/`

## Manual Setup (Development)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run database migrations:**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

4. **Create superuser (optional):**
   ```bash
   python manage.py createsuperuser
   ```

5. **Run the development server:**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

6. If you are calling from a Chrome Extension or another origin over the network, set these env vars before running Django:
   ```bash
   export HOST_IP=<your-ip>
   export ALLOWED_HOSTS="<your-ip>,localhost,127.0.0.1,0.0.0.0"
   export CSRF_TRUSTED_ORIGINS="http://<your-ip>,https://<your-ip>,http://localhost,https://localhost"
   export CORS_ALLOWED_ORIGINS="https://mis.dmed.uz,https://<your-ip>,http://<your-ip>,chrome-extension://peifjgpicbnlpobobglipjgbmpkmcafh"
   ```

## Deployment (Other Machines / New IP)

Option A — Automated (recommended):
1. On the new PC, install Docker + Compose
2. Clone the repo and run `./deploy.sh`
3. The script auto-detects the new IP and regenerates `.env` and self‑signed certs

Option B — Manual reconfiguration:
1. Edit `.env` to set the new IP:
   - `HOST_IP=NEW_IP`
   - `ALLOWED_HOSTS=NEW_IP,localhost,127.0.0.1,0.0.0.0`
   - `CSRF_TRUSTED_ORIGINS=http://NEW_IP,https://NEW_IP`
   - `CORS_ALLOWED_ORIGINS=https://mis.dmed.uz,https://NEW_IP,http://NEW_IP,chrome-extension://peifjgpicbnlpobobglipjgbmpkmcafh`
2. Regenerate TLS certs for the new IP and restart Nginx:
   ```bash
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
     -keyout nginx/certs/server.key -out nginx/certs/server.crt \
     -subj "/CN=NEW_IP"
   docker compose restart nginx
   ```
3. If desired, set `server_name _;` in `nginx/default.conf` to avoid editing per IP

Restart stack after changes:
```bash
docker compose up -d --build
```

## API Endpoints

- Login: `https://<your-ip>/medical_access/login/`
- Create appointment (internal view): `https://<your-ip>/medical_access/create-appointment/`
- External APIs:
  - Create appointment: `https://<your-ip>/medical_access/api/create-appointment/`
  - Validate QR: `https://<your-ip>/medical_access/api/validate-qr/`
- Admin Interface: `https://<your-ip>/admin/`

## Default Superuser Credentials

- **Username:** admin
- **Email:** admin@example.com
- **Password:** admin123

## Dependencies

- Django
- Django REST Framework
- Django REST Framework Simple JWT
- Django CORS Headers

## Development Notes

- Uses custom User model `medical_access.User`
- JWT authentication configured for REST endpoints
- CORS via `django-cors-headers`; middleware is first; exact origins required
- For Chrome Extension access, ensure the extension ID is present in `CORS_ALLOWED_ORIGINS`
- Nginx terminates TLS; Django respects `X-Forwarded-Proto` for HTTPS detection

## Troubleshooting

- COOP/“origin untrustworthy” warnings:
  - Use `https://<your-ip>` or `http://localhost`. Browsers distrust plain HTTP over LAN for certain features

- CORS error: “No 'Access-Control-Allow-Origin' header”
  - Confirm origin is exactly listed in `.env` → `CORS_ALLOWED_ORIGINS`
  - For Chrome Extension, origin must be `chrome-extension://<extension-id>`

- CSRF 403 on login via extension:
  - Login view is `csrf_exempt`; ensure you POST JSON to `/medical_access/login/`

- Can’t reach HTTPS:
  - Ensure `nginx/default.conf` has a `listen 443 ssl;` server and certs exist in `nginx/certs/`
  - Restart Nginx: `docker compose restart nginx`
