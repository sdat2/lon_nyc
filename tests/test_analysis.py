"""Tests for lon_nyc.analysis – rainy-hour and annual summary statistics."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from lon_nyc import analysis


def _make_precip_df(values_mm: list) -> pd.DataFrame:
    """Build a minimal processed DataFrame with a precipitation_mm column."""
    index = pd.date_range("2023-01-01", periods=len(values_mm), freq="h", tz="UTC")
    return pd.DataFrame({"precipitation_mm": values_mm}, index=index)


# ---------------------------------------------------------------------------
# rainy_hours_summary
# ---------------------------------------------------------------------------


def test_summary_counts_rainy_hours():
    df = _make_precip_df([0.0, 0.5, 1.2, 0.0, 3.0])
    result = analysis.rainy_hours_summary(df)
    assert result["total_hours"] == 5
    assert result["rainy_hours"] == 3


def test_summary_rainy_fraction():
    df = _make_precip_df([0.0, 1.0])
    result = analysis.rainy_hours_summary(df)
    assert pytest.approx(result["rainy_fraction"]) == 0.5


def test_summary_total_precip():
    df = _make_precip_df([1.0, 2.0, 0.0])
    result = analysis.rainy_hours_summary(df)
    assert pytest.approx(result["total_precip_mm"]) == 3.0


def test_summary_mean_precip_rainy_only():
    df = _make_precip_df([0.0, 2.0, 4.0])
    result = analysis.rainy_hours_summary(df)
    assert pytest.approx(result["mean_precip_mm"]) == 3.0


def test_summary_custom_threshold():
    df = _make_precip_df([0.0, 0.05, 0.5, 2.0])
    result = analysis.rainy_hours_summary(df, threshold_mm=0.1)
    assert result["rainy_hours"] == 2  # 0.5 and 2.0 exceed 0.1 mm


def test_summary_all_dry():
    df = _make_precip_df([0.0, 0.0, 0.0])
    result = analysis.rainy_hours_summary(df)
    assert result["rainy_hours"] == 0
    assert result["rainy_fraction"] == 0.0
    assert math.isnan(result["mean_precip_mm"])


def test_summary_all_nan():
    df = _make_precip_df([float("nan"), float("nan")])
    result = analysis.rainy_hours_summary(df)
    assert result["total_hours"] == 0
    assert result["rainy_hours"] == 0
    assert math.isnan(result["rainy_fraction"])


def test_summary_empty_dataframe():
    result = analysis.rainy_hours_summary(pd.DataFrame())
    assert result["total_hours"] == 0
    assert math.isnan(result["rainy_fraction"])


def test_summary_label_preserved():
    df = _make_precip_df([1.0])
    result = analysis.rainy_hours_summary(df, label="Test Station")
    assert result["label"] == "Test Station"


def test_summary_nan_rows_excluded_from_total():
    import numpy as np

    df = _make_precip_df([1.0, float("nan"), 2.0])
    result = analysis.rainy_hours_summary(df)
    assert result["total_hours"] == 2
    assert result["rainy_hours"] == 2


# ---------------------------------------------------------------------------
# annual_summary
# ---------------------------------------------------------------------------


def _make_annual_df(records: list[tuple]) -> pd.DataFrame:
    """Build a processed DataFrame spanning multiple years.

    ``records`` is a list of (iso_datetime_str, precip_mm) tuples.
    """
    timestamps = pd.DatetimeIndex(
        [pd.Timestamp(dt, tz="UTC") for dt, _ in records]
    )
    values = [v for _, v in records]
    return pd.DataFrame({"precipitation_mm": values}, index=timestamps)


def test_annual_single_year_totals():
    df = _make_annual_df([
        ("2022-06-01 00:00", 1.0),
        ("2022-06-01 01:00", 2.5),
        ("2022-06-02 00:00", 0.0),
        ("2022-06-03 00:00", 0.8),
    ])
    result = analysis.annual_summary(df)
    assert len(result) == 1
    assert result.iloc[0]["year"] == 2022
    assert pytest.approx(result.iloc[0]["total_precip_mm"]) == 4.3
    assert result.iloc[0]["rainy_hours"] == 3
    assert result.iloc[0]["rainy_days"] == 2


def test_annual_multi_year_row_count():
    df = _make_annual_df([
        ("2021-03-01 00:00", 1.0),
        ("2022-07-15 12:00", 2.0),
        ("2023-11-20 06:00", 0.5),
    ])
    result = analysis.annual_summary(df)
    assert list(result["year"]) == [2021, 2022, 2023]


def test_annual_rainy_days_same_day_multiple_hours():
    """Multiple rainy hours on the same day count as only one rainy day."""
    df = _make_annual_df([
        ("2023-05-10 08:00", 1.0),
        ("2023-05-10 09:00", 0.8),
        ("2023-05-10 10:00", 1.2),
    ])
    result = analysis.annual_summary(df)
    assert result.iloc[0]["rainy_days"] == 1
    assert result.iloc[0]["rainy_hours"] == 3


def test_annual_all_dry_year():
    df = _make_annual_df([
        ("2020-01-01 00:00", 0.0),
        ("2020-06-15 12:00", 0.0),
    ])
    result = analysis.annual_summary(df)
    assert result.iloc[0]["rainy_hours"] == 0
    assert result.iloc[0]["rainy_days"] == 0
    assert pytest.approx(result.iloc[0]["total_precip_mm"]) == 0.0


def test_annual_label_propagated():
    df = _make_annual_df([("2023-01-01 00:00", 1.0)])
    result = analysis.annual_summary(df, label="Test City")
    assert all(result["label"] == "Test City")


def test_annual_empty_dataframe_returns_empty():
    result = analysis.annual_summary(pd.DataFrame())
    assert len(result) == 0


def test_annual_column_order():
    df = _make_annual_df([("2023-04-01 00:00", 2.0)])
    result = analysis.annual_summary(df, label="X")
    assert list(result.columns) == ["label", "year", "total_precip_mm", "rainy_hours", "rainy_days"]


def test_annual_rainy_days_integer_dtype():
    df = _make_annual_df([("2023-01-01 00:00", 1.0)])
    result = analysis.annual_summary(df)
    assert result["rainy_days"].dtype == int
    assert result["rainy_hours"].dtype == int


# ---------------------------------------------------------------------------
# annual_temperature_summary
# ---------------------------------------------------------------------------


def _make_temp_df(records: list[tuple]) -> pd.DataFrame:
    """Build a processed temperature DataFrame.

    ``records`` is a list of (iso_datetime_str, temp_c) tuples.
    """
    timestamps = pd.DatetimeIndex(
        [pd.Timestamp(dt, tz="UTC") for dt, _ in records]
    )
    values = [v for _, v in records]
    return pd.DataFrame({"temp_c": values}, index=timestamps)


_BASELINES = {"comfort": 21.0}


def test_temp_summary_mean_cold_dev():
    """All obs below baseline: cold dev = (21 - T), warm dev = 0."""
    df = _make_temp_df([
        ("2023-01-01 00:00", 11.0),  # 10 below
        ("2023-01-01 01:00", 16.0),  # 5 below
    ])
    result = analysis.annual_temperature_summary(df, baselines_c=_BASELINES)
    assert len(result) == 1
    assert pytest.approx(result.iloc[0]["mean_cold_dev_c"]) == 7.5
    assert pytest.approx(result.iloc[0]["mean_warm_dev_c"]) == 0.0
    assert pytest.approx(result.iloc[0]["mean_abs_dev_c"]) == 7.5


def test_temp_summary_mean_warm_dev():
    """All obs above baseline: warm dev = (T - 21), cold dev = 0."""
    df = _make_temp_df([
        ("2023-07-01 12:00", 25.0),  # 4 above
        ("2023-07-01 13:00", 27.0),  # 6 above
    ])
    result = analysis.annual_temperature_summary(df, baselines_c=_BASELINES)
    assert pytest.approx(result.iloc[0]["mean_warm_dev_c"]) == 5.0
    assert pytest.approx(result.iloc[0]["mean_cold_dev_c"]) == 0.0


def test_temp_summary_mixed_dev():
    """One obs below, one above: both deviations contribute."""
    df = _make_temp_df([
        ("2023-01-01 00:00", 17.0),  # 4 below 21
        ("2023-07-01 00:00", 25.0),  # 4 above 21
    ])
    result = analysis.annual_temperature_summary(df, baselines_c=_BASELINES)
    assert pytest.approx(result.iloc[0]["mean_cold_dev_c"]) == 2.0   # 4/2
    assert pytest.approx(result.iloc[0]["mean_warm_dev_c"]) == 2.0   # 4/2
    assert pytest.approx(result.iloc[0]["mean_abs_dev_c"]) == 4.0


def test_temp_summary_multi_year():
    df = _make_temp_df([
        ("2021-06-01 00:00", 10.0),
        ("2022-06-01 00:00", 30.0),
    ])
    result = analysis.annual_temperature_summary(df, baselines_c=_BASELINES)
    assert list(result["year"]) == [2021, 2022]


def test_temp_summary_multiple_baselines():
    df = _make_temp_df([("2023-01-01 00:00", 10.0)])
    baselines = {"low": 15.5, "high": 21.0}
    result = analysis.annual_temperature_summary(df, baselines_c=baselines)
    assert len(result) == 2
    assert set(result["baseline_label"]) == {"low", "high"}
    # At 10°C: cold_dev from 15.5 baseline = 5.5; from 21.0 = 11.0
    low_row = result[result["baseline_label"] == "low"].iloc[0]
    high_row = result[result["baseline_label"] == "high"].iloc[0]
    assert pytest.approx(low_row["mean_cold_dev_c"]) == 5.5
    assert pytest.approx(high_row["mean_cold_dev_c"]) == 11.0


def test_temp_summary_n_obs_counts_valid_only():
    df = _make_temp_df([
        ("2023-01-01 00:00", 10.0),
        ("2023-01-01 01:00", 20.0),
    ])
    # Manually inject a NaN (as if it were a missing sentinel)
    df.iloc[1, 0] = float("nan")
    result = analysis.annual_temperature_summary(df, baselines_c=_BASELINES)
    assert result.iloc[0]["n_obs"] == 1


def test_temp_summary_label_propagated():
    df = _make_temp_df([("2023-01-01 00:00", 10.0)])
    result = analysis.annual_temperature_summary(df, baselines_c=_BASELINES, label="Test City")
    assert all(result["label"] == "Test City")


def test_temp_summary_empty_returns_empty():
    result = analysis.annual_temperature_summary(pd.DataFrame())
    assert len(result) == 0


def test_temp_summary_column_order():
    df = _make_temp_df([("2023-01-01 00:00", 10.0)])
    result = analysis.annual_temperature_summary(df, baselines_c=_BASELINES)
    assert list(result.columns) == [
        "label", "year", "baseline_label", "baseline_c",
        "n_obs", "mean_cold_dev_c", "mean_warm_dev_c", "mean_abs_dev_c",
    ]
