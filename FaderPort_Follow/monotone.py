"""Shape-preserving cubic Hermite interpolation, using only Python's stdlib."""

from bisect import bisect_right
from math import isfinite


class MonotoneSpline:
    def __init__(self, points):
        self.points = tuple(points)
        self.x = tuple(point[0] for point in self.points)
        self.y = tuple(point[1] for point in self.points)
        h = [b - a for a, b in zip(self.x, self.x[1:])]
        if len(h) < 1 or any(not isfinite(value) for point in self.points for value in point) or any(width <= 0 for width in h):
            raise ValueError("Spline coordinates must be finite and strictly increasing")
        delta = [(b - a) / width for a, b, width in zip(self.y, self.y[1:], h)]
        if any(slope <= 0 for slope in delta):
            raise ValueError("Spline points must strictly increase in both coordinates")
        if len(h) == 1:
            self.slopes = (delta[0], delta[0])
            return
        slopes = [self._end_slope(h[0], h[1], delta[0], delta[1])]
        for i in range(1, len(self.x) - 1):
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            slopes.append((w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i]))
        slopes.append(self._end_slope(h[-1], h[-2], delta[-1], delta[-2]))
        self.slopes = tuple(slopes)

    @staticmethod
    def _end_slope(h0, h1, d0, d1):
        return max(0.0, min(3 * d0, ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)))

    def _segment(self, value):
        value = max(self.x[0], min(self.x[-1], value))
        index = max(0, min(len(self.x) - 2, bisect_right(self.x, value) - 1))
        width = self.x[index + 1] - self.x[index]
        return index, width, (value - self.x[index]) / width

    def __call__(self, value):
        i, h, t = self._segment(value)
        result = ((2 * t ** 3 - 3 * t ** 2 + 1) * self.y[i]
                  + (t ** 3 - 2 * t ** 2 + t) * h * self.slopes[i]
                  + (-2 * t ** 3 + 3 * t ** 2) * self.y[i + 1]
                  + (t ** 3 - t ** 2) * h * self.slopes[i + 1])
        return max(self.y[i], min(self.y[i + 1], result))

    def derivative(self, value):
        i, h, t = self._segment(value)
        return (((6 * t ** 2 - 6 * t) * self.y[i]
                 + (3 * t ** 2 - 4 * t + 1) * h * self.slopes[i]
                 + (-6 * t ** 2 + 6 * t) * self.y[i + 1]
                 + (3 * t ** 2 - 2 * t) * h * self.slopes[i + 1]) / h)

    def inverse(self, value):
        if value <= self.y[0]:
            return self.x[0]
        if value >= self.y[-1]:
            return self.x[-1]
        i = bisect_right(self.y, value) - 1
        low, high = self.x[i], self.x[i + 1]
        for _ in range(40):
            mid = (low + high) / 2
            if self(mid) < value:
                low = mid
            else:
                high = mid
        return (low + high) / 2
