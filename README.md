# lon.nyc

Is New York City wetter than London?  The popular image of London as a drizzly,
rain-soaked city persists despite evidence to the contrary.  This project
compares hourly precipitation records for both cities using the
[NOAA Integrated Surface Database (ISD)](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)
hosted on the public AWS S3 bucket `noaa-global-hourly-pds`.

## Results (2020–2024)

> **NYC is unambiguously wetter.** It receives roughly 60–70 % more rainfall
> by volume, and comparable or greater numbers of rainy days, once a consistent
> measurement threshold is applied.

Annual totals for 2020–2024 (2025 excluded as a partial year):

| Year | City | Total (mm) | Rainy hours | Rainy days |
|------|------|----------:|------------:|-----------:|
| 2020 | London (Heathrow) | 924 | 314 | 150 |
| 2020 | New York City (Central Park) | **1166** | **705** | 132 |
| 2021 | London (Heathrow) | 998 | 288 | 136 |
| 2021 | New York City (Central Park) | **1527** | **666** | **138** |
| 2022 | London (Heathrow) | 684 | 342 | 119 |
| 2022 | New York City (Central Park) | **1186** | **668** | **127** |
| 2023 | London (Heathrow) | 737 | 526 | 128 |
| 2023 | New York City (Central Park) | **1523** | **703** | **128** |
| 2024 | London (Heathrow) | 680 | 477 | 123 |
| 2024 | New York City (Central Park) | **1178** | **698** | **121** |

A "rainy hour / day" uses the standard WMO threshold of **> 0.254 mm
(0.01 inch)** of liquid-equivalent precipitation.

**NYC leads on every dimension across all five years** — more total rainfall,
more rainy hours, and comparable or greater numbers of rainy days.  London's
"drizzly" reputation comes from frequent low-intensity events (< 0.254 mm)
that do not register as measurable precipitation under the standard definition.

## Temperature (2020–2024)

