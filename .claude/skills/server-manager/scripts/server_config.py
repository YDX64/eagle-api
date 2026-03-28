#!/usr/bin/env python3
"""
Server configuration for Golsinyali API production server.
This file contains connection details for the production server.
"""

# Production Server Configuration
SERVER_CONFIG = {
    "host": "72.61.105.107",
    "user": "root",
    "password": "xzW0;TpH?jBn05;KdT#2",
    "port": 22,
    "app_path": "/root/football-analysis-api",
    "service_name": "golsinyali-api",
    "api_port": 8000,
}

# Common paths on server
PATHS = {
    "app": "/root/football-analysis-api",
    "logs": "/root/football-analysis-api/logs",
    "env": "/root/football-analysis-api/.env",
    "gunicorn_config": "/root/football-analysis-api/gunicorn_config.py",
}

# Health check endpoints (public - no auth required)
HEALTH_ENDPOINTS = [
    "/api/v1/health",
    "/api/v1/health/detailed",
]
