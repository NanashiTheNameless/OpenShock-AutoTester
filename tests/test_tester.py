"""
Tests for tester module
"""

from unittest.mock import Mock, call, patch

import pytest

from openshock_autotester.hardware_tests import (
    CheckResult,
    HardwareTestConfig,
    HardwareTestError,
    HardwareTestResult,
)
from openshock_autotester.styles import StateColors
from openshock_autotester.tester import AutoTester

COMPORTS = "openshock_autotester.tester.serial.tools.list_ports.comports"
SLEEP = "openshock_autotester.tester.time.sleep"


@pytest.fixture
def tester():
    return AutoTester(board="test-board", hardware_tests=HardwareTestConfig(wifi=True))


def test_tester_initialization(tester):
    assert tester.board == "test-board"
    assert tester.alert is False
    assert tester.state == "waiting"
    assert tester.session_report is None
    assert tester.hardware_tests.wifi is True


@pytest.mark.parametrize(
    "state,style",
    [
        ("waiting", StateColors.WAITING),
        ("testing", StateColors.TESTING),
        ("done", StateColors.DONE),
        ("error", StateColors.ERROR),
        ("unknown", StateColors.WAITING),
    ],
)
def test_set_state_updates_style(tester, state, style):
    tester.set_state(state)
    assert tester.state == state
    assert tester.current_style == style


@pytest.mark.parametrize("installed", [True, False])
def test_run_handles_missing_package_metadata(tester, installed):
    from importlib.metadata import PackageNotFoundError

    with (
        patch(
            "openshock_autotester.tester.importlib.metadata.version",
            return_value="0.0.1",
            side_effect=None if installed else PackageNotFoundError("OpenShock-AutoTester"),
        ),
        patch(COMPORTS, return_value=[]),
        patch.object(tester, "detect_new_port", side_effect=KeyboardInterrupt()),
        patch.object(tester, "log") as log,
    ):
        tester.run()
    version = "0.0.1" if installed else "unknown (not installed)"
    log.assert_any_call(f"OpenShock Auto-Tester {version}")


def test_log_wraps_long_messages(tester):
    with (patch("openshock_autotester.tester.console") as console,):
        console.width = 30
        tester.log("word " * 20)
    assert console.print.call_count > 1
    for printed in console.print.call_args_list:
        assert len(printed.args[0]) == 28


def test_detect_new_port(tester):
    with patch(COMPORTS) as ports:
        ports.return_value = [Mock(device="a")]
        assert tester.detect_new_port() == ["a"]
        assert tester.detect_new_port() is None
        ports.return_value = [Mock(device="a"), Mock(device="b"), Mock(device="c")]
        assert tester.detect_new_port() == ["b", "c"]


def test_detect_new_port_logs_errors(tester):
    with (
        patch(COMPORTS, side_effect=OSError("boom")),
        patch.object(tester, "log") as log,
    ):
        assert tester.detect_new_port() is None
    log.assert_called_once_with("⚠ Warning: Port detection error: boom")


def test_reconnected_monitor_is_excluded_from_detection():
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_port="monitor"))
    with patch(COMPORTS) as ports:
        ports.return_value = [Mock(device="monitor"), Mock(device="dut")]
        assert tester.detect_new_port() == ["dut"]
        assert tester.detect_new_port() is None
        ports.return_value = []
        assert tester.detect_new_port() is None
        ports.return_value = [Mock(device="monitor")]
        assert tester.detect_new_port() is None


def test_monitor_port_alias_is_never_tested(tmp_path):
    port = tmp_path / "ttyUSB0"
    port.touch()
    alias = tmp_path / "monitor"
    alias.symlink_to(port)
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_port=str(alias)))
    with patch("openshock_autotester.tester.run_hardware_tests") as run:
        with pytest.raises(HardwareTestError, match="Refusing"):
            tester.test_device(str(port))
    run.assert_not_called()
    assert tester.state == "error"


