"""Air quality comparison: NYC vs London, 2015–2024.

Design: single matched urban-background monitors on each side
---------------------------------------------------------
Both cities are represented by a single, centrally-located, officially
classified "urban background" monitoring site with a continuous instrument,
giving near-complete daily records across the full 2015–2024 window.

NYC — EPA pre-generated daily concentration files (no authentication):
  https://aqs.epa.gov/aqsweb/airdata/daily_{param}_{year}.zip
  Parameter 88502 = PM2.5 Continuous (µg/m³) → CCNY (City College of New York)
    160 Convent Ave, New York NY 10031 — Washington Heights / Hamilton Heights,
    Manhattan.  Continuous TEOM/BAM instrument, 363–366 valid days/year.
  Parameter 42602 = NO2 (ppb)               → IS 52 (South Bronx)
    IS 52, Bronx — 3.5 km from CCNY, same neighbourhood character, continuous
    analyser, full 10-year record.  No Manhattan NO2 monitor exists in the EPA
    network.
    NO2 converted from ppb to µg/m³ (× 1.88 at 20 °C / 1 atm) for direct
    comparison with London.

London — ERG / King's College London API (no authentication):
  https://api.erg.ic.ac.uk/AirQuality/Data/Site/SiteCode=KC1/
       StartDate={start}/EndDate={end}/Json
  Site KC1 = Kensington and Chelsea – North Ken — LAQN "Urban Background"
  classification, open since 1995, continuous PM25 and NO2 instruments,
  near-complete data through end of 2024.  (BL0 Bloomsbury was used
  previously but has an 11-month PM2.5 gap in 2021–22 and no data after
  Aug 2023.)  Hourly species are fetched by month, averaged to daily means,
  then resampled to calendar-month means.

All data are cached in .cache/ to avoid re-downloading on subsequent runs.
The London fetch takes ~2 minutes for a decade of data on first run.

Run from the project root::

    python scripts/air_quality.py
"""

from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lon_nyc.plots import plot_air_quality

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
START_YEAR = 2010
END_YEAR = 2025

# EPA parameter codes
EPA_PM25 = 88502   # Continuous PM2.5 (BAM/TEOM) — near-complete daily record
EPA_PM25_DURATION = "24-HR BLK AVG"   # rolling 24-h block average, one row/day
EPA_NO2 = 42602

# Single NYC urban-background monitors (continuous instruments)
NYC_PM25_SITE = "CCNY"           # City College NY, 160 Convent Ave, Manhattan — continuous TEOM
NYC_NO2_SITE = "IS 52"           # South Bronx, 3.5 km from CCNY — continuous analyser
NYC_STATE = "New York"
NYC_BOROUGHS = {"New York", "Kings", "Queens", "Bronx", "Richmond"}

# London ERG site
ERG_SITE = "KC1"   # Kensington & Chelsea – North Ken, Urban Background, continuous 2015–2024
ERG_BASE = "https://api.erg.ic.ac.uk/AirQuality"

# NO2 unit conversion: 1 ppb NO2 → µg/m³ at 20 °C / 1 atm
NO2_PPB_TO_UGM3 = 1.88

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

OUTPUT_PATH = Path("plots/air_quality.png")

# ---------------------------------------------------------------------------
# EPA helpers
# ---------------------------------------------------------------------------

def _epa_daily_url(param: int, year: int) -> str:
    return f"https://aqs.epa.gov/aqsweb/airdata/daily_{param}_{year}.zip"


