"""Analysis functions for lon_nyc hourly rain data.

This module provides helpers to count rainy hours and summarize
precipitation statistics from processed NOAA ISD data.
"""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
import pandas as pd

from lon_nyc import config as cfg

logger = logging.getLogger(__name__)


def rainy_hours_summary(
    processed_df: pd.DataFrame,
    threshold_mm: float = cfg.RAINY_THRESHOLD_MM,
    label: str = "",
) -> dict:
    """Summarise rainy-hour statistics for a processed precipitation DataFrame.

    An hour is considered **rainy** when ``precipitation_mm > threshold_mm``.

    Parameters
    ----------
    processed_df:
        Tidy DataFrame as returned by :func:`lon_nyc.noaa.process_precipitation_data`.
        Must have a ``precipitation_mm`` column.
    threshold_mm:
        Minimum precipitation in mm to count an hour as rainy.  Default is 0
        (any measurable precipitation).
    label:
        Optional station/city label included in the returned dict.

    Returns
    -------
    dict
        Keys:

        * ``label`` – the supplied label string
        * ``total_hours`` – number of rows with a non-NaN precipitation value
        * ``rainy_hours`` – number of hours exceeding *threshold_mm*
        * ``rainy_fraction`` – ``rainy_hours / total_hours`` (or NaN)
        * ``mean_precip_mm`` – mean precipitation over **rainy** hours (mm)
        * ``total_precip_mm`` – total precipitation over all hours (mm)
    """
    if processed_df.empty or "precipitation_mm" not in processed_df.columns:
        logger.warning("No precipitation data available for '%s'.", label)
        return {
            "label": label,
            "total_hours": 0,
            "rainy_hours": 0,
            "rainy_fraction": float("nan"),
            "mean_precip_mm": float("nan"),
            "total_precip_mm": float("nan"),
        }

    precip = processed_df["precipitation_mm"].dropna()
    total_hours = len(precip)
    rainy = precip[precip > threshold_mm]
    rainy_hours = len(rainy)
    rainy_fraction = rainy_hours / total_hours if total_hours > 0 else float("nan")

    return {
        "label": label,
        "total_hours": total_hours,
        "rainy_hours": rainy_hours,
        "rainy_fraction": rainy_fraction,
        "mean_precip_mm": float(rainy.mean()) if rainy_hours > 0 else float("nan"),
        "total_precip_mm": float(precip.sum()),
    }


