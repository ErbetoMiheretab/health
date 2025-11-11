"""
Module for loading and validating application configuration from a YAML file.
"""
import logging
import sys
import yaml
from pathlib import Path

# Setup a local logger for this module
log = logging.getLogger("health")

def load_config(config_file_path: str) -> dict:
    """
    Loads configuration from a specified YAML file.

    Args:
        config_file_path (str): The path to the YAML configuration file.

    Returns:
        dict: The loaded configuration dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        yaml.YAMLError: If there is an error parsing the YAML file.
        SystemExit: If critical configuration errors are found (for early exit).
    """
    config_path = Path(config_file_path)
    if not config_path.exists():
        log.error("Configuration file not found: %s", config_file_path)
        sys.exit(1) # Exit immediately on critical error

    try:
        with open(config_path, "r", encoding="utf8") as fh:
            conf = yaml.safe_load(fh)
        if conf is None: # Handle empty YAML file
            log.warning("Configuration file '%s' is empty. Using default values where applicable.", config_file_path)
            conf = {}
    except yaml.YAMLError as e:
        log.error("Error parsing YAML configuration file '%s': %s", config_file_path, e)
        sys.exit(1) # Exit immediately on critical error
    except Exception as e:
        log.error("An unexpected error occurred while loading config '%s': %s", config_file_path, e, exc_info=True)
        sys.exit(1) # Exit immediately on critical error

    # Validate essential top-level keys and set defaults if missing
    conf.setdefault("interval", 30) # Default check interval in seconds
    conf.setdefault("timeout", 5)   # Default network timeout in seconds
    conf.setdefault("http_retries", 0) # Default HTTP request retries
    conf.setdefault("ping_count", 3) # Default ICMP ping attempts
    conf.setdefault("max_workers", 20) # Default ThreadPoolExecutor max_workers
    conf.setdefault("hosts", []) # Ensure hosts list exists
    conf.setdefault("urls", [])  # Ensure URLs list exists
    conf.setdefault("log_file_path", "health.jsonl") # Default log file name
    conf.setdefault("prometheus_port", 8000) # Default Prometheus port

    # Basic validation for lists of checks
    if not isinstance(conf["hosts"], list):
        log.error("Configuration error: 'hosts' must be a list.")
        sys.exit(1)
    if not isinstance(conf["urls"], list):
        log.error("Configuration error: 'urls' must be a list.")
        sys.exit(1)

    # Basic validation for individual host entries
    for i, host in enumerate(conf["hosts"]):
        if not isinstance(host, dict):
            log.error("Configuration error: hosts[%d] must be a dictionary.", i)
            sys.exit(1)
        if "name" not in host or not isinstance(host["name"], str):
            log.error("Configuration error: hosts[%d] missing 'name' or it's not a string.", i)
            sys.exit(1)
        if "ip" not in host or not isinstance(host["ip"], str):
            log.error("Configuration error: hosts[%d] '%s' missing 'ip' or it's not a string.", i, host.get("name", "unknown"))
            sys.exit(1)

    # Basic validation for individual URL entries
    for i, url_check in enumerate(conf["urls"]):
        if not isinstance(url_check, dict):
            log.error("Configuration error: urls[%d] must be a dictionary.", i)
            sys.exit(1)
        if "name" not in url_check or not isinstance(url_check["name"], str):
            log.error("Configuration error: urls[%d] missing 'name' or it's not a string.", i)
            sys.exit(1)
        if "url" not in url_check or not isinstance(url_check["url"], str):
            log.error("Configuration error: urls[%d] '%s' missing 'url' or it's not a string.", i, url_check.get("name", "unknown"))
            sys.exit(1)
        # Optional: Add more specific validation for 'method', 'expected_status', 'must_contain'

    log.info("Configuration loaded successfully from '%s'.", config_file_path)
    return conf