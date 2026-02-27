"""Tests for scripts/daylight_latitude.py — astronomical daylight calculations."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# Allow importing the script module directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daylight_latitude as dl  # noqa: E402


# ---------------------------------------------------------------------------
# solar_declination
# ---------------------------------------------------------------------------


def test_solar_declination_summer_solstice():
    """Near summer solstice (doy ≈ 172) declination approaches +23.45°."""
    delta_rad = dl.solar_declination(np.array([172]))
    delta_deg = np.degrees(delta_rad[0])
    assert delta_deg == pytest.approx(23.45, abs=0.5)


def test_solar_declination_winter_solstice():
    """Near winter solstice (doy ≈ 355) declination approaches −23.45°."""
    delta_rad = dl.solar_declination(np.array([355]))
    delta_deg = np.degrees(delta_rad[0])
    assert delta_deg == pytest.approx(-23.45, abs=0.5)


def test_solar_declination_equinox():
    """Near vernal equinox (doy ≈ 80) declination is close to 0°."""
    delta_rad = dl.solar_declination(np.array([80]))
    delta_deg = np.degrees(delta_rad[0])
    assert abs(delta_deg) < 2.0


# ---------------------------------------------------------------------------
# day_length_hours
# ---------------------------------------------------------------------------


def test_day_length_equator_roughly_twelve_hours():
    """At 0° latitude every day has ≈ 12 h of daylight."""
    doy = np.arange(1, 366)
    dl_h = dl.day_length_hours(0.0, doy)
    assert dl_h.mean() == pytest.approx(12.0, abs=0.1)


def test_day_length_london_summer_longer_than_nyc():
    """London's summer solstice day is longer than NYC's (higher latitude)."""
    lon_june = dl.day_length_hours(dl.LON_LAT, np.array([172]))[0]
    nyc_june = dl.day_length_hours(dl.NYC_LAT, np.array([172]))[0]
    assert lon_june > nyc_june


def test_day_length_london_winter_shorter_than_nyc():
    """London's winter solstice day is shorter than NYC's (higher latitude)."""
    lon_dec = dl.day_length_hours(dl.LON_LAT, np.array([355]))[0]
    nyc_dec = dl.day_length_hours(dl.NYC_LAT, np.array([355]))[0]
    assert lon_dec < nyc_dec


def test_day_length_both_cities_near_twelve_at_equinox():
    """Both cities have ≈ 12 h day length near the vernal equinox."""
    doy = np.array([80])
    for lat in [dl.LON_LAT, dl.NYC_LAT]:
        assert dl.day_length_hours(lat, doy)[0] == pytest.approx(12.0, abs=0.5)


def test_day_length_london_summer_solstice_approx():
    """London summer solstice day length should be ~16 h."""
    val = dl.day_length_hours(dl.LON_LAT, np.array([172]))[0]
    assert 15.5 < val < 17.0


def test_day_length_london_winter_solstice_approx():
    """London winter solstice day length should be ~7–8 h."""
    val = dl.day_length_hours(dl.LON_LAT, np.array([355]))[0]
    assert 7.0 < val < 8.5


def test_day_length_annual_mean_near_twelve():
    """Annual mean day length at any latitude should be ≈ 12 h."""
    for lat in [dl.LON_LAT, dl.NYC_LAT, 30.0, 60.0]:
        doy = np.arange(1, 366)
        assert dl.day_length_hours(lat, doy).mean() == pytest.approx(12.0, abs=0.2)


def test_day_length_vectorised():
    """Function accepts a numpy array and returns same-length array."""
    doy = np.array([1, 100, 200, 300])
    result = dl.day_length_hours(dl.LON_LAT, doy)
    assert result.shape == doy.shape


# ---------------------------------------------------------------------------
# usable_daylight_hours
# ---------------------------------------------------------------------------


def test_usable_never_exceeds_waking_window():
    """Usable daylight cannot exceed the waking-window width."""
    doy = np.arange(1, 366)
    for lat in [dl.LON_LAT, dl.NYC_LAT]:
        ud = dl.usable_daylight_hours(lat, doy)
        assert (ud <= dl.WAKING_HOURS + 1e-9).all()


def test_usable_never_negative():
    """Usable daylight is always ≥ 0."""
    doy = np.arange(1, 366)
    for lat in [dl.LON_LAT, dl.NYC_LAT]:
        ud = dl.usable_daylight_hours(lat, doy)
        assert (ud >= 0).all()


def test_usable_london_winter_all_daylight_usable():
    """In London's deep winter the entire short day falls within waking hours."""
    # Dec solstice: sunrise ≈ 08:10, sunset ≈ 15:50 — both inside [07:00, 23:00]
    doy = np.array([355])
    ud = dl.usable_daylight_hours(dl.LON_LAT, doy)[0]
    total = dl.day_length_hours(dl.LON_LAT, doy)[0]
    assert ud == pytest.approx(total, abs=0.05)


