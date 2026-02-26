"""Station configuration for the lon_nyc rain analysis.

NOAA ISD station IDs have the form ``USAF-WBAN``.  Note that the S3
object key omits the hyphen (e.g. ``2023/72505394728.csv``).
UK stations have no WBAN code; the placeholder ``99999`` is used instead.
"""

# NYC Central Park (ASOS station), USAF 725053, WBAN 94728
NYC_STATION_ID: str = "725053-94728"
NYC_LABEL: str = "New York City (Central Park)"

# London Heathrow (EGLL), USAF 037720, WBAN 99999 (UK placeholder)
# WMO station 03772; the standard Met Office benchmark station for London.
# S3 key format: YYYY/03772099999.csv
LON_STATION_ID: str = "037720-99999"
LON_LABEL: str = "London (Heathrow)"

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
# 0.254 mm = 0.01 inch, the standard WMO / US NWS definition of a measurable
# precipitation event and the basis for "rainy day" counts on Wikipedia climate
# tables. Using > 0.0 mm inflates London's counts because FM-12 SYNOP reports
# frequently record sub-trace amounts (0.1–0.2 mm drizzle) that FM-15 METAR
# stations (like NYC Central Park) encode as condition-code 2 / depth 0 instead.
RAINY_THRESHOLD_MM: float = 0.254
