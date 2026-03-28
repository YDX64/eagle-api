"""
Gunicorn Configuration File
Production-ready WSGI server configuration for Gol Sinyali API
"""
import multiprocessing
import os
import gunicorn

# Server header'ı gizle - saldırgana teknoloji bilgisi verme
gunicorn.SERVER = ''

# =============================================================================
# SERVER SOCKET
# =============================================================================
bind = os.getenv('GUNICORN_BIND', '0.0.0.0:8000')
backlog = 2048

# =============================================================================
# WORKER PROCESSES
# =============================================================================
# Recommended formula: (2 x CPU cores) + 1
# For 2 cores: 5 workers, For 4 cores: 9 workers
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))

# Worker class - gevent for better concurrency
# NOTE: All async/asyncio code has been removed from the project, so gevent is safe to use now
# Gevent provides better concurrency for I/O-bound operations (HTTP requests, Redis, etc.)
worker_class = 'gevent'

# Maximum number of simultaneous clients per worker
# Increased from 1000 to 10000 for gevent (greenlets are lightweight)
worker_connections = 10000

# Workers silent for more than this many seconds are killed and restarted
# FAST FAILOVER: 90s timeout (2 sources × 6 endpoints × 5s = ~60s max, 90s buffer)
# With fast failover (5s timeout per source), most requests complete in 10-20s
timeout = 90

# Graceful timeout - workers get this much time to finish existing requests before hard kill
graceful_timeout = 60

# Keep alive connections for this many seconds
# Increased from 2s to 5s for better connection reuse
keepalive = 5

# Maximum requests a worker will process before restarting
# Helps prevent memory leaks
# Increased from 1000 to 10000 since we cleaned up the codebase
max_requests = 10000
# Increased jitter from 100 to 1000 to spread out worker restarts
max_requests_jitter = 1000

# =============================================================================
# LOGGING
# =============================================================================
# Access log - requests
accesslog = os.getenv('GUNICORN_ACCESS_LOG', 'logs/gunicorn_access.log')

# Error log - errors and warnings
errorlog = os.getenv('GUNICORN_ERROR_LOG', 'logs/gunicorn_error.log')

# Log level
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')

# Access log format
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# =============================================================================
# PROCESS NAMING
# =============================================================================
proc_name = 'golsinyali_api'

# =============================================================================
# SERVER MECHANICS
# =============================================================================
# Run in background - set to True for production daemon mode
daemon = False

# PID file location
pidfile = os.getenv('GUNICORN_PID_FILE', 'gunicorn.pid')

# User to run workers as (production only)
# user = 'www-data'
# group = 'www-data'

# Directory to change to before loading apps
# chdir = '/path/to/app'

# =============================================================================
# SERVER HOOKS
# =============================================================================
def on_starting(server):
    """Called just before the master process is initialized."""
    print("=" * 80)
    print("Gol Sinyali API - Starting Gunicorn")
    print("=" * 80)
    print(f"Workers: {workers}")
    print(f"Worker class: {worker_class}")
    print(f"Binding to: {bind}")
    print(f"Timeout: {timeout}s")
    print("=" * 80)

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    print("Reloading workers...")

def when_ready(server):
    """Called just after the server is started."""
    print(f"✅ Gunicorn server ready! PID: {os.getpid()}")

def worker_int(worker):
    """Called when a worker receives the SIGINT or SIGQUIT signal."""
    print(f"Worker {worker.pid} received SIGINT/SIGQUIT")

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    print(f"💥 Worker {worker.pid} aborted - likely timeout")

    # Log to Sentry for monitoring worker crashes
    try:
        import sentry_sdk
        sentry_sdk.capture_message(
            f"Gunicorn worker {worker.pid} aborted (timeout or crash)",
            level='error',
            extras={
                'worker_pid': worker.pid,
                'worker_age': worker.age,
                'worker_ppid': worker.ppid,
                'timeout_configured': timeout,
                'graceful_timeout': graceful_timeout
            }
        )
    except Exception as e:
        # Don't crash if Sentry logging fails
        print(f"Failed to log worker abort to Sentry: {e}")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    print(f"Worker spawned (pid: {worker.pid})")

def pre_exec(server):
    """Called just before a new master process is forked."""
    print("Forking new master process...")

def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    print(f"Worker initialized (pid: {worker.pid})")

def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    print(f"Worker exited (pid: {worker.pid})")

def nworkers_changed(server, new_value, old_value):
    """Called just after num_workers has been changed."""
    print(f"Worker count changed from {old_value} to {new_value}")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    print("=" * 80)
    print("Shutting down Gunicorn...")
    print("=" * 80)

# =============================================================================
# SSL (HTTPS) - Optional
# =============================================================================
# Uncomment and configure for HTTPS
# keyfile = '/path/to/keyfile.key'
# certfile = '/path/to/certfile.crt'
# ssl_version = 2  # TLSv1_2
# cert_reqs = 0  # ssl.CERT_NONE
# ca_certs = '/path/to/ca_certs.pem'
# suppress_ragged_eofs = True
# do_handshake_on_connect = False
# ciphers = 'TLSv1'
