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
    baselines_c: dict[str, float] | None = None,
    label: str = "",
) -> pd.DataFrame:
    """Compute per-year temperature discomfort statistics from a processed DataFrame.

    For each baseline temperature *b* and each valid hourly observation *T*:

    * **cold deviation** = max(b − T, 0)  → how many °C below the baseline
    * **warm deviation** = max(T − b, 0)  → how many °C above the baseline

    All deviations are averaged over the number of valid observations in that
    year, giving a **mean °C deviation per observation**.  This normalisation
    makes stations with different observation densities (e.g. FM-12 SYNOP vs
    FM-15 METAR) directly comparable.

    Parameters
    ----------
    processed_df:
        Tidy DataFrame as returned by :func:`lon_nyc.noaa.process_temperature_data`.
        Must be indexed by a UTC-aware :class:`pandas.DatetimeIndex` and have a
        ``temp_c`` column.
    baselines_c:
        Dict mapping a human-readable label to a baseline temperature in °C.
        Defaults to :data:`lon_nyc.config.COMFORT_BASELINES_C`.
    label:
        Station/city label added as a column to the result.

    Returns
    -------
    pd.DataFrame
        One row per (year, baseline) combination with columns:

        * ``label``
        * ``year``
        * ``baseline_label``   – the key from *baselines_c*
        * ``baseline_c``       – the numeric baseline value
        * ``n_obs``            – number of valid temperature observations
        * ``mean_cold_dev_c``  – mean °C below baseline (heating pressure)
        * ``mean_warm_dev_c``  – mean °C above baseline (cooling pressure)
        * ``mean_abs_dev_c``   – mean total deviation (cold + warm)
    """
    if baselines_c is None:
        baselines_c = cfg.COMFORT_BASELINES_C

    empty_cols = [
        "label", "year", "baseline_label", "baseline_c",
        "n_obs", "mean_cold_dev_c", "mean_warm_dev_c", "mean_abs_dev_c",
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

    rows = []
    for bl_label, bl_c in baselines_c.items():
        df["cold_dev"] = (bl_c - df["temp_c"]).clip(lower=0)
        df["warm_dev"] = (df["temp_c"] - bl_c).clip(lower=0)

        yearly = (
            df.groupby("year")
            .agg(
                n_obs=("temp_c", "count"),
                sum_cold=("cold_dev", "sum"),
                sum_warm=("warm_dev", "sum"),
            )
            .reset_index()
        )
        yearly["mean_cold_dev_c"] = yearly["sum_cold"] / yearly["n_obs"]
        yearly["mean_warm_dev_c"] = yearly["sum_warm"] / yearly["n_obs"]
        yearly["mean_abs_dev_c"] = yearly["mean_cold_dev_c"] + yearly["mean_warm_dev_c"]
        yearly["baseline_label"] = bl_label
        yearly["baseline_c"] = bl_c
        yearly["label"] = label
        rows.append(yearly)

    result = pd.concat(rows, ignore_index=True)
    result = result[empty_cols]
    result["n_obs"] = result["n_obs"].astype(int)
    result = result.sort_values(["year", "baseline_c"]).reset_index(drop=True)

    logger.info(
        "Temperature summary for '%s': %d year×baseline rows.", label, len(result)
    )
    return result

