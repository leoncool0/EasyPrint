# EasyPrint Server Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create data and logs directories with proper permissions
RUN mkdir -p /app/data /app/logs && chmod -R 777 /app/data /app/logs

# Expose ports
# 8080: HTTP API / Web UI
# 9100: TCP Gateway
# 20000/udp: UDP Discovery
EXPOSE 8080
EXPOSE 9100
EXPOSE 20000/udp

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run the application
CMD ["python", "-m", "app.main"]