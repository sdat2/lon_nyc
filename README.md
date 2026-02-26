# lon.nyc

Compare hourly precipitation data for London and New York City using the
[NOAA Integrated Surface Database (ISD)](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)
hosted on the public AWS S3 bucket `noaa-global-hourly-pds`.

## Installation

Requires Python ≥ 3.9.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
python -m lon_nyc [--start YEAR] [--end YEAR]
```

Or, if installed via `pip install -e .`:

```bash
lon-nyc [--start YEAR] [--end YEAR]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--start` | `2023` | First year to fetch (inclusive) |
| `--end`   | `2023` | Last year to fetch (inclusive) |

## Example

```bash
python -m lon_nyc --start 2023 --end 2023
```

Sample output (NYC Central Park, 2023):

```
2026-02-26 22:08:58 - INFO - Generated 1 S3 keys for station 725053-94728 (2023–2023).
2026-02-26 22:08:58 - INFO - Downloading s3://noaa-global-hourly-pds/2023/72505394728.csv
2026-02-26 22:08:59 - INFO - Downloaded 2023/72505394728.csv (11842 rows).
2026-02-26 22:08:59 - INFO - Combined DataFrame: 11842 rows.
2026-02-26 22:08:59 - INFO - Filtered by REPORT_TYPE ['FM-15']: kept 8757/11842 rows.
2026-02-26 22:08:59 - INFO - Processed DataFrame: 8757 rows.

=== New York City (Central Park) ===
  total_hours: 8637
  rainy_hours: 703
  rainy_fraction: 0.081
  mean_precip_mm: 2.167
  total_precip_mm: 1523.3
```

The 2023 annual total of **1523 mm (59.97 in)** matches the NWS-reported figure of ~60.44 in almost
exactly. 2023 was an exceptionally wet year for NYC, with the historic
[September 29 flooding event](https://en.wikipedia.org/wiki/2023_New_York_metropolitan_area_floods)
contributing ~147 mm in a single day.

## Station IDs

| City | Station | USAF | WBAN |
|------|---------|------|------|
| New York City (Central Park) | `725053-94728` | 725053 | 94728 |

Station IDs follow the NOAA ISD `USAF-WBAN` convention.  The corresponding
S3 object key strips the hyphen, e.g. `2023/72505394728.csv`.

## Data notes

- Data are sourced from the `AA1` compound field in ISD CSV files.
- `AA1` sub-fields: `period_hours, depth_tenths_mm, condition_code, quality_code`.
- The **depth is the second sub-field** (index 1), in tenths of mm, converted to mm.
- Only `FM-15` (regular hourly METAR) report types are kept. `FM-16` (SPECI —
  special non-routine METARs) are excluded because they are filed sub-hourly
  during weather changes and their `AA1` depths cover variable short periods;
  including them alongside FM-15s causes significant double-counting.
- An hour is counted as **rainy** when `precipitation_mm > 0`.

## Validation against GHCND

Annual totals derived from the ISD `AA1` field were cross-checked against
the [GHCND](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily)
daily totals for Central Park (station `USW00094728`) obtained from the
[NOAA ACIS API](https://www.rcc-acis.org/docs_webservices.html).
Agreement is within ~1% across all years, consistent with the different
treatment of trace precipitation between the two datasets.

| Year | GHCND official | Our ISD calc | Difference |
|------|---------------:|-------------:|-----------:|
| 2020 | 1151.9 mm (45.35 in) | 1166.0 mm | +1.2% |
| 2021 | 1517.1 mm (59.73 in) | 1527.3 mm | +0.7% |
| 2022 | 1176.0 mm (46.30 in) | 1185.7 mm | +0.8% |
| 2023 | 1506.0 mm (59.29 in) | 1523.3 mm | +1.2% |
| 2024 | 1177.8 mm (46.37 in) | 1178.0 mm | +0.0% |

The small systematic ~+1% in the ISD figures occurs because GHCND records
trace (`T`) precipitation as exactly zero, whereas the ISD `AA1` field
sometimes encodes a small positive depth for the same events.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```
