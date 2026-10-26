# Volume calibration

The default panel profile maps physical fader travel to Live volume. It uses monotone cubic interpolation, with the same curve and numerical inverse for input and motor feedback.

## Range

Below -60 dB, a smooth power tail reaches Live's native minimum. The mapping assumes no fixed silence threshold.

At +6 dB, the curve reaches approximately 88.4233% of fader travel. Input above that point is clamped. The motor pauses during touch and returns to the current parameter position on release.

The profile comes from one controller. Mechanical differences may affect where the motor lands.

## Settings

The editable profile is in FaderPort_Follow/calibration_profile.py.

- FADER_SMOOTH_CURVE selects monotone cubic interpolation. False selects piecewise linear interpolation.
- Set FADER_CALIBRATION = () and FADER_PANEL_UPPER_MARK = None together to restore the uncalibrated mapping.
- Live's str_for_value map is read-only. The script does not move a parameter to discover its scale.

## Fitting a profile

The optional offline tool accepts your own measurement file:

    python tools/fit_volume_curve.py --input measurements.json
    python tools/fit_volume_curve.py --input measurements.json --plot

The JSON needs a measurements array with panel_db and raw_14bit for each mark. It also needs ruler_measurements_mm entries with from_db, to_db, and distance_mm. The current model expects marks at -60, -50, -40, -30, -20, -10, -5, 0, +5, and +10 dB, plus ruler distances connecting them to "-inf". Each mark also needs physical_normalized if plots are requested.

Fitting writes a replacement calibration_profile.py and a local report under tmp/. Review the generated profile before installing it. Plotting requires Matplotlib; the installed Control Surface does not.
