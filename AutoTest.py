#!/usr/bin/env python3
"""
OpenShock Auto-Tester
Automatically tests flashed OpenShock hubs when plugged in
Background colors indicate status: Blue=Waiting, Yellow=Testing, Green=Passed, Red=Failed
"""

from openshock_autotester.cli import main

if __name__ == "__main__":
    main()
