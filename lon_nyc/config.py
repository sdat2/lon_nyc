"""Station configuration for the NYC rain analysis.

NOAA ISD station IDs have the form ``USAF-WBAN``.  Note that the S3
object key omits the hyphen (e.g. ``2023/72505394728.csv``).
"""

# NYC Central Park (ASOS station), USAF 725053, WBAN 94728
NYC_STATION_ID: str = "725053-94728"
NYC_LABEL: str = "New York City (Central Park)"

# Precipitation column name used in ISD CSV files from noaa-global-hourly-pds.
# The compound field AA1 encodes liquid precipitation accumulation.
# Sub-field layout: period_hours, depth_tenths_mm, condition_code, quality_code.
# See noaa.parse_aa1_depth_mm for parsing logic.
AA1_COLUMN: str = "AA1"

# Missing-value sentinels used in the AA1 depth sub-field (index 1, tenths of mm).
AA1_MISSING_DEPTHS: frozenset = frozenset({"9999", "+9999"})

# Missing-value sentinel in the HourlyPrecipitation column (LCD/GHCN-H format).
HOURLY_PRECIP_MISSING: frozenset = frozenset(
    {"99999", "+99999", "99999.0", "+99999.0", "T"}
)

# Threshold (mm) above which an hour is considered "rainy".
RAINY_THRESHOLD_MM: float = 0.0
