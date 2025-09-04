FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install pipenv (since repo uses Pipfile)
RUN pip install --no-cache-dir pipenv

# Copy Pipfile first
COPY Pipfile Pipfile.lock /app/

# Install dependencies
RUN PIPENV_VENV_IN_PROJECT=0 pipenv install --system --deploy

# Copy project files
COPY . /app

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000