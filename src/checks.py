"""
Module containing individual health check functions (ping, HTTP/HTTPS).
Each function performs a specific check and logs its result.
"""

import logging
import time
import requests

# Local imports
from helpers import ping_host

# Setup a local logger for this module
log = logging.getLogger("health")


def check_host(item: dict, timeout: int, ping_count: int) -> dict:
    """
    Performs a host reachability check (ICMP/TCP ping).

    Args:
        item (dict): A dictionary containing host details, e.g., {"name": "MyServer", "ip": "192.168.1.1"}.
        timeout (int): The network timeout in seconds for ping operations.

    Returns:
        dict: A dictionary containing the check results, including name, type, health status, and RTT.
    """
    name = item["name"]
    ip = item["ip"]

    log.debug("Running host check for %s (%s)", name, ip)
    rtt = ping_host(ip, timeout=timeout)  # RTT in milliseconds

    healthy = rtt is not None

    # Log the result with structured data for JSON handler and human-readable for stream handler
    log.info(
        "%s | %s | healthy=%s | rtt=%s",
        name.ljust(20),  # Left-justify name for consistent console output
        ip.ljust(15),  # Left-justify IP for consistent console output
        healthy,
        f"{rtt:.1f}ms" if rtt else "—",  # Format RTT if available
        extra={
            "type": "ping",
            "check_name": name,
            "target": ip, # Renamed 'ip' to 'target' for consistency with prometheus_metrics labels
            "healthy": healthy,
            "rtt": rtt,
        },
    )

    return {"name": name, "type": "ping", "healthy": healthy, "rtt": rtt, "target": ip}


def check_url(item: dict, timeout: int, retries: int) -> dict:
    """
    Performs an HTTP/HTTPS URL check, including status code, content validation.

    Args:
        item (dict): A dictionary containing URL details, e.g.,
                     {"name": "MyWebsite", "url": "https://example.com",
                      "method": "GET", "expected_status": [200], "must_contain": "Success"}.
        timeout (int): The network timeout in seconds for HTTP requests.
        retries (int): The number of times to retry the HTTP request on failure.
        ssl_warn_days (int): The threshold in days below which an SSL certificate
                             expiry is considered a warning.

    Returns:
        dict: A dictionary containing the check results, including name, type,
              health status, HTTP status, latency, error message, and SSL days left.
    """
    name = item["name"]
    url = item["url"]
    method = item.get("method", "GET").upper()  # Default to GET if not specified
    expect_status = item.get(
        "expected_status", [200]
    )  # Default to 200 if not specified
    must_contain = item.get("must_contain")

    healthy = False
    status_code = None
    latency = None  # Latency in milliseconds
    error = None
    response_text_snippet = None  # Store a snippet of response for debugging

    log.debug("Running URL check for %s (%s)", name, url)


    try:
        # Use requests.Session for efficient retries and connection pooling
        session = requests.Session()
        # Adapter for retries; backoff_factor for exponential backoff between retries
        adapter = requests.adapters.HTTPAdapter(max_retries=requests.packages.urllib3.util.retry.Retry(
            total=retries,
            backoff_factor=0.5, # 0.5s, 1s, 2s etc. between retries
            status_forcelist=[500, 502, 503, 504], # Retry on these HTTP status codes
        ))
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        t0 = time.perf_counter()
        resp = session.request(method, url, timeout=timeout, allow_redirects=True)
        latency = (time.perf_counter() - t0) * 1000  # Calculate latency in ms
        status_code = resp.status_code
        response_text_snippet = resp.text[:200] if resp.text else "" # Take first 200 chars for logging

        # Check if the HTTP status code is as expected
        if status_code in expect_status:
            # If content validation is required, check 'must_contain'
            if must_contain and must_contain not in resp.text:
                error = f"Missing keyword '{must_contain}' in response content."
                log.debug(
                    "URL check '%s' failed content validation: %s", name, error
                )
            else:
                healthy = True  # Check passed
                log.debug(
                    "URL check '%s' successful (status: %s, latency: %.1fms).",
                    name,
                    status_code,
                    latency,
                )
        else:
            error = f"Unexpected status code {status_code}, expected one of {expect_status}."
            log.debug(
                "URL check '%s' failed status validation: %s", name, error
            )

    except requests.exceptions.Timeout:
        error = f"Request timed out after {timeout} seconds."
        log.error("URL check '%s' timed out after %s seconds.", name, timeout)
    except requests.exceptions.ConnectionError as e:
        error = f"Connection error: {e}"
        log.error("URL check '%s' connection error: %s.", name, e)
    except requests.exceptions.TooManyRedirects:
        error = "Too many redirects."
        log.error("URL check '%s' encountered too many redirects.", name)
    except requests.exceptions.RequestException as e:
        error = f"Request failed: {e}"
        log.error("URL check '%s' general request error: %s.", name, e)
    except Exception as e:
        error = f"An unexpected error occurred: {e}"
        log.critical(
            "URL check '%s' unexpected critical error: %s.",
            name,
            e,
            exc_info=True,
        )

    # Final log for the URL check
    log.info(
        "%s | %s | healthy=%s | status=%s | latency=%s | error=%s ",
        name.ljust(20),
        url,
        healthy,
        status_code if status_code else "—",  # Display status or a dash
        f"{latency:.1f}ms" if latency else "—",
        error or "—",  # Display error or a dash
        extra={
            "type": "http",
            "check_name": name,
            "target": url, # Renamed 'url' to 'target' for consistency with prometheus_metrics labels
            "healthy": healthy,
            "status_code": status_code,
            "latency": latency,
            "error": error,
            "response_snippet": (
                response_text_snippet if not healthy and response_text_snippet else None
            ),  # Only log snippet on error or if specific failure to show context
        },
    )

    return {
        "name": name,
        "type": "http",
        "healthy": healthy,
        "status_code": status_code,
        "latency": latency,
        "error": error,
        "target": url,
    }

    