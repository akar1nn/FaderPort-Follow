"""Reversible panel calibration, without writing a Live parameter to probe it."""

import math
import re

from .monotone import MonotoneSpline


def parse_db(text):
    text = str(text).strip().replace("\u2212", "-").replace(",", ".")
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*dB", text, re.IGNORECASE)
    if match:
        result = float(match.group(1))
        if math.isfinite(result):
            return result
    if re.fullmatch(r"-(?:inf(?:inity)?|\u221e)\s*dB", text, re.IGNORECASE):
        return float("-inf")
    raise ValueError("Unrecognized volume display: " + text)


def interpolate(value, points):
    value = max(points[0][0], min(points[-1][0], value))
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return points[-1][1]


class VolumeCurve:
    """Map physical 0..1 travel to normalized Live values in both directions.

    Marks are (physical travel, desired dB). Live's own str_for_value supplies
    the native parameter curve. An optional upper panel mark locates the
    parameter maximum on the physical scale. Input above it saturates, while
    feedback returns the actual maximum position. Between measured marks
    calibration is piecewise linear in native values.
    """

    def __init__(self, points=((0.0, 0.0), (1.0, 1.0))):
        self.points = tuple(points)
        self.inverse = tuple((y, x) for x, y in self.points)

    def to_parameter(self, physical):
        return interpolate(physical, self.points)

    def to_physical(self, normalized):
        return interpolate(normalized, self.inverse)

    @classmethod
    def from_marks(cls, parameter, marks, upper_mark=None, smooth=False):
        if not marks:
            if upper_mark is not None:
                raise ValueError("An upper panel mark requires calibration marks")
            return cls()
        marks = tuple((float(position), float(db)) for position, db in marks)
        previous_position, previous_db = 0.0, float("-inf")
        for position, db in marks:
            if not (math.isfinite(position) and math.isfinite(db)
                    and previous_position < position < 1.0 and previous_db < db):
                raise ValueError("Calibration marks must increase in position and dB")
            previous_position, previous_db = position, db
        minimum, maximum = parameter.min, parameter.max
        if maximum <= minimum:
            raise ValueError("Volume has no usable range")

        def db_at(normalized):
            return parse_db(parameter.str_for_value(minimum + normalized * (maximum - minimum)))

        # Check the display is usable and monotonic before searching it.
        probes = [db_at(index / 16.0) for index in range(17)]
        if any(a > b for a, b in zip(probes, probes[1:])):
            raise ValueError("Volume display is not monotonic")
        maximum_position = 1.0
        if upper_mark is not None:
            upper_position, upper_db = map(float, upper_mark)
            last_position, last_db = marks[-1]
            maximum_db = probes[-1]
            if not (math.isfinite(upper_position) and math.isfinite(upper_db)
                    and math.isfinite(maximum_db)
                    and last_position < upper_position <= 1.0
                    and last_db < maximum_db <= upper_db):
                raise ValueError("Upper panel mark must bracket the Live maximum")
            maximum_position = (last_position + (maximum_db - last_db)
                                / (upper_db - last_db) * (upper_position - last_position))
        points = [(0.0, 0.0)]

        def normalized_for_db(db):
            if not probes[0] < db < probes[-1]:
                raise ValueError("Calibration dB is outside the Live volume range")
            # Display strings are rounded. Locate both edges of the requested
            # display plateau and use its center, avoiding a biased edge value.
            edges = []
            for strict in (False, True):
                low, high = 0.0, 1.0
                for _ in range(24):
                    mid = (low + high) / 2.0
                    shown = db_at(mid)
                    if shown > db or (shown == db and not strict):
                        high = mid
                    else:
                        low = mid
                edges.append((low + high) / 2.0)
            normalized = sum(edges) / 2.0
            if abs(db_at(normalized) - db) > 0.11:
                raise ValueError("Live cannot represent the requested dB mark")
            return normalized

        for position, db in marks:
            normalized = normalized_for_db(db)
            if not points[-1][1] < normalized < 1.0:
                raise ValueError("Calibration cannot be inverted")
            points.append((position, normalized))
        points.append((maximum_position, 1.0))
        if smooth:
            maximum_db = probes[-1]
            if not math.isfinite(maximum_db):
                raise ValueError("Smooth calibration requires a finite volume maximum")
            first_db = marks[0][1]
            # Discover Live's nonlinear native scale read-only, at 1 dB spacing.
            # No API calls are needed while moving the fader or driving the motor.
            db_samples = {db: normalized for (_, db), (_, normalized) in zip(marks, points[1:-1])}
            for db in range(math.ceil(first_db), math.ceil(maximum_db)):
                if first_db < db < maximum_db and db not in db_samples:
                    db_samples[db] = normalized_for_db(db)
            db_samples[maximum_db] = 1.0
            panel_points = [(db, position) for position, db in marks]
            panel_points.append((upper_mark[1], upper_mark[0]) if upper_mark is not None
                                else (maximum_db, 1.0))
            return SmoothVolumeCurve(panel_points, sorted(db_samples.items()), points)
        return cls(points)


class SmoothVolumeCurve:
    """Compose a smooth physical dB scale with Live's sampled native scale.

    Only the panel curve is regressed offline. Live's scale remains a read-only
    measured conversion. Inversion uses the same curves, avoiding asymmetric
    input/output approximations. Upper overtravel saturates at the true maximum.
    """

    def __init__(self, panel_points, native_points, anchor_points):
        self.panel = MonotoneSpline(panel_points)  # dB -> physical travel
        self.native = MonotoneSpline(native_points)  # dB -> native normalized
        self.minimum_db = native_points[0][0]
        self.maximum_db = native_points[-1][0]
        self.minimum_position = self.panel(self.minimum_db)
        self.minimum_native = native_points[0][1]
        self.maximum_position = self.panel(self.maximum_db)
        # Join the unmeasured bottom tail to native silence with matching slope.
        slope = self.native.derivative(self.minimum_db) / self.panel.derivative(self.minimum_db)
        self.tail_power = self.minimum_position * slope / self.minimum_native
        if not math.isfinite(self.tail_power) or self.tail_power <= 0:
            raise ValueError("Cannot smoothly join the lower volume range")
        self.points = tuple(anchor_points[:-1]) + ((self.maximum_position, 1.0),)

    def to_parameter(self, physical):
        physical = max(0.0, min(1.0, physical))
        if physical <= self.minimum_position:
            return self.minimum_native * (physical / self.minimum_position) ** self.tail_power
        if physical >= self.maximum_position:
            return 1.0
        return self.native(self.panel.inverse(physical))

    def to_physical(self, normalized):
        normalized = max(0.0, min(1.0, normalized))
        if normalized <= self.minimum_native:
            return self.minimum_position * (normalized / self.minimum_native) ** (1.0 / self.tail_power)
        if normalized >= 1.0:
            return self.maximum_position
        return self.panel(self.native.inverse(normalized))
