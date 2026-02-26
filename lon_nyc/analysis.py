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

