# Project guide

FaderPort Follow 1.0.0 is a native MIDI Control Surface for the PreSonus FaderPort V2/2018 single-fader controller and Ableton Live 12.

## Maintenance

Keep the controls bound to Live's selected track. Preserve touch protection, gesture cleanup on track changes, direct Session Record toggling, and the calibrated monotone volume curve.

The runtime uses Live's bundled ableton.v2 package and Python's standard library. It needs no external service.

See VALIDATION.md for test coverage and limits, ARCHITECTURE.md for the implementation, and CURVE_FIT.md for calibration settings.

## Checks

    python tools/verify.py
    python tools/build.py

The verification command runs the automated suite and writes docs/validation-results.json. It does not test physical hardware.

The build command creates the release ZIP, its MANIFEST.json, and a SHA-256 file. Documentation is selected from an explicit list in tools/build.py.

## Publication

Publish only the final release snapshot and its ZIP and checksum. Keep local notes, logs, measurement records, temporary projects, and older builds out of the repository and release assets.

Public text is English. Review both the Git file list and the ZIP before publishing. The license is GPL-3.0-or-later.
