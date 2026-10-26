# FaderPort Follow

FaderPort Follow is an independent native MIDI Control Surface script for the PreSonus FaderPort V2/2018 single-fader controller and Ableton Live 12. Volume, pan, Arm, Mute, and Solo follow Live's selected track without switching eight-track banks.

Version 1.0.0 supports the behavior validated on Windows 11 with Ableton Live 12.4.7 and a PreSonus FaderPort V2/2018 in Studio One native mode. The footswitch, macOS, other Live versions, and other firmware versions remain untested. See [validation](docs/VALIDATION.md) for the test scope.

PreSonus and Ableton are not affiliated with FaderPort Follow.

## Windows installation

1. Quit Live and extract the release ZIP.
2. Power off the FaderPort. Hold **NEXT** while powering it on, then press **Solo** to select Studio One native mode.
3. Open PowerShell in the extracted directory and run:

   ~~~powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
   ~~~

   The installer reads Live 12's Library.cfg. You can pass the library path explicitly:

   ~~~powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -UserLibrary 'D:\My Ableton Library'
   ~~~

4. In Live, open Settings > Tempo & MIDI. Select **FaderPort Follow** in one Control Surface row and select the matching FaderPort input and output ports.
5. Do not configure another FaderPort or Mackie Control surface on the same ports. Track, Sync, and Remote are not required for those ports.

Live bundles Python for the script. Installation requires no separate Python setup, pip packages, background service, or virtual MIDI bridge.

## Controls

| Control | Behavior |
| --- | --- |
| Fader | Selected-track volume with motor feedback |
| Arm / Mute / Solo | Selected-track state; Arm and Solo follow Live's exclusive preferences |
| Channel | Select tracks; press to focus the current main view |
| Prev / Next | Navigate visible tracks, Returns, and Master without wrapping |
| Pan | Adjust selected-track pan; press to center |
| Master | Select Master; press again to return to the previous track |
| Play / Stop | Live-native transport behavior |
| Record | Arrangement Record or Session Record according to the focused main view |
| Loop / Click | Arrangement loop / metronome |
| Rewind / Forward | Move by one bar; hold to repeat; press both to return to zero |
| Write | Automation Arm |
| Read | Re-enable automation |
| Touch | Toggle Draw Mode |
| Scroll | Native Arrangement cursor navigation |
| Section | Move between locator markers |
| Marker | Add or remove a locator at the current position |
| Link | Adjust the selected Live parameter; press to reset it |
| Bypass | Toggle the selected device |
| Footswitch | Toggles transport like Play (not tested) |

Use the controller's physical Shift key for Shift combinations. Shift+Scroll selects horizontal zoom mode. Scroll moves the Arrangement cursor; independent viewport scrolling is not available.

## Calibration and safety

The default volume mapping uses the measured monotone calibration profile. Input above Live's +6 dB maximum is clamped and released to the +6 dB position. Set FADER_CALIBRATION = () and FADER_PANEL_UPPER_MARK = None to restore the uncalibrated mapping.

Touching the fader pauses motor feedback. A track change during a touch ends the old gesture and ignores fader input until release. The default input guard accepts fader movement only after a touch signal.

## Uninstall and diagnostics

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Uninstall.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\Uninstall.ps1 -RestorePrevious
~~~

For local diagnostics only:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -DebugMidi
~~~

Return DEBUG_MIDI to False after diagnosis. Do not publish Live logs, temporary projects, or raw MIDI captures.

## Development

~~~powershell
python -m unittest discover -v
python tools/verify.py
python tools/build.py
~~~

Live supplies the runtime dependency. The validation, architecture, and curve fitting documents cover implementation details and known limits.

## License

GNU GPL-3.0-or-later. See [LICENSE](LICENSE).
