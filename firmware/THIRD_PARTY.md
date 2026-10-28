# Third-party firmware and visual assets

Original copyright and SPDX notices are retained in the source files. The repository's top-level license applies to project-authored work subject to these existing component licenses; it does not replace them or claim ownership of upstream code, fonts, icons or trademarks.

## QMK and the AK820 Pro port

Source base: [fpb/qmk_firmware](https://github.com/fpb/qmk_firmware/tree/8777e05bd03182565052850fab2afd1d34de1e77), commit `8777e05bd03182565052850fab2afd1d34de1e77`. The AJAZZ port credits Fernando Birra and other upstream contributors. Modified source files retain their `GPL-2.0-or-later` notices. The upstream repository's complete GPL v2 text is preserved as [QMK-GPL-2.0.txt](licenses/QMK-GPL-2.0.txt).

The six ChibiOS-Contrib patches are copied unchanged from that upstream keyboard port. Their hashes and order are recorded in `upstream.json`. They target the pinned [SonixQMK/ChibiOS-Contrib](https://github.com/SonixQMK/ChibiOS-Contrib) revision, retain original notices, and must be used with the licensing of the corresponding upstream files. The full ChibiOS/QMK repositories and their dependency trees are fetched separately; this publication contains only the listed overlay and patches.

## Open Sans font raster data

`app_font.c` / `app_font.h` contain generated 4-bit-alpha raster glyphs from the historical Open Sans Semibold and ExtraBold fonts, copyright 2011 Google Corporation, under the Apache License 2.0. The fonts used during development were carried by the official keyboard driver package; no driver executable or font binary is included in this publication.

- License: [Apache-2.0.txt](licenses/Apache-2.0.txt).
- Source font hashes, sizes and glyph counts: `asset-provenance.json`.
- Transformation: selected glyphs are rasterized at the documented pixel sizes and quantized to 4-bit coverage by `tools/generate_assets.py`.
- Upstream font project: [googlefonts/opensans](https://github.com/googlefonts/opensans). The historical source-font hashes identify the exact inputs; newer font releases may have different hashes or licenses.

The complete generated glyph arrays are supplied, so building the firmware does not require fetching or installing the original fonts. Optional regeneration accepts a directory via `AK820_FONT_DIR`; obtain appropriately licensed inputs separately and preserve their notices.

## Material Design Icons and Nerd Fonts

`app_icons.c` / `app_icons.h` contain generated raster coverage for named [Material Design Icons](https://github.com/Templarian/MaterialDesign), by the Pictogrammers community. Icon names and codepoints are listed in `asset-provenance.json`. These icons were rasterized from an installed JetBrains Mono Nerd Font; the font itself is not distributed here.

- Material Design Icons licensing: [Material-Design-Icons-LICENSE.txt](licenses/Material-Design-Icons-LICENSE.txt), with the full [Apache 2.0 text](licenses/Apache-2.0.txt).
- Nerd Fonts notices and MIT / SIL OFL 1.1 terms: [Nerd-Fonts-LICENSE.txt](licenses/Nerd-Fonts-LICENSE.txt).
- JetBrains Mono, copyright 2020 The JetBrains Mono Project Authors: [JetBrains-Mono-OFL-1.1.txt](licenses/JetBrains-Mono-OFL-1.1.txt).
- Transformations: icon glyphs are cropped, scaled, centered, rasterized and quantized to 4-bit alpha by the generator. Names such as `CODEX` and `CLAUDE` are application mappings for generic console/star icons, not official product logos.

For optional regeneration, set `AK820_ICON_FONT` to a separately obtained, compatible font. Preserving the generated arrays avoids dependency on the original developer's local font installation. License source URLs and retrieved-text hashes are in `licenses/sources.json`.

## Preview images and branding

Preview PNGs use the included renderer and fictional host fixtures. They include the above licensed font/icon artwork and are not photographs or live account screenshots. AJAZZ, Codex, Claude, Apple, Windows and other product names remain the property of their respective owners; no endorsement or official affiliation is claimed.
