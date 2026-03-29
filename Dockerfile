FROM python:3.12-slim

LABEL maintainer="AWA Stats <info@awastats.com>"
LABEL description="Eagle API - Unified Football Prediction Engine"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Data directory (volume mount point)
RUN mkdir -p /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
    CMD curl -f http://localhost:8098/api/v1/health || exit 1

EXPOSE 8098

CMD ["gunicorn", \
     "-w", "2", \
     "-k", "gevent", \
     "--bind", "0.0.0.0:8098", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
