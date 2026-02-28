"""Download and process NOAA Integrated Surface Database (ISD) hourly data.

Data are stored on the public AWS S3 bucket ``noaa-global-hourly-pds``.
The object key format is ``YYYY/USAFWBAN.csv`` — note that the hyphen
between the USAF and WBAN identifiers is **omitted** in the key, even
though the station ID is conventionally written as ``USAF-WBAN``.

Precipitation is encoded in the compound ``AA1`` field.  The four
comma-separated sub-fields are::

    period_hours,depth_tenths_mm,condition_code,quality_code

For example ``"01,0005,C,5"`` means 0.5 mm accumulated over the last
1 hour.  A depth value of ``"9999"`` or ``"+9999"`` signals a missing
observation.

Only FM-15 (regular hourly METAR) observations are used.  FM-16 SPECI
reports are excluded because they are filed sub-hourly during significant
weather changes; their AA1 accumulation periods are shorter and variable,
so mixing them with FM-15s causes substantial double-counting.

Units
-----
ISD AA1 depth is in **tenths of millimetres**; this module converts to
**mm** before returning results.
"""

from __future__ import annotations

import io
import logging
from typing import Sequence

import boto3
import numpy as np
import pandas as pd
from botocore import UNSIGNED
from botocore.client import Config

from lon_nyc import config as cfg

logger = logging.getLogger(__name__)

S3_BUCKET: str = "noaa-global-hourly-pds"

# Report types that correspond to reliable hourly surface observations.
# FM-15 = METAR (regular hourly).  FM-16 = SPECI (special/non-routine METAR)
# is excluded because SPECIs are filed sub-hourly during weather changes and
# their AA1 depths cover variable short periods; including them alongside
# FM-15s causes significant double-counting of precipitation totals.
# FM-12 = SYNOP (WMO surface synoptic observation, used at many non-US stations
# such as London Heathrow, where AA1 precipitation data is reported on FM-12
# rows rather than FM-15 rows).
#
# ORDER MATTERS for temperature deduplication: when both FM-12 and FM-15 rows
# exist at the same timestamp, process_temperature_data keeps the type listed
# FIRST.  FM-12 is listed first because Heathrow's FM-12 (SYNOP) rows carry
# 0.1 °C temperature resolution, whereas its FM-15 (METAR) rows are stored at
# whole-degree resolution in ISD — producing large artificial spikes in the
# histogram at every integer °C.  NYC only files FM-15, so the ordering has no
# effect there.  For precipitation the order is irrelevant because the two
# report types are kept separately before deduplication by timestamp.
HOURLY_REPORT_TYPES: list[str] = ["FM-12", "FM-15"]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def make_s3_client():
    """Return an anonymous (unsigned) boto3 S3 client for public buckets."""
    return boto3.client("s3", config=Config(signature_version=UNSIGNED))


def generate_s3_file_keys(
    station_id: str, start_year: int, end_year: int
) -> list[str]:
    """Generate S3 object keys for *station_id* over ``[start_year, end_year]``.

    The ISD S3 key format is ``YYYY/USAFWBAN.csv`` — the hyphen that
    separates the USAF and WBAN codes in the conventional ``USAF-WBAN``
    station ID string is **not** present in the filename.  For example,
    station ``725053-94728`` maps to the key ``2023/72505394728.csv``.

    Parameters
    ----------
    station_id:
        Station identifier in ``USAF-WBAN`` format, e.g. ``"725053-94728"``.
        The hyphen is stripped automatically when constructing the S3 key.
    start_year:
        First year to include (inclusive).
    end_year:
        Last year to include (inclusive).

    Returns
    -------
    list[str]
        Ordered list of S3 object keys.
    """
    # The S3 bucket stores files without the hyphen separator, e.g.
    # "2023/72505394728.csv" rather than "2023/725053-94728.csv".
    station_id_no_dash = station_id.replace("-", "")
    file_keys: list[str] = []
    for year in range(start_year, end_year + 1):
        file_keys.append(f"{year}/{station_id_no_dash}.csv")
    logger.info(
        "Generated %d S3 keys for station %s (%d–%d).",
        len(file_keys),
        station_id,
        start_year,
        end_year,
    )
    return file_keys


