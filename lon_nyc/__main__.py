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

from lon_nyc import analysis, config, noaa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Download and summarize NYC hourly rain data from NOAA ISD."
    )
    parser.add_argument(
        "--start", type=int, default=2023, metavar="YEAR", help="First year (default: 2023)"
    )
    parser.add_argument(
        "--end", type=int, default=2023, metavar="YEAR", help="Last year (default: 2023)"
    )
    args = parser.parse_args(argv)

    s3 = noaa.make_s3_client()
    keys = noaa.generate_s3_file_keys(config.NYC_STATION_ID, args.start, args.end)
    raw = noaa.download_and_concatenate_s3_csvs(s3, noaa.S3_BUCKET, keys)
    processed = noaa.process_precipitation_data(raw)
    summary = analysis.rainy_hours_summary(processed, label=config.NYC_LABEL)

    print(f"\n=== {config.NYC_LABEL} ===")
    for k, v in summary.items():
        if k != "label":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
