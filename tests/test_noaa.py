"""Tests for lon_nyc.noaa – download and precipitation processing functions."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from lon_nyc import noaa


# ---------------------------------------------------------------------------
# generate_s3_file_keys
# ---------------------------------------------------------------------------


def test_generate_s3_file_keys_single_year():
    keys = noaa.generate_s3_file_keys("725053-94728", 2023, 2023)
    assert keys == ["2023/72505394728.csv"]


def test_generate_s3_file_keys_range():
    keys = noaa.generate_s3_file_keys("725053-94728", 2021, 2023)
    assert keys == [
        "2021/72505394728.csv",
        "2022/72505394728.csv",
        "2023/72505394728.csv",
    ]


def test_generate_s3_file_keys_empty_range():
    keys = noaa.generate_s3_file_keys("725053-94728", 2024, 2023)
    assert keys == []


# ---------------------------------------------------------------------------
# download_and_concatenate_s3_csvs
# ---------------------------------------------------------------------------


def _make_csv_bytes(data: dict) -> bytes:
    """Return CSV-encoded bytes from a dict of lists."""
    return pd.DataFrame(data).to_csv(index=False).encode()


def test_download_concatenates_multiple_files():
    csv1 = _make_csv_bytes({"DATE": ["2023-01-01T00:00:00"], "AA1": ["0005,01,C,5"]})
    csv2 = _make_csv_bytes({"DATE": ["2023-02-01T00:00:00"], "AA1": ["0010,01,C,5"]})

    s3 = MagicMock()
    s3.get_object.side_effect = [
        {"Body": io.BytesIO(csv1)},
        {"Body": io.BytesIO(csv2)},
    ]
    s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

    result = noaa.download_and_concatenate_s3_csvs(
        s3, "bucket", ["a.csv", "b.csv"], cache_dir=""
    )
    assert len(result) == 2


def test_download_skips_missing_key():
    csv1 = _make_csv_bytes({"DATE": ["2023-01-01T00:00:00"], "AA1": ["0005,01,C,5"]})

    NoSuchKey = type("NoSuchKey", (Exception,), {})
    s3 = MagicMock()
    s3.exceptions.NoSuchKey = NoSuchKey
    s3.get_object.side_effect = [{"Body": io.BytesIO(csv1)}, NoSuchKey("not found")]

    result = noaa.download_and_concatenate_s3_csvs(
        s3, "bucket", ["a.csv", "b.csv"], cache_dir=""
    )
    assert len(result) == 1


def test_download_returns_empty_when_all_missing():
    NoSuchKey = type("NoSuchKey", (Exception,), {})
    s3 = MagicMock()
    s3.exceptions.NoSuchKey = NoSuchKey
    s3.get_object.side_effect = NoSuchKey("not found")

    result = noaa.download_and_concatenate_s3_csvs(s3, "bucket", ["a.csv"], cache_dir="")
    assert result.empty


def test_download_uses_cache_on_second_call(tmp_path):
    """Second call with the same key must not hit S3 when a cache file exists."""
    csv1 = _make_csv_bytes({"DATE": ["2023-01-01T00:00:00"], "AA1": ["0005,01,C,5"]})

    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(csv1)}
    s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

    cache_dir = str(tmp_path)
    # First call — downloads and caches
    noaa.download_and_concatenate_s3_csvs(s3, "bucket", ["2023/test.csv"], cache_dir=cache_dir)
    assert s3.get_object.call_count == 1

    # Second call — must serve from cache, no new S3 request
    noaa.download_and_concatenate_s3_csvs(s3, "bucket", ["2023/test.csv"], cache_dir=cache_dir)
    assert s3.get_object.call_count == 1  # still 1


# ---------------------------------------------------------------------------
# parse_aa1_depth_mm
# ---------------------------------------------------------------------------


def test_parse_aa1_depth_normal():
    series = pd.Series(["0005,0050,C,5"])  # depth = 50 tenths = 5.0 mm
    result = noaa.parse_aa1_depth_mm(series)
    assert pytest.approx(result.iloc[0]) == 5.0


def test_parse_aa1_depth_zero():
    series = pd.Series(["0001,0000,C,5"])  # depth = 0 tenths = 0.0 mm
    result = noaa.parse_aa1_depth_mm(series)
    assert result.iloc[0] == 0.0


def test_parse_aa1_depth_missing_sentinel():
    series = pd.Series(["0001,9999,C,5"])  # missing sentinel
    result = noaa.parse_aa1_depth_mm(series)
    assert np.isnan(result.iloc[0])


def test_parse_aa1_depth_nan_input():
    series = pd.Series([np.nan])
    result = noaa.parse_aa1_depth_mm(series)
    assert np.isnan(result.iloc[0])


def test_parse_aa1_depth_mixed():
    series = pd.Series(["0001,0100,C,5", "0001,9999,C,5", "0001,0000,C,5"])
    result = noaa.parse_aa1_depth_mm(series)
    assert pytest.approx(result.iloc[0]) == 10.0
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == 0.0


# ---------------------------------------------------------------------------
# process_precipitation_data
# ---------------------------------------------------------------------------


def _make_raw_df(**kwargs) -> pd.DataFrame:
    """Build a minimal raw ISD DataFrame."""
    defaults = {
        "DATE": ["2023-06-01T10:00:00", "2023-06-01T11:00:00"],
        "STATION": ["725053-94728", "725053-94728"],
        "REPORT_TYPE": ["FM-15", "FM-15"],
        # AA1 format: period_hours,depth_tenths_mm,condition_code,quality_code
        "AA1": ["0001,0050,C,5", "0001,0000,C,5"],
    }
    defaults.update(kwargs)
    return pd.DataFrame(defaults)


def test_process_sets_datetime_index():
    df = noaa.process_precipitation_data(_make_raw_df())
    assert isinstance(df.index, pd.DatetimeIndex)


def test_process_creates_precipitation_mm_column():
    df = noaa.process_precipitation_data(_make_raw_df())
    assert "precipitation_mm" in df.columns


def test_process_converts_units_correctly():
    raw = _make_raw_df(AA1=["0001,0050,C,5", "0001,0100,C,5"])  # 5.0 mm, 10.0 mm
    df = noaa.process_precipitation_data(raw, report_types=[])
    assert pytest.approx(df["precipitation_mm"].iloc[0]) == 5.0
    assert pytest.approx(df["precipitation_mm"].iloc[1]) == 10.0


def test_process_missing_becomes_nan():
    raw = _make_raw_df(AA1=["0001,9999,C,5", "0001,0050,C,5"])  # missing, then 5.0 mm
    df = noaa.process_precipitation_data(raw, report_types=[])
    assert np.isnan(df["precipitation_mm"].iloc[0])
    assert not np.isnan(df["precipitation_mm"].iloc[1])


def test_process_filters_report_type():
    raw = _make_raw_df(
        DATE=["2023-06-01T10:00:00", "2023-06-01T11:00:00"],
        REPORT_TYPE=["FM-15", "SOD  "],
        AA1=["0005,01,C,5", "0010,01,C,5"],
    )
    df = noaa.process_precipitation_data(raw, report_types=["FM-15"])
    assert len(df) == 1


def test_process_no_report_type_filter():
    raw = _make_raw_df(REPORT_TYPE=["FM-15", "SOD  "])
    df = noaa.process_precipitation_data(raw, report_types=[])
    assert len(df) == 2


def test_process_deduplicates_timestamps():
    raw = _make_raw_df(
        DATE=["2023-06-01T10:00:00", "2023-06-01T10:00:00"],
        AA1=["0005,01,C,5", "0010,01,C,5"],
    )
    df = noaa.process_precipitation_data(raw, report_types=[])
    assert len(df) == 1


def test_process_empty_input_returns_empty():
    df = noaa.process_precipitation_data(pd.DataFrame())
    assert df.empty


def test_process_missing_date_column_returns_empty():
    raw = pd.DataFrame({"AA1": ["0005,01,C,5"]})
    df = noaa.process_precipitation_data(raw)
    assert df.empty


def test_process_missing_aa1_column_gives_nan_precip():
    raw = _make_raw_df()
    raw = raw.drop(columns=["AA1"])
    df = noaa.process_precipitation_data(raw, report_types=[])
    assert "precipitation_mm" in df.columns
    assert df["precipitation_mm"].isna().all()


# ---------------------------------------------------------------------------
# parse_tmp_celsius
# ---------------------------------------------------------------------------


def _tmp_series(*vals) -> pd.Series:
    return pd.Series(list(vals))


def test_parse_tmp_positive():
    result = noaa.parse_tmp_celsius(_tmp_series("+0215,1"))
    assert pytest.approx(result.iloc[0]) == 21.5


def test_parse_tmp_negative():
    result = noaa.parse_tmp_celsius(_tmp_series("-0056,1"))
    assert pytest.approx(result.iloc[0]) == -5.6


def test_parse_tmp_zero():
    result = noaa.parse_tmp_celsius(_tmp_series("+0000,1"))
    assert pytest.approx(result.iloc[0]) == 0.0


def test_parse_tmp_missing_sentinel_9999():
    result = noaa.parse_tmp_celsius(_tmp_series("+9999,9"))
    assert pd.isna(result.iloc[0])


def test_parse_tmp_nan_input():
    result = noaa.parse_tmp_celsius(_tmp_series(float("nan")))
    assert pd.isna(result.iloc[0])


def test_parse_tmp_multiple_values():
    result = noaa.parse_tmp_celsius(_tmp_series("+0100,1", "+0200,1", "+9999,9"))
    assert pytest.approx(result.iloc[0]) == 10.0
    assert pytest.approx(result.iloc[1]) == 20.0
    assert pd.isna(result.iloc[2])


# ---------------------------------------------------------------------------
# process_temperature_data
# ---------------------------------------------------------------------------


def _make_raw_temp_df(
    dates=("2023-06-01T12:00:00",),
    tmp_vals=("+0200,1",),
    report_types=("FM-15",),
) -> pd.DataFrame:
    return pd.DataFrame({
        "DATE": list(dates),
        "TMP": list(tmp_vals),
        "REPORT_TYPE": list(report_types),
    })


def test_process_temperature_basic():
    raw = _make_raw_temp_df()
    df = noaa.process_temperature_data(raw, report_types=[])
    assert "temp_c" in df.columns
    assert pytest.approx(df["temp_c"].iloc[0]) == 20.0


def test_process_temperature_filters_report_type():
    raw = _make_raw_temp_df(
        dates=("2023-01-01T00:00:00", "2023-01-01T01:00:00"),
        tmp_vals=("+0100,1", "+0200,1"),
        report_types=("FM-15", "FM-16"),
    )
    df = noaa.process_temperature_data(raw, report_types=["FM-15"])
    assert len(df) == 1
    assert pytest.approx(df["temp_c"].iloc[0]) == 10.0


def test_process_temperature_deduplicates():
    raw = _make_raw_temp_df(
        dates=("2023-03-01T06:00:00", "2023-03-01T06:00:00"),
        tmp_vals=("+0150,1", "+0160,1"),
        report_types=("FM-15", "FM-15"),
    )
    df = noaa.process_temperature_data(raw, report_types=[])
    assert len(df) == 1
    assert pytest.approx(df["temp_c"].iloc[0]) == 15.0


def test_process_temperature_missing_tmp_gives_nan():
    raw = _make_raw_temp_df(tmp_vals=("+9999,9",))
    df = noaa.process_temperature_data(raw, report_types=[])
    assert pd.isna(df["temp_c"].iloc[0])


def test_process_temperature_empty_returns_empty():
    df = noaa.process_temperature_data(pd.DataFrame())
    assert df.empty


def test_process_temperature_missing_date_returns_empty():
    raw = pd.DataFrame({"TMP": ["+0100,1"]})
    df = noaa.process_temperature_data(raw)
    assert df.empty