def download_and_concatenate_s3_csvs(
    s3_client,
    bucket_name: str,
    file_keys: Sequence[str],
    cache_dir: str | None = None,
) -> pd.DataFrame:
    """Download ISD CSV files from S3 and concatenate them into one DataFrame.

    Downloaded files are cached to *cache_dir* (default: ``.cache/`` relative
    to the current working directory) so that repeated runs do not re-fetch
    the same data from S3.  Pass ``cache_dir=""`` to disable caching.

    Parameters
    ----------
    s3_client:
        A boto3 S3 client (e.g. from :func:`make_s3_client`).
    bucket_name:
        Name of the S3 bucket.
    file_keys:
        Iterable of object keys to download.
    cache_dir:
        Directory in which to cache raw CSV files.  Defaults to ``.cache``.
        Set to ``""`` or ``None`` to disable caching.

    Returns
    -------
    pd.DataFrame
        Concatenated raw data, or an empty DataFrame if nothing could be
        downloaded.
    """
    import pathlib

    if cache_dir is None:
        cache_dir = ".cache"

    cache_path = pathlib.Path(cache_dir) if cache_dir else None
    if cache_path is not None:
        cache_path.mkdir(parents=True, exist_ok=True)

    frames: list[pd.DataFrame] = []
    for key in file_keys:
        # Use a flat filename derived from the key to avoid subdirectory issues
        cache_file = cache_path / key.replace("/", "_") if cache_path else None

        try:
            if cache_file is not None and cache_file.exists():
                logger.info("Cache hit: %s", cache_file)
                df = pd.read_csv(
                    cache_file,
                    dtype=str,
                    keep_default_na=False,
                    na_values=[""],
                )
            else:
                logger.info("Downloading s3://%s/%s", bucket_name, key)
                obj = s3_client.get_object(Bucket=bucket_name, Key=key)
                raw_bytes = obj["Body"].read()
                if cache_file is not None:
                    cache_file.write_bytes(raw_bytes)
                    logger.info("Cached to %s", cache_file)
                df = pd.read_csv(
                    io.BytesIO(raw_bytes),
                    dtype=str,
                    keep_default_na=False,
                    na_values=[""],
                )
            frames.append(df)
            logger.info("Loaded %s (%d rows).", key, len(df))
        except s3_client.exceptions.NoSuchKey:
            logger.warning("Not found in S3: s3://%s/%s – skipping.", bucket_name, key)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error downloading %s: %s", key, exc)

    if not frames:
        logger.warning("No data downloaded; returning empty DataFrame.")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info("Combined DataFrame: %d rows.", len(combined))
    return combined


def parse_aw_snow_flag(df: pd.DataFrame) -> pd.Series:
    """Return a boolean Series indicating whether each row carries a snow/frozen code.

    The ISD automated present-weather fields ``AW1``, ``AW2``, and ``AW3``
    (when present) each encode a single weather phenomenon as::

        condition_code,quality_code

    A row is considered a **snow hour** when *any* of the available ``AWn``
    columns contains a condition code that is a member of
    :data:`lon_nyc.config.AW_SNOW_CODES`.  The full set of frozen-precip codes
    is documented in that constant (broadly: ISD codes 70–79 for continuous
    snow / ice pellets and 83–89 for snow showers and mixed rain/snow).

    Parameters
    ----------
    df:
        Raw or processed ISD DataFrame that may contain ``AW1``, ``AW2``,
        and/or ``AW3`` columns.

    Returns
    -------
    pd.Series
        Boolean Series (same index as *df*), ``True`` where frozen precipitation
        is indicated by at least one ``AWn`` field.
    """
    snow_flag = pd.Series(False, index=df.index, dtype=bool)
    for col in cfg.AW_COLUMNS:
        if col not in df.columns:
            continue
        # Extract the leading condition code (first comma-delimited sub-field).
        # .dropna() gives a narrower Series, so we use fillna("") to keep the
        # full index before calling .str — this avoids the MultiIndex / dtype error
        # that arises when the column is entirely NaN.
        raw_col = df[col].fillna("")
        codes = raw_col.str.split(",").str[0].str.strip()
        is_snow = codes.isin(cfg.AW_SNOW_CODES)
        snow_flag = snow_flag | is_snow
    return snow_flag