def annual_summary(
    processed_df: pd.DataFrame,
    threshold_mm: float = cfg.RAINY_THRESHOLD_MM,
    label: str = "",
) -> pd.DataFrame:
    """Compute per-year precipitation statistics from a processed DataFrame.

    An hour is **rainy** when ``precipitation_mm > threshold_mm``.
    A calendar day is **rainy** when *any* of its hours are rainy.

    Parameters
    ----------
    processed_df:
        Tidy DataFrame as returned by :func:`lon_nyc.noaa.process_precipitation_data`.
        Must be indexed by a UTC-aware :class:`pandas.DatetimeIndex` and have a
        ``precipitation_mm`` column.
    threshold_mm:
        Minimum precipitation in mm to count an hour as rainy.
    label:
        Station/city label added as a column to the result.

    Returns
    -------
    pd.DataFrame
        One row per calendar year with columns:

        * ``label``
        * ``year``
        * ``total_precip_mm``   – annual rainfall in mm
        * ``rainy_hours``       – hours with measurable precipitation
        * ``rainy_days``        – calendar days containing at least one rainy hour
        * ``snow_hours``        – rainy hours also flagged as frozen (``is_snow=True``)
        * ``snow_days``         – calendar days with at least one snow hour
        * ``liquid_rain_hours`` – rainy hours that are *not* flagged as snow
        * ``liquid_rain_days``  – calendar days with at least one liquid-rain hour
                                  but *no* snow hours on the same day
    """
    if processed_df.empty or "precipitation_mm" not in processed_df.columns:
        logger.warning("No precipitation data available for '%s'.", label)
        return pd.DataFrame(
            columns=["label", "year", "total_precip_mm", "rainy_hours", "rainy_days",
                     "snow_hours", "snow_days", "liquid_rain_hours", "liquid_rain_days"]
        )

    df = processed_df[["precipitation_mm"]].copy()
    df = df.dropna(subset=["precipitation_mm"])

    if df.empty:
        return pd.DataFrame(
            columns=["label", "year", "total_precip_mm", "rainy_hours", "rainy_days",
                     "snow_hours", "snow_days", "liquid_rain_hours", "liquid_rain_days"]
        )

    dti = pd.DatetimeIndex(df.index)
    df["year"] = dti.year
    df["is_rainy_hour"] = df["precipitation_mm"] > threshold_mm
    # Normalise to date for day-level aggregation
    df["date"] = dti.normalize()

    # Propagate snow flag if available; default to False when column is absent
    # (e.g. when processing legacy DataFrames that pre-date the snow feature).
    if "is_snow" in processed_df.columns:
        df["is_snow"] = processed_df["is_snow"].reindex(df.index, fill_value=False)
    else:
        df["is_snow"] = False

    # A snow hour requires measurable precipitation AND a frozen-precip weather code.
    df["is_snow_hour"] = df["is_rainy_hour"] & df["is_snow"]
    df["is_liquid_rain_hour"] = df["is_rainy_hour"] & ~df["is_snow"]

    yearly = (
        df.groupby("year")
        .agg(
            total_precip_mm=("precipitation_mm", "sum"),
            rainy_hours=("is_rainy_hour", "sum"),
            snow_hours=("is_snow_hour", "sum"),
            liquid_rain_hours=("is_liquid_rain_hour", "sum"),
        )
        .reset_index()
    )

    # Rainy days: count distinct dates that contain at least one rainy hour
    rainy_days_per_year = (
        df[df["is_rainy_hour"]]
        .groupby("year")["date"]
        .nunique()
        .rename("rainy_days")
        .reset_index()
    )

    # Snow days: distinct dates with at least one snow hour
    snow_days_per_year = (
        df[df["is_snow_hour"]]
        .groupby("year")["date"]
        .nunique()
        .rename("snow_days")
        .reset_index()
    )

    # Liquid-rain days: dates that have at least one liquid-rain hour AND no snow
    # hours at all (i.e. entirely non-frozen precipitation days).
    dates_with_snow = (
        df[df["is_snow_hour"]]
        .groupby("year")["date"]
        .apply(set)
        .rename("snow_date_set")
        .reset_index()
    )
    liquid_rain_hour_dates = df[df["is_liquid_rain_hour"]][["year", "date"]].copy()
    # Merge in the set of snowy dates to exclude mixed days
    liquid_rain_hour_dates = liquid_rain_hour_dates.merge(
        dates_with_snow, on="year", how="left"
    )
    liquid_rain_hour_dates["snow_date_set"] = liquid_rain_hour_dates[
        "snow_date_set"
    ].apply(lambda x: x if isinstance(x, set) else set())
    # Keep only dates where the day had no snow at all
    liquid_rain_hour_dates = liquid_rain_hour_dates[
        liquid_rain_hour_dates.apply(
            lambda r: r["date"] not in r["snow_date_set"], axis=1
        )
    ]
    liquid_rain_days_per_year = (
        liquid_rain_hour_dates.groupby("year")["date"]
        .nunique()
        .rename("liquid_rain_days")
        .reset_index()
    )

    result = yearly.merge(rainy_days_per_year, on="year", how="left")
    result = result.merge(snow_days_per_year, on="year", how="left")
    result = result.merge(liquid_rain_days_per_year, on="year", how="left")

    for col in ("rainy_days", "snow_days", "liquid_rain_days"):
        result[col] = result[col].fillna(0).astype(int)
    for col in ("rainy_hours", "snow_hours", "liquid_rain_hours"):
        result[col] = result[col].astype(int)

    result["label"] = label
    result = result[
        ["label", "year", "total_precip_mm", "rainy_hours", "rainy_days",
         "snow_hours", "snow_days", "liquid_rain_hours", "liquid_rain_days"]
    ]

    logger.info("Annual summary for '%s': %d years.", label, len(result))
    return result


