"""
Command-line interface for OpenShock Auto-Tester
"""

import argparse
import json
import math
import signal
import sys

from rich.style import Style

from .styles import console
from .tester import AutoTester
from .hardware_tests import HardwareTestConfig, same_port
from .report import SessionReport


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return parsed


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser"""
    parser = argparse.ArgumentParser(
        description=(
            "OpenShock Auto-Tester: run hardware tests on already-flashed OpenShock hubs. "
            "At least one of --test-wifi, --test-rf or --test-rf-port is required."
        ),
    )
    parser.add_argument(
        "--board",
        "-B",
        help="Board label recorded in logs and the session report (optional)",
    )
    parser.add_argument(
        "--alert",
        "-A",
        action="store_true",
        help="Beep audibly when a hub passes all tests",
    )
    parser.add_argument("--port", help="Test this hub once, then exit (COM3 or /dev/ttyUSB0)")
    reports = parser.add_mutually_exclusive_group()
    reports.add_argument(
        "--report",
        metavar="PATH",
        help="Session HTML report path (default: timestamped file in current directory)",
    )
    reports.add_argument("--no-report", action="store_true", help="Disable the session report")

    tests = parser.add_argument_group("Hardware tests")
    tests.add_argument(
        "--test-wifi",
        action="store_true",
        help="Verify the hub broadcasts its OpenShock-MAC access point",
    )
    tests.add_argument(
        "--test-wifi-ssid",
        help="Explicit expected OpenShock-MAC SSID (otherwise read hub MAC with esptool)",
    )
    tests.add_argument(
        "--test-wifi-interface",
        help="WiFi adapter name (Linux/macOS) or description (Windows); default: all adapters",
    )
    tests.add_argument(
        "--test-wifi-scan-command",
        type=json.loads,
        metavar="JSON_ARGV",
        help="Custom fresh WiFi scan command as a JSON argument array; stdout must be a JSON SSID array",
    )
    rf = tests.add_mutually_exclusive_group()
    rf.add_argument(
        "--test-rf",
        action="store_true",
        help="Auto-detect the RF tester's serial port; plug the tester in before any hubs",
    )
    rf.add_argument("--test-rf-port", help="Separate CaiXianlinRemoteIDMonitor serial port")
    tests.add_argument(
        "--test-timeout",
        type=positive_float,
        default=60.0,
        metavar="SECONDS",
        help="Timeout per hardware test operation (default: 60)",
    )
    tests.add_argument(
        "--factory-reset-after-test",
        action="store_true",
        help="Send factoryreset after tests (pass or fail), clearing hub settings and restarting",
    )
    return parser


def main() -> None:
    """Main entry point for the application"""

    def signal_handler(sig: int, frame: object) -> None:
        # esptool treats SystemExit(0) as success; preserve cancellation instead.
        raise KeyboardInterrupt()

    signal.signal(signal.SIGINT, signal_handler)

    parser = create_argument_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if not (args.test_wifi or args.test_rf or args.test_rf_port is not None):
        parser.error("at least one of --test-wifi, --test-rf or --test-rf-port is required")
    if args.port and args.test_rf_port and same_port(args.port, args.test_rf_port):
        parser.error("--port and --test-rf-port must refer to separate devices")
    if not args.test_wifi and any(
        value is not None
        for value in (args.test_wifi_ssid, args.test_wifi_interface, args.test_wifi_scan_command)
    ):
        parser.error("WiFi scan options require --test-wifi")
    if args.test_wifi_scan_command is not None and (
        not isinstance(args.test_wifi_scan_command, list)
        or not args.test_wifi_scan_command
        or any(not isinstance(arg, str) or not arg for arg in args.test_wifi_scan_command)
    ):
        parser.error("--test-wifi-scan-command must be a nonempty JSON array of nonempty strings")
    try:
        hardware_tests = HardwareTestConfig(
            wifi=args.test_wifi,
            wifi_ssid=args.test_wifi_ssid,
            wifi_interface=args.test_wifi_interface,
            wifi_scan_command=(
                tuple(args.test_wifi_scan_command) if args.test_wifi_scan_command else None
            ),
            rf_port=args.test_rf_port,
            rf_auto_detect=args.test_rf,
            timeout=args.test_timeout,
            factory_reset_after_test=args.factory_reset_after_test,
        )
    except ValueError as exc:
        parser.error(str(exc))

    report = None
    if not args.no_report:
        try:
            report = SessionReport(
                args.report,
                settings={
                    "board": args.board,
                    "wifi": args.test_wifi,
                    "rf": hardware_tests.rf_enabled,
                    "factory_reset_after_test": args.factory_reset_after_test,
                    "test_timeout_seconds": args.test_timeout,
                },
            )
        except OSError as exc:
            parser.error(f"Cannot create session report: {exc}")
    status = "completed"
    try:
        tester = AutoTester(
            board=args.board,
            alert=args.alert,
            hardware_tests=hardware_tests,
            session_report=report,
        )

        if report is not None:
            tester.log(f"Session report: {report.path}")

        if args.port:
            tester.log_test_settings()
            try:
                tester.prepare_rf_monitor(target_port=args.port)
                tester.test_device(args.port)
            except Exception as exc:
                tester.set_state("error")
                tester.log(f"Failed: {exc}")
                sys.exit(1)
            return
        tester.run()
    except (KeyboardInterrupt, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code:
            status = "failed"
        elif report is not None:
            report.finish_on_stop()
        if isinstance(exc, KeyboardInterrupt):
            console.print("\nExiting...", style=Style(color="white"), markup=False, highlight=False)
            sys.exit(0)
        raise
    except Exception:
        status = "failed"
        raise
    finally:
        if report is not None:
            report.finish(status)


if __name__ == "__main__":
    main()
