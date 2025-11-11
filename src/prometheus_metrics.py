"""
Module for integrating health check results with Prometheus.
Starts an HTTP server to expose metrics.
"""
import logging
import threading
import time

# Deferred import: prometheus_client is only required if METRICS is enabled
try:
    from prometheus_client import Gauge, Histogram, start_http_server
except ImportError:
    # Log a warning if prometheus_client is not installed but METRICS is attempted
    logging.getLogger("health").warning(
        "Prometheus client library not found. "
        "Install with 'pip install prometheus_client' to enable Prometheus metrics."
    )
    # Define dummy classes/functions to prevent NameErrors if import fails
    # This also ensures start_http_server is not actually callable if client is missing
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
    def start_http_server(*args, **kwargs):
        logging.getLogger("health").error("Prometheus client not installed, cannot start HTTP server.")
        raise RuntimeError("Prometheus client not available.") # Raise to propagate failure

# Setup a local logger for this module
log = logging.getLogger("health")

# Initialize Prometheus metrics. These are global for the Prometheus client.
# health_check_status: Gauge for health (1=healthy, 0=down)
#   Labels: 'check_name' (name of the check item), 'check_type' (e.g., 'ping', 'http'), 'target' (IP/URL)
health_check_status = Gauge(
    "health_check_status", 
    "Health status of the check (1=up, 0=down)", 
    ["check_name", "check_type", "target"]
)

# health_check_latency_ms: Histogram for latency distribution
#   Labels: 'check_name', 'check_type', 'target'
health_check_latency_ms = Histogram(
    "health_check_latency_milliseconds", 
    "Latency of health check in milliseconds", 
    ["check_name", "check_type", "target"],
    buckets=[1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, float('inf')]
)

# health_check_http_status_code: Gauge for HTTP status codes (for HTTP checks)
#   Labels: 'check_name', 'check_type', 'target'
health_check_http_status_code = Gauge(
    "health_check_http_status_code",
    "HTTP status code returned by HTTP checks",
    ["check_name", "check_type", "target"]
)

def update_check_metrics(result: dict):
    """
    Updates Prometheus gauges and histograms based on a single check result dictionary.

    Args:
        result (dict): A dictionary containing the result of a check from checks.py.
    """
    check_name = result.get("name")
    check_type = result.get("type")
    target = result.get("target")
    healthy = result.get("healthy")
    latency = result.get("latency") or result.get("rtt") # Ping uses 'rtt', HTTP uses 'latency'
    status_code = result.get("status_code")

    if not all([check_name, check_type, target]) is None: # Ensure basic labels exist
        labels = {"check_name": check_name, "check_type": check_type, "target": target}

        # Update status gauge
        health_check_status.labels(**labels).set(1 if healthy else 0)

        # Update latency histogram
        if latency is not None and latency >= 0:
            health_check_latency_ms.labels(**labels).observe(latency)
        
        # Update HTTP status code gauge for HTTP checks
        if check_type == "http" and status_code is not None:
            health_check_http_status_code.labels(**labels).set(status_code)
        
        log.debug("Prometheus metrics updated for %s '%s' (Target: %s)", check_type, check_name, target)
    else:
        log.warning("Skipping Prometheus metric update due to missing required labels in result: %s", result)


def _metrics_server_thread_target(port: int):
    """
    Target function for the Prometheus HTTP server thread.
    """
    try:
        start_http_server(port)
        log.info("Prometheus metrics server started on http://0.0.0.0:%s/metrics", port)
        # Keep the thread alive, as start_http_server is non-blocking
        while True:
            time.sleep(1) 
    except Exception as e:
        log.error("Failed to start Prometheus HTTP server on port %s: %s", port, e, exc_info=True)
        # The main loop will continue without metrics if the server fails to start


def start_metrics_server(port: int = 8000):
    """
    Starts the Prometheus metrics exposition HTTP server in a separate daemon thread.
    This function only starts the server, it does not run checks or update metrics.
    """
    # Check if prometheus_client's start_http_server is the actual one, not the dummy
    if 'start_http_server' in globals() and start_http_server.__module__ == 'prometheus_client':
        metrics_thread = threading.Thread(target=_metrics_server_thread_target, args=(port,), daemon=True)
        metrics_thread.name = "PrometheusMetricsServer"
        metrics_thread.start()
        log.info("Prometheus metrics server thread launched.")
    else:
        log.error("Prometheus client library is not available, metrics server cannot be started.")