"""Plot usable waking-hours in sunlight vs wake-up time for London & NYC.

Assumes a fixed **8-hour sleep window** (so 16 waking hours) and sweeps the
wake-up hour across the full 24-hour cycle (0 h → 24 h in 0.25-h steps).
For each wake-up hour the bedtime is wake + 16 (i.e. sleep for 8 h before
waking again), and the usable daylight is the overlap of [sunrise, sunset]
with the 16-hour waking window — averaged over all 365 days of the year.

Cities
------
* London  – 51.5°N  (red)
* NYC     – 40.7°N  (blue)

Run from the project root::

    python scripts/sleep_schedule_daylight.py
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ---------------------------------------------------------------------------
# Re-use astronomical helpers from the companion script
# ---------------------------------------------------------------------------

#: Latitude of London (°N).
LON_LAT: float = 51.5085

#: Latitude of New York City (°N).
NYC_LAT: float = 40.7128

#: Fixed sleep duration (hours).
SLEEP_DURATION: float = 8.0

#: Waking duration = 24 − sleep (hours).
WAKING_DURATION: float = 24.0 - SLEEP_DURATION


def solar_declination(day_of_year: np.ndarray) -> np.ndarray:
    """Return solar declination in radians (standard WMO approximation)."""
    return np.radians(-23.45 * np.cos(np.radians(360.0 / 365 * (day_of_year + 10))))


def day_length_hours(lat_deg: float, day_of_year: np.ndarray) -> np.ndarray:
    """Astronomical day length in hours for *lat_deg* and *day_of_year*."""
    delta = solar_declination(day_of_year)
    lat = np.radians(lat_deg)
    cos_omega = np.clip(-np.tan(lat) * np.tan(delta), -1.0, 1.0)
    return 2.0 * np.degrees(np.arccos(cos_omega)) / 15.0


def annual_mean_usable(lat_deg: float, wake_hours: np.ndarray) -> np.ndarray:
    """Annual-mean usable daylight hours for every wake-up time in *wake_hours*.

    Parameters
    ----------
    lat_deg:
        Geographic latitude in degrees north.
    wake_hours:
        1-D array of wake-up times in decimal hours (0–24).

    Returns
    -------
    np.ndarray
        Shape ``(len(wake_hours),)`` – annual-mean usable daylight hours for
        each wake-up time.
    """
    # Use days 1–365 as the "wake day"; day 2–366 (capped at 365) as the next day
    # for windows that cross midnight.
    doy = np.arange(1, 366)                     # shape (365,)
    doy_next = np.minimum(doy + 1, 365)         # next calendar day (capped)

    dl      = day_length_hours(lat_deg, doy)      # (365,)
    dl_next = day_length_hours(lat_deg, doy_next) # (365,)

    sunrise      = 12.0 - dl / 2.0              # (365,)
    sunset       = 12.0 + dl / 2.0              # (365,)
    sunrise_next = 12.0 - dl_next / 2.0         # (365,) — next day
    sunset_next  = 12.0 + dl_next / 2.0         # (365,)

    # Broadcast: wake_hours (W,) vs doy (365,)
    wake      = wake_hours[:, np.newaxis]        # (W, 1)
    bed_raw   = wake + WAKING_DURATION           # (W, 1) — bedtime, may exceed 24
    wraps     = bed_raw >= 24.0                  # (W, 1) — waking window crosses midnight
    bed       = bed_raw % 24.0                   # (W, 1) — time-of-day bedtime

    # ── No midnight wrap: entire waking window within one calendar day ───────
    # overlap of [wake, wake+16] with [sunrise, sunset]
    no_wrap = np.clip(
        np.minimum(sunset, bed_raw) - np.maximum(sunrise, wake),
        0.0, None,
    )  # (W, 365)

    # ── Midnight wrap: waking window spans two calendar days ─────────────────
    # Segment A: [wake, 24) on the wake day  ∩  [sunrise, sunset]
    wrap_a = np.clip(sunset - np.maximum(sunrise, wake), 0.0, None)
    # Segment B: [0, bed) on the next day    ∩  [sunrise_next, sunset_next]
    wrap_b = np.clip(np.minimum(sunset_next, bed) - sunrise_next, 0.0, None)
    wrapped = wrap_a + wrap_b  # (W, 365)

    usable = np.where(wraps, wrapped, no_wrap)  # (W, 365)

    return usable.mean(axis=1)  # (W,)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    wake_hours = np.arange(0, 24, 0.25)   # 0:00, 0:15, …, 23:45

    lon_usable = annual_mean_usable(LON_LAT, wake_hours)
    nyc_usable = annual_mean_usable(NYC_LAT, wake_hours)

    # ── Plot ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 5.5))

    ax.plot(wake_hours, lon_usable, color="red",  lw=2.5, label="London  (51.5°N)")
    ax.plot(wake_hours, nyc_usable, color="royalblue", lw=2.5, label="NYC  (40.7°N)")

    # Shade the NYC advantage / London advantage regions
    ax.fill_between(wake_hours, lon_usable, nyc_usable,
                    where=(nyc_usable >= lon_usable),
                    alpha=0.15, color="royalblue", label="NYC advantage")
    ax.fill_between(wake_hours, nyc_usable, lon_usable,
                    where=(lon_usable >= nyc_usable),
                    alpha=0.15, color="red", label="London advantage")

    # x-axis: hour labels
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(3))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{int(x):02d}:00")
    )

    ax.set_ylim(0, WAKING_DURATION + 0.5)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(2))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(1))

    ax.set_xlabel("Wake-up time (local solar time, 8 h sleep / 16 h awake)", fontsize=12)
    ax.set_ylabel("Annual-mean usable daylight\nduring waking hours (h/day)", fontsize=12)
    ax.set_title(
        "Usable daylight vs sleep schedule\n"
        "London (51.5°N) vs New York City (40.7°N) — 8 h sleep, 16 h awake",
        fontsize=13,
    )

    ax.legend(fontsize=11)
    ax.grid(True, which="major", alpha=0.4)
    ax.grid(True, which="minor", alpha=0.15)

    fig.tight_layout()
    out_path = "plots/sleep_schedule_daylight.png"
    fig.savefig(out_path, dpi=150)
    print(f"Plot saved to {out_path}")

    # ── Print the optimum wake time for each city ────────────────────────────
    print(f"\nOptimal wake time for maximum usable daylight (8 h sleep):")
    for label, ud in [("London", lon_usable), ("NYC", nyc_usable)]:
        best_idx = int(np.argmax(ud))
        best_wake = wake_hours[best_idx]
        h, m = divmod(round(best_wake * 60), 60)
        print(f"  {label}: wake at {h:02d}:{m:02d}  →  {ud[best_idx]:.2f} h/day in sunlight")


if __name__ == "__main__":
    main()
