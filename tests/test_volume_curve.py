import math
import unittest
from types import SimpleNamespace

from FaderPort_Follow import protocol, settings
from FaderPort_Follow.controller import FollowController
from FaderPort_Follow.live_api import LiveBridge
from FaderPort_Follow.volume_curve import VolumeCurve, parse_db
from .fakes import Parameter, environment


def formatted_db(value):
    # Deliberately nonlinear test curve, not an assertion about Live's taper.
    return "-inf dB" if value <= 0 else "%.1f dB" % (40 * math.log10(value) + 6)


class VolumeCurveTests(unittest.TestCase):
    def parameter(self):
        parameter = Parameter(value=0.63, minimum=-2, maximum=3)
        parameter.str_for_value = lambda value: formatted_db((value + 2) / 5)
        return parameter

    def test_display_formats_and_invalid_units(self):
        for text, expected in (("\u221210,5 dB", -10.5), ("+6.0 dB", 6),
                               ("-inf dB", -math.inf), ("-\u221e dB", -math.inf)):
            self.assertEqual(parse_db(text), expected)
        for text in ("0.5", "12 %", "nan dB", "inf dB", "10 dB extra"):
            with self.assertRaises(ValueError):
                parse_db(text)

    def test_marks_use_read_only_conversion_and_retain_endpoints(self):
        parameter = self.parameter()
        original = parameter.value
        changes = []
        parameter.add_value_listener(lambda: changes.append(parameter.value))
        curve = VolumeCurve.from_marks(parameter, ((0.3, -20), (0.5, -10), (0.8, 0)))
        for physical, db in ((0.3, -20), (0.5, -10), (0.8, 0)):
            value = parameter.min + curve.to_parameter(physical) * (parameter.max - parameter.min)
            self.assertEqual(parse_db(parameter.str_for_value(value)), db)
        self.assertEqual(curve.to_parameter(0), 0)
        self.assertEqual(curve.to_parameter(1), 1)
        self.assertEqual(parameter.value, original)
        self.assertEqual(changes, [])
        self.assertEqual(parameter.gestures, [])

    def test_round_trip_is_monotonic_through_all_segments(self):
        curve = VolumeCurve.from_marks(self.parameter(), ((0.3, -20), (0.5, -10), (0.8, 0)))
        previous = -1
        for raw in range(16384):
            physical = raw / 16383.0
            normalized = curve.to_parameter(physical)
            self.assertGreater(normalized, previous)
            self.assertAlmostEqual(curve.to_physical(normalized), physical, places=12)
            previous = normalized

    def test_measured_profile_aligns_supported_marks_and_preserves_live_maximum(self):
        parameter = self.parameter()
        curve = VolumeCurve.from_marks(parameter, settings.FADER_CALIBRATION,
                                       settings.FADER_PANEL_UPPER_MARK, smooth=True)
        for position, db in settings.FADER_CALIBRATION:
            value = parameter.min + curve.to_parameter(position) * (parameter.max - parameter.min)
            self.assertAlmostEqual(parse_db(parameter.str_for_value(value)), db, delta=0.1)
        maximum_position = 14486.391139511526 / 16383.0  # Regression + monotone cubic.
        self.assertAlmostEqual(curve.to_physical(1), maximum_position)
        self.assertAlmostEqual(curve.to_parameter(maximum_position), 1)
        self.assertEqual(curve.to_parameter(settings.FADER_PANEL_UPPER_MARK[0]), 1)
        self.assertEqual(curve.to_parameter(1), 1)
        previous = -1
        for raw in range(16384):
            physical = raw / 16383.0
            value = curve.to_parameter(physical)
            self.assertGreaterEqual(value, previous)
            self.assertAlmostEqual(curve.to_physical(value), min(physical, maximum_position), places=12)
            previous = value

    def test_invalid_upper_mark_fails_without_a_partial_curve(self):
        for upper in ((0.7, 10), (1.1, 10), (0.9, 5), (0.9, math.inf),
                      (math.nan, 10), (0.9, -10)):
            with self.subTest(upper=upper), self.assertRaises(ValueError):
                VolumeCurve.from_marks(self.parameter(), ((0.8, 0),), upper)
        with self.assertRaises(ValueError):
            VolumeCurve.from_marks(self.parameter(), (), (0.9, 10))

    def test_ruler_estimates_preserve_nonuniform_spacing_near_zero(self):
        positions = {db: position for position, db in settings.FADER_CALIBRATION}
        self.assertAlmostEqual((positions[1] - positions[0]) / (positions[5] - positions[0]), 4 / 13.0)
        self.assertAlmostEqual((positions[0] - positions[-1]) / (positions[0] - positions[-5]), 4 / 13.0)

    def test_overtravel_clamps_volume_suppresses_motor_until_release_then_returns(self):
        song, app = environment()
        parameter = song.tracks[0].mixer_device.volume
        parameter.str_for_value = formatted_db
        config = SimpleNamespace(**{key: getattr(settings, key) for key in dir(settings) if key.isupper()})
        messages = []
        control = FollowController(LiveBridge(song, app, lambda _: None, lambda _: None),
                                   messages.append, config=config)
        try:
            control.receive_midi((0x90, protocol.FADER_TOUCH, 127))
            messages.clear()
            for position in (0.95, 1.0):
                control.receive_midi(protocol.fader_message(position))
                self.assertEqual(parameter.value, parameter.max)
                self.assertFalse(any(message[0] == 0xE0 for message in messages))
            control.receive_midi((0x90, protocol.FADER_TOUCH, 0))
            motor = [message for message in messages if message[0] == 0xE0][-1]
            self.assertEqual(motor, protocol.fader_message(14486.391139511526 / 16383.0))
            # A motor echo while untouched cannot write, and touching again at
            # the returned position keeps the maximum instead of causing a jump.
            control.receive_midi(motor)
            self.assertEqual(parameter.value, parameter.max)
            control.receive_midi((0x90, protocol.FADER_TOUCH, 127))
            control.receive_midi(motor)
            control.receive_midi((0x90, protocol.FADER_TOUCH, 0))
            self.assertAlmostEqual(parameter.value, parameter.max, delta=1 / 16383)
            self.assertEqual(parameter.gestures, ["begin", "end", "begin", "end"])
        finally:
            control.disconnect()

    def test_invalid_or_out_of_range_marks_are_rejected(self):
        for marks in (((0.8, 0), (0.3, -20)), ((0.3, -10), (0.5, -20)),
                      ((0, -20),), ((1, 0),), ((0.8, 10),), ((math.nan, 0),),
                      ((0.3, -20), (0.3, -10)), ((0.3, math.inf),)):
            with self.subTest(marks=marks), self.assertRaises(ValueError):
                VolumeCurve.from_marks(self.parameter(), marks)
        parameter = self.parameter()
        parameter.str_for_value = lambda value: "%.1f dB" % (-value)
        with self.assertRaises(ValueError):
            VolumeCurve.from_marks(parameter, ((0.5, 0),))

    def test_empty_calibration_needs_no_display_api(self):
        curve = VolumeCurve.from_marks(Parameter(), ())
        self.assertEqual(curve.to_parameter(0.7), 0.7)
        self.assertEqual(curve.to_physical(0.7), 0.7)

    def test_controller_uses_same_curve_in_both_directions_and_touch_switch(self):
        song, app = environment()
        first = song.tracks[0].mixer_device.volume
        second = song.tracks[1].mixer_device.volume
        for parameter in (first, second):
            parameter.str_for_value = formatted_db
        config = SimpleNamespace(**{key: getattr(settings, key) for key in dir(settings) if key.isupper()})
        config.FADER_CALIBRATION = ((0.3, -20), (0.5, -10), (0.8, 0))
        messages, logs = [], []
        control = FollowController(LiveBridge(song, app, logs.append, lambda _: None), messages.append,
                                   config=config)
        try:
            original = first.value
            motor = [message for message in messages if message[0] == 0xE0][-1]
            control.receive_midi((0x90, protocol.FADER_TOUCH, 127))
            control.receive_midi(motor)
            self.assertAlmostEqual(first.value, original, delta=2 / 16383)
            control.receive_midi(protocol.fader_message(0.8))
            self.assertAlmostEqual(parse_db(formatted_db(first.value)), 0, delta=0.1)
            old, new = first.value, second.value
            song.view.selected_track = song.tracks[1]
            control.receive_midi(protocol.fader_message(0.3))
            self.assertEqual((first.value, second.value), (old, new))
            control.receive_midi((0x90, protocol.FADER_TOUCH, 0))
            control.receive_midi((0x90, protocol.FADER_TOUCH, 127))
            control.receive_midi(protocol.fader_message(0.3))
            control.receive_midi((0x90, protocol.FADER_TOUCH, 0))
            self.assertAlmostEqual(parse_db(formatted_db(second.value)), -20, delta=0.1)
            self.assertEqual(logs, [])
        finally:
            control.disconnect()

    def test_bad_display_api_falls_back_without_writing_volume(self):
        song, app = environment()
        config = SimpleNamespace(**{key: getattr(settings, key) for key in dir(settings) if key.isupper()})
        config.FADER_CALIBRATION = ((0.8, 0),)
        logs = []
        control = FollowController(LiveBridge(song, app, logs.append, lambda _: None), lambda _: None,
                                   config=config)
        try:
            self.assertEqual(control._volume_curve.to_physical(0.5), 0.5)
            self.assertEqual(song.tracks[0].mixer_device.volume.value, 0.5)
            self.assertTrue(any("calibration unavailable" in line for line in logs))
        finally:
            control.disconnect()
