#!/usr/bin/env python3
"""
SSH connection and command execution for Golsinyali API server.
Usage: python ssh_connect.py <command>

Examples:
    python ssh_connect.py "systemctl status golsinyali-api"
    python ssh_connect.py "tail -50 /var/www/golsinyali_api/logs/app.log"
"""

import subprocess
import sys
import os

# Import server config
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
from server_config import SERVER_CONFIG

def run_ssh_command(command: str, interactive: bool = False) -> tuple[int, str, str]:
    """
    Execute a command on the remote server via SSH.

    Args:
        command: The command to execute on the server
        interactive: If True, use interactive mode (for commands needing TTY)

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    host = SERVER_CONFIG["host"]
    user = SERVER_CONFIG["user"]
    password = SERVER_CONFIG["password"]
    port = SERVER_CONFIG["port"]

    # Use sshpass for password authentication
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

    if interactive:
        # For interactive commands, don't capture output
        result = subprocess.run(ssh_cmd)
        return result.returncode, "", ""
    else:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout, result.stderr


def main():
    if len(sys.argv) < 2:
        print("Usage: python ssh_connect.py <command>")
        print("Example: python ssh_connect.py 'systemctl status golsinyali-api'")
        sys.exit(1)

    command = sys.argv[1]
    print(f"Executing on {SERVER_CONFIG['host']}: {command}")
    print("-" * 60)

    returncode, stdout, stderr = run_ssh_command(command)

    if stdout:
        print(stdout)
    if stderr:
        print(f"STDERR: {stderr}", file=sys.stderr)

    sys.exit(returncode)


if __name__ == "__main__":
    main()