def parse_aa1_depth_mm(series: pd.Series) -> pd.Series:
    """Extract precipitation depth (mm) from the ISD ``AA1`` compound field.

    The ``AA1`` field has the form::

        period_hours,depth_tenths_mm,condition_code,quality_code

    The **depth** is the *second* sub-field (index 1), given as an integer
    in tenths of millimetres.  Missing observations are coded as ``9999``
    or ``+9999``; these are returned as NaN.  A depth of ``0`` (no
    measurable precipitation) is returned as 0.0 mm.

    Parameters
    ----------
    series:
        Raw string values of the ``AA1`` column.

    Returns
    -------
    pd.Series
        Precipitation depth in **mm** (float), with NaN for missing values.
    """

    def _extract(val) -> float:
        if pd.isna(val):
            return float("nan")
        # AA1 sub-fields: period_hours, depth_tenths_mm, condition_code, quality_code
        parts = str(val).split(",")
        if len(parts) < 2:
            return float("nan")
        depth_str = parts[1].strip()
        if depth_str in cfg.AA1_MISSING_DEPTHS:
            return float("nan")
        try:
            return int(depth_str) / 10.0
        except ValueError:
            return float("nan")

    return series.map(_extract)


def process_precipitation_data(
    raw_df: pd.DataFrame,
    report_types: list[str] | None = None,
) -> pd.DataFrame:
    """Clean raw ISD data and return a tidy precipitation DataFrame.

    Precipitation is sourced from the ``AA1`` column (ISD compound field).
    The result contains a ``precipitation_mm`` column with values in mm.

    Parameters
    ----------
    raw_df:
        Raw DataFrame as returned by :func:`download_and_concatenate_s3_csvs`.
    report_types:
        If non-empty, keep only rows whose ``REPORT_TYPE`` is in this list.
        Defaults to :data:`HOURLY_REPORT_TYPES`.  Pass ``[]`` to disable
        filtering.

    Returns
    -------
    pd.DataFrame
        Processed DataFrame indexed by ``DATE`` (UTC datetime), with at least
        the ``precipitation_mm`` column and an ``is_snow`` boolean column
        indicating whether the observation hour carried a frozen-precipitation
        weather code (AW1/AW2/AW3 codes in :data:`lon_nyc.config.AW_SNOW_CODES`).
    """
    if report_types is None:
        report_types = HOURLY_REPORT_TYPES

    if raw_df.empty:
        logger.warning("Input DataFrame is empty; cannot process.")
        return pd.DataFrame()

    if "DATE" not in raw_df.columns:
        logger.error("'DATE' column is missing; returning empty DataFrame.")
        return pd.DataFrame()

    df = raw_df.copy()

    # --- Parse timestamp ---
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce", utc=True)
    df.dropna(subset=["DATE"], inplace=True)
    df.set_index("DATE", inplace=True)

    # --- Parse precipitation ---
    if cfg.AA1_COLUMN in df.columns:
        df["precipitation_mm"] = parse_aa1_depth_mm(df[cfg.AA1_COLUMN])
    else:
        logger.warning(
            "'%s' column not found; 'precipitation_mm' will be NaN.", cfg.AA1_COLUMN
        )
        df["precipitation_mm"] = np.nan

    # --- Parse snow flag from automated present-weather fields (AW1/AW2/AW3) ---
    # An hour is flagged as snow/frozen when any AWn field carries a code from
    # cfg.AW_SNOW_CODES (ISD codes 70–79, 83–89).
    df["is_snow"] = parse_aw_snow_flag(df)

    # --- Filter by report type ---
    if report_types and "REPORT_TYPE" in df.columns:
        before = len(df)
        df = df[df["REPORT_TYPE"].astype(str).isin(report_types)]
        logger.info(
            "Filtered by REPORT_TYPE %s: kept %d/%d rows.",
            report_types,
            len(df),
            before,
        )
    elif report_types:
        logger.warning(
            "'REPORT_TYPE' column not found; skipping report-type filter."
        )

    # --- Deduplicate (keep first occurrence per timestamp) ---
    df = df[~df.index.duplicated(keep="first")]
    df.sort_index(inplace=True)

    # --- Select output columns ---
    keep = ["precipitation_mm", "is_snow"]
    for col in ("STATION", "NAME", "REPORT_TYPE", "SOURCE"):
        if col in df.columns:
            keep.insert(0, col)

    logger.info("Processed DataFrame: %d rows.", len(df))
    return df[[c for c in keep if c in df.columns]]


