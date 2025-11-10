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
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
    def start_http_server(*args, **kwargs):
        logging.getLogger("health").error("Prometheus client not installed, cannot start HTTP server.")

# Local imports for running checks
from checks import check_host


# Setup a local logger for this module
log = logging.getLogger("health")

# Initialize Prometheus metrics. These are global for the Prometheus client.
# health_up: Gauge for overall health (1=healthy, 0=down)
#   Labels: 'name' (name of the check item), 'type' (e.g., 'ping', 'http')
UP = Gauge("health_up", "1 = healthy, 0 = down", ["name", "type"])

# health_latency_ms: Histogram for latency distribution
#   Labels: 'name', 'type'
LATENCY = Histogram("health_latency_ms", "Latency in milliseconds", ["name", "type"])


def update_prometheus_metrics(conf: dict):
    """
    Runs all configured health checks and updates the Prometheus metrics.

    Args:
        conf (dict): The loaded configuration dictionary.
    """
    log.debug("Updating Prometheus metrics...")
    
    # Extract common parameters from configuration
    timeout = conf["timeout"]
    http_retries = conf.get("http_retries", 0)


    # --- Update metrics for host (ping) checks ---
    for host_item in conf.get("hosts", []):
        name = host_item["name"]
        # Run the check to get the latest status
        res = check_host(host_item, timeout)
        
        # Update 'health_up' gauge
        UP.labels(name=name, type="ping").set(1 if res["healthy"] else 0)
        
        # Update 'health_latency_ms' histogram if RTT is available
        if res["rtt"] is not None:
            LATENCY.labels(name=name, type="ping").observe(res["rtt"])

    # --- Update metrics for URL (HTTP/HTTPS) checks ---
    for url_item in conf.get("urls", []):
        name = url_item["name"]
        url = url_item["url"]
        
        # Update 'health_up' gauge
        UP.labels(name=name, type="http").set(1 if res["healthy"] else 0)
        
        # Update 'health_latency_ms' histogram if latency is available
        if res["latency"] is not None:
            LATENCY.labels(name=name, type="http").observe(res["latency"])



def prometheus_server_loop(conf: dict, port: int):
    """
    The main loop for the Prometheus metrics server.
    It continuously updates metrics at a specified interval.

    Args:
        conf (dict): The loaded configuration dictionary.
        port (int): The port on which the Prometheus HTTP server should listen.
    """
    # Start the Prometheus HTTP server to expose metrics
    try:
        start_http_server(port)
        log.info("Prometheus metrics server started on http://0.0.0.0:%s/metrics", port)
    except Exception as e:
        log.error("Failed to start Prometheus HTTP server on port %s: %s", port, e, exc_info=True)
        return # Exit the thread if server cannot start

    interval = conf.get("interval", 30)
    if interval <= 0:
        log.warning("Prometheus metrics interval is %s, using default 30s to prevent busy loop.", interval)
        interval = 30

    while True:
        update_prometheus_metrics(conf)
        log.debug("Prometheus metrics updated. Sleeping for %s seconds...", interval)
        time.sleep(interval)

def start_metrics_server_thread(conf: dict, port: int = 8000):
    """
    Starts the Prometheus metrics server in a separate daemon thread.

    Args:
        conf (dict): The loaded configuration dictionary.
        port (int): The port for the Prometheus server. Defaults to 8000.
    """
    if 'start_http_server' not in globals() or start_http_server.__name__ == 'start_http_server':
        # Only try to start if prometheus_client was successfully imported
        metrics_thread = threading.Thread(target=prometheus_server_loop, args=(conf, port), daemon=True)
        metrics_thread.name = "PrometheusMetricsThread"
        metrics_thread.start()
        log.info("Prometheus metrics server thread launched.")
    else:
        log.error("Prometheus client library is not available, metrics server cannot be started.")