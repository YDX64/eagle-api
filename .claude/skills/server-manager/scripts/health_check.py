#!/usr/bin/env python3
"""
Health check script for Golsinyali API production server.
Checks all health endpoints and reports status.

Usage: python health_check.py [--verbose]
"""

import subprocess
import sys
import os
import json

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
from server_config import SERVER_CONFIG, HEALTH_ENDPOINTS

def run_ssh_command(command: str) -> tuple[int, str, str]:
    """Execute command on remote server."""
    host = SERVER_CONFIG["host"]
    user = SERVER_CONFIG["user"]
    password = SERVER_CONFIG["password"]
    port = SERVER_CONFIG["port"]

    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-p", str(port),
        f"{user}@{host}",
        command
    ]

    result = subprocess.run(ssh_cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def check_service_status() -> dict:
    """Check systemd service status."""
    service = SERVER_CONFIG["service_name"]
    returncode, stdout, stderr = run_ssh_command(f"systemctl is-active {service}")

    is_active = stdout.strip() == "active"

    # Get more details if active
    if is_active:
        _, details, _ = run_ssh_command(f"systemctl status {service} --no-pager -l | head -20")
    else:
        details = stderr or stdout

    return {
        "service": service,
        "active": is_active,
        "status": stdout.strip(),
        "details": details.strip()
    }


def check_api_endpoints() -> list[dict]:
    """Check all health endpoints."""
    results = []
    api_port = SERVER_CONFIG["api_port"]

    for endpoint in HEALTH_ENDPOINTS:
        url = f"http://localhost:{api_port}{endpoint}"
        cmd = f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 '{url}'"

        returncode, stdout, stderr = run_ssh_command(cmd)
        status_code = stdout.strip().replace("'", "")

        # Get response body for health endpoints
        body = ""
        if status_code == "200":
            _, body, _ = run_ssh_command(f"curl -s --max-time 10 '{url}'")

        results.append({
            "endpoint": endpoint,
            "status_code": status_code,
            "healthy": status_code == "200",
            "response": body[:500] if body else None
        })

    return results


def check_recent_logs() -> str:
    """Get recent error logs."""
    log_path = "/var/www/golsinyali_api/logs/app.log"
    cmd = f"tail -20 {log_path} | grep -i 'error\\|exception\\|critical' || echo 'No recent errors'"

    _, stdout, _ = run_ssh_command(cmd)
    return stdout.strip()


def check_disk_space() -> dict:
    """Check disk usage."""
    _, stdout, _ = run_ssh_command("df -h / | tail -1 | awk '{print $5}'")
    usage = stdout.strip()

    return {
        "disk_usage": usage,
        "warning": int(usage.replace("%", "")) > 80 if usage else False
    }


def check_memory() -> dict:
    """Check memory usage."""
    _, stdout, _ = run_ssh_command("free -m | grep Mem | awk '{printf \"%.1f%%\", $3/$2 * 100}'")
    usage = stdout.strip()

    return {
        "memory_usage": usage,
        "warning": float(usage.replace("%", "")) > 80 if usage else False
    }


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print("=" * 60)
    print("GOLSINYALI API - PRODUCTION SERVER HEALTH CHECK")
    print(f"Server: {SERVER_CONFIG['host']}")
    print("=" * 60)

    # 1. Service Status
    print("\n[1] SERVICE STATUS")
    print("-" * 40)
    service = check_service_status()
    status_icon = "✅" if service["active"] else "❌"
    print(f"{status_icon} {service['service']}: {service['status']}")
    if verbose and service["details"]:
        print(f"\n{service['details']}")

    # 2. API Endpoints
    print("\n[2] API ENDPOINTS")
    print("-" * 40)
    endpoints = check_api_endpoints()
    for ep in endpoints:
        icon = "✅" if ep["healthy"] else "❌"
        print(f"{icon} {ep['endpoint']}: {ep['status_code']}")
        if verbose and ep["response"]:
            try:
                data = json.loads(ep["response"])
                print(f"   {json.dumps(data, indent=2)[:200]}...")
            except:
                print(f"   {ep['response'][:100]}...")

    # 3. System Resources
    print("\n[3] SYSTEM RESOURCES")
    print("-" * 40)
    disk = check_disk_space()
    memory = check_memory()

    disk_icon = "⚠️" if disk["warning"] else "✅"
    mem_icon = "⚠️" if memory["warning"] else "✅"

    print(f"{disk_icon} Disk Usage: {disk['disk_usage']}")
    print(f"{mem_icon} Memory Usage: {memory['memory_usage']}")

    # 4. Recent Errors
    print("\n[4] RECENT ERRORS")
    print("-" * 40)
    errors = check_recent_logs()
    if errors == "No recent errors":
        print("✅ No recent errors in logs")
    else:
        print("⚠️ Recent errors found:")
        print(errors)

    # Summary
    print("\n" + "=" * 60)
    all_healthy = service["active"] and all(ep["healthy"] for ep in endpoints)
    if all_healthy:
        print("✅ ALL SYSTEMS OPERATIONAL")
    else:
        print("❌ ISSUES DETECTED - CHECK ABOVE")
    print("=" * 60)

    return 0 if all_healthy else 1


if __name__ == "__main__":
    sys.exit(main())
