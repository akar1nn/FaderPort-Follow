# FaderPort Follow 1.0.0

This release provides a native MIDI Control Surface for the PreSonus FaderPort V2/2018 single-fader controller and Ableton Live 12.

Volume, pan, Arm, Mute, and Solo follow the selected track. Other controls cover transport, recording, automation, devices, parameters, markers, views, and horizontal zoom. Touch protection pauses motor feedback and prevents a track change during touch from writing to the new track.

## Installation

Use Studio One native mode on the controller. Extract FaderPort_Follow-1.0.0.zip and follow README.md. Verify the archive against FaderPort_Follow-1.0.0.zip.sha256.

## Validation and limits

The automated suite passes 73 tests. Hardware coverage is Windows 11, Ableton Live 12.4.7, and FaderPort V2/2018 in Studio One native mode.

Scroll moves the Arrangement cursor. Pure viewport scrolling is unavailable. Footswitch, macOS, other Live versions, and other firmware versions are untested. See VALIDATION.md for details.

## License

GPL-3.0-or-later. See LICENSE.
