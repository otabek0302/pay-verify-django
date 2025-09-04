#!/usr/bin/env python
"""
Local development runner for Django
Uses SQLite instead of PostgreSQL for easier local development
"""

import os
import sys
import django
from django.core.management import execute_from_command_line

if __name__ == "__main__":
    # Set Django settings module to use local settings
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "controller.local_settings")
    
    # Setup Django
    django.setup()
    
    # Run the development server
    execute_from_command_line(sys.argv)
