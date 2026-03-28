---
name: server-manager
description: This skill manages the Golsinyali API production server (72.61.105.107). Use this skill when the user wants to connect to the server, check server health, restart services, deploy updates, view logs, or perform any server-related operations. Trigger phrases include "sunucuya bağlan", "sunucu durumu", "servisi yeniden başlat", "deploy yap", "health check", "logları göster".
---

# Server Manager

This skill provides automated management of the Golsinyali API production server. It enables quick connection, health monitoring, service management, and deployment operations without requiring manual credential entry.

## Server Details

- **Host**: 72.61.105.107
- **Service**: golsinyali-api (systemd)
- **App Path**: /var/www/golsinyali_api
- **API Port**: 8000

## Available Scripts

### 1. Health Check (`scripts/health_check.py`)

Comprehensive health check of all server systems:

```bash
python scripts/health_check.py           # Standard check
python scripts/health_check.py --verbose # Detailed output
```

Checks:
- Systemd service status
- All API health endpoints (/health, /sources/health, /cache/stats)
- Disk and memory usage
- Recent error logs

### 2. Service Manager (`scripts/service_manager.py`)

Service and deployment operations:

```bash
python scripts/service_manager.py restart     # Restart API service
python scripts/service_manager.py stop        # Stop service
python scripts/service_manager.py start       # Start service
python scripts/service_manager.py status      # Check status
python scripts/service_manager.py deploy      # Git pull + restart
python scripts/service_manager.py logs        # Show recent logs
python scripts/service_manager.py logs-error  # Show error logs only
```

### 3. SSH Connect (`scripts/ssh_connect.py`)

Execute any command on the server:

```bash
python scripts/ssh_connect.py "systemctl status golsinyali-api"
python scripts/ssh_connect.py "tail -100 /var/www/golsinyali_api/logs/app.log"
python scripts/ssh_connect.py "df -h"
python scripts/ssh_connect.py "free -m"
```

## Common Workflows

### After Local Code Changes

To verify updates are running on production:

1. Run `python scripts/service_manager.py deploy` to pull and restart
2. Run `python scripts/health_check.py` to verify everything is working

### Quick Status Check

To check if everything is running:

```bash
python scripts/health_check.py
```

### Troubleshooting

To investigate issues:

1. Check service status: `python scripts/service_manager.py status`
2. View error logs: `python scripts/service_manager.py logs-error`
3. Check detailed health: `python scripts/health_check.py --verbose`

### Manual Server Commands

For any custom operation, use ssh_connect.py:

```bash
# View environment variables
python scripts/ssh_connect.py "cat /var/www/golsinyali_api/.env"

# Check running processes
python scripts/ssh_connect.py "ps aux | grep gunicorn"

# Clear cache
python scripts/ssh_connect.py "curl -X POST http://localhost:8000/api/v1/cache/clear"

# Check Redis
python scripts/ssh_connect.py "redis-cli ping"
```

## Prerequisites

The `sshpass` utility must be installed on the local machine:

```bash
# macOS
brew install hudochenkov/sshpass/sshpass

# Ubuntu/Debian
sudo apt-get install sshpass
```

## Important Paths on Server

| Path | Description |
|------|-------------|
| /var/www/golsinyali_api | Application root |
| /var/www/golsinyali_api/.env | Environment configuration |
| /var/www/golsinyali_api/logs/app.log | Application logs |
| /var/www/golsinyali_api/logs/gunicorn_error.log | Gunicorn error logs |
| /etc/systemd/system/golsinyali-api.service | Systemd service file |
