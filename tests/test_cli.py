"""
Tests for CLI module
"""

from unittest.mock import call, patch

import pytest

from openshock_autotester.cli import create_argument_parser, main, positive_float


@pytest.fixture(autouse=True)
def no_report_file():
    with patch("openshock_autotester.cli.SessionReport"):
        yield


def run_cli(monkeypatch, *arguments):
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest", *arguments])
    with patch("openshock_autotester.cli.AutoTester") as tester:
        main()
    return tester


def test_argument_parser_defaults():
    args = create_argument_parser().parse_args(["--test-wifi"])
    assert args.test_wifi is True
    assert args.board is None
    assert args.port is None
    assert args.test_timeout == 60.0
    assert args.alert is False


def test_argument_parser_has_no_flashing_options():
    parser = create_argument_parser()
    for option in ("--channel", "--version", "--erase", "--post-flash", "--chip", "--test-only"):
        with pytest.raises(SystemExit):
            parser.parse_args(["--test-wifi", option, "x"])


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_positive_float_rejects_invalid(value):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        positive_float(value)


def test_no_arguments_prints_help(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    assert "--test-wifi" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    [
        ["--board", "test-board"],
        ["--factory-reset-after-test"],
        ["--port", "dut"],
        ["--port", "monitor", "--test-rf-port", "monitor"],
        ["--test-rf", "--test-rf-port", "monitor"],
        ["--test-wifi", "--test-timeout", "nan"],
        ["--test-wifi", "--test-timeout", "inf"],
        ["--test-wifi", "--test-timeout", "0"],
        ["--test-wifi", "--report", "a.html", "--no-report"],
    ],
)
def test_invalid_options_exit_before_testing(monkeypatch, arguments):
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest", *arguments])
    with patch("openshock_autotester.cli.AutoTester") as tester:
        with pytest.raises(SystemExit) as error:
            main()
    assert error.value.code == 2
    tester.assert_not_called()


@pytest.mark.parametrize(
    "options",
    [
        ["--test-rf-port", "monitor", "--test-wifi-ssid", "OpenShock-AA:BB:CC:DD:EE:FF"],
        ["--test-wifi", "--test-wifi-ssid", "wrong-name"],
        ["--test-wifi", "--test-wifi-scan-command", "{}"],
        ["--test-wifi", "--test-wifi-scan-command", "[]"],
        ["--test-wifi", "--test-wifi-scan-command", '["python", 3]'],
    ],
)
def test_invalid_wifi_options(monkeypatch, options):
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest", *options])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_one_shot_port_tests_once(monkeypatch):
    tester = run_cli(
        monkeypatch,
        "--port",
        "dut",
        "--test-rf-port",
        "monitor",
        "--test-wifi",
        "--factory-reset-after-test",
        "--board",
        "test-board",
    )
    instance = tester.return_value
    instance.test_device.assert_called_once_with("dut")
    instance.run.assert_not_called()
    config = tester.call_args.kwargs["hardware_tests"]
    assert config.wifi is True and config.rf_port == "monitor"
    assert config.factory_reset_after_test is True
    assert tester.call_args.kwargs["board"] == "test-board"


@pytest.mark.parametrize("options", [["--test-wifi"], ["--test-rf"], ["--test-rf-port", "monitor"]])
def test_without_port_starts_continuous_testing(monkeypatch, options):
    tester = run_cli(monkeypatch, *options)
    tester.return_value.run.assert_called_once_with()
    tester.return_value.test_device.assert_not_called()


def test_wifi_scan_command_is_passed_as_tuple(monkeypatch):
    tester = run_cli(monkeypatch, "--test-wifi", "--test-wifi-scan-command", '["scan", "--json"]')
    assert tester.call_args.kwargs["hardware_tests"].wifi_scan_command == ("scan", "--json")


def test_report_created_once_with_explicit_path_and_finalized(monkeypatch):
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest", "--test-wifi", "--report", "batch.html"])
    with (
        patch("openshock_autotester.cli.SessionReport") as report,
        patch("openshock_autotester.cli.AutoTester") as tester,
    ):
        main()
    report.assert_called_once()
    assert report.call_args.args == ("batch.html",)
    assert tester.call_args.kwargs["session_report"] is report.return_value
    report.return_value.finish.assert_called_once_with("completed")


def test_no_report_disables_file_creation(monkeypatch):
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest", "--test-wifi", "--no-report"])
    with (
        patch("openshock_autotester.cli.SessionReport") as report,
        patch("openshock_autotester.cli.AutoTester") as tester,
    ):
        main()
    report.assert_not_called()
    assert tester.call_args.kwargs["session_report"] is None


def test_report_creation_error_exits_cleanly(monkeypatch):
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest", "--test-wifi"])
    with (
        patch("openshock_autotester.cli.SessionReport", side_effect=FileExistsError("exists")),
        patch("openshock_autotester.cli.AutoTester") as tester,
    ):
        with pytest.raises(SystemExit) as error:
            main()
    assert error.value.code == 2
    tester.assert_not_called()


def test_one_shot_failure_exits_nonzero(monkeypatch):
    monkeypatch.setattr("sys.argv", ["OPSH-AutoTest", "--port", "dut", "--test-rf-port", "monitor"])
    with patch("openshock_autotester.cli.AutoTester") as tester:
        tester.return_value.test_device.side_effect = RuntimeError("failed")
        with pytest.raises(SystemExit) as error:
            main()
    assert error.value.code == 1


def test_auto_rf_selects_tester_before_one_shot_test(monkeypatch):
    tester = run_cli(monkeypatch, "--port", "hub", "--test-rf", "--factory-reset-after-test")
    assert tester.call_args.kwargs["hardware_tests"].rf_auto_detect
    calls = tester.return_value.mock_calls
    assert calls.index(call.prepare_rf_monitor(target_port="hub")) < calls.index(
        call.test_device("hub")
    )
