# Public-source validation

Prepared on **28 October 2026**, separately from the original development workspace.

## Checks performed on the public copy

- **81 Studio Python tests passed** with Python 3.12.14 and Pillow 12.3.0. HID devices, account data and settings changes in these tests use fakes or temporary files. API tests use local loopback sockets.
- The launcher's shell syntax and command-line help were checked. The personal Python runtime path was replaced with a checkout-local virtual environment / current interpreter.
- The pinned Pillow and hidapi dependency versions were verified as downloadable for the tested Python/macOS architecture. Native dependency binaries are not committed.
- **20 firmware source files matched** the recorded studio-v3.2 source hashes. The Studio patch applied to its pinned upstream baseline and produced the same files. All six required ChibiOS patches applied to their pinned baseline.
- Portable C tests passed with AddressSanitizer and UndefinedBehaviorSanitizer: **106,755 menu assertions**, **121 bridge checks**, **2,617 raster checks**, and **101 idle checks**.
- Publication used an explicit source allowlist. Runtime state, account snapshots, status-line backups, transcripts, user uploads, vendor installers, stock firmware dumps, build binaries and flashing executables were excluded. Text files were scanned for personal machine paths and common credential/key patterns; source and fixture occurrences were reviewed.
- Original license notices were retained. Full relevant font/icon license texts and upstream references are included.

## What these checks do not establish

No keyboard was flashed or controlled during publication preparation. No live provider account was queried to refresh the historical feature status. A new full ARM firmware build was not performed in this publication pass. Passing fake-device and portable C tests does not prove physical LCD, radio, RGB or flash behavior on another keyboard revision.

The historical studio-v3.2 build was flashed on one unit on **11 October 2026**. Its recorded SHA-256 was `849f3cf0d5e17b504d1d7287c2268c800ba107be91fd3942d9ece0bc48cd850e`, with checksum16 `0xd04d`, successful loader exit and subsequent live bridge acknowledgement. Those records establish the earlier device event; they do not mean a newly rebuilt binary is byte-identical.

QMK image/GIF uploading remains disabled and desktop QMK RGB control remains unavailable. The README describes these limitations explicitly. Renderer previews are illustrative test fixtures, not live screenshots of an account or the physical keyboard.

The GitHub Actions workflow repeats the Studio and portable firmware tests. Its results are shown in the repository's Actions page separately from the local checks above.
