"""
artixinstall.utils.log — File-based logging to /tmp/artixinstall.log.

All shell commands, their outputs, and any errors are logged here with timestamps.
Passwords are automatically masked in all log output.
"""

import os
import re
from datetime import datetime

LOG_PATH = "/tmp/artixinstall.log"

# Patterns that look like password assignments in commands
_PASSWORD_PATTERNS = [
    # echo "user:password" | chpasswd  →  mask the password portion
    re.compile(r'(echo\s+["\']?\w+:)([^"\'|]+)'),
    # Any --password=XYZ flag
    re.compile(r'(--password[= ])(\S+)'),
]


def _mask_passwords(text: str) -> str:
    """Replace password-like content with asterisks in log output."""
    masked = text
    for pattern in _PASSWORD_PATTERNS:
        masked = pattern.sub(r'\1******', masked)
    return masked


def _timestamp() -> str:
    """Return a formatted timestamp string [HH:MM:SS]."""
    return datetime.now().strftime("[%H:%M:%S]")


def init_log() -> None:
    """Initialize (truncate) the log file at the start of a session."""
    try:
        with open(LOG_PATH, "w") as f:
            f.write(f"{_timestamp()} artixinstall session started\n")
            f.write(f"{_timestamp()} PID: {os.getpid()}\n")
            f.write("-" * 60 + "\n")
    except OSError:
        pass  # If we can't write to the log, continue silently


def log_cmd(cmd: str) -> None:
    """Log a shell command about to be executed."""
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"{_timestamp()} CMD: {_mask_passwords(cmd)}\n")
    except OSError:
        pass


def log_output(stdout: str, stderr: str) -> None:
    """Log the stdout and stderr from a completed command."""
    try:
        with open(LOG_PATH, "a") as f:
            if stdout.strip():
                for line in stdout.strip().splitlines():
                    f.write(f"{_timestamp()} OUT: {_mask_passwords(line)}\n")
            if stderr.strip():
                for line in stderr.strip().splitlines():
                    f.write(f"{_timestamp()} ERR: {_mask_passwords(line)}\n")
            f.write("\n")
    except OSError:
        pass


def log_live_output(line: str) -> None:
    """Log a single line from a live-streamed command."""
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"{_timestamp()} LIVE: {_mask_passwords(line.rstrip())}\n")
    except OSError:
        pass


def log_info(message: str) -> None:
    """Log an informational message."""
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"{_timestamp()} INFO: {_mask_passwords(message)}\n")
    except OSError:
        pass


def log_error(message: str) -> None:
    """Log an error message."""
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"{_timestamp()} ERROR: {_mask_passwords(message)}\n")
    except OSError:
        pass
