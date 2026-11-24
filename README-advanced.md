# OpenShock Auto-Tester - Advanced Guide

See the [main README](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README.md) for installation and the common test commands.

- [Alternative installation](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#alternative-installation)
- [Command-line options](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#command-line-options)
- [WiFi AP testing](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#wifi-ap-testing)
- [RF tester setup](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#rf-tester-setup)
- [RF command validation](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#rf-command-validation)
- [Connecting hubs and testers](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#connect-and-run)
- [Session report](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#session-report)
- [How it works](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#how-it-works)
- [Linux permissions](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#permissions-linux)
- [Troubleshooting](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#troubleshooting)
- [Development](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README-advanced.md#development)

## Alternative installation

### From PyPI

If you prefer a release from PyPI:

```bash
pipx install OpenShock-AutoTester
```

### From Source

1. Clone this repository:

```bash
git clone https://github.com/NanashiTheNameless/OpenShock-AutoTester.git
cd OpenShock-AutoTester
```

2. Create a virtual environment and install the command from this checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead.

## Command-Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--board` | `-B` | Board label recorded in logs and the session report | - |
| `--alert` | `-A` | Beep after a hub passes all enabled tests | `false` |
| `--port` | - | Test this serial port once and exit | - |
| `--report` | - | Filename for the single HTML session report | Timestamped filename |
| `--no-report` | - | Disable the session report | `false` |
| `--test-wifi` | - | Verify the hub broadcasts its OpenShock-MAC access point | `false` |
| `--test-wifi-ssid` | - | Explicit expected AP name; otherwise read hub MAC over USB | - |
| `--test-wifi-interface` | - | Adapter name on Linux/macOS, description on Windows | All adapters |
| `--test-wifi-scan-command` | - | Custom scan command as a JSON argument array | Automatic platform backend |
| `--test-rf` | - | Auto-detect the RF tester port by plugging the tester in first | `false` |
| `--test-rf-port` | - | Explicit serial port of the separate CaiXianlin RF monitor | - |
| `--test-timeout` | - | Timeout in seconds per test operation | `60` |
| `--factory-reset-after-test` | - | Send `factoryreset` after completed tests, whether they pass or fail | `false` |

At least one of `--test-wifi`, `--test-rf`, or `--test-rf-port` is required.

## Automated WiFi and RF testing

Enable either test independently, or both together. Green success and the
completion alert require all enabled tests to pass. In continuous mode, a failed
hub is reported and the tester continues waiting for the next hub.

### WiFi AP testing

The WiFi test uses the **host computer's WiFi adapter** to confirm that the hub
broadcasts `OpenShock-XX:XX:XX:XX:XX:XX`. Enable it with `--test-wifi`.
The tester reads the hub's base/STA MAC over USB using esptool, restarts the hub,
and scans for that exact SSID. A different nearby OpenShock hub cannot pass the
check. This leaves the hub's saved WiFi configuration unchanged and requires no
network credentials or association with the AP.

The scanner automatically chooses a backend. Platform-specific Python dependencies
are installed with Auto-Tester:

| Platform | Backend | Requirements |
|----------|---------|--------------|
| Linux with `nmcli` and `busctl` | NetworkManager | Running NetworkManager, enabled WiFi adapter, permission to scan |
| Other Linux setups | `pywifi` | Running wpa_supplicant and access to its control socket |
| Windows | `pywifi`, with `comtypes` | WLAN AutoConfig service, enabled WiFi adapter, Location access where required |
| macOS | `pyobjc-framework-CoreWLAN` | Enabled WiFi adapter and Location Services permission for the terminal/Python app |

Select an adapter with `--test-wifi-interface wlan0` on Linux, `en0` on macOS,
or the adapter's description on Windows. Each backend requests a scan. NetworkManager
results must have a fresh `LastSeen`; the pywifi backends check wpa_supplicant BSS
age or Windows beacon timestamps because pywifi's ordinary result objects omit
freshness information. CoreWLAN uses a directed scan rather than its cached-results API.
Library scans run in a separate process so `--test-timeout` can stop a blocked call.

The hub must be in a state where its setup AP is enabled; saved configuration or
a backend connection may cause firmware to turn it off. A WiFi connection to the
hub is not required, and the scanner does not disconnect the host's existing network.

For an explicit AP name (or firmware with a customized MAC), use
`--test-wifi --test-wifi-ssid OpenShock-AA:BB:CC:DD:EE:FF`. This skips the USB MAC
read and its reboot. The SSID must be the specific hub's complete AP name.

To override the backend on any platform, supply your own scanner using
`--test-wifi-scan-command '["python", "scan_wifi.py"]'`. The command runs on the
host without a shell and must perform a **fresh WiFi scan**, exit successfully,
and print a JSON array of SSIDs, for example `["OpenShock-AA:BB:CC:DD:EE:FF"]`.
The adapter and any OS permissions are the custom scanner's responsibility;
returning cached network names can produce incorrect results. Malformed output,
command failure, and timeout fail the check. No scan command is needed for the
built-in scanners. `scan_wifi.py` is a user-provided script, not a bundled file.

API references: [pywifi](https://github.com/awkman/pywifi),
[CoreWLAN scans](<https://developer.apple.com/documentation/corewlan/cwinterface/scanfornetworks(withname:)>),
and [Windows WiFi location permissions](https://learn.microsoft.com/en-us/windows/win32/nativewifi/wi-fi-access-location-changes).

### RF tester setup

The tester is a **separate USB device** running
[CaiXianlinRemoteIDMonitor](https://github.com/NanashiTheNameless/CaiXianlinRemoteIDMonitor).
Prepare it separately:

1. Get the monitor sketch from the
   [monitor repository and setup instructions](https://github.com/NanashiTheNameless/CaiXianlinRemoteIDMonitor#usage).
   Use the updated receiver decoder with the signed buffer-index fix.
2. Connect a 433 MHz receiver to the tester. Match its signal wire to `rx_pin` in
   [CaiXianlinRemoteIDMonitor.ino](https://github.com/NanashiTheNameless/CaiXianlinRemoteIDMonitor/blob/main/CaiXianlinRemoteIDMonitor.ino);
   check the sketch's value instead of assuming a fixed pin number.
3. Upload that sketch to the tester using your board's Arduino workflow.
   Its serial output must use 115200 baud and the standard format, for example:

   ```text
   ID: 0x2E16 (11798) | Channel: 1 | Mode: Beep
   ```

4. Close the tester's serial monitor before running Auto-Tester so it can read
   the tester port. Keep the tester connected during the hub tests.
5. Connect the hub's RF transmitter to its configured transmit pin. Custom pins
   must already be configured on the hub (for example with Auto-Flasher's
   `--post-flash "rftxpin 15"`).

### RF command validation

The RF test sends three CaiXianlin commands, each with a different randomly
selected nonzero ID:

| Command | Intensity sent | Duration | Expected monitor mode |
|---------|----------------|----------|-----------------------|
| Beep | 0 | 1 second | `Beep` |
| Vibrate | 1 | 1 second | `Vibrate` |
| Stop | 0 | 300 milliseconds | `Stop` |

Every command must match its own ID, displayed channel 1, and expected mode.
Each has a separate pass/fail line, and remaining commands are attempted even if
an earlier command fails. The test discards old serial data and waits for each
burst and the monitor's debounce interval before sending the next command.
The tester is read asynchronously starting before transmission, capturing immediate
broadcasts even while the hub's serial acknowledgement is pending.
A transmit acknowledgement alone does not pass the test. No paired collar is
needed. The monitor's current output verifies ID/channel/mode, but does not expose
numeric intensity or measure RF power/range. Light and Shock are not transmitted.
Firmware emergency-stop rejection fails the test normally.

Add `--factory-reset-after-test` to send the hub's `factoryreset` serial command
once all enabled tests have finished, whether they pass or fail. This clears saved
hub settings and restarts the hub. The tester requires the firmware's reset/restart
messages and a serial response after reboot before reporting reset success. Test
failures remain failures even if reset succeeds; reset failure also fails the run.
It is off by default and is not run when the run is interrupted.

### Connect and run

Use `--test-rf` to select the tester port automatically:

1. Start Auto-Tester with the hubs disconnected.
2. Plug in the RF tester first. It can also already be connected if it is the only
   serial device present. Wait for `RF tester detected ...; reserved for testing.`
3. Leave the tester connected and plug in hubs to test.

Selection uses connection order. If multiple serial ports are already present or
arrive together, Auto-Tester waits for you to unplug and reconnect only the tester.
With `--port`, the specified hub port is excluded from tester selection.
Alternatively, use `--test-rf-port PORT` to select the tester explicitly; this
cannot be combined with `--test-rf`.

The selected tester is never tested as a hub. If an automatically selected tester
has a unique USB serial number, Auto-Tester follows it when it reconnects on a new
port. Without a USB serial number, keep its port stable or restart Auto-Tester to
select it again. Close other serial terminals during testing. For explicit selection
on Linux, a `/dev/serial/by-id/...` path is useful for keeping its identity stable.
The hub must return on the supplied port after reboot.

Test each newly connected hub, with an audible alert and factory reset:

```bash
OPSH-AutoTest --board Wemos-D1-Mini-ESP32 --alert \
  --test-wifi --test-rf --factory-reset-after-test
```

Test one hub with explicit ports. In this example, `/dev/ttyUSB0` is the tester
and `/dev/ttyUSB1` is the hub; replace them with your actual ports:

```bash
OPSH-AutoTest --port /dev/ttyUSB1 --test-wifi --test-rf-port /dev/ttyUSB0
```

Retest only RF, or only the WiFi AP:

```bash
OPSH-AutoTest --test-rf

OPSH-AutoTest --test-wifi
```

On Windows, use port names such as `COM3` and `COM4`. Single-hub runs exit with
**0** on success, **1** on test failure, and **2** for invalid arguments.

Test results appear in the terminal, including pass/fail and failure details for
each enabled check. RF progress distinguishes the hub acknowledgement from waiting
for the tester, with updates every five seconds and separate errors for a silent
tester, unrecognized serial output, or mismatched frames. Reception timeouts with
unrecognized output show the tester's first 256 bytes; up to five
unrecognized lines per case are also printed as they arrive. Control characters
are escaped to keep boot/error messages and garbled data readable. RF acknowledgement
waits at most five seconds. `--test-timeout` bounds individual connection, response,
and reception operations; USB MAC detection and device startup are additional to the
WiFi scan timeout.

The RF check uses OpenShock's automated `$sysinfo` and `$rftransmit` serial commands
and `$SYS$` responses. Optional factory reset sends `$factoryreset` and checks its
plain-text reset/restart messages. Firmware that lacks these commands or has serial input
disabled fails the RF test instead of being assumed functional.

## Session report

By default, one `OpenShock-session-<timestamp>-<id>.html` file is created in the
current directory for each session. The terminal prints its absolute path. Choose
a path with `--report batch.html`, or disable reporting with `--no-report`.
An existing report file is never overwritten by a new session; choose a new name.

Each hub connection attempt gets a record containing:

- Port, board label, MAC address and its source, expected AP name, and USB metadata.
- USB adapter serial number when available. This is not a separate ESP32 serial
  number; the MAC identifies the chip. Missing identity fields say `Unavailable`.
- WiFi AP, RF, and factory-reset results with durations and failure details.
- Every attempted RF command's ID, channel, mode, intensity, duration, and result.
- Start/end times in UTC, elapsed time, overall outcome, warnings, and errors.

The WiFi test supplies the MAC it reads from the hub. Runs without that MAC read
(RF only, or an explicit `--test-wifi-ssid`) attempt a separate USB identity read,
which restarts the hub; failure to read identity is recorded as a warning and does
not invent a MAC or serial number.

The same file is updated atomically as each test finishes. Completed records
survive later failures or Ctrl+C. Pressing Ctrl+C while waiting for another hub
ends the session as `completed`, preserving each hub's pass or fail result.
Stopping during a test marks that hub and the session as `interrupted`.
A forced process kill can leave its last saved state as `in_progress`.
Reconnecting the same hub creates another attempt, preserving its earlier result.
The RF tester is not included as a hub. Disabled or unattempted tests are never
counted as passes.

The HTML uses a dark theme with color-coded status labels. It is self-contained
and can be opened locally without network access.

## How It Works

Terminal backgrounds indicate status: blue means waiting, yellow means testing,
green means success, and red means an error.

1. **Reserves** the RF tester port (auto-detected or explicit), if RF testing is enabled
2. **Initializes** known USB ports and begins monitoring
3. **Detects** when new hubs are connected
4. **Reads** the hub MAC over USB with esptool (for the expected AP name and report)
5. **Tests** WiFi and/or RF and displays results
6. **Optionally factory-resets** the hub (`--factory-reset-after-test`)
7. **Repeats** for additional hubs (continuous mode), or exits for `--port`

## Permissions (Linux)

On Linux, you may need to add your user to the `dialout` group to access serial ports:

```bash
sudo usermod -a -G dialout $USER
```

Then log out and log back in for the changes to take effect.

## Troubleshooting

**Hub not detected:**

- Start Auto-Tester before plugging in hubs; only newly connected ports are tested
- Check USB cable connection and that it supports data transfer (not charge-only)
- Verify the hub appears in the system (check `dmesg` on Linux or Device Manager on Windows)

**Permission errors:**

- Add user to dialout/uucp group (Linux)
- Close other serial monitors using the hub or tester port

**WiFi AP not found:**

- Confirm the hub's setup AP is enabled (no saved WiFi network it connects to)
- Check WiFi scanning permissions for your platform (see [WiFi AP testing](#wifi-ap-testing))
- Try `--test-wifi-interface` to select the right adapter

**RF commands not received:**

- Confirm the tester prints frames at 115200 baud when a remote is used nearby
- Check the hub's RF transmit pin configuration and the transmitter wiring

## Development

### Running Tests

1. Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

2. Run the test suite:

```bash
pytest tests/ -v
```

3. Run tests with coverage:

```bash
pytest tests/ -v --cov=openshock_autotester --cov-report=term-missing
```

### Code Quality

```bash
# Format code
black openshock_autotester/ tests/

# Lint code
flake8 openshock_autotester/ tests/

# Type check
mypy openshock_autotester/
```

### Project Structure

- `openshock_autotester/` - Main package
  - `constants.py` - Polling constants
  - `styles.py` - Terminal styling and colors
  - `tester.py` - Core AutoTester class: port detection, RF tester reservation, test runs
  - `hardware_tests.py` - WiFi/RF test orchestration and serial checks
  - `wifi.py` - Host WiFi scanning and hub AP identification
  - `wifi_native.py` - Native WiFi library scanning in a bounded subprocess
  - `report.py` - One HTML report for all hubs in a session
  - `cli.py` - Command-line interface and argument parsing
  - `__init__.py` - Package initialization
  - `__main__.py` - Module entry point
- `tests/` - Test suite
  - `test_constants.py` - Tests for constants module
  - `test_styles.py` - Tests for styles module
  - `test_tester.py` - Tests for tester module
  - `test_cli.py` - Tests for CLI module
  - `test_hardware_tests.py` - Serial protocol and hardware-test regressions
  - `test_wifi.py` - Host WiFi scanner tests
  - `test_wifi_native.py` - Native WiFi scanner tests
  - `test_report.py` - Session report and hub recording tests

### Continuous Integration

The project uses GitHub Actions for CI/CD:

- **Tests Workflow** - Runs tests on Ubuntu, Windows, and macOS with Python 3.12-3.15
- **Publish Workflow** - Publishes to PyPI on release

[Back to the main README](https://github.com/NanashiTheNameless/OpenShock-AutoTester/blob/main/README.md).