def test_usable_london_summer_less_than_day_length():
    """In London's summer, sunrise before 07:00 wastes early-morning daylight."""
    doy = np.array([172])
    ud = dl.usable_daylight_hours(dl.LON_LAT, doy)[0]
    total = dl.day_length_hours(dl.LON_LAT, doy)[0]
    assert ud < total


def test_usable_nyc_more_consistent_than_london():
    """NYC's usable daylight varies less across the year (lower latitude)."""
    doy = np.arange(1, 366)
    lon_std = dl.usable_daylight_hours(dl.LON_LAT, doy).std()
    nyc_std = dl.usable_daylight_hours(dl.NYC_LAT, doy).std()
    assert lon_std > nyc_std


def test_usable_custom_waking_window():
    """Custom wake/sleep times are correctly applied."""
    doy = np.array([172])
    # Very wide window (0–24 h): usable should equal full day length
    wide = dl.usable_daylight_hours(dl.LON_LAT, doy, wake=0.0, sleep=24.0)[0]
    full = dl.day_length_hours(dl.LON_LAT, doy)[0]
    assert wide == pytest.approx(full, abs=0.01)


# ---------------------------------------------------------------------------
# monthly_daylight_table
# ---------------------------------------------------------------------------


def test_monthly_table_shape():
    """Table has 12 rows and the expected columns."""
    tbl = dl.monthly_daylight_table(dl.LON_LAT)
    assert len(tbl) == 12
    for col in ["month", "day_length_h", "sunrise_h", "sunset_h", "usable_h", "usable_pct"]:
        assert col in tbl.columns


def test_monthly_table_month_values():
    """Month column contains 1–12."""
    tbl = dl.monthly_daylight_table(dl.NYC_LAT)
    assert (tbl["month"] == range(1, 13)).all()


def test_monthly_table_usable_pct_range():
    """usable_pct is between 0 and 100 for both cities."""
    for lat in [dl.LON_LAT, dl.NYC_LAT]:
        tbl = dl.monthly_daylight_table(lat)
        assert (tbl["usable_pct"] >= 0).all()
        assert (tbl["usable_pct"] <= 100).all()


def test_monthly_table_london_june_has_highest_usable():
    """London's peak usable daylight is in June (longest days)."""
    tbl = dl.monthly_daylight_table(dl.LON_LAT)
    peak_month = tbl.loc[tbl["usable_h"].idxmax(), "month"]
    assert peak_month == 6


def test_monthly_table_london_december_has_lowest_usable():
    """London's lowest usable daylight is in December."""
    tbl = dl.monthly_daylight_table(dl.LON_LAT)
    low_month = tbl.loc[tbl["usable_h"].idxmin(), "month"]
    assert low_month == 12


def test_monthly_table_nyc_higher_usable_in_winter():
    """NYC has more usable daylight than London in January and December."""
    lon = dl.monthly_daylight_table(dl.LON_LAT)
    nyc = dl.monthly_daylight_table(dl.NYC_LAT)
    for m in [1, 12]:
        lon_u = lon[lon["month"] == m]["usable_h"].iloc[0]
        nyc_u = nyc[nyc["month"] == m]["usable_h"].iloc[0]
        assert nyc_u > lon_u, f"NYC should have more usable daylight in month {m}"


def test_monthly_table_london_higher_usable_in_summer():
    """London has more usable daylight than NYC in June and July."""
    lon = dl.monthly_daylight_table(dl.LON_LAT)
    nyc = dl.monthly_daylight_table(dl.NYC_LAT)
    for m in [6, 7]:
        lon_u = lon[lon["month"] == m]["usable_h"].iloc[0]
        nyc_u = nyc[nyc["month"] == m]["usable_h"].iloc[0]
        assert lon_u > nyc_u, f"London should have more usable daylight in month {m}"
