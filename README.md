# OpenShock Auto-Tester [![Ask DeepWiki](<https://deepwiki.com/badge.svg>)](<https://deepwiki.com/NanashiTheNameless/OpenShock-AutoTester>)

[![PyPI - Version](https://img.shields.io/pypi/v/OpenShock-AutoTester)](https://pypi.org/project/OpenShock-AutoTester/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/OpenShock-AutoTester)](https://pypi.org/project/OpenShock-AutoTester/)
[![PyPI - Implementation](https://img.shields.io/pypi/implementation/OpenShock-AutoTester)](https://pypi.org/project/OpenShock-AutoTester/)
[![PyPI - Types](https://img.shields.io/pypi/types/OpenShock-AutoTester)](https://pypi.org/project/OpenShock-AutoTester/)

[![Tests](https://github.com/NanashiTheNameless/OpenShock-AutoTester/workflows/Tests/badge.svg)](https://github.com/NanashiTheNameless/OpenShock-AutoTester/actions/workflows/test.yml)
[![GitHub License](https://img.shields.io/github/license/NanashiTheNameless/OpenShock-AutoTester)](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/LICENSE)

Automatically test already-flashed OpenShock hubs as they are plugged in: verify
their WiFi AP and RF transmitter, optionally factory-reset them, and record every
result in one HTML session report. Terminal colors show progress and pass/fail results.

This tool does not flash firmware. To flash hubs (with or without testing), use
[OpenShock Auto-Flasher](https://github.com/NanashiTheNameless/OpenShock-AutoFlasher).

## Install

Requires Python 3.12+, pipx, and a USB connection to your hub. Runs on Linux,
macOS, and Windows.

```bash
pipx install --force 'git+https://github.com/NanashiTheNameless/OpenShock-AutoTester@main'
```

For PyPI or source installation, see the
[advanced guide](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#alternative-installation).

## Tests

- **WiFi:** the host computer scans for the hub's exact
  `OpenShock-XX:XX:XX:XX:XX:XX` AP using its WiFi adapter. Scanning supports
  Linux, Windows, and macOS. See [platform requirements](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#wifi-ap-testing)
  for WiFi services and permissions.
- **RF:** prepare a separate USB tester with a 433 MHz receiver running
  [CaiXianlinRemoteIDMonitor](https://github.com/NanashiTheNameless/CaiXianlinRemoteIDMonitor).
  Follow the [tester setup guide](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#rf-tester-setup).

At least one test is required. Enable either alone by omitting the other flag.

## Test hubs

Start the command with hubs disconnected. **Plug the RF tester in first**, wait for
`RF tester detected ...; reserved for testing.`, then connect hubs one at a time.
Close other serial monitors before testing.

```bash
OPSH-AutoTest --test-wifi --test-rf --factory-reset-after-test --alert
```

The tester checks each newly connected hub and waits for the next one, continuing
after a pass or failure. Press Ctrl+C to stop. RF testing checks Beep, Vibrate,
and Stop with different IDs; Light and Shock are not transmitted.

Factory reset clears saved hub settings after testing, whether tests pass or fail.
Omit `--factory-reset-after-test` to keep the settings. Add `--board NAME` to label
the run in the logs and report.

To test one already-connected hub and exit, add `--port /dev/ttyUSB1` (or a
Windows port such as `COM3`). For an explicit tester port, use
`--test-rf-port /dev/ttyUSB0` instead of `--test-rf`; the hub and tester must use
separate ports.

## Session report

One dark-mode HTML file records every hub attempt in the session, including MAC address,
USB serial number when available, and detailed test results.
The file is updated throughout the run, and its path is printed at startup.
Use `--report batch.html` to choose a filename, or `--no-report` to disable it.
See [report details](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#session-report).

## More information

See [README-advanced.md](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md) for all flags,
WiFi scanning, RF validation, Linux permissions, troubleshooting, and development instructions.

For contributions, see [CONTRIBUTING.md](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/CONTRIBUTING.md). Report vulnerabilities
using [SECURITY.md](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/SECURITY.md).

## License

Licensed under [GNU AGPL-3.0](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/LICENSE).

## Disclaimer

This tool is provided as-is. Use at your own risk. Factory reset erases saved hub settings.

## Support My Work

If this project is useful to you, you can support it here:

- [<https://github.com/sponsors/NanashiTheNameless>](<https://github.com/sponsors/NanashiTheNameless>)
- [<https://buymeacoffee.com/NamelessNanashi>](<https://buymeacoffee.com/NamelessNanashi>)
- [<https://ko-fi.com/NanashiTheNameless>](<https://ko-fi.com/NanashiTheNameless>)
- [<https://liberapay.com/NamelessNanashi>](<https://liberapay.com/NamelessNanashi>)
- [<https://throne.com/NamelessNanashi>](<https://throne.com/NamelessNanashi>)