def test_setup_failure_sets_error_state(tester):
    with patch(
        "openshock_autotester.tester.run_hardware_tests",
        side_effect=HardwareTestError("No serial"),
    ):
        with pytest.raises(HardwareTestError, match="setup: No serial"):
            tester.test_device("dut")
    assert tester.state == "error"


def test_unexpected_setup_error_reports_type_only(tester):
    with patch(
        "openshock_autotester.tester.run_hardware_tests", side_effect=RuntimeError("secret")
    ):
        with pytest.raises(HardwareTestError, match="setup: RuntimeError"):
            tester.test_device("dut")


@pytest.mark.parametrize("passed", [True, False])
def test_alert_requires_passing_tests(passed):
    tester = AutoTester(alert=True, hardware_tests=HardwareTestConfig(wifi=True))
    result = HardwareTestResult("hub", [CheckResult("wifi", passed, "AP check", 0)])
    with (
        patch("openshock_autotester.tester.run_hardware_tests", return_value=result),
        patch.object(tester, "play_alert") as alert,
    ):
        if passed:
            tester.test_device("hub")
        else:
            with pytest.raises(HardwareTestError):
                tester.test_device("hub")
    assert alert.call_count == int(passed)
    assert tester.state == ("done" if passed else "error")


def test_play_alert_beeps(tester, capsys):
    with patch(SLEEP):
        tester.play_alert()
    assert capsys.readouterr().out == "\a" * 4


def test_auto_rf_reserves_first_plugged_device_before_detecting_hubs():
    monitor = Mock(device="monitor", serial_number="tester-1", vid=1, pid=2)
    hub = Mock(device="hub", serial_number="hub-1", vid=1, pid=2)
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_auto_detect=True))
    with (
        patch(COMPORTS, side_effect=[[], [], [monitor], [monitor, hub]]),
        patch(SLEEP),
    ):
        tester.prepare_rf_monitor()
        assert tester.hardware_tests.rf_port == "monitor"
        assert tester.known_ports == {"monitor"}
        assert tester.detect_new_port() == ["hub"]


def test_auto_rf_accepts_only_existing_tester_and_excludes_explicit_target():
    monitor = Mock(device="monitor", serial_number=None)
    hub = Mock(device="hub")
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_auto_detect=True))
    with patch(COMPORTS, return_value=[monitor, hub]):
        tester.prepare_rf_monitor(target_port="hub")
    assert tester.hardware_tests.rf_port == "monitor"
    assert tester.rf_monitor_identity is None


def test_auto_rf_requires_replug_when_existing_ports_are_ambiguous():
    monitor = Mock(device="monitor", serial_number=None)
    other = Mock(device="other")
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_auto_detect=True))
    with (
        patch(COMPORTS, side_effect=[[monitor, other], [other], [other, monitor]]),
        patch(SLEEP),
        patch.object(tester, "log") as log,
    ):
        tester.prepare_rf_monitor()
    assert tester.hardware_tests.rf_port == "monitor"
    assert any("Multiple serial ports" in c.args[0] for c in log.call_args_list)


def test_auto_rf_does_not_choose_arbitrarily_when_two_ports_arrive_together():
    monitor = Mock(device="monitor", serial_number=None)
    other = Mock(device="other")
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_auto_detect=True))
    with (
        patch(COMPORTS, side_effect=[[], [monitor, other], [other], [other, monitor]]),
        patch(SLEEP),
    ):
        tester.prepare_rf_monitor()
    assert tester.hardware_tests.rf_port == "monitor"


def test_auto_rf_tracks_tester_serial_number_after_port_changes():
    original = Mock(device="monitor-old", serial_number="tester", vid=1, pid=2)
    reconnected = Mock(device="monitor-new", serial_number="tester", vid=1, pid=2)
    hub = Mock(device="hub", serial_number="hub", vid=1, pid=2)
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_auto_detect=True))
    with patch(COMPORTS, side_effect=[[original], [], [reconnected, hub]]):
        tester.prepare_rf_monitor()
        assert tester.detect_new_port() is None
        assert tester.detect_new_port() == ["hub"]
    assert tester.hardware_tests.rf_port == "monitor-new"
    assert tester.is_monitor_port("monitor-new")


