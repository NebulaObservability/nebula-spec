import unittest

from tools.spec_tool import monotonic_sum_accumulation_errors


class MonotonicSumAccumulationTest(unittest.TestCase):
    def test_large_integer_regression_is_exact(self) -> None:
        errors = monotonic_sum_accumulation_errors(
            {"asInt": "9007199254740993"},
            {"asInt": "9007199254740992"},
            "large-integer-series",
        )

        self.assertTrue(any("value regressed" in error for error in errors), errors)

    def test_large_integer_growth_is_valid(self) -> None:
        errors = monotonic_sum_accumulation_errors(
            {"asInt": "9007199254740992"},
            {"asInt": "9007199254740993"},
            "large-integer-series",
        )

        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
