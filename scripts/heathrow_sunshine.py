"""Compute mean monthly sunshine hours at London Heathrow from NOAA ISD data.

Sunshine duration is encoded in ISD as the WMO SYNOP ``55SSS`` group, which
appears in the free-text ``REM`` field of FM-12 (SYNOP) rows.  The group gives
duration in **tenths of hours** over the preceding hour.  Values >= 300 are
WMO sentinel/missing codes and are discarded.

The script fetches 2020–2024 Heathrow data (using the same S3 bucket and
caching logic as the rest of the lon_nyc project), extracts valid sunshine
readings, converts to hours, and aggregates to monthly means.  The results
are compared against the Wikipedia/Met Office 1991–2020 long-term normals for
Heathrow.

Run from the project root::

    python scripts/heathrow_sunshine.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow imports from the package without installing in editable mode.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lon_nyc import config as cfg
from lon_nyc.noaa import (
    S3_BUCKET,
    download_and_concatenate_s3_csvs,
    generate_s3_file_keys,
    make_s3_client,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
START_YEAR = 2015
END_YEAR = 2024

# 1991–2020 Heathrow long-term normals (hours/month), from Met Office / Wikipedia.
# https://en.wikipedia.org/wiki/London_Heathrow_Airport#Climate
WIKI_NORMALS: dict[int, float] = {
    1: 57.5,
    2: 77.8,
    3: 111.5,
    4: 157.3,
    5: 192.0,
    6: 196.4,
    7: 203.3,
    8: 196.8,
    9: 144.7,
    10: 100.9,
    11: 62.8,
    12: 44.6,
}
MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# ---------------------------------------------------------------------------
# Regex to extract the 55SSS sunshine group from the REM field.
# The group is 55 followed by exactly three digits (SSS = tenths of hours).
# ---------------------------------------------------------------------------
RE_55SSS = re.compile(r"\b55(\d{3})\b")


def extract_sunshine_tenths(rem: str) -> int | None:
    """Return the SSS value (tenths of hours) from a REM field, or None."""
    m = RE_55SSS.search(rem)
    if m is None:
        return None
    val = int(m.group(1))
    # WMO: values 300–399 are special codes (not measured), >=400 undefined.
    if val >= 300:
        return None
    return val


def main() -> None:
    print(f"Fetching Heathrow ISD data {START_YEAR}–{END_YEAR} …")
    s3 = make_s3_client()
    keys = generate_s3_file_keys(cfg.LON_STATION_ID, START_YEAR, END_YEAR)
    raw = download_and_concatenate_s3_csvs(s3, S3_BUCKET, keys, cache_dir=".cache")

    if raw.empty:
        print("ERROR: no data downloaded.", file=sys.stderr)
        sys.exit(1)

    # Keep only FM-12 (SYNOP) rows — that's where 55SSS appears at Heathrow.
    fm12 = raw[raw["REPORT_TYPE"].str.startswith("FM-12", na=False)].copy()
    print(f"  Total rows: {len(raw):,}  |  FM-12 rows: {len(fm12):,}")

    # Drop rows with no REM field.
    fm12 = fm12.dropna(subset=["REM"])
    print(f"  FM-12 rows with REM: {len(fm12):,}")

    # Parse timestamps.
    fm12["dt"] = pd.to_datetime(fm12["DATE"], utc=True, errors="coerce")
    fm12 = fm12.dropna(subset=["dt"])
    fm12["year"]  = fm12["dt"].dt.year
    fm12["month"] = fm12["dt"].dt.month

    # Extract sunshine values.
    fm12["sunshine_tenths"] = fm12["REM"].map(extract_sunshine_tenths)
    valid = fm12.dropna(subset=["sunshine_tenths"]).copy()
    valid["sunshine_h"] = valid["sunshine_tenths"].astype(float) / 10.0

    print(f"  Valid 55SSS observations: {len(valid):,}")
    print()

    # ---------------------------------------------------------------------------
    # Monthly totals per year, then mean over years.
    # ---------------------------------------------------------------------------
    # Sum sunshine hours within each (year, month) pair.
    monthly_totals = (
        valid.groupby(["year", "month"])["sunshine_h"]
        .sum()
        .reset_index()
        .rename(columns={"sunshine_h": "total_h"})
    )

    # Mean across years for each calendar month.
    mean_by_month = (
        monthly_totals.groupby("month")["total_h"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    mean_by_month.columns = ["month", "mean_h", "std_h", "n_years"]

    # Annual totals per year (for a sanity check).
    annual = monthly_totals.groupby("year")["total_h"].sum()

    # ---------------------------------------------------------------------------
    # Print year-by-year annual sunshine.
    # ---------------------------------------------------------------------------
    print("Annual sunshine totals (hours):")
    for yr, total in annual.items():
        print(f"  {yr}: {total:.0f} h")
    print()

    # ---------------------------------------------------------------------------
    # Month-by-month comparison table.
    # ---------------------------------------------------------------------------
    wiki_annual = sum(WIKI_NORMALS.values())
    obs_annual  = mean_by_month["mean_h"].sum()

    header = f"{'Month':<5}  {'Obs(h)':>7}  {'±σ':>6}  {'Wiki(h)':>7}  {'Δ(h)':>6}"
    sep    = "-" * len(header)
    print(header)
    print(sep)
    for _, row in mean_by_month.iterrows():
        m    = int(row["month"])
        obs  = row["mean_h"]
        std  = row["std_h"]
        wiki = WIKI_NORMALS.get(m, float("nan"))
        diff = obs - wiki
        name = MONTH_NAMES[m - 1]
        print(f"{name:<5}  {obs:>7.1f}  {std:>6.1f}  {wiki:>7.1f}  {diff:>+6.1f}")
    print(sep)
    print(
        f"{'Total':<5}  {obs_annual:>7.1f}  {'':>6}  "
        f"{wiki_annual:>7.1f}  {obs_annual - wiki_annual:>+6.1f}"
    )
    print()
    print(
        "Note: observed values are means of monthly totals over "
        f"{START_YEAR}–{END_YEAR} ({END_YEAR - START_YEAR + 1} years).\n"
        "Wiki normals are 1991–2020 Met Office long-term averages."
    )


if __name__ == "__main__":
    main()