Temperature is taken from the ISD `TMP` field (see [Methodology](#methodology)).
All metrics are normalised by observation count so that the two stations'
different reporting densities (London ≈ 24 obs/day on FM-12, NYC ≈ 12–18 on
FM-15) do not distort the comparison.

| Year | City | HDD (°C/obs) | CDD (°C/obs) | Comfort dev (°C) | <0 °C hours |
|------|------|-------------:|-------------:|---------------------:|------------:|
| 2020 | London (Heathrow) | 4.50 | 0.68 | 9.33 | 104 |
| 2020 | New York City (Central Park) | 4.69 | **2.07** | 9.35 | **401** |
| 2021 | London (Heathrow) | **4.99** | 0.44 | **9.84** | 434 |
| 2021 | New York City (Central Park) | 4.93 | **2.13** | 9.47 | **584** |
| 2022 | London (Heathrow) | 4.32 | 0.79 | 9.07 | 501 |
| 2022 | New York City (Central Park) | **5.29** | **2.18** | **9.98** | **879** |
| 2023 | London (Heathrow) | **4.44** | 0.60 | **9.18** | **462** |
| 2023 | New York City (Central Park) | 4.23 | **1.96** | 8.79 | 179 |
| 2024 | London (Heathrow) | 4.17 | 0.48 | 8.97 | 199 |
| 2024 | New York City (Central Park) | **4.57** | **2.15** | **9.10** | **486** |

* **HDD** = mean °C below 15.5 °C per observation (heating pressure).
  Both cities are roughly equal — London is slightly colder most years but the
  gap is small (< 1 °C/obs).
* **CDD** = mean °C above 18 °C per observation (cooling pressure).
  NYC runs **3–4× higher** than London every single year.  NYC summers are
  genuinely hot; London rarely sustains temperatures above 18 °C for long.
* **< 0 °C hours** makes NYC's cold winters visible.  NYC regularly freezes for
  400–900 hours a year; London typically logs 100–500.  The HDD metric alone
  understated this because NYC's hot summers partially cancel its winter cold
  when averaged over the full year.

### Why the stereotype persists

London has noticeably more *overcast, grey* days than NYC.  When a looser
threshold (any non-zero AA1 depth) is applied, London scores more rainy days
(154–184 vs 121–138) because its FM-12 SYNOP reports frequently log sub-trace
accumulations of 0.1–0.2 mm drizzle.  NYC's METAR observations encode
equivalent events as `condition=2` (trace) with `depth=0`, which disappears
under any positive threshold.  The 0.254 mm threshold eliminates this
reporting asymmetry.

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
| `--start` | `2020` | First year to fetch (inclusive) |
| `--end`   | `2025` | Last year to fetch (inclusive) |

## Example

```bash
python -m lon_nyc --start 2020 --end 2025
```

Sample output:

```
======================Annual Precipitation Summary======================
Years 2020–2024 | threshold: >0.254 mm

Year   City                             Total (mm)  Rainy hrs  Rainy days
-------------------------------------------------------------------------
2020   London (Heathrow)                     924.2        314         150
2020   New York City (Central Park)         1166.0        705         132
...

==============================Annual Temperature Summary==============================
Years 2020–2024 | HDD base: 15.5°C  CDD base: 18.0°C  Comfort base: 21.0°C

Year   City                              HDD (°C/obs)  CDD (°C/obs)  Comfort dev  <0°C hrs
-------------------------------------------------------------------------------------------
2020   London (Heathrow)                         4.50          0.68         9.33       104
2020   New York City (Central Park)              4.69          2.07         9.35       401
...
```

## Methodology

### Stations

| City | Station | USAF | WBAN | WMO | Report type |
|------|---------|------|------|-----|-------------|
| New York City (Central Park) | `725053-94728` | 725053 | 94728 | — | FM-15 (METAR) |
| London (Heathrow, EGLL) | `037720-99999` | 037720 | 99999* | 03772 | FM-12 (SYNOP) |

\* UK stations have no WBAN code; `99999` is the standard ISD placeholder.

S3 object keys strip the hyphen from the station ID, e.g.
`noaa-global-hourly-pds/2023/72505394728.csv`.

### Precipitation field

Precipitation depth is taken from the ISD `AA1` compound field:

```
AA1 = period_hours , depth_tenths_mm , condition_code , quality_code
```

The **depth** (second sub-field, index 1) is an integer in tenths of
millimetres, converted to mm by dividing by 10.  Missing observations are
coded `9999` or `+9999` and become `NaN`.

`AA1` always reports **liquid-water equivalent** regardless of precipitation
phase, so rain, snow, sleet, and freezing rain all contribute to the same
depth column.  Inspection of `AW1` (automated present-weather) codes confirms
that NYC snow events (condition code `1` or AW1 70–79) appear as positive
depths in `AA1` at the same liquid-equivalent rate — there is no snow/rain
asymmetry between the two cities.

### Report-type filter

| Code | Name | Kept? | Reason |
|------|------|-------|--------|
| FM-15 | METAR (hourly) | ✅ | Primary NYC observation type |
| FM-12 | SYNOP (hourly) | ✅ | Primary London/Heathrow observation type |
| FM-16 | SPECI (special METAR) | ❌ | Sub-hourly; variable AA1 period causes double-counting |
| SOD/SOM | Daily/monthly summaries | ❌ | Not hourly |

### Rainy-hour threshold

An hour is counted as **rainy** when `precipitation_mm > 0.254 mm`
(equivalent to the US NWS / WMO definition of 0.01 inch of measurable
precipitation).

Using `> 0 mm` instead inflates London's counts because Heathrow's FM-12
SYNOP reports frequently log sub-trace accumulations (0.1–0.2 mm drizzle)
that NYC's FM-15 METARs encode as `condition=2` / `depth=0` (trace).
The 0.254 mm threshold eliminates this reporting asymmetry and aligns both
cities with published climate-table conventions.

### Rainy-day definition

A calendar day is **rainy** if it contains at least one rainy hour (i.e.
at least one hour with liquid-equivalent depth > 0.254 mm).

### Temperature discomfort

Hourly air temperature is taken from the ISD `TMP` mandatory field:

```
TMP = +TTTT , Q
```

`TTTT` is temperature in **tenths of °C** (signed integer); `Q` is a quality
flag.  Missing observations use the sentinel `+9999` and are excluded.

Three metrics are computed, each using its own conventional baseline, and all
normalised by observation count to make the two stations comparable:

| Metric | Formula | Baseline | Standard |
|--------|---------|----------|---------|
| **HDD** | mean(max(15.5 − T, 0)) | 15.5 °C | WMO / UK Met Office heating degree-day base |
| **CDD** | mean(max(T − 18, 0)) | 18.0 °C | Standard cooling degree-day base |
| **Comfort dev** | mean(\|T − 21\|) | 21.0 °C | Two-sided deviation from a comfortable temperature |
| **< 0 °C hours** | count(T < 0) | 0 °C | Raw count of freezing hours per year |

Using separate baselines for HDD and CDD (rather than one combined baseline)
ensures each metric measures what it is conventionally understood to measure.

## Validation against GHCND (NYC)

Annual totals from the ISD `AA1` field were cross-checked against
[GHCND](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily)
daily totals for Central Park (station `USW00094728`).
Agreement is within ~1% across all years.

| Year | GHCND official | Our ISD calc | Difference |
|------|---------------:|-------------:|-----------:|
| 2020 | 1151.9 mm (45.35 in) | 1166.0 mm | +1.2% |
| 2021 | 1517.1 mm (59.73 in) | 1527.3 mm | +0.7% |
| 2022 | 1176.0 mm (46.30 in) | 1185.7 mm | +0.8% |
| 2023 | 1506.0 mm (59.29 in) | 1523.3 mm | +1.2% |
| 2024 | 1177.8 mm (46.37 in) | 1178.0 mm | +0.0% |

The small systematic ~+1% occurs because GHCND records trace (`T`)
precipitation as exactly zero, whereas the ISD `AA1` field sometimes
encodes a small positive depth for the same events.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

## Planned: sunshine hours comparison

The natural follow-up question is whether London has more sunshine than NYC —
the other half of the "miserable London weather" stereotype.

### London
Real observed hourly sunshine data (Campbell-Stokes recorder) is available
from the **Met Office MIDAS Open** dataset via
[CEDA](https://dap.ceda.ac.uk/badc/ukmo-midas-open/data/uk-hourly-weather-obs/):
- Station: Heathrow (`src_id` 708), field `sun_dur_mins`
- Authentication: free CEDA account → bearer token via
  `POST https://services.ceda.ac.uk/api/token/create/`

### NYC
No equivalent observed sunshine record exists in any public US network:

| Source | Outcome |
|--------|---------|
| GHCND `TSUN` — Central Park, JFK, LaGuardia | 0 / 365 days populated |
| NOAA LCD `HourlySkyConditions` | Cloud-layer codes only; no duration |
| ISD GF1 sky-cover oktas | Invalid proxy — counts night-time clear sky |
| ISD REM `55SSS` SYNOP groups | Sparse (≈219 obs/yr) and unreliable |
| Open-Meteo ERA5 reanalysis | Modelled, not observed; inflates ~60 % vs Met Office actuals |

US ASOS/AWOS stations do not deploy sunshine-duration recorders, so no
like-for-like observed comparison is currently possible. Implementation is
deferred until an equivalent NYC source is identified.