def parse_tmp_celsius(series: pd.Series) -> pd.Series:
    """Parse the ISD ``TMP`` field into °C (float), with NaN for missing or bad values.

    The ``TMP`` field has the form::

        +TTTT,Q

    where ``TTTT`` is air temperature in **tenths of °C** (signed integer) and
    ``Q`` is a quality flag.  Missing observations use the sentinel ``+9999``.
    Observations whose quality flag indicates a suspect or erroneous reading
    (codes 2, 3, 6, 7, 9 — see :data:`lon_nyc.config.TMP_REJECTED_QUALITY_FLAGS`)
    are returned as NaN and excluded from all downstream analysis.

    Parameters
    ----------
    series:
        Raw string values of the ``TMP`` column.

    Returns
    -------
    pd.Series
        Air temperature in **°C** (float), with NaN for missing or bad-quality values.
    """

    def _extract(val) -> float:
        if pd.isna(val):
            return float("nan")
        parts = str(val).split(",")
        temp_str = parts[0].strip()
        if temp_str in cfg.TMP_MISSING:
            return float("nan")
        # Reject observations flagged as suspect, erroneous, or missing
        if len(parts) >= 2 and parts[1].strip() in cfg.TMP_REJECTED_QUALITY_FLAGS:
            return float("nan")
        try:
            return int(temp_str) / 10.0
        except ValueError:
            return float("nan")

    return series.map(_extract)


