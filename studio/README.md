# AK820 Studio

Local Turkish control panel for the AJAZZ AK820 Pro. The host application was developed and tested on macOS with Python 3.12. Windows is not supported by this version: the device transport uses POSIX process and file locks. Other operating systems and keyboard revisions have not been validated.

## Install and open

From this `studio` directory, create an isolated Python environment and install the dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python start.py
```

Use Python 3.12 or newer. After setup, macOS users can double-click `AK820 Studio.command`. `start.py` uses this directory's `.venv` when it exists, or the Python interpreter that launched it. No machine-specific runtime or bundled native library is required.

The panel opens at <http://127.0.0.1:8765>. It listens only on the local machine. To stop it after an active transfer finishes:

```sh
.venv/bin/python stop.py
```

The service is started locally and does not install a login item or system daemon. State, uploads, previews, configuration and logs are created under `work/`; these are intentionally excluded from the public repository. Run only one Studio instance against a keyboard at a time.

## Device support and limits

The app checks exact USB identities and report descriptors before writing:

- Stock firmware: `0c45:8009`, SONiX / AK820, revision `0114`, with the expected control and data interfaces. Still-image transfer and RGB changes were observed on the original test unit. GIF playback was not separately confirmed.
- Custom Studio QMK firmware: `0c45:8009`, AJAZZ / AK820 PRO, revision `0100`, with a compatible Studio bridge. Battery, connection route, screen state, sleep duration and AI quota forwarding use that bridge. See the repository's firmware documentation for the matching source and hardware validation limits.

**QMK image/GIF upload remains disabled.** Its external-flash transfer code is included for development and tests, but has not been validated on hardware. Do not interpret a preview or unit test as proof of a physical transfer. QMK RGB control from the host is also unavailable: its adapter reports that limitation without sending a packet. RGB is controlled through the firmware's on-screen Işık page and knob.

The app's stock image and RGB packets must not be sent to custom QMK firmware. Screen and sleep settings in the Studio bridge are temporary runtime settings. The app distinguishes missing values, stale quota snapshots, protocol acknowledgements and physical visual confirmation.

## AI connections

The **Bağlantılar** page controls forwarding for Codex and Claude Code. Disconnecting stops Studio's data forwarding; it does not sign the user out.

- Codex uses a locally installed and already authenticated CLI's `app-server` usage metadata endpoint. It searches `PATH`, `~/.local/bin/codex`, and the standard macOS Codex app bundle. Studio does not create a model turn or change the account.
- Claude Code uses an explicit status-line integration. Setup backs up the previous status-line field, installs a local receiver and then executes the previous command with its input preserved. Setup may edit `~/.claude/settings.json`, or `settings.json` under `CLAUDE_CONFIG_DIR`. Quota availability depends on what the existing Claude session exports; a running receiver alone does not establish that usable quota data is available. Do not move this checkout after installing the receiver without setting the integration up again.

With Studio running, the same actions are available from this directory:

```sh
.venv/bin/python connect.py all status
.venv/bin/python connect.py codex connect
.venv/bin/python connect.py codex refresh
.venv/bin/python connect.py codex disconnect
.venv/bin/python connect.py claude_code setup
.venv/bin/python connect.py claude_code connect
.venv/bin/python connect.py claude_code refresh
.venv/bin/python connect.py claude_code disconnect
```

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The tests use fake HID devices and temporary state. They do not flash firmware, send commands to the physical keyboard, query real AI accounts, or change the user's Claude settings. A local loopback socket is used by the API tests. Synthetic image fixtures and the generated color test image are included; private images and live quota snapshots are not.

For a separate local UI preview without USB operations:

```sh
.venv/bin/python start.py --simulate connected --port 8771
```

Simulation state is stored separately under `work/test-connected`. This preview is not a hardware verification. `stop.py` only stops the normal service; stop a preview server using its recorded PID after checking it belongs to that preview instance.
