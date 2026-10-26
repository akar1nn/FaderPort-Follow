# Architecture and protocol

## Layers

- `protocol.py` encodes and decodes MIDI messages and defines native button identifiers. It has no Live dependency.
- `live_api.py` accesses Live objects and manages views, track navigation, parameter gestures, and listener lifecycles.
- `controller.py` handles modes, touch state, fader protection, transport repeat, lights, and motor rate limiting.
- `volume_curve.py` converts between panel position and Live parameter values using read-only value discovery.
- `monotone.py` implements monotone cubic Hermite interpolation and numerical inversion without dependencies.
- `calibration_profile.py` stores editable nodes from the offline regression.
- `surface.py` adapts `ableton.v2.control_surface.ControlSurface` and forwards MIDI messages in order.
- `settings.py` configures logging, encoder format, fine adjustment, and feedback timing.

Live loads the script through `create_instance(c_instance)`. The script leaves Live's built-in files alone and sends no keyboard or mouse input.

## Native messages

The fader sends channel 0 `E0 ll hh` 14-bit messages. Buttons send `90 id 7F` on press and `90 id 00` or `80 id xx` on release. Note `68` reports fader touch, and note `66` is the footswitch.

The tested FP2 encoder sends CC `10`; the script also accepts the documented CC `3C`. Values `01`, `41`, and `42` mean one positive step, one negative step, and two negative steps. Output uses `90 id 00/7F/01` for off/on/flash and `91/92/93 id level` for RGB levels.

On startup and reconnection, the script sends the tested CC pair `B0 00 06`, `B0 20 27`, then keepalive, lights, and fader position. Testing validated the sequence as a whole and did not isolate a single motor-unlock message.

## State and safety

The fader always controls the selected track's `mixer_device.volume`. Touch pauses motor feedback and begins an automation gesture. If the user changes tracks while touching the fader, the script ends the old gesture, ignores fader movement until release, then synchronizes the new track.

Live's `update_display` clock drives transport repeat. On reconnection, the script clears Shift and repeat state, ends stale gestures, and waits for a touch release before accepting fader input.

In Session view, Record toggles `song.session_record`. In Arrangement view, it toggles `song.record_mode`. The script avoids `trigger_session_record()`, which moved to the next empty slot in testing.

## Tools

`midi_probe.py` lists Windows WinMM ports and captures input without sending MIDI or motor output. `build.py` uses an explicit file allowlist to create a reproducible ZIP and SHA-256 file.
