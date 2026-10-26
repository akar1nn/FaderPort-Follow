# Validation

## Automated tests

The current release passes 73 automated tests. See validation-results.json for the run date, Python version, platform, and result.

The suite checks MIDI decoding, selected-track binding, touch protection, feedback, transport, recording, device and parameter control, volume mapping, installation, and distribution contents. Tests use simulated Live objects and temporary installation directories.

## Hardware coverage

The behavior shipped in this release was validated on Windows 11 with Ableton Live 12.4.7 and a PreSonus FaderPort V2/2018 in Studio One native MIDI mode.

Checks covered selected-track control, motor and light feedback, touch protection, transport, automation recording and playback, device and parameter control, USB reconnection, and switching Live Sets.

The release changes packaging, documentation, and version metadata without changing the validated controller behavior. No new hardware run was performed for those release changes.

## Limits

- Scroll moves the Arrangement cursor. Pure viewport scrolling is unavailable. Horizontal Zoom and mode restoration passed testing.
- The footswitch, macOS, other Live versions, and other firmware versions were not tested.
- The firmware version of the tested controller was not recorded.
- The volume calibration comes from one controller. No independent motor-accuracy test was performed.
- Play/Stop follows the Live behavior accepted during testing and does not always restore the paused playhead.

## Diagnostics

The release sets DEBUG_MIDI = False. To install a local diagnostic copy:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -DebugMidi

Turn diagnostic logging off after use. Keep Live logs and raw MIDI captures local.
