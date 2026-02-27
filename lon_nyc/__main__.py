"""Command-line entry point for the lon_nyc package.

Run with::

    python -m lon_nyc [--start YEAR] [--end YEAR]

or, if installed::

    lon-nyc [--start YEAR] [--end YEAR]
"""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from lon_nyc import analysis, config, noaa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def _fetch_annual(
    s3,
    station_id: str,
    label: str,
    start: int,
    end: int,
) -> pd.DataFrame:
    """Download ISD data for one station and return annual summary rows."""
    keys = noaa.generate_s3_file_keys(station_id, start, end)
    raw = noaa.download_and_concatenate_s3_csvs(s3, noaa.S3_BUCKET, keys)
    processed = noaa.process_precipitation_data(raw)
    return analysis.annual_summary(processed, label=label)


def _fetch_annual_temperature(
    s3,
    station_id: str,
    label: str,
    start: int,
    end: int,
) -> pd.DataFrame:
    """Download ISD data for one station and return annual temperature summary rows."""
    keys = noaa.generate_s3_file_keys(station_id, start, end)
    raw = noaa.download_and_concatenate_s3_csvs(s3, noaa.S3_BUCKET, keys)
    processed = noaa.process_temperature_data(raw)
    return analysis.annual_temperature_summary(processed, label=label)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download NOAA ISD data and print annual rain statistics "
            "for London (Heathrow) and New York City (Central Park)."
        )
    )
    parser.add_argument(
        "--start", type=int, default=2020, metavar="YEAR", help="First year (default: 2020)"
    )
    parser.add_argument(
        "--end", type=int, default=2025, metavar="YEAR", help="Last year (default: 2025)"
    )
    args = parser.parse_args(argv)

    s3 = noaa.make_s3_client()

    stations = [
        (config.LON_STATION_ID, config.LON_LABEL),
        (config.NYC_STATION_ID, config.NYC_LABEL),
    ]

    frames = []
    temp_frames = []
    for station_id, label in stations:
        frames.append(_fetch_annual(s3, station_id, label, args.start, args.end))
        temp_frames.append(_fetch_annual_temperature(s3, station_id, label, args.start, args.end))

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["year", "label"]).reset_index(drop=True)

    combined_temp = pd.concat(temp_frames, ignore_index=True)
    combined_temp = combined_temp.sort_values(["year", "label"]).reset_index(drop=True)

    # ── Print precipitation table ─────────────────────────────────────────────
    print(
        f"\n{'Annual Precipitation Summary':=^72}\n"
        f"{'Years':>4} {args.start}–{args.end} | "
        f"threshold: >{config.RAINY_THRESHOLD_MM} mm\n"
    )

    header = f"{'Year':<6} {'City':<32} {'Total (mm)':>10} {'Rainy hrs':>10} {'Rainy days':>11}"
    print(header)
    print("-" * len(header))

    for _, row in combined.iterrows():
        print(
            f"{int(row['year']):<6} {row['label']:<32} "
            f"{row['total_precip_mm']:>10.1f} "
            f"{int(row['rainy_hours']):>10} "
            f"{int(row['rainy_days']):>11}"
        )
        if row.name < len(combined) - 1 and combined.loc[row.name + 1, "year"] != row["year"]:
            print()

    # ── Print temperature discomfort table ────────────────────────────────────
    # HDD = mean °C below 15.5°C per obs (heating pressure)
    # CDD = mean °C above 18°C per obs   (cooling pressure)
    # Comfort dev = mean |T − 21°C| per obs (total discomfort from both sides)
    print(
        f"\n{'Annual Temperature Discomfort (mean °C per observation)':=^80}\n"
        f"{'Years':>4} {args.start}–{args.end} | "
        f"HDD base: {config.HDD_BASE_C}°C  "
        f"CDD base: {config.CDD_BASE_C}°C  "
        f"Comfort base: {config.COMFORT_BASE_C}°C\n"
    )

    temp_header = (
        f"{'Year':<6} {'City':<32} "
        f"{'HDD (°C/obs)':>13} {'CDD (°C/obs)':>13} {'Comfort dev':>12}"
    )
    print(temp_header)
    print("-" * len(temp_header))

    prev_year = None
    for _, row in combined_temp.iterrows():
        yr = int(row["year"])
        if prev_year is not None and yr != prev_year:
            print()
        prev_year = yr
        print(
            f"{yr:<6} {row['label']:<32} "
            f"{row['mean_hdd_c']:>13.2f} "
            f"{row['mean_cdd_c']:>13.2f} "
            f"{row['mean_comfort_dev_c']:>12.2f}"
        )



if __name__ == "__main__":
    sys.exit(main())
