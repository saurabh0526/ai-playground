# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY chat.py .
COPY templates/ templates/
COPY static/ static/
COPY images/ images/

# Expose port for Google Cloud
EXPOSE 8080

# Set environment variables
ENV FLASK_APP=app.py
ENV PORT=8080

# Run app with gunicorn
CMD exec gunicorn --bind 0.0.0.0:8080 --workers 4 --threads 2 --worker-class gthread --timeout 0 app:app
