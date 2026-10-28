# AK820 Studio firmware source

This is the **studio-v3.2** source snapshot for the AJAZZ AK820 Pro, built on [fpb/qmk_firmware](https://github.com/fpb/qmk_firmware) at commit `8777e05bd03182565052850fab2afd1d34de1e77`. It contains the 20 changed/added source files and a patch against that exact upstream revision. It is not a complete QMK checkout.

The source was used for a firmware image tested on one keyboard on 11 October 2026. The publication audit on 28 October 2026 matched all 20 files to the recorded source hashes and reran the CPU tests. **No firmware binary, stock firmware, device dump or flasher executable is distributed here.**

## Features and current limits

- A 128×128 color LCD interface with two home faces, quota rings/bars, clock, battery/charging, connection state and an icon menu.
- Codex and Claude Code usage snapshots received from the companion Studio over USB Raw HID. Missing windows remain unknown; old data is marked stale. Bluetooth/2.4 GHz alone do not carry these Studio packets.
- Fn + knob opens the menu. Knob modes include volume, media, display brightness keys, RGB brightness and zoom shortcuts.
- On-device RGB controls use the keyboard's existing QMK handlers. The companion's QMK RGB sender is **not implemented**; its controls remain disabled.
- Screen power, sleep duration, connection selection and macOS/Windows layout controls. Some settings are session-only; the existing debounced RGB persistence remains in the upstream keyboard implementation.
- Experimental media playback support exists in the source. **QMK image/GIF upload remains disabled in Studio and has not been validated on hardware.** The external-flash upload region and media protocol must not be described as a tested release feature.

The on-screen connection switching/pairing, host brightness/zoom behavior across operating systems, and exact LCD performance on other hardware revisions still need hardware validation. Compilation and CPU tests do not establish compatibility with another keyboard or panel revision.

## Source map

| Path | Purpose |
|---|---|
| `overlay/keyboards/a_jazz/ak820pro/` | Exact changed/added v3.2 firmware sources |
| `patches/studio-v3.2.patch` | Applies those changes to the pinned QMK revision |
| `patches/*.diff` | Six upstream ChibiOS-Contrib patches required by this keyboard |
| `source-manifest.json` | Source hashes and original image identifier |
| `upstream.json` | QMK/submodule revisions, patch order and tested toolchain |
| `tests/` | Host CPU tests with no USB/device access |
| `tools/simulator.py` | Interactive simulator using the actual C renderer |
| `tools/make_previews.py` | Rebuilds preview PNGs from fictional host fixtures |
| `tools/generate_assets.py` | Optional font/icon raster generation; source fonts supplied separately |
| `licenses/`, `THIRD_PARTY.md` | Preserved upstream licensing and asset attribution |

The overlay and patch are alternatives: apply the patch **once**; do not also copy the overlay over it.

## CPU tests and screen simulator

Requirements: Python 3, a C99 compiler (Clang was used for the publication checks), and Make. AddressSanitizer and UndefinedBehaviorSanitizer must be available for the default tests. Pillow is only needed to regenerate PNG previews.

From the repository root:

```sh
make -C firmware/tests test
make -C firmware/tests clean
python3 firmware/tools/simulator.py
```

The simulator opens a service at `http://127.0.0.1:8770`; open that address in your browser. It does not connect to a keyboard or send host media keys. All displayed usage percentages and device states are fictional fixtures. The controls are described in its UI.

To regenerate the preview gallery after installing Pillow into your chosen Python environment:

```sh
python3 firmware/tools/make_previews.py
```

![Example screens rendered from fictional fixtures](previews/overview.png)

## Building QMK

Use a separate clean checkout. Install the normal QMK build prerequisites and an Arm GCC toolchain first. The recorded local build used **Arm GNU Toolchain 13.2.Rel1 / GCC 13.2.1**. The commands below select the same upstream source and patch order; the publication audit verified their patches against clean pinned source, but did not download/rebuild the complete ARM toolchain.

Run from the root of this repository:

```sh
AK820_STUDIO_ROOT="$PWD"
git clone https://github.com/fpb/qmk_firmware.git qmk-build
git -C qmk-build checkout --detach 8777e05bd03182565052850fab2afd1d34de1e77
git -C qmk-build submodule update --init --recursive
git -C qmk-build apply --check "$AK820_STUDIO_ROOT/firmware/patches/studio-v3.2.patch"
git -C qmk-build apply "$AK820_STUDIO_ROOT/firmware/patches/studio-v3.2.patch"

for patch in hardware_pwm i2c_fallback rtc_lld spi_fifo_pump spi_flash_dma efl_ramtext
do
  git -C qmk-build/lib/chibios-contrib apply --check "$AK820_STUDIO_ROOT/firmware/patches/$patch.diff" || exit 1
  git -C qmk-build/lib/chibios-contrib apply "$AK820_STUDIO_ROOT/firmware/patches/$patch.diff" || exit 1
done

make -C qmk-build a_jazz/ak820pro:studio DASHBOARD_BACKEND=qp LCD_PANEL=v1 SKIP_GIT=yes -j4
```

The critical submodules are `lib/chibios` at `8bd61b804303f1614d574546c2dd735eeabb09f5` and `lib/chibios-contrib` at `5bed8690c4434309e3ab3e14348e70e588eb192f`. All recorded submodule pins are in `upstream.json`. Updating submodules after applying the patches can discard their working-tree changes.

The tested unit used `LCD_PANEL=v1`. Upstream documents another panel orientation/inversion variant selected by `LCD_PANEL=v2`. A successful build is not sufficient to choose the right panel for a different unit.

## Updating a keyboard

There is no automatic flashing in this repository. The historical development setup used a reviewed, hash-locked Sonix loader wrapper tied to a specific complete 256 KiB image; those machine-specific wrappers and executables are deliberately excluded.

On the tested custom firmware, **Fn + Esc** enters the bootloader. Finish any active transfer, stop Studio, enter that mode, and verify the expected USB identity before using a separately obtained, compatible loader:

| Mode | Tested USB identity |
|---|---|
| Custom QMK application | `0c45:8009`, release `0100` |
| Sonix bootloader | `0c45:7140` |

On macOS, `system_profiler SPUSBDataType` can be used for a read-only USB inventory. Verify exactly one intended bootloader device. A complete update requires a successful loader checksum/verification result, a zero exit status, and return to the normal QMK USB identity. Then check ordinary typing, knob/menu operation and the Studio handshake.

Boot pads are a recovery option, not the normal Fn + Esc update flow. A stock firmware image matching every hardware revision was **not** established during this project; this repository does not promise a stock rollback image. Keep a separately verified working custom image and its matching loader/checksum record before changing a physical keyboard.

## Validation recorded for publication

On 28 October 2026, the source and clean-patch checks passed, followed by:

- Menu/navigation: 9 suites, 106,755 assertions.
- Studio bridge: 121 checks.
- Raster: 2,617 checks.
- Idle/redraw behavior: 101 checks.
- AddressSanitizer/UndefinedBehaviorSanitizer: no reported errors.

See `validation.json`. These are CPU-only tests; no USB device was accessed and no firmware was flashed as part of publication.
