"""Editable settings. Restart/reload the control surface after changing these."""

from .calibration_profile import FITTED_MARKS, FITTED_UPPER_MARK

DEBUG_MIDI = False  # Raw RX/TX and errors go to Ableton's Preferences/Log.txt.
ENCODER_FORMAT = "signed_bit"  # Also: "twos_complement", "binary_offset".
ENCODER_INVERT = False
REQUIRE_FADER_TOUCH = True  # Prevent motor echoes from changing a parameter.
# Default FP2 panel calibration. See docs/CURVE_FIT.md.
# (physical travel 0..1, panel dB), ordered from bottom to top. The fit combines
# ten MIDI observations with ruler geometry; no motor direction correction.
# To restore the original mapping, set FADER_CALIBRATION = () and
# FADER_PANEL_UPPER_MARK = None. +10 is a physical reference, not a gain target.
FADER_CALIBRATION = FITTED_MARKS
FADER_SMOOTH_CURVE = True  # Monotone cubic in dB; False uses legacy linear segments.
# Use the measured +10 mark to locate Live's +6 ceiling between +5 and +10.
# Above the ceiling input is clamped; releasing sends the motor back to +6.
FADER_PANEL_UPPER_MARK = FITTED_UPPER_MARK
PAN_STEPS = 127.0
LINK_STEPS = 127.0
FINE_FACTOR = 0.1
MOTOR_INTERVAL = 1.0 / 30.0
KEEPALIVE_INTERVAL = 0.8  # Native heartbeat used by independent host implementations.
JOG_DELAY = 0.45
JOG_INTERVAL = 0.10

