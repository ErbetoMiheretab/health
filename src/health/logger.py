"""
Module for setting up a custom JSON-lines rotating log handler.
"""
import sys
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

# Define the default log message format for stream handler
LOG_FMT = "%(asctime)s | %(levelname)-8s | %(message)s"

# Get the root logger for the application
log = logging.getLogger("health")

class JsonLinesRotatingHandler(logging.Handler):
    """
    A custom logging handler that writes log records as JSON-lines to a file.
    The file automatically rotates when it exceeds a maximum size.
    """
    def __init__(self, filename: str, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 5):
        """
        Initializes the JsonLinesRotatingHandler.

        Args:
            filename (str): The base name of the log file (e.g., "health.jsonl").
            max_bytes (int): The maximum size of the log file in bytes before rotation.
                             Defaults to 5MB.
            backup_count (int): The number of backup log files to keep.
                                Defaults to 5 (e.g., health.jsonl.1, health.jsonl.2).
        """
        super().__init__()
        self.filename = Path(filename)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock = threading.Lock() # Protect file writes during rotation and concurrent logging

    def emit(self, record: logging.LogRecord):
        """
        Emits a log record. Converts the record into a JSON object and writes it
        as a single line to the log file. Performs rotation if the file size
        exceeds `max_bytes`.

        Args:
            record (logging.LogRecord): The log record to emit.
        """
        # Prepare the log entry as a dictionary
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "pathname": record.pathname,
            "lineno": record.lineno,
            # 'extra' keyword arguments passed to log methods will be added here
            "extra": getattr(record, "extra", {}),
        }

        with self._lock: # Ensure only one thread writes to the file at a time
            try:
                # Check if file needs rotation before writing
                if self.filename.exists() and self.filename.stat().st_size >= self.max_bytes:
                    self._rotate()
                
                # Append the JSON-line to the file
                with open(self.filename, "a", encoding="utf8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                # If logging itself fails, print to stderr to at least capture the error
                print(f"ERROR: Failed to write log entry to {self.filename}: {e}", file=sys.stderr)
                print(f"Failed log entry: {entry}", file=sys.stderr)


    def _rotate(self):
        """
        Manages the rotation of log files.
        Moves existing backups (e.g., .4 to .5, .3 to .4, etc.)
        and renames the primary log file to the first backup.
        """
        # Delete the oldest backup if it exists
        if Path(f"{self.filename}.{self.backup_count}").exists():
            Path(f"{self.filename}.{self.backup_count}").unlink()

        # Shift existing backup files
        for i in range(self.backup_count - 1, 0, -1):
            old = Path(f"{self.filename}.{i}")
            new = Path(f"{self.filename}.{i + 1}")
            if old.exists():
                old.rename(new)
        
        # Rename the current log file to the first backup
        if self.filename.exists():
            self.filename.rename(f"{self.filename}.1")
        
        # Create a new empty log file to continue logging
        self.filename.touch()
        log.info("Log file '%s' rotated.", self.filename, extra={"log_action": "rotate"})

def setup_logging(log_file_path: str = "health.jsonl", log_level=logging.INFO):
    """
    Configures the application's logging handlers.
    Adds a StreamHandler for console output and a JsonLinesRotatingHandler for file output.

    Args:
        log_file_path (str): The path for the JSON-lines log file.
        log_level (int): The minimum logging level to capture (e.g., logging.INFO, logging.DEBUG).
    """
    # Clear any existing handlers to prevent duplicates if called multiple times
    for handler in log.handlers[:]:
        log.removeHandler(handler)

    log.setLevel(log_level)

    # 1. Stream Handler for console output (human-readable)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter(LOG_FMT))
    stream_handler.setLevel(log_level)
    log.addHandler(stream_handler)

    # 2. JSON-Lines Rotating File Handler (machine-readable, persistent)
    json_handler = JsonLinesRotatingHandler(log_file_path)
    json_handler.setLevel(log_level)
    log.addHandler(json_handler)

    log.info("Logging configured. Stream output and JSON-lines file '%s' enabled.", log_file_path)