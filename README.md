# PayVerify Django Project

A Django-based medical access management system with JWT authentication and REST API.

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

3. **Access the application:**
   - Main app: http://localhost
   - Admin panel: http://localhost/admin (admin/admin123)

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
   python manage.py runserver
   ```

## Deployment

For detailed deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)

## API Endpoints

- **Admin Interface:** `http://127.0.0.1:8000/admin/`
- **Medical Access API:** `http://127.0.0.1:8000/api/v1/medical_access/`

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

- The project uses a custom User model (`medical_access.User`)
- JWT authentication is configured for API endpoints
- CORS is enabled for development purposes
- Static files are served from the `static/` directory
