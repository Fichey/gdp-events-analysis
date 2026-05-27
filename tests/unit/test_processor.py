"""Unit tests for the processing module."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../processing'))

from processor import _pearson


class TestPearson:
    def test_perfect_positive_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert abs(_pearson(x, y) - 1.0) < 1e-9

    def test_perfect_negative_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        assert abs(_pearson(x, y) - (-1.0)) < 1e-9

    def test_no_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0]
        y = [1.0, 1.0, 1.0, 1.0]
        assert _pearson(x, y) == 0.0

    def test_returns_zero_for_single_element(self):
        assert _pearson([5.0], [5.0]) == 0.0

    def test_returns_float(self):
        result = _pearson([1.0, 2.0, 3.0], [3.0, 1.0, 2.0])
        assert isinstance(result, float)

    def test_known_value(self):
        x = [1.0, 2.0, 3.0]
        y = [1.0, 3.0, 2.0]
        r = _pearson(x, y)
        assert abs(r - 0.5) < 0.01