def annual_temperature_summary(
    processed_df: pd.DataFrame,
    hdd_base_c: float | None = None,
    cdd_base_c: float | None = None,
    comfort_base_c: float | None = None,
    label: str = "",
) -> pd.DataFrame:
    """Compute per-year temperature discomfort statistics from a processed DataFrame.

    Three standard metrics are computed, each from its own conventional baseline:

    * **HDD** (Heating Degree — hours): mean °C *below* ``hdd_base_c`` per
      observation (WMO / Met Office base: 15.5°C).
    * **CDD** (Cooling Degree — hours): mean °C *above* ``cdd_base_c`` per
      observation (standard base: 18°C).
    * **Comfort deviation**: mean °C deviation from ``comfort_base_c`` in
      *either* direction — i.e. mean(|T − base|) — from a single comfort
      temperature (default 21°C).

    All metrics are normalised by the number of valid hourly observations in
    that year, so stations with different reporting densities (FM-12 SYNOP
    ~24 obs/day vs FM-15 METAR ~12–24 obs/day) are directly comparable.

    Parameters
    ----------
    processed_df:
        Tidy DataFrame as returned by :func:`lon_nyc.noaa.process_temperature_data`.
        Must be indexed by a UTC-aware :class:`pandas.DatetimeIndex` and have a
        ``temp_c`` column.
    hdd_base_c:
        Baseline for HDD calculation.  Defaults to :data:`lon_nyc.config.HDD_BASE_C`.
    cdd_base_c:
        Baseline for CDD calculation.  Defaults to :data:`lon_nyc.config.CDD_BASE_C`.
    comfort_base_c:
        Baseline for comfort-deviation calculation.
        Defaults to :data:`lon_nyc.config.COMFORT_BASE_C`.
    label:
        Station/city label added as a column to the result.

    Returns
    -------
    pd.DataFrame
        One row per calendar year with columns:

        * ``label``
        * ``year``
        * ``n_obs``              – number of valid temperature observations
        * ``mean_hdd_c``         – mean °C below HDD base (heating pressure)
        * ``mean_cdd_c``         – mean °C above CDD base (cooling pressure)
        * ``mean_comfort_dev_c`` – mean |T − comfort base| (total discomfort)
        * ``sub_zero_hours``     – count of hours where T < 0°C
    """
    if hdd_base_c is None:
        hdd_base_c = cfg.HDD_BASE_C
    if cdd_base_c is None:
        cdd_base_c = cfg.CDD_BASE_C
    if comfort_base_c is None:
        comfort_base_c = cfg.COMFORT_BASE_C

    empty_cols = [
        "label", "year", "n_obs",
        "mean_hdd_c", "mean_cdd_c", "mean_comfort_dev_c", "sub_zero_hours",
    ]

    if processed_df.empty or "temp_c" not in processed_df.columns:
        logger.warning("No temperature data available for '%s'.", label)
        return pd.DataFrame(columns=empty_cols)

    df = processed_df[["temp_c"]].copy()
    df = df.dropna(subset=["temp_c"])

    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    dti = pd.DatetimeIndex(df.index)
    df["year"] = dti.year
    df["hdd"] = (hdd_base_c - df["temp_c"]).clip(lower=0)
    df["cdd"] = (df["temp_c"] - cdd_base_c).clip(lower=0)
    df["comfort_dev"] = (df["temp_c"] - comfort_base_c).abs()
    df["sub_zero"] = (df["temp_c"] < 0.0).astype(int)

    yearly = (
        df.groupby("year")
        .agg(
            n_obs=("temp_c", "count"),
            sum_hdd=("hdd", "sum"),
            sum_cdd=("cdd", "sum"),
            sum_comfort=("comfort_dev", "sum"),
            sub_zero_hours=("sub_zero", "sum"),
        )
        .reset_index()
    )
    yearly["mean_hdd_c"] = yearly["sum_hdd"] / yearly["n_obs"]
    yearly["mean_cdd_c"] = yearly["sum_cdd"] / yearly["n_obs"]
    yearly["mean_comfort_dev_c"] = yearly["sum_comfort"] / yearly["n_obs"]
    yearly["label"] = label
    yearly["n_obs"] = yearly["n_obs"].astype(int)
    yearly["sub_zero_hours"] = yearly["sub_zero_hours"].astype(int)

    result = yearly[empty_cols].reset_index(drop=True)

    logger.info("Temperature summary for '%s': %d years.", label, len(result))
    return result


def threshold_sensitivity(
    processed_df: pd.DataFrame,
    thresholds_mm: Sequence[float] | None = None,
    label: str = "",
) -> pd.DataFrame:
    """Compute mean annual rainy-hours and rainy-days across a range of thresholds.

    For each threshold value the function calls :func:`annual_summary`, then
    averages the per-year ``rainy_hours`` and ``rainy_days`` across all years
    present in *processed_df*.  This lets you see how sensitive the headline
    counts are to the choice of measurement threshold.

    Parameters
    ----------
    processed_df:
        Tidy DataFrame as returned by
        :func:`lon_nyc.noaa.process_precipitation_data`.  Must be indexed by a
        UTC-aware :class:`pandas.DatetimeIndex` and have a
        ``precipitation_mm`` column.
    thresholds_mm:
        Sequence of threshold values (mm) to sweep.  Defaults to 50 values
        log-spaced from 0.01 mm to 5 mm plus 0.0 mm.
    label:
        Station/city label added as a column to the result.

    Returns
    -------
    pd.DataFrame
        One row per threshold with columns:

        * ``label``              – station label
        * ``threshold_mm``       – the threshold tested
        * ``mean_rainy_hours``   – mean annual rainy hours across years
        * ``mean_rainy_days``    – mean annual rainy days across years
    """
    effective_thresholds: Sequence[float]
    if thresholds_mm is None:
        effective_thresholds = list(
            np.concatenate([[0.0], np.logspace(np.log10(0.01), np.log10(5.0), 50)])
        )
    else:
        effective_thresholds = thresholds_mm

    records = []
    for thr in effective_thresholds:
        summary = annual_summary(processed_df, threshold_mm=float(thr), label=label)
        if summary.empty:
            records.append(
                {
                    "label": label,
                    "threshold_mm": float(thr),
                    "mean_rainy_hours": float("nan"),
                    "mean_rainy_days": float("nan"),
                }
            )
        else:
            records.append(
                {
                    "label": label,
                    "threshold_mm": float(thr),
                    "mean_rainy_hours": float(summary["rainy_hours"].mean()),
                    "mean_rainy_days": float(summary["rainy_days"].mean()),
                }
            )

    result = pd.DataFrame(records).sort_values("threshold_mm").reset_index(drop=True)
    logger.info(
        "Threshold sensitivity for '%s': %d thresholds swept.", label, len(result)
    )
    return result
