#!/usr/bin/env python3
"""
Main entry point for the health checking application.
Loads configuration, runs checks, and optionally starts a Prometheus metrics server.
"""
import concurrent.futures
import logging
import os
import sys
import time
import signal



# Local imports
from config import load_config
from logger import setup_logging
from checks import check_host, check_url
from prometheus_metrics import start_metrics_server_thread # Renamed to avoid direct execution

# Setup logging for the main application
log = logging.getLogger("health")

#Global flag to signal shutdown
shutdown_flag = False

def signal_handler(signum, frame):
    """Handles OS signals for graceful shutdown"""
    global shutdown_flag
    log.info("Received shutdown signal (%s). Initiating graceful exit...", signum)
    shutdown_flag = True


def run_all_checks(conf: dict, metrics_enabled: bool = False):
    """
    Executes all configured health checks concurrently using a ThreadPoolExecutor.
    Results are logged by the individual check functions and optionally update Prometheus metrics.

    Args:
        conf (dict): The loaded configuration dictionary.
        metrics_enabled (bool): True if Prometheus metrics should be updated.
    """
    log.info("Starting a round of health checks...")
    
    # Extract common parameters from configuration
    timeout = conf["timeout"]
    http_retries = conf.get("http_retries", 0) # Default to 0 if not specified
    ping_count = conf.get("ping_count", 3)
    max_workers = conf.get("max_workers", 20)

    # Use a thread pool for concurrent execution of I/O-bound tasks (network checks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = []

        # Schedule host (ping) checks
        for host_item in conf.get("hosts", []):
            futures.append(pool.submit(check_host, host_item, timeout, ping_count))

        # Schedule URL (HTTP/HTTPS) checks
        for url_item in conf.get("urls", []):
            futures.append(pool.submit(check_url, url_item, timeout, http_retries))

        # Wait for all checks to complete.
        for future in concurrent.futures.as_completed(futures):
            try:
                # Assuming check_host and check_url now return a dict/object with results
                # e.g., {'type': 'host', 'name': 'example.com', 'status': 'up', 'duration_ms': 50}
                result = future.result()
                
                # Log the result (already handled by checks internally, but can add aggregate logging here)
                # If checks are modified to return more detailed status for main to log.

                if metrics_enabled and result:
                    # Update Prometheus metrics based on the result
                    # The `update_check_metrics` function needs to be implemented in prometheus_metrics.py
                    # It would take parameters like result['type'], result['name'], result['status'], result['duration_ms']
                    update_check_metrics(result)
            except Exception as exc:
                log.error("Check generated an exception: %s", exc, exc_info=True)
    
    log.info("Finished a round of health checks.")


def main():
    """
    Parses command-line arguments, loads configuration, sets up logging,
    and starts the health check loop or Prometheus server.
    """
    if len(sys.argv) != 2:
        print("Usage: python healthcheck.py <config_file.yaml>")
        sys.exit(1)

    config_file_path = sys.argv[1]

    try:
        conf = load_config(config_file_path)
    except Exception as e:
        # Initial logging setup might not be complete, print to stderr
        print(f"ERROR: Failed to load configuration from {config_file_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup the custom JSON logging handler and stream handler
    # This must happen after config is loaded to get log_file_path if defined
    setup_logging(log_file_path=conf.get("log_file_path", "health.jsonl"))

    interval = conf.get("interval", 30) # Default check interval to 30 seconds

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    metrics_enabled = os.getenv("METRICS", "false").lower() == "true"
    prometheus_port = conf.get("prometheus_port", 8000)

    if metrics_enabled:
        log.info("Prometheus metrics enabled. Starting metrics server on port %d.", prometheus_port)
        start_metrics_server_thread(prometheus_port) # Only starts the exposition server

    # Decide operation mode:
    # 1. Single run (if interval is 0 or less)
    # 2. Continuous loop with Prometheus metrics (if METRICS env var is set)
    # 3. Continuous loop without Prometheus metrics
    if interval <= 0:
        log.info("Running health checks once (interval is %s).", interval)
        run_all_checks(conf, metrics_enabled)
    else:
        log.info("Starting continuous loop with checks every %s seconds.", interval)
        if metrics_enabled:
            log.info("Prometheus metrics will be updated during each check round.")
        else:
            log.info("Prometheus metrics are NOT enabled.")

        while not shutdown_flag: # Loop until shutdown signal is received
            run_all_checks(conf, metrics_enabled)
            if not shutdown_flag: # Check again before sleeping
                log.info("Sleeping for %s seconds until next check round...", interval)
                time.sleep(interval)
        log.info("Shutdown flag received. Exiting continuous loop.")

if __name__ == "__main__":
    main()