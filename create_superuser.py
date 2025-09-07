#!/usr/bin/env python3
"""
Create a superuser for testing the admin interface
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'controller.settings')
django.setup()

from medical_access.models import User

def create_superuser():
    """Create a superuser for testing"""
    
    # Check if superuser already exists
    if User.objects.filter(is_superuser=True).exists():
        print("✅ Superuser already exists!")
        superuser = User.objects.filter(is_superuser=True).first()
        print(f"   Username: {superuser.username}")
        print(f"   Email: {superuser.email}")
        print(f"   Role: {superuser.role}")
        return
    
    # Create superuser
    username = "admin"
    email = "admin@payverify.com"
    password = "admin123"
    
    try:
        superuser = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            role='super_admin'
        )
        
        print("✅ Superuser created successfully!")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        print(f"   Email: {email}")
        print(f"   Role: {superuser.role}")
        print("\n🔗 Admin URLs:")
        print("   Default Django Admin: http://localhost:8000/admin/")
        print("   Custom Medical Admin: http://localhost:8000/medical_admin/")
        print("   Web Dashboard: http://localhost:8000/medical_access/")
        
    except Exception as e:
        print(f"❌ Error creating superuser: {e}")

if __name__ == "__main__":
    create_superuser()
