import math
import unittest

from FaderPort_Follow.monotone import MonotoneSpline
from FaderPort_Follow.volume_curve import VolumeCurve, parse_db
from FaderPort_Follow import settings
from .test_volume_curve import formatted_db
from .fakes import Parameter
from tools.fit_volume_curve import least_squares


class MonotoneTests(unittest.TestCase):
    def test_recovers_an_affine_regression_and_zero_mean_residual(self):
        samples = [(0, 10), (1, 11), (2, 16), (3, 17)]
        offset, scale = least_squares(samples)
        self.assertAlmostEqual(offset, 9.6)
        self.assertAlmostEqual(scale, 2.6)
        self.assertAlmostEqual(sum(y - offset - scale * x for x, y in samples), 0)

    def test_linear_reproduction_and_exact_inverse(self):
        curve = MonotoneSpline(((0, 3), (2, 7), (3, 9), (10, 23)))
        for i in range(1001):
            x = i / 100
            self.assertAlmostEqual(curve(x), 3 + 2 * x)
            self.assertAlmostEqual(curve.inverse(curve(x)), x, places=10)

    def test_steep_spacing_is_monotone_without_overshoot_and_is_c1(self):
        points = ((-60, .05), (-40, .14), (-10, .48), (-5, .59), (-1, .68),
                  (0, .72), (1, .76), (5, .86), (10, .97))
        curve = MonotoneSpline(points)
        previous = -1
        for i in range(7001):
            x = -60 + i / 100
            value = curve(x)
            self.assertGreater(value, previous)
            self.assertGreaterEqual(value, .05)
            self.assertLessEqual(value, .97)
            previous = value
        for x, y in points[1:-1]:
            self.assertEqual(curve(x), y)
            epsilon = 1e-5
            left = (curve(x) - curve(x - epsilon)) / epsilon
            right = (curve(x + epsilon) - curve(x)) / epsilon
            self.assertAlmostEqual(left, right, delta=1e-6)

    def test_invalid_spline_data_is_rejected(self):
        for points in ((), ((0, 1),), ((0, 1), (0, 2)), ((0, 2), (1, 1)),
                       ((0, 1), (1, math.nan)), ((0, 1), (math.inf, 2))):
            with self.subTest(points=points), self.assertRaises(ValueError):
                MonotoneSpline(points)

    def test_native_conversion_accuracy_and_lower_tail_join_without_parameter_writes(self):
        parameter = Parameter()
        parameter.str_for_value = formatted_db
        original = parameter.value
        curve = VolumeCurve.from_marks(parameter, settings.FADER_CALIBRATION,
                                       settings.FADER_PANEL_UPPER_MARK, smooth=True)
        for i in range(1321):
            db = -60 + i / 20
            physical = curve.panel(db)
            native = curve.to_parameter(physical)
            self.assertAlmostEqual(parse_db(formatted_db(native)), db, delta=.11)
        x = curve.minimum_position
        step = 1e-7
        left = (curve.to_parameter(x) - curve.to_parameter(x - step)) / step
        right = (curve.to_parameter(x + step) - curve.to_parameter(x)) / step
        self.assertAlmostEqual(left, right, delta=1e-4)
        self.assertEqual(curve.to_parameter(0), 0)
        self.assertEqual(curve.to_physical(0), 0)
        self.assertEqual(parameter.value, original)
        self.assertEqual(parameter.gestures, [])
