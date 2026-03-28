#!/usr/bin/env python3
"""
Service management script for Golsinyali API.
Provides commands to restart, stop, start services and deploy updates.

Usage:
    python service_manager.py restart    - Restart the API service
    python service_manager.py stop       - Stop the API service
    python service_manager.py start      - Start the API service
    python service_manager.py status     - Check service status
    python service_manager.py deploy     - Pull latest code and restart
    python service_manager.py logs       - Show recent logs
    python service_manager.py logs-error - Show recent error logs
"""

import subprocess
import sys
import os
import time

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
from server_config import SERVER_CONFIG, PATHS

def run_ssh_command(command: str, show_output: bool = True) -> tuple[int, str, str]:
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

    if show_output:
        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)

    return result.returncode, result.stdout, result.stderr


def restart_service():
    """Restart the golsinyali-api service."""
    service = SERVER_CONFIG["service_name"]
    print(f"Restarting {service}...")

    # Kill any stuck processes first
    run_ssh_command(f"pkill -9 -f 'gunicorn.*golsinyali' || true", show_output=False)
    time.sleep(1)

    returncode, _, _ = run_ssh_command(f"systemctl restart {service}")

    if returncode == 0:
        print("✅ Service restarted successfully")
        time.sleep(3)
        # Check if it's running
        check_status()
    else:
        print("❌ Failed to restart service")

    return returncode


def stop_service():
    """Stop the golsinyali-api service."""
    service = SERVER_CONFIG["service_name"]
    print(f"Stopping {service}...")

    returncode, _, _ = run_ssh_command(f"systemctl stop {service}")

    if returncode == 0:
        print("✅ Service stopped")
    else:
        print("❌ Failed to stop service")

    return returncode


def start_service():
    """Start the golsinyali-api service."""
    service = SERVER_CONFIG["service_name"]
    print(f"Starting {service}...")

    returncode, _, _ = run_ssh_command(f"systemctl start {service}")

    if returncode == 0:
        print("✅ Service started")
        time.sleep(3)
        check_status()
    else:
        print("❌ Failed to start service")

    return returncode


def check_status():
    """Check service status."""
    service = SERVER_CONFIG["service_name"]
    print(f"\n--- {service} Status ---")
    run_ssh_command(f"systemctl status {service} --no-pager -l | head -15")

    # Quick API health check
    print("\n--- API Health Check ---")
    api_port = SERVER_CONFIG["api_port"]
    returncode, stdout, _ = run_ssh_command(
        f"curl -s --max-time 5 'http://localhost:{api_port}/api/v1/health'",
        show_output=False
    )

    if returncode == 0 and stdout:
        print(f"✅ API responding: {stdout[:100]}")
    else:
        print("❌ API not responding")


def deploy():
    """Pull latest code and restart service."""
    app_path = PATHS["app"]

    print("Starting deployment...")
    print("-" * 40)

    # 1. Git pull
    print("\n[1/3] Pulling latest code...")
    returncode, stdout, stderr = run_ssh_command(f"cd {app_path} && git pull")

    if returncode != 0:
        print(f"❌ Git pull failed: {stderr}")
        return returncode

    if "Already up to date" in stdout:
        print("ℹ️ No new changes to deploy")
    else:
        print("✅ Code updated")

    # 2. Check for requirements changes (optional pip install)
    print("\n[2/3] Checking dependencies...")
    run_ssh_command(
        f"cd {app_path} && pip install -r requirements.txt -q 2>/dev/null || true",
        show_output=False
    )
    print("✅ Dependencies checked")

    # 3. Restart service
    print("\n[3/3] Restarting service...")
    restart_service()

    print("\n" + "=" * 40)
    print("✅ DEPLOYMENT COMPLETE")
    print("=" * 40)

    return 0


def show_logs(error_only: bool = False):
    """Show recent logs."""
    log_path = f"{PATHS['logs']}/app.log"

    if error_only:
        print("--- Recent Errors ---")
        run_ssh_command(f"grep -i 'error\\|exception\\|critical' {log_path} | tail -30")
    else:
        print("--- Recent Logs ---")
        run_ssh_command(f"tail -50 {log_path}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    command = sys.argv[1].lower()

    commands = {
        "restart": restart_service,
        "stop": stop_service,
        "start": start_service,
        "status": check_status,
        "deploy": deploy,
        "logs": lambda: show_logs(error_only=False),
        "logs-error": lambda: show_logs(error_only=True),
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        print(__doc__)
        return 1

    print(f"Server: {SERVER_CONFIG['host']}")
    print("=" * 40)

    return commands[command]()


if __name__ == "__main__":
    sys.exit(main())
