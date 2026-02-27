"""Quantify the effect of latitude on usable daylight hours in London vs NYC.

London sits at ~51.5°N and New York City at ~40.7°N.  The higher latitude
makes London's day length much more seasonal: very long summer days (≈16.4 h
near the solstice) and very short winter days (≈7.6 h).  NYC's days are more
moderate year-round (≈14.9 h in summer, ≈9.1 h in winter).

This analysis quantifies how much of that daylight is actually *usable* given
typical waking hours.  Early-morning daylight before you wake up and late
evening daylight after typical bedtime are counted as wasted.  The key metric
is the fraction of waking hours spent in daylight.

All calculations are purely astronomical (no cloud cover, no NOAA data
required).  Sunrise/sunset are computed in local **solar time**, which is a
good proxy for clock time at these longitudes (London ≈ 0°W, NYC ≈ 74°W with
UTC−5 in winter / UTC−4 in summer).  Daylight Saving Time is not applied
here; the comparison is between the two latitudes, and DST affects both cities
similarly.

The sunrise equation used is the standard WMO approximation::

    δ = −23.45° × cos(360/365 × (doy + 10))
    cos(ω₀) = −tan(φ) × tan(δ)
    day_length = 2ω₀ / 15   (hours)

where *doy* is day-of-year (1–365), *φ* is latitude, and *ω₀* is the hour
angle at sunrise/sunset in degrees.

Run from the project root::

    python scripts/daylight_latitude.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Latitude of London Heathrow (°N).
LON_LAT: float = 51.5085

#: Latitude of New York City Central Park (°N).
NYC_LAT: float = 40.7128

#: Start of the assumed waking day (decimal hours, local solar time).
WAKE_HOUR: float = 7.0

#: End of the assumed waking day (decimal hours, local solar time).
SLEEP_HOUR: float = 23.0

#: Total waking hours per day.
WAKING_HOURS: float = SLEEP_HOUR - WAKE_HOUR

MONTH_NAMES: list[str] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


# ---------------------------------------------------------------------------
# Astronomical calculations
# ---------------------------------------------------------------------------


def solar_declination(day_of_year: np.ndarray) -> np.ndarray:
    """Return solar declination in radians for each day of year (1–365).

    Uses the standard approximation:
        δ = −23.45° × cos(360/365 × (doy + 10))
    """
    return np.radians(-23.45 * np.cos(np.radians(360.0 / 365 * (day_of_year + 10))))


def day_length_hours(lat_deg: float, day_of_year: np.ndarray) -> np.ndarray:
    """Astronomical day length in hours for a given latitude and day of year.

    Parameters
    ----------
    lat_deg:
        Geographic latitude in degrees north.
    day_of_year:
        Integer day(s) of year (1 = 1 Jan, 365 = 31 Dec).

    Returns
    -------
    np.ndarray
        Day length in decimal hours for each element of *day_of_year*.
    """
    delta = solar_declination(day_of_year)
    lat = np.radians(lat_deg)
    cos_omega = -np.tan(lat) * np.tan(delta)
    cos_omega = np.clip(cos_omega, -1.0, 1.0)
    return 2.0 * np.degrees(np.arccos(cos_omega)) / 15.0


def usable_daylight_hours(
    lat_deg: float,
    day_of_year: np.ndarray,
    wake: float = WAKE_HOUR,
    sleep: float = SLEEP_HOUR,
) -> np.ndarray:
    """Daylight hours that fall within the waking window [wake, sleep].

    Sunrise and sunset are expressed in local solar time (decimal hours from
    midnight).  Usable daylight is the overlap of [sunrise, sunset] and
    [wake, sleep], i.e.::

        usable = max(0, min(sunset, sleep) − max(sunrise, wake))

    Parameters
    ----------
    lat_deg:
        Geographic latitude in degrees north.
    day_of_year:
        Integer day(s) of year (1–365).
    wake:
        Start of waking day in decimal hours (default 7.0 = 07:00).
    sleep:
        End of waking day in decimal hours (default 23.0 = 23:00).

    Returns
    -------
    np.ndarray
        Usable daylight hours for each element of *day_of_year*.
    """
    dl = day_length_hours(lat_deg, day_of_year)
    sunrise = 12.0 - dl / 2.0
    sunset = 12.0 + dl / 2.0
    return np.clip(np.minimum(sunset, sleep) - np.maximum(sunrise, wake), 0.0, None)


def monthly_daylight_table(lat_deg: float, year: int = 2024) -> pd.DataFrame:
    """Build a monthly summary of day length and usable daylight.

    Parameters
    ----------
    lat_deg:
        Geographic latitude in degrees north.
    year:
        Calendar year to use for month lengths (day counts vary slightly for
        leap years).  Defaults to 2024 (a leap year giving 366 days).

    Returns
    -------
    pd.DataFrame
        One row per calendar month with columns:

        * ``month``          – calendar month number (1–12)
        * ``day_length_h``   – mean astronomical day length (hours)
        * ``sunrise_h``      – mean sunrise in decimal hours (solar time)
        * ``sunset_h``       – mean sunset in decimal hours (solar time)
        * ``usable_h``       – mean usable daylight hours within waking window
        * ``usable_pct``     – ``usable_h / WAKING_HOURS × 100``
    """
    dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    doy = dates.day_of_year.values
    dl = day_length_hours(lat_deg, doy)
    sunrise = 12.0 - dl / 2.0
    sunset = 12.0 + dl / 2.0
    ud = usable_daylight_hours(lat_deg, doy)

    df = pd.DataFrame(
        {
            "month": dates.month,
            "day_length_h": dl,
            "sunrise_h": sunrise,
            "sunset_h": sunset,
            "usable_h": ud,
        }
    )

    monthly = (
        df.groupby("month")
        .agg(
            day_length_h=("day_length_h", "mean"),
            sunrise_h=("sunrise_h", "mean"),
            sunset_h=("sunset_h", "mean"),
            usable_h=("usable_h", "mean"),
        )
        .reset_index()
    )
    monthly["usable_pct"] = monthly["usable_h"] / WAKING_HOURS * 100.0
    return monthly


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_time(decimal_hours: float) -> str:
    """Format decimal hours as HH:MM (24-hour local solar time)."""
    total_min = round(decimal_hours * 60)
    return f"{total_min // 60:02d}:{total_min % 60:02d}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    lon = monthly_daylight_table(LON_LAT)
    nyc = monthly_daylight_table(NYC_LAT)

    # Day-by-day arrays for annual statistics
    doy = np.arange(1, 366)
    lon_ud_daily = usable_daylight_hours(LON_LAT, doy)
    nyc_ud_daily = usable_daylight_hours(NYC_LAT, doy)

    print(
        "Daylight seasonality: London (51.5°N) vs New York City (40.7°N)\n"
        f"Waking window: {int(WAKE_HOUR):02d}:00–{int(SLEEP_HOUR):02d}:00 "
        f"({int(WAKING_HOURS)} h/day)\n"
    )

    # ── Monthly table ────────────────────────────────────────────────────────
    col_w = 76
    hdr = (
        f"{'Month':<5}  "
        f"{'LHR day':>7}  {'LHR rise':>8}  {'LHR set':>7}  {'LHR use':>7}  {'LHR%':>5}  "
        f"{'NYC day':>7}  {'NYC rise':>8}  {'NYC set':>7}  {'NYC use':>7}  {'NYC%':>5}"
    )
    sep = "─" * len(hdr)
    print(hdr)
    print(sep)

    for m in range(1, 13):
        lr = lon[lon["month"] == m].iloc[0]
        nr = nyc[nyc["month"] == m].iloc[0]
        print(
            f"{MONTH_NAMES[m - 1]:<5}  "
            f"{lr['day_length_h']:>7.1f}  "
            f"{_fmt_time(lr['sunrise_h']):>8}  "
            f"{_fmt_time(lr['sunset_h']):>7}  "
            f"{lr['usable_h']:>7.1f}  "
            f"{lr['usable_pct']:>4.1f}%  "
            f"{nr['day_length_h']:>7.1f}  "
            f"{_fmt_time(nr['sunrise_h']):>8}  "
            f"{_fmt_time(nr['sunset_h']):>7}  "
            f"{nr['usable_h']:>7.1f}  "
            f"{nr['usable_pct']:>4.1f}%"
        )

    print(sep)

    # Annual summary row
    lon_ann_dl = day_length_hours(LON_LAT, doy).mean()
    nyc_ann_dl = day_length_hours(NYC_LAT, doy).mean()
    lon_ann_ud = lon_ud_daily.mean()
    nyc_ann_ud = nyc_ud_daily.mean()
    print(
        f"{'Year':<5}  "
        f"{lon_ann_dl:>7.1f}  "
        f"{'':>8}  "
        f"{'':>7}  "
        f"{lon_ann_ud:>7.1f}  "
        f"{lon_ann_ud / WAKING_HOURS * 100:>4.1f}%  "
        f"{nyc_ann_dl:>7.1f}  "
        f"{'':>8}  "
        f"{'':>7}  "
        f"{nyc_ann_ud:>7.1f}  "
        f"{nyc_ann_ud / WAKING_HOURS * 100:>4.1f}%"
    )
    print()

    # ── Seasonal variance ────────────────────────────────────────────────────
    lon_dl_std = day_length_hours(LON_LAT, doy).std()
    nyc_dl_std = day_length_hours(NYC_LAT, doy).std()

    print("Seasonal variability (std dev of daily values):")
    print(
        f"  Day length:    London {lon_dl_std:.2f} h/day  |  "
        f"NYC {nyc_dl_std:.2f} h/day  "
        f"(London {lon_dl_std / nyc_dl_std:.1f}× more variable)"
    )
    print(
        f"  Usable daylt:  London {lon_ud_daily.std():.2f} h/day  |  "
        f"NYC {nyc_ud_daily.std():.2f} h/day"
    )
    print()

    # ── Key finding ──────────────────────────────────────────────────────────
    nyc_advantage_h_per_day = nyc_ann_ud - lon_ann_ud
    nyc_advantage_h_per_year = nyc_advantage_h_per_day * 365
    print("Key findings:")
    print(
        f"  Annual-mean usable daylight:\n"
        f"    London: {lon_ann_ud:.2f} h/day  "
        f"({lon_ann_ud / WAKING_HOURS * 100:.1f}% of waking hours)\n"
        f"    NYC:    {nyc_ann_ud:.2f} h/day  "
        f"({nyc_ann_ud / WAKING_HOURS * 100:.1f}% of waking hours)"
    )
    print(
        f"\n  NYC advantage: {nyc_advantage_h_per_day:+.2f} h/day "
        f"≈ {nyc_advantage_h_per_year:+.0f} h/year of usable daylight"
    )
    print(
        f"\n  London's day length is {lon_dl_std / nyc_dl_std:.1f}× more variable\n"
        f"  across the year, but extra summer hours fall before wake-up\n"
        f"  (before {_fmt_time(WAKE_HOUR)}) and are therefore unusable."
    )
    print(
        "\nNote: sunrise/sunset are in local solar time (WMO approximation).\n"
        "Daylight Saving Time is not applied; DST shifts both cities equally."
    )


if __name__ == "__main__":
    main()
