"""
Module containing various utility functions used by health checks.
"""
import logging
import socket
import time
from typing import Optional


# External library for ICMP ping
from ping3 import ping

# Setup a local logger for this module
log = logging.getLogger("health")

def tcp_ping(host: str, port: int, timeout: int) -> float | None:
    """
    Performs a TCP connection attempt to a specific host and port.
    Measures the time taken for a successful connection.

    Args:
        host (str): The hostname or IP address to connect to.
        port (int): The TCP port to connect to.
        timeout (int): The maximum time in seconds to wait for a connection.

    Returns:
        float | None: The connection time in milliseconds if successful,
                      otherwise None if the connection fails or times out.
    """
    t0 = time.perf_counter()
    try:
        # Create a socket, connect, and then immediately close it.
        # This checks for basic TCP reachability.
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - t0) * 1000  # Return duration in milliseconds
    except socket.timeout:
        log.debug("TCP ping to %s:%s timed out after %s seconds.", host, port, timeout)
        return None
    except ConnectionRefusedError:
        log.debug("TCP ping to %s:%s connection refused.", host, port)
        return None
    except OSError as e: # Catch other OS-level errors like "Network is unreachable"
        log.debug("TCP ping to %s:%s failed: %s", host, port, e)
        return None
    except Exception as e:
        log.warning("An unexpected error occurred during TCP ping to %s:%s: %s", host, port, e)
        return None

def ping_host(ip: str, count: int = 3, timeout: int = 5) -> float | None:
    """
    Pings an IP address multiple times and returns the average Round-Trip Time (RTT).
    Prioritizes ICMP ping, but falls back to TCP ping on port 22 (SSH) if ICMP fails.

    Args:
        ip (str): The IP address to ping.
        count (int): The number of ping attempts. Defaults to 3.
        timeout (int): The maximum time in seconds to wait for each ping response. Defaults to 5.

    Returns:
        float | None: The average RTT in milliseconds across successful pings,
                      or None if all attempts fail.
    """
    rtts = []

    for i in range(count):
        log.debug("Attempt %d: ICMP ping to %s", i + 1, ip)
        # ping3.ping returns float (RTT), None (timeout), or False (other error)
        rtt_icmp = ping(ip, timeout=timeout)
        if rtt_icmp is not None and rtt_icmp is not False: # Success for ICMP
            rtts.append(rtt_icmp * 1000) # Convert to milliseconds
            log.debug("ICMP ping to %s successful: %.1fms", ip, rtt_icmp * 1000)
        else:
            log.debug("ICMP ping to %s failed or timed out. Falling back to TCP ping on port 22.", ip)
            # Fallback to TCP ping on port 22 (SSH)
            rtt_tcp = tcp_ping(ip, 22, timeout)
            if rtt_tcp is not None:
                rtts.append(rtt_tcp)
                log.debug("TCP ping to %s:22 successful: %.1fms", ip, rtt_tcp)
            else:
                log.debug("TCP ping to %s:22 also failed.", ip)
            
    
    # Calculate average RTT if any successful pings were recorded
    if rtts:
        avg_rtt = sum(rtts) / len(rtts)
        return avg_rtt
    else:
        log.debug("All ping attempts to %s failed.", ip)
        return None