def test_ambiguous_tester_identity_is_never_returned_for_testing():
    original = Mock(device="monitor-old", serial_number="tester", vid=1, pid=2)
    copies = [Mock(device=f"monitor-{i}", serial_number="tester", vid=1, pid=2) for i in range(2)]
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_auto_detect=True))
    with patch(COMPORTS, side_effect=[[original], copies]):
        tester.prepare_rf_monitor()
        assert tester.detect_new_port() is None


def test_manual_rf_port_does_not_wait_for_auto_detection():
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_port="monitor"))
    with patch(COMPORTS) as ports:
        tester.prepare_rf_monitor()
    ports.assert_not_called()


def test_unresolved_auto_rf_cannot_test_a_device():
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_auto_detect=True))
    with patch("openshock_autotester.tester.run_hardware_tests") as run:
        with pytest.raises(HardwareTestError, match="Select the RF tester"):
            tester.test_device("monitor")
    run.assert_not_called()


def test_auto_rf_startup_shows_enabled_while_awaiting_tester():
    tester = AutoTester(hardware_tests=HardwareTestConfig(rf_auto_detect=True))
    with patch.object(tester, "log") as log:
        tester.log_test_settings()
    log.assert_any_call("RF test: True")
    log.assert_any_call("RF monitor port: auto-detect (plug tester in first)")


@pytest.mark.parametrize("auto_tester", [False, True])
def test_continuous_testing_detects_hubs_and_continues_after_failure(auto_tester):
    monitor = Mock(device="monitor", serial_number="tester", vid=1, pid=2)
    first = Mock(device="hub-one", serial_number="hub-one", vid=1, pid=2)
    second = Mock(device="hub-two", serial_number="hub-two", vid=1, pid=2)
    # The explicit tester is already connected; automatic selection sees it arrive first.
    ports = ([[], [monitor]] if auto_tester else [[monitor]]) + [
        [monitor, first],
        [monitor],
        [monitor, second],
        KeyboardInterrupt(),
    ]
    tester = AutoTester(
        board="board",
        hardware_tests=HardwareTestConfig(
            wifi=True,
            rf_auto_detect=auto_tester,
            rf_port=None if auto_tester else "monitor",
            factory_reset_after_test=True,
        ),
    )
    with (
        patch(COMPORTS, side_effect=ports),
        patch(SLEEP),
        patch.object(
            tester, "test_device", side_effect=[HardwareTestError("RF failed"), None]
        ) as test,
        patch.object(tester, "log") as log,
    ):
        tester.run()
    assert test.call_args_list == [call("hub-one"), call("hub-two")]
    log.assert_any_call("Board: board")
    log.assert_any_call("Testing failed: RF failed")
    assert tester.hardware_tests.factory_reset_after_test
    assert tester.hardware_tests.rf_port == "monitor"


def test_continuous_wifi_only_detects_new_hub_without_tester():
    existing = Mock(device="existing")
    hub = Mock(device="hub")
    tester = AutoTester(hardware_tests=HardwareTestConfig(wifi=True))
    with (
        patch(COMPORTS, side_effect=[[existing], [existing, hub], KeyboardInterrupt()]),
        patch(SLEEP),
        patch.object(tester, "test_device") as test,
    ):
        tester.run()
    test.assert_called_once_with("hub")


def test_fatal_loop_error_marks_report_failed():
    report = Mock()
    tester = AutoTester(hardware_tests=HardwareTestConfig(wifi=True), session_report=report)
    with (
        patch(COMPORTS, return_value=[]),
        patch.object(tester, "detect_new_port", side_effect=RuntimeError("boom")),
        patch.object(tester, "log"),
        patch("traceback.print_exc"),
    ):
        tester.run()
    report.finish.assert_called_once_with("failed")
    assert tester.state == "error"