def _fetch_epa_year(param: int, year: int) -> pd.DataFrame:
    """Download one year of EPA daily data, return raw DataFrame."""
    cache = CACHE_DIR / f"epa_{param}_{year}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)

    url = _epa_daily_url(param, year)
    print(f"  Downloading {url} …", end=" ", flush=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
    print(f"{len(data)//1024} KB")

    zf = zipfile.ZipFile(io.BytesIO(data))
    csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
    df = pd.read_csv(zf.open(csv_name), low_memory=False)
    df.to_parquet(cache)
    return df


def get_nyc_daily(param: int, years: range, site_name: str) -> pd.DataFrame:
    """Return daily mean concentration for a single named NYC EPA monitor.

    Columns: date (datetime64), mean_conc (float).
    Units: µg/m³ for PM2.5 (param 88502); ppb for NO2 (converted by caller).
    For continuous PM2.5 (88502) the pre-aggregated '24-HR BLK AVG' rows are
    used — one row per day, so no further grouping is needed.
    For NO2 (42602) hourly '1 HOUR' daily summary rows are averaged.
    """
    frames = []
    for year in years:
        df = _fetch_epa_year(param, year)

        mask = (
            (df["State Name"] == NYC_STATE)
            & df["County Name"].isin(NYC_BOROUGHS)
            & (df["Local Site Name"] == site_name)
            & (df["Observation Percent"] >= 75)
        )
        site = df[mask].copy()

        # For continuous PM2.5 (88502), use the pre-computed 24-hour block average
        if param == EPA_PM25 and "Sample Duration" in site.columns:
            site = site[site["Sample Duration"] == EPA_PM25_DURATION]

        if site.empty:
            continue

        daily = (
            site.groupby("Date Local")["Arithmetic Mean"]
            .mean()
            .reset_index()
            .rename(columns={"Date Local": "date", "Arithmetic Mean": "mean_conc"})
        )
        daily["date"] = pd.to_datetime(daily["date"])
        frames.append(daily)

    result = pd.concat(frames, ignore_index=True).sort_values("date")
    return result


# ---------------------------------------------------------------------------
# London ERG helpers
# ---------------------------------------------------------------------------

def _erg_month_url(site: str, start: str, end: str) -> str:
    return (
        f"{ERG_BASE}/Data/Site/SiteCode={site}"
        f"/StartDate={start}/EndDate={end}/Json"
    )


def _fetch_erg_month(site: str, year: int, month: int) -> pd.DataFrame:
    """Fetch one calendar month of hourly data from ERG for a single site."""
    cache = CACHE_DIR / f"erg_{site}_{year}_{month:02d}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)

    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    url = _erg_month_url(site, first.isoformat(), last.isoformat())
    with urllib.request.urlopen(url, timeout=30) as resp:
        raw = resp.read().decode("utf-8-sig")

    d = json.loads(raw)
    records = d.get("AirQualityData", {}).get("Data", [])
    if not records:
        return pd.DataFrame(columns=["dt", "species", "value"])

    df = pd.DataFrame(records)
    df.columns = [c.lstrip("@") for c in df.columns]
    df = df.rename(columns={"SpeciesCode": "species", "MeasurementDateGMT": "dt", "Value": "value"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["dt"] = pd.to_datetime(df["dt"])

    df.to_parquet(cache)
    return df


def get_london_daily(species: str, years: range) -> pd.DataFrame:
    """Return daily mean concentration for London KC1 (North Kensington).

    Columns: date (datetime64), mean_conc (float).
    """
    frames = []
    total_months = len(years) * 12
    fetched = 0
    for year in years:
        for month in range(1, 13):
            cache = CACHE_DIR / f"erg_{ERG_SITE}_{year}_{month:02d}.parquet"
            if not cache.exists():
                print(
                    f"  Fetching London {year}-{month:02d} "
                    f"({fetched+1}/{total_months}) …",
                    end="\r",
                    flush=True,
                )
                time.sleep(0.1)  # be polite to the API
            df = _fetch_erg_month(ERG_SITE, year, month)
            fetched += 1

            sp = df[df["species"] == species].dropna(subset=["value"])
            if sp.empty:
                continue

            sp = sp.copy()
            dt_col: pd.DatetimeIndex = pd.DatetimeIndex(sp["dt"])
            sp["date"] = dt_col.floor("D")
            daily = sp.groupby("date")["value"].mean().reset_index()
            daily.columns = ["date", "mean_conc"]
            frames.append(daily)

    if frames:
        print()  # newline after \r progress
    result = pd.concat(frames, ignore_index=True).sort_values("date")
    return result


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily mean_conc to calendar-month means."""
    df = daily.set_index("date")["mean_conc"]
    monthly = df.resample("MS").mean().reset_index()
    monthly.columns = ["date", "mean_conc"]
    return monthly


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    years = range(START_YEAR, END_YEAR + 1)

    # ---- NYC data ----
    print(f"\nFetching NYC PM2.5 (EPA 88502, {NYC_PM25_SITE}) {START_YEAR}–{END_YEAR} …")
    nyc_pm25_daily = get_nyc_daily(EPA_PM25, years, NYC_PM25_SITE)
    nyc_pm25_monthly = to_monthly(nyc_pm25_daily)

    print(f"\nFetching NYC NO2 (EPA 42602, {NYC_NO2_SITE}) {START_YEAR}–{END_YEAR} …")
    nyc_no2_daily = get_nyc_daily(EPA_NO2, years, NYC_NO2_SITE)
    # Convert ppb → µg/m³ to match London units
    nyc_no2_daily["mean_conc"] = nyc_no2_daily["mean_conc"] * NO2_PPB_TO_UGM3
    nyc_no2_monthly = to_monthly(nyc_no2_daily)

    # ---- London data ----
    print(f"\nFetching London PM2.5 (ERG {ERG_SITE}) {START_YEAR}–{END_YEAR} …")
    lon_pm25_daily = get_london_daily("PM25", years)
    lon_pm25_monthly = to_monthly(lon_pm25_daily)

    print(f"\nFetching London NO2 (ERG {ERG_SITE}) {START_YEAR}–{END_YEAR} …")
    lon_no2_daily = get_london_daily("NO2", years)
    lon_no2_monthly = to_monthly(lon_no2_daily)

    # ---- Quick sanity check ----
    print("\nData summary:")
    print(f"  NYC PM2.5  ({NYC_PM25_SITE}): {len(nyc_pm25_monthly)} months, "
          f"mean {nyc_pm25_monthly['mean_conc'].mean():.1f} µg/m³")
    print(f"  London PM2.5 ({ERG_SITE}): {len(lon_pm25_monthly)} months, "
          f"mean {lon_pm25_monthly['mean_conc'].mean():.1f} µg/m³")
    print(f"  NYC NO2    ({NYC_NO2_SITE}): {len(nyc_no2_monthly)} months, "
          f"mean {nyc_no2_monthly['mean_conc'].mean():.1f} µg/m³")
    print(f"  London NO2 ({ERG_SITE}): {len(lon_no2_monthly)} months, "
          f"mean {lon_no2_monthly['mean_conc'].mean():.1f} µg/m³")

    # ---- Plot ----
    print(f"\nGenerating plot → {OUTPUT_PATH}")
    plot_air_quality(
        nyc_pm25=nyc_pm25_monthly,
        lon_pm25=lon_pm25_monthly,
        nyc_no2=nyc_no2_monthly,
        lon_no2=lon_no2_monthly,
        output_path=OUTPUT_PATH,
        start_year=START_YEAR,
        end_year=END_YEAR,
        nyc_pm25_label=f"NYC ({NYC_PM25_SITE} CCNY, Manhattan)",
        nyc_no2_label=f"NYC ({NYC_NO2_SITE}, S. Bronx)",
        lon_label=f"London ({ERG_SITE} N. Kensington)",
    )
    print("Done.")


if __name__ == "__main__":
    main()