def process_temperature_data(
    raw_df: pd.DataFrame,
    report_types: list[str] | None = None,
) -> pd.DataFrame:
    """Clean raw ISD data and return a tidy temperature DataFrame.

    Temperature is sourced from the ``TMP`` column (ISD mandatory field).
    The result contains a ``temp_c`` column with values in °C.

    When multiple rows share the same timestamp, the row whose ``REPORT_TYPE``
    appears **earliest** in *report_types* is kept.  The default order is
    ``["FM-12", "FM-15"]``, which means FM-12 (SYNOP — 0.1 °C resolution at
    Heathrow) is preferred over FM-15 (METAR — whole-degree resolution at
    Heathrow) when both are present.  NYC Central Park only files FM-15 reports
    so the ordering has no effect there.

    Parameters
    ----------
    raw_df:
        Raw DataFrame as returned by :func:`download_and_concatenate_s3_csvs`.
    report_types:
        If non-empty, keep only rows whose ``REPORT_TYPE`` is in this list.
        Defaults to :data:`HOURLY_REPORT_TYPES`.  Pass ``[]`` to disable
        filtering.  The list order determines deduplication priority — the
        first matching type per timestamp is kept.

    Returns
    -------
    pd.DataFrame
        Processed DataFrame indexed by ``DATE`` (UTC datetime), with at least
        the ``temp_c`` column.
    """
    if report_types is None:
        report_types = HOURLY_REPORT_TYPES

    if raw_df.empty:
        logger.warning("Input DataFrame is empty; cannot process temperature.")
        return pd.DataFrame()

    if "DATE" not in raw_df.columns:
        logger.error("'DATE' column is missing; returning empty DataFrame.")
        return pd.DataFrame()

    df = raw_df.copy()

    # --- Parse timestamp ---
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce", utc=True)
    df.dropna(subset=["DATE"], inplace=True)
    df.set_index("DATE", inplace=True)

    # --- Parse temperature ---
    if cfg.TMP_COLUMN in df.columns:
        df["temp_c"] = parse_tmp_celsius(df[cfg.TMP_COLUMN])
    else:
        logger.warning(
            "'%s' column not found; 'temp_c' will be NaN.", cfg.TMP_COLUMN
        )
        df["temp_c"] = np.nan

    # --- Filter by report type ---
    if report_types and "REPORT_TYPE" in df.columns:
        before = len(df)
        df = df[df["REPORT_TYPE"].astype(str).isin(report_types)]
        logger.info(
            "Filtered by REPORT_TYPE %s: kept %d/%d rows.",
            report_types,
            len(df),
            before,
        )
    elif report_types:
        logger.warning(
            "'REPORT_TYPE' column not found; skipping report-type filter."
        )

    # --- Drop lower-priority report types when higher-priority ones are present ---
    # At stations like London Heathrow, FM-12 (SYNOP) and FM-15 (METAR) rows
    # occupy *different* timestamps, so the deduplication step cannot choose
    # between them.  Heathrow FM-15 records temperature at whole-degree
    # resolution, producing artificial histogram spikes, while FM-12 rows have
    # genuine 0.1 °C resolution.  If any FM-12 data is present in the dataset
    # we therefore discard all FM-15 rows for temperature entirely, keeping
    # FM-15 only at stations (like NYC) that file no FM-12 reports.
    if report_types and "REPORT_TYPE" in df.columns and len(report_types) > 1:
        rt_col = df["REPORT_TYPE"].astype(str)
        for i, preferred in enumerate(report_types[:-1]):
            if (rt_col == preferred).any():
                # Higher-priority type is present — drop everything below it
                drop_types = set(report_types[i + 1:])
                before = len(df)
                df = df[~rt_col.isin(drop_types)]
                logger.info(
                    "Station has '%s' data; dropped lower-priority types %s "
                    "(%d → %d rows) to avoid mixed-resolution temperature bias.",
                    preferred,
                    drop_types,
                    before,
                    len(df),
                )
                break

    # --- Sort by report-type priority before deduplication ---
    # Assign a numeric priority based on position in report_types so that when
    # two rows share a timestamp the preferred type is kept.  Lower rank = higher
    # priority (kept first after sort).
    if report_types and "REPORT_TYPE" in df.columns:
        priority = {rt: i for i, rt in enumerate(report_types)}
        df["_rt_priority"] = (
            df["REPORT_TYPE"].astype(str).map(priority).fillna(len(report_types))
        )
        df.sort_values("_rt_priority", kind="stable", inplace=True)
        df.drop(columns=["_rt_priority"], inplace=True)

    # --- Deduplicate (keep first occurrence per timestamp, i.e. highest priority) ---
    df = df[~df.index.duplicated(keep="first")]
    df.sort_index(inplace=True)

    # --- Select output columns ---
    keep = ["temp_c"]
    for col in ("STATION", "NAME", "REPORT_TYPE", "SOURCE"):
        if col in df.columns:
            keep.insert(0, col)

    logger.info("Processed temperature DataFrame: %d rows.", len(df))
    return df[[c for c in keep if c in df.columns]]
