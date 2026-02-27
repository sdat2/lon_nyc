"""Analysis functions for lon_nyc hourly rain data.

This module provides helpers to count rainy hours and summarize
precipitation statistics from processed NOAA ISD data.
"""

from __future__ import annotations

import logging

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
        * ``total_precip_mm``  – annual rainfall in mm
        * ``rainy_hours``      – hours with measurable precipitation
        * ``rainy_days``       – calendar days containing at least one rainy hour
    """
    if processed_df.empty or "precipitation_mm" not in processed_df.columns:
        logger.warning("No precipitation data available for '%s'.", label)
        return pd.DataFrame(
            columns=["label", "year", "total_precip_mm", "rainy_hours", "rainy_days"]
        )

    df = processed_df[["precipitation_mm"]].copy()
    df = df.dropna(subset=["precipitation_mm"])

    if df.empty:
        return pd.DataFrame(
            columns=["label", "year", "total_precip_mm", "rainy_hours", "rainy_days"]
        )

    dti = pd.DatetimeIndex(df.index)
    df["year"] = dti.year
    df["is_rainy_hour"] = df["precipitation_mm"] > threshold_mm
    # Normalise to date for day-level aggregation
    df["date"] = dti.normalize()

    yearly = (
        df.groupby("year")
        .agg(
            total_precip_mm=("precipitation_mm", "sum"),
            rainy_hours=("is_rainy_hour", "sum"),
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

    result = yearly.merge(rainy_days_per_year, on="year", how="left")
    result["rainy_days"] = result["rainy_days"].fillna(0).astype(int)
    result["rainy_hours"] = result["rainy_hours"].astype(int)
    result["label"] = label
    result = result[["label", "year", "total_precip_mm", "rainy_hours", "rainy_days"]]

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

