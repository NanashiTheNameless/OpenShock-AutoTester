"""
Core testing controller for OpenShock Auto-Tester
"""

import importlib.metadata
import textwrap
import time
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Iterator, Optional, List, Set

import serial.tools.list_ports
from rich.style import Style

from .constants import (
    INITIAL_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    POLL_BACKOFF_THRESHOLD,
    DEVICE_INIT_DELAY,
)
from .styles import StateColors, console
from .report import SessionReport
from .wifi import read_ap_ssid
from .hardware_tests import (
    CheckResult,
    HardwareTestConfig,
    HardwareTestError,
    HardwareTestResult,
    run_hardware_tests,
    same_port,
)


class AutoTester:
    """Hardware-testing controller for already-flashed OpenShock hubs"""

    def __init__(
        self,
        board: Optional[str] = None,
        alert: bool = False,
        hardware_tests: Optional[HardwareTestConfig] = None,
        session_report: Optional[SessionReport] = None,
    ) -> None:
        self.board: Optional[str] = board
        self.alert: bool = alert
        self.hardware_tests = hardware_tests or HardwareTestConfig()
        self.session_report = session_report
        self._record: Optional[dict[str, Any]] = None
        self.rf_monitor_identity: Optional[tuple[Optional[int], Optional[int], str]] = None
        self.known_ports: Set[str] = set()
        self.state: str = "waiting"
        self.current_style: Style = StateColors.WAITING

    def get_style(self) -> Style:
        """Get style based on current state"""
        styles = {
            "waiting": StateColors.WAITING,
            "testing": StateColors.TESTING,
            "done": StateColors.DONE,
            "error": StateColors.ERROR,
        }
        return styles.get(self.state, StateColors.WAITING)

    @contextmanager
    def _report_device(self, port: str) -> Iterator[None]:
        if self.session_report is None or self._record is not None:
            yield
            return
        usb: dict[str, Any] = {}
        try:
            info = next(
                (p for p in serial.tools.list_ports.comports() if same_port(p.device, port)), None
            )
            if info is not None:
                usb = {
                    key: getattr(info, key, None)
                    for key in (
                        "serial_number",
                        "vid",
                        "pid",
                        "manufacturer",
                        "product",
                        "description",
                        "location",
                    )
                }
        except Exception:
            pass
        self._record = self.session_report.start_device(
            port,
            board=self.board,
            tests={
                "wifi": self.hardware_tests.wifi,
                "rf": self.hardware_tests.rf_enabled,
                "factory_reset": self.hardware_tests.factory_reset_after_test,
            },
            usb=usb,
        )
        self._record["rf_tester_port"] = self.hardware_tests.rf_port
        try:
            # The WiFi test reads the MAC itself unless an SSID was given.
            if not self.hardware_tests.wifi or self.hardware_tests.wifi_ssid:
                try:
                    self._report_identity(read_ap_ssid(port).removeprefix("OpenShock-"))
                except Exception as exc:
                    self._record["warnings"].append(f"MAC read unavailable: {type(exc).__name__}")
            yield
        except BaseException as exc:
            status = "failed" if isinstance(exc, Exception) else "interrupted"
            self.session_report.finish_device(self._record, status, str(exc) or type(exc).__name__)
            raise
        else:
            self.session_report.finish_device(self._record, "passed")
        finally:
            self._record = None

    def _report_identity(self, mac: str) -> None:
        if self._record is not None and self.session_report is not None:
            self._record.update(mac_address=mac.upper(), mac_source="hub base MAC")
            self.session_report.save()

    def _report_event(self, kind: str, value: Any) -> None:
        if self._record is None or self.session_report is None:
            return
        if kind == "start":
            self._record["tests"][value]["status"] = "in_progress"
        elif kind == "check":
            self._record["tests"][value.name] = {
                "status": "passed" if value.passed else "failed",
                "detail": value.detail,
                "elapsed_seconds": value.elapsed_seconds,
            }
        elif kind == "rf_command":
            self._record["rf_commands"].append(value)
        elif kind == "mac":
            self._report_identity(value)
        elif kind == "ap":
            self._record["expected_ap"] = value
        self.session_report.save()

    def set_state(self, state: str) -> None:
        """Change state and update terminal background"""
        self.state = state
        self.current_style = self.get_style()

    def play_alert(self) -> None:
        """Play an audible beep alert"""
        for _ in range(4):
            print("\a", end="", flush=True)
            time.sleep(0.15)

    def log(self, message: str) -> None:
        """Print log message with current background"""
        timestamp = time.strftime("%H:%M:%S")
        # Fill entire width with background color
        max_len = console.width - 2
        text = f"[{timestamp}] {message}"
        lines = (
            textwrap.wrap(text, width=max_len, break_long_words=False, break_on_hyphens=False)
            if len(text) > max_len
            else [text]
        )
        for line in lines:
            console.print(
                line + " " * (max_len - len(line)),
                style=self.current_style,
                markup=False,
                highlight=False,
            )

    def is_monitor_port(self, port: str) -> bool:
        return bool(self.hardware_tests.rf_port and same_port(port, self.hardware_tests.rf_port))

    def test_device(self, port: str) -> None:
        """Run enabled checks and show their results in the terminal."""
        if self.hardware_tests.rf_auto_detect and self.hardware_tests.rf_port is None:
            self.set_state("error")
            raise HardwareTestError("Select the RF tester port before testing")
        if self.is_monitor_port(port):
            self.set_state("error")
            raise HardwareTestError("Refusing to test the RF monitor port as a hub")
        with self._report_device(port):
            self._test_device(port)

    def _test_device(self, port: str) -> None:
        self.set_state("testing")
        self.log("=" * 60)
        self.log("Starting hardware tests" + (f" for {self.board}" if self.board else ""))
        self.log(f"Port: {port}")
        self.log("=" * 60)
        try:
            result = run_hardware_tests(
                port, self.hardware_tests, self.log, on_event=self._report_event
            )
        except Exception as exc:
            detail = str(exc) if isinstance(exc, HardwareTestError) else type(exc).__name__
            result = HardwareTestResult(port, [CheckResult("setup", False, detail, 0)])
        for check in result.checks:
            self._report_event("check", check)
        if not result.passed:
            self.set_state("error")
            raise HardwareTestError(
                "Hardware testing failed: "
                + "; ".join(
                    f"{check.name}: {check.detail}" for check in result.checks if not check.passed
                )
            )
        self.set_state("done")
        self.log("=" * 60)
        self.log("✓ All hardware tests passed")
        self.log("=" * 60)
        if self.alert:
            self.play_alert()

    def prepare_rf_monitor(self, target_port: Optional[str] = None) -> None:
        """Reserve the first tester connection before accepting hubs to test."""
        if not self.hardware_tests.rf_auto_detect or self.hardware_tests.rf_port is not None:
            return

        self.log("RF tester auto-detection: plug in the tester first, then the hubs.")
        previous: Optional[Set[str]] = None
        while True:
            ports = list(serial.tools.list_ports.comports())
            eligible = [
                p for p in ports if target_port is None or not same_port(p.device, target_port)
            ]
            current = {p.device for p in eligible}
            candidates = current if previous is None else current - previous
            if len(candidates) == 1:
                selected = next(p for p in eligible if p.device in candidates)
                self.hardware_tests = replace(self.hardware_tests, rf_port=selected.device)
                if isinstance(selected.serial_number, str) and selected.serial_number:
                    self.rf_monitor_identity = (selected.vid, selected.pid, selected.serial_number)
                self.known_ports = {p.device for p in ports}
                self.log(f"RF tester detected on {selected.device}; reserved for testing.")
                return
            if len(candidates) > 1:
                self.log("Multiple serial ports detected. Unplug and reconnect only the RF tester.")
            elif previous is None:
                self.log("Waiting for the RF tester to be plugged in...")
            previous = current
            time.sleep(INITIAL_POLL_INTERVAL)

    def refresh_rf_monitor_port(self, ports: list) -> None:
        """Follow the selected USB tester if its serial port number changes."""
        if self.rf_monitor_identity is None:
            return
        matches = [p for p in ports if (p.vid, p.pid, p.serial_number) == self.rf_monitor_identity]
        if len(matches) == 1 and matches[0].device != self.hardware_tests.rf_port:
            self.hardware_tests = replace(self.hardware_tests, rf_port=matches[0].device)
            self.log(f"RF tester reconnected on {matches[0].device}; reserved for testing.")

    def detect_new_port(self) -> Optional[List[str]]:
        """Detect when a new serial port is connected"""
        try:
            ports = list(serial.tools.list_ports.comports())
            self.refresh_rf_monitor_port(ports)
            current_ports = {p.device for p in ports}
            new_ports = current_ports - self.known_ports
            self.known_ports = current_ports
            if new_ports:
                targets = [
                    p.device
                    for p in ports
                    if p.device in new_ports
                    and not self.is_monitor_port(p.device)
                    and (
                        self.rf_monitor_identity is None
                        or (p.vid, p.pid, p.serial_number) != self.rf_monitor_identity
                    )
                ]
                return targets or None
        except Exception as e:
            self.log(f"⚠ Warning: Port detection error: {e}")
        return None

    def log_test_settings(self) -> None:
        """Show which hardware tests and cleanup steps are enabled."""
        self.log(f"WiFi AP test: {self.hardware_tests.wifi}")
        self.log(f"RF test: {self.hardware_tests.rf_enabled}")
        if self.hardware_tests.rf_port is not None:
            self.log(f"RF monitor port: {self.hardware_tests.rf_port}")
        elif self.hardware_tests.rf_auto_detect:
            self.log("RF monitor port: auto-detect (plug tester in first)")
        self.log(f"Factory reset after testing: {self.hardware_tests.factory_reset_after_test}")

    def run(self) -> None:
        """Main run loop: test every hub connected after startup"""
        self.set_state("waiting")
        try:
            pkg_version = importlib.metadata.version("OpenShock-AutoTester")
        except importlib.metadata.PackageNotFoundError:
            pkg_version = "unknown (not installed)"
        self.log(f"OpenShock Auto-Tester {pkg_version}")
        self.log("=" * 60)
        if self.board:
            self.log(f"Board: {self.board}")
        self.log_test_settings()
        self.log("=" * 60)
        self.log("")

        if self.hardware_tests.rf_auto_detect:
            self.prepare_rf_monitor()
        else:
            self.known_ports = {p.device for p in serial.tools.list_ports.comports()}

        self.set_state("waiting")
        self.log("Waiting for hub to be plugged in...")
        self.log("(Press Ctrl+C to exit)")

        try:
            # Adaptive polling: start fast, back off when idle
            poll_interval = INITIAL_POLL_INTERVAL
            consecutive_checks = 0

            while True:
                new_ports = self.detect_new_port()
                if new_ports:
                    for new_port in new_ports:
                        self.log(f"✓ Hub detected on {new_port}")
                        poll_interval = INITIAL_POLL_INTERVAL
                        consecutive_checks = 0
                        # Give device time to initialize
                        time.sleep(DEVICE_INIT_DELAY)
                        try:
                            self.test_device(new_port)
                        except Exception as exc:
                            self.set_state("error")
                            self.log(f"Testing failed: {exc}")
                            self.log("Hub failed. Connect the next hub to continue.")
                        self.log("")
                        self.set_state("waiting")
                        self.log("Waiting for next hub...")
                        self.log("(Press Ctrl+C to exit)")
                        self.log("")
                else:
                    consecutive_checks += 1
                    if consecutive_checks > POLL_BACKOFF_THRESHOLD:
                        poll_interval = min(MAX_POLL_INTERVAL, poll_interval + 0.1)

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            if self.session_report is not None:
                self.session_report.finish_on_stop()
            console.print("\n")
            self.log("Exiting...")

        except Exception as e:
            self.set_state("error")
            self.log(f"Fatal error: {e}")
            if self.session_report is not None:
                self.session_report.finish("failed")
            import traceback

            traceback.print_exc()
