# FaderPort Follow maintainer notes

Read [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md), then the guide for the area you are changing. If `AGENTS.local.md` exists, read it for workstation-specific context. That file is ignored by Git and must stay local.

## Current baseline

- Product: FaderPort Follow; runtime package: `FaderPort_Follow`.
- Current release: `1.0.0`.
- Tested environment: Windows 11, Ableton Live 12.4.7, PreSonus FaderPort V2/2018 in Studio One native mode.
- See `docs/VALIDATION.md` for automated test results, hardware coverage, and known limits.
- Scroll currently moves the Arrangement cursor. Zoom works. Footswitch, macOS, other Live versions, and other firmware versions are untested.

## Behavioral constraints

- Bind directly to Live's selected track; do not restore eight-track bank addressing.
- Preserve touch protection, track-switch gesture cleanup, and motor feedback suspension while touched.
- Session Record must toggle `song.session_record` directly.
- Keep the accepted native Play/Stop behavior.
- Shift means the controller's physical Shift key.
- Keep the calibrated monotone volume curve and the +6 dB clamp.
- Do not add Windows UI injection for viewport scrolling.

## Runtime and testing

- The runtime uses Live's bundled `ableton.v2` and the Python standard library.
- Keep the runtime self-contained and free of proprietary dependencies.
- After relevant changes, run `python tools/verify.py`, the affected unittest modules, and `python tools/build.py`.

## Release rules

- The repository and release use GPL-3.0-or-later.
- All public human-readable content must be in English.
- Review evidence JSON for local paths before publishing.
- Review the staged file list and ZIP contents before each release.
- FaderPort Follow is an independent project and is not affiliated with PreSonus or Ableton.
