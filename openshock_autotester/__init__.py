"""
OpenShock Auto-Tester
Automatically runs hardware tests on flashed OpenShock hubs when plugged in
Background colors indicate status:
Blue=Waiting, Yellow=Testing, Green=Passed, Red=Failed
"""

from openshock_autotester.tester import AutoTester

__all__ = ["AutoTester"]
