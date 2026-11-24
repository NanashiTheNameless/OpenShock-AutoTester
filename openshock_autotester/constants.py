"""
Configuration constants for OpenShock Auto-Tester
"""

# Polling settings
INITIAL_POLL_INTERVAL: float = 0.5  # seconds
MAX_POLL_INTERVAL: float = 1.0  # seconds
POLL_BACKOFF_THRESHOLD: int = 10  # checks before increasing interval
DEVICE_INIT_DELAY: int = 1  # seconds to wait after device detection
