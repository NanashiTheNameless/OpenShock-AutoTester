"""
Tests for constants module
"""

from openshock_autotester.constants import (
    INITIAL_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    POLL_BACKOFF_THRESHOLD,
    DEVICE_INIT_DELAY,
)


def test_polling_intervals():
    """Test polling interval constants are logical"""
    assert INITIAL_POLL_INTERVAL > 0
    assert MAX_POLL_INTERVAL >= INITIAL_POLL_INTERVAL
    assert POLL_BACKOFF_THRESHOLD > 0
    assert DEVICE_INIT_DELAY >= 0
