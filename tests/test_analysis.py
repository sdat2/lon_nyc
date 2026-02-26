"""Tests for lon_nyc.analysis – rainy-hour summary statistics."""

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
