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



# Local imports
from config import load_config
from logger import setup_logging
from checks import check_host, check_url
from prometheus_metrics import start_metrics_server_thread # Renamed to avoid direct execution

# Setup logging for the main application
log = logging.getLogger("health")

def run_all_checks(conf: dict):
    """
    Executes all configured health checks concurrently using a ThreadPoolExecutor.
    Results are logged by the individual check functions.

    Args:
        conf (dict): The loaded configuration dictionary.
    """
    log.info("Starting a round of health checks...")
    
    # Extract common parameters from configuration
    timeout = conf["timeout"]
    http_retries = conf.get("http_retries", 0) # Default to 0 if not specified
    ssl_warn_days = conf.get("ssl_warn_days", 30) # Default to 30 if not specified

    # Use a thread pool for concurrent execution of I/O-bound tasks (network checks)
    # A max_workers of 20 is a reasonable default for many scenarios.
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futures = []

        # Schedule host (ping) checks
        for host_item in conf.get("hosts", []):
            futures.append(pool.submit(check_host, host_item, timeout))

        # Schedule URL (HTTP/HTTPS) checks
        for url_item in conf.get("urls", []):
            futures.append(pool.submit(check_url, url_item, timeout, http_retries))

        # Wait for all checks to complete.
        # The results are already logged by the `check_host` and `check_url` functions.
        for future in concurrent.futures.as_completed(futures):
            try:
                # Optionally retrieve result if needed, though checks log internally
                future.result() 
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

    # Load configuration from the specified YAML file
    conf = load_config(config_file_path)

    # Setup the custom JSON logging handler and stream handler
    # This must happen after config is loaded to get log_file_path if defined
    setup_logging(log_file_path=conf.get("log_file_path", "health.jsonl"))

    interval = conf.get("interval", 30) # Default check interval to 30 seconds

    # Decide operation mode:
    # 1. Single run (if interval is 0 or less)
    # 2. Continuous loop with Prometheus metrics (if METRICS env var is set)
    # 3. Continuous loop without Prometheus metrics
    if interval <= 0:
        log.info("Running health checks once (interval <= 0).")
        run_all_checks(conf)
    else:
        # Check if Prometheus metrics server should be started
        if os.getenv("METRICS", "false").lower() == "true":
            log.info("Starting in continuous loop with Prometheus metrics.")
            # Start Prometheus server in a separate thread
            # The metrics server itself will run `update_prom` which internally calls `check_host` and `check_url`
            # so we don't need to call `run_all_checks` directly here.
            prometheus_port = conf.get("prometheus_port", 8000)
            start_metrics_server_thread(conf, prometheus_port)
            # The Prometheus thread will handle continuous checks and metric updates.
            # The main thread can just keep alive or perform other tasks.
            # In this case, we'll keep it alive indefinitely.
            while True:
                time.sleep(interval) # Small sleep to prevent busy-waiting
        else:
            log.info("Starting in continuous loop without Prometheus metrics.")
            while True:
                run_all_checks(conf)
                log.info("Sleeping for %s seconds until next check round...", interval)
                time.sleep(interval)

if __name__ == "__main__":
    main()