"""Session reports preserve device attempts, failures, identity and test details."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from openshock_autotester.tester import AutoTester
from openshock_autotester.hardware_tests import (
    CheckResult,
    HardwareTestConfig,
    HardwareTestError,
    HardwareTestResult,
)
from openshock_autotester.report import SessionReport


def test_single_file_contains_all_attempts_and_escapes_device_text(tmp_path):
    report = SessionReport(str(tmp_path / "session.html"))
    for status in ("passed", "failed", "interrupted"):
        record = report.start_device(
            "hub",
            board="board",
            tests={"wifi": True, "rf": False},
            usb={"serial_number": "<script>USB</script>"},
        )
        record["mac_address"] = "AA:BB:CC:DD:EE:FF"
        report.finish_device(record, status, "<bad>" if status == "failed" else None)
    report.finish("interrupted")
    assert list(tmp_path.iterdir()) == [report.path]
    html = report.path.read_text()
    assert "3 attempts" in html and "AA:BB:CC:DD:EE:FF" in html
    assert "&lt;script&gt;USB&lt;/script&gt;" in html and "<script>" not in html
    assert [d["status"] for d in report.data["devices"]] == ["passed", "failed", "interrupted"]
    assert all(
        d["finished_at"] and d["elapsed_seconds"] is not None for d in report.data["devices"]
    )


def test_existing_report_is_not_overwritten(tmp_path):
    path = tmp_path / "session.html"
    path.write_text("keep")
    with pytest.raises(FileExistsError):
        SessionReport(str(path))
    assert path.read_text() == "keep"


@pytest.mark.parametrize("stop", ["signal", "keyboard", "error"])
@pytest.mark.parametrize("device_status", [None, "passed", "failed", "interrupted"])
def test_cli_stop_preserves_finished_attempts(tmp_path, monkeypatch, stop, device_status):
    from openshock_autotester.cli import main

    report = SessionReport(str(tmp_path / "session.html"))
    if device_status is not None:
        device = report.start_device("hub", board="board", tests={}, usb={})
        report.finish_device(device, device_status)
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest", "--test-wifi"])
    with (
        patch("openshock_autotester.cli.SessionReport", return_value=report),
        patch("openshock_autotester.cli.AutoTester") as tester,
        patch("openshock_autotester.cli.signal.signal") as register_signal,
    ):

        def stop_run():
            if stop == "signal":
                register_signal.call_args.args[1](2, None)
            elif stop == "keyboard":
                raise KeyboardInterrupt()
            else:
                raise SystemExit(1)

        tester.return_value.run.side_effect = stop_run
        with pytest.raises((SystemExit, KeyboardInterrupt)):
            main()
    expected = (
        "failed"
        if stop == "error"
        else "interrupted" if device_status == "interrupted" else "completed"
    )
    assert report.data["status"] == expected
    assert report.data["finished_at"] is not None
    assert f"class='status {expected}'" in report.path.read_text()
    if device_status is not None:
        assert report.data["devices"][0]["status"] == device_status


def test_failed_atomic_update_preserves_previous_report(tmp_path):
    report = SessionReport(str(tmp_path / "session.html"))
    original = report.path.read_bytes()
    with patch("openshock_autotester.report.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            report.save()
    assert report.path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [report.path]


@pytest.fixture
def reporter(tmp_path, monkeypatch):
    report = SessionReport(str(tmp_path / "session.html"))
    info = SimpleNamespace(device="hub", serial_number="USB123", vid=0x1234, pid=0x5678)
    monkeypatch.setattr(
        "openshock_autotester.tester.serial.tools.list_ports.comports", lambda: [info]
    )
    tester = AutoTester(
        board="board",
        hardware_tests=HardwareTestConfig(wifi=True, rf_port="tester"),
        session_report=report,
    )
    monkeypatch.setattr(tester, "log", lambda *_: None)
    return tester, report


def test_tester_keyboard_interrupt_while_waiting_completes_report(reporter):
    tester, report = reporter
    with patch.object(tester, "detect_new_port", side_effect=KeyboardInterrupt()):
        tester.run()
    assert report.data["status"] == "completed"
    assert report.data["finished_at"] is not None


def test_tests_record_identity_usb_and_rf_commands(reporter):
    tester, report = reporter

    def tests(port, config, log, *, on_event):
        on_event("mac", "aa:bb:cc:dd:ee:ff")
        on_event("ap", "OpenShock-AA:BB:CC:DD:EE:FF")
        on_event(
            "rf_command",
            {
                "remote_id": 123,
                "channel": 1,
                "mode": "Beep",
                "intensity": 0,
                "duration_ms": 1000,
                "status": "passed",
                "detail": "matched",
            },
        )
        return HardwareTestResult(
            port, [CheckResult("wifi", True, "AP seen", 1), CheckResult("rf", True, "matched", 2)]
        )

    with patch("openshock_autotester.tester.run_hardware_tests", side_effect=tests):
        tester.test_device("hub")
    assert len(report.data["devices"]) == 1
    d = report.data["devices"][0]
    assert d["status"] == "passed" and d["board"] == "board"
    assert d["mac_address"] == "AA:BB:CC:DD:EE:FF" and d["usb"]["serial_number"] == "USB123"
    assert d["expected_ap"] == "OpenShock-AA:BB:CC:DD:EE:FF"
    assert d["tests"]["wifi"]["status"] == d["tests"]["rf"]["status"] == "passed"
    assert d["rf_commands"][0]["remote_id"] == 123
    assert d["rf_tester_port"] == "tester"


def test_partial_failure_marks_attempt_failed(reporter):
    tester, report = reporter
    result = HardwareTestResult(
        "hub", [CheckResult("wifi", True, "seen", 1), CheckResult("rf", False, "missing", 2)]
    )
    with patch("openshock_autotester.tester.run_hardware_tests", return_value=result):
        with pytest.raises(HardwareTestError):
            tester.test_device("hub")
    d = report.data["devices"][0]
    assert d["status"] == "failed"
    assert d["tests"]["rf"]["status"] == "failed" and d["tests"]["wifi"]["status"] == "passed"


def test_interrupted_test_preserves_completed_checks(reporter):
    tester, report = reporter

    def interrupted(port, config, log, *, on_event):
        on_event("mac", "AA:BB:CC:DD:EE:FF")
        on_event("check", CheckResult("wifi", True, "seen", 1))
        on_event("start", "rf")
        raise KeyboardInterrupt()

    with patch("openshock_autotester.tester.run_hardware_tests", side_effect=interrupted):
        with pytest.raises(KeyboardInterrupt):
            tester.test_device("hub")
    d = report.data["devices"][0]
    assert d["status"] == "interrupted" and d["tests"]["rf"]["status"] == "interrupted"
    assert d["tests"]["wifi"]["status"] == "passed"
    report.finish_on_stop()
    assert report.data["status"] == "interrupted"
    assert "AA:BB:CC:DD:EE:FF" in report.path.read_text()


def test_missing_usb_serial_is_unavailable_and_tester_is_not_reported(reporter):
    tester, report = reporter
    with pytest.raises(HardwareTestError):
        tester.test_device("tester")
    assert not report.data["devices"]
    result = HardwareTestResult("other-hub", [CheckResult("wifi", True, "seen", 1)])
    with patch("openshock_autotester.tester.run_hardware_tests", return_value=result):
        tester.test_device("other-hub")
    assert report.data["devices"][0]["usb"] == {}
    assert "Unavailable" in report.path.read_text()


def test_rf_only_reads_mac_for_report(tmp_path, monkeypatch):
    report = SessionReport(str(tmp_path / "session.html"))
    monkeypatch.setattr("openshock_autotester.tester.serial.tools.list_ports.comports", lambda: [])
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_port="tester"), session_report=report)
    monkeypatch.setattr(tester, "log", lambda *_: None)
    result = HardwareTestResult("hub", [CheckResult("rf", True, "matched", 1)])
    with (
        patch(
            "openshock_autotester.tester.read_ap_ssid", return_value="OpenShock-AA:BB:CC:DD:EE:FF"
        ),
        patch("openshock_autotester.tester.run_hardware_tests", return_value=result),
    ):
        tester.test_device("hub")
    assert report.data["devices"][0]["mac_address"] == "AA:BB:CC:DD:EE:FF"


def test_mac_read_failure_is_a_warning_not_a_failure(tmp_path, monkeypatch):
    report = SessionReport(str(tmp_path / "session.html"))
    monkeypatch.setattr("openshock_autotester.tester.serial.tools.list_ports.comports", lambda: [])
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_port="tester"), session_report=report)
    monkeypatch.setattr(tester, "log", lambda *_: None)
    result = HardwareTestResult("hub", [CheckResult("rf", True, "matched", 1)])
    with (
        patch("openshock_autotester.tester.read_ap_ssid", side_effect=OSError("busy")),
        patch("openshock_autotester.tester.run_hardware_tests", return_value=result),
    ):
        tester.test_device("hub")
    d = report.data["devices"][0]
    assert d["status"] == "passed"
    assert d["warnings"] == ["MAC read unavailable: OSError"]


def test_only_progress_saves_skip_fsync(tmp_path):
    report = SessionReport(str(tmp_path / "session.html"))
    with patch("openshock_autotester.report.os.fsync") as fsync:
        record = report.start_device("hub", board="b", tests={}, usb={})
        report.save()
        assert fsync.call_count == 0
        report.finish_device(record, "passed")
        assert fsync.call_count == 1
        report.finish()
        assert fsync.call_count == 2


def test_finished_attempts_render_once_and_in_progress_attempts_stay_live(tmp_path):
    report = SessionReport(str(tmp_path / "session.html"))
    done = report.start_device("hub", board="b", tests={}, usb={})
    report.finish_device(done, "passed")
    live = report.start_device("hub2", board="b", tests={}, usb={})
    assert list(report._rendered) == [1]
    live["mac_address"] = "11:22:33:44:55:66"
    report.save()
    assert "11:22:33:44:55:66" in report.path.read_text()
