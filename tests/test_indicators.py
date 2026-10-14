import unittest
from src.monitor import DataUnavailable, ema, rsi


class IndicatorTests(unittest.TestCase):
    def test_ema_constant_series(self):
        self.assertAlmostEqual(ema([2.0] * 60, 12), 2.0)

    def test_rsi_rising_series(self):
        self.assertAlmostEqual(rsi([float(i) for i in range(20)], 14), 100.0)

    def test_ema_rejects_short_series(self):
        with self.assertRaises(DataUnavailable):
            ema([1.0, 2.0], 5)


if __name__ == "__main__":
    unittest.main()
