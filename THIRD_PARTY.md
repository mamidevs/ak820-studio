# Third-party notices

Original file-level copyright and SPDX notices are preserved. The root GPL-3.0-or-later grant applies to project-authored source, not as a replacement for third-party licenses.

## Firmware and assets

The firmware is an overlay for [fpb/qmk_firmware](https://github.com/fpb/qmk_firmware) at the exact revision recorded in [`firmware/upstream.json`](firmware/upstream.json). Modified keyboard sources carry their original GPL-2.0-or-later notices. Local Studio display components carry GPL-2.0-or-later or GPL-3.0-or-later notices as stated in their files. The GPLv3 distribution of the combined project retains those grants.

The font and raster icon assets have separate attribution and license texts in [`firmware/THIRD_PARTY.md`](firmware/THIRD_PARTY.md) and [`firmware/licenses/`](firmware/licenses/): Open Sans, Material Design Icons, Nerd Fonts and JetBrains Mono. Asset origin and transformations are recorded in `firmware/asset-provenance.json`.

QMK's upstream dependencies, including ChibiOS and its platform patches, are fetched separately during a firmware build. Their own licenses continue to apply. This repository does not redistribute the full toolchain, upstream source checkout, prebuilt firmware or flash-loader binaries.

## Host dependencies

Dependencies are installed from their upstream distributions rather than vendored as native binaries:

| Dependency | Source / license |
| --- | --- |
| Pillow | [python-pillow/Pillow](https://github.com/python-pillow/Pillow), HPND/PIL license with additional bundled-component notices in its distribution. |
| hidapi Python package | [trezor/cython-hidapi](https://github.com/trezor/cython-hidapi), package BSD license; underlying HIDAPI is available under its published BSD/GPLv3/original HIDAPI license alternatives. Consult the installed distribution's license files. |

Codex and Claude Code are separately installed applications, not bundled dependencies. Their names identify supported integrations. Authentication stays with the user's own installations.

## Excluded materials

AJAZZ installer executables, proprietary stock firmware images, extracted vendor binaries, firmware dumps, personal account data, transcripts, uploaded user images, local configuration backups and native extension binaries are not part of this public source distribution.
