"""Plotting helpers for lon_nyc analysis results.

Four figures are currently supported:

* :func:`plot_threshold_sensitivity` — two-panel rainfall threshold sweep
  (rainy hours / rainy days vs threshold mm, log scale).
* :func:`plot_temperature_hist_and_deviation` — side-by-side temperature
  density histogram (a) and mean absolute deviation vs chosen temperature (b).
* :func:`plot_snow_vs_rain` — stacked-bar chart comparing snow days / hours
  with liquid-rain days / hours for each city across years.
* :func:`plot_long_term_trends` — multi-panel time series (shared year x-axis)
  showing annual precipitation, rainy hours/days, snow days, sub-zero hours,
  and cooling degree-days for both cities with a rolling 5-year mean.

London is always drawn in red (``tab:red``), NYC in blue (``tab:blue``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lon_nyc import config as cfg

if TYPE_CHECKING:
    from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

# City colours used consistently across all plots
_CITY_COLOURS: dict[str, str] = {
    cfg.LON_LABEL: "tab:red",
    cfg.NYC_LABEL: "tab:blue",
}


def plot_threshold_sensitivity(
    sensitivity_frames: list[pd.DataFrame],
    output_path: str | Path | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
) -> "Figure":  # type: ignore[name-defined]
    """Two-panel plot showing how rainy-hour and rainy-day counts vary with threshold.

    The x-axis (shared) is the precipitation threshold in mm (log scale).
    The top panel shows mean annual **rainy hours**; the bottom panel shows
    mean annual **rainy days**.  London is drawn in red, New York in blue.
    A vertical dashed line marks the standard WMO threshold (0.254 mm).

    Parameters
    ----------
    sensitivity_frames:
        List of DataFrames as returned by
        :func:`lon_nyc.analysis.threshold_sensitivity`, one per city.  Each
        must have columns ``label``, ``threshold_mm``, ``mean_rainy_hours``,
        ``mean_rainy_days``.
    output_path:
        If given, the figure is saved to this path (PNG at 150 dpi).
    start_year, end_year:
        Used only in the figure title to indicate the data range.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, (ax_hours, ax_days) = plt.subplots(
        2, 1, figsize=(8, 7), sharex=True, constrained_layout=True
    )

    for df in sensitivity_frames:
        label = df["label"].iloc[0] if not df.empty else "unknown"
        colour = _CITY_COLOURS.get(label, "black")
        # Exclude threshold=0 from log-scale x axis to avoid -inf
        plot_df = df[df["threshold_mm"] > 0].copy()

        ax_hours.plot(
            plot_df["threshold_mm"],
            plot_df["mean_rainy_hours"],
            color=colour,
            linewidth=2,
            label=label,
        )
        ax_days.plot(
            plot_df["threshold_mm"],
            plot_df["mean_rainy_days"],
            color=colour,
            linewidth=2,
            label=label,
        )

    # Mark the standard WMO / NWS threshold
    wmo = cfg.RAINY_THRESHOLD_MM
    for ax in (ax_hours, ax_days):
        ax.axvline(
            wmo,
            color="gray",
            linestyle="--",
            linewidth=1.2,
            label=f"WMO threshold ({wmo} mm)",
        )
        ax.set_xscale("log")
        ax.grid(True, which="both", linestyle=":", linewidth=0.6, alpha=0.7)
        ax.spines[["top", "right"]].set_visible(False)

    ax_hours.set_ylabel("Mean annual rainy hours", fontsize=11)
    ax_days.set_ylabel("Mean annual rainy days", fontsize=11)
    ax_days.set_xlabel("Precipitation threshold (mm, log scale)", fontsize=11)

    # Legend only on the top panel to avoid duplication
    ax_hours.legend(fontsize=9, framealpha=0.9)

    year_range = ""
    if start_year is not None and end_year is not None:
        year_range = f"  ({start_year}–{end_year}, averaged over years)"
    elif start_year is not None:
        year_range = f"  (from {start_year}, averaged over years)"

    fig.suptitle(
        f"Rainfall threshold sensitivity{year_range}",
        fontsize=13,
        fontweight="bold",
    )

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out), dpi=150)
        logger.info("Saved threshold sensitivity plot to %s", out)

    return fig


def plot_temperature_hist_and_deviation(
    temp_pairs: list[tuple[str, pd.DataFrame]],
    output_path: str | Path | None = None,
    chosen_temps: Sequence[float] | None = None,
    title_years: tuple[int, int] | None = None,
) -> "Figure":  # type: ignore[name-defined]
    """Create a side-by-side figure: (a) temperature histograms, (b) mean abs-deviation vs chosen temp.

    Parameters
    ----------
    temp_pairs:
        List of (label, DataFrame) pairs where each DataFrame must contain
        a ``temp_c`` column of temperature observations (°C).
    output_path:
        If provided, save the figure to this path.
    chosen_temps:
        Sequence of chosen temperatures (°C) to evaluate mean absolute deviation.
        Defaults to np.arange(-10, 41, 0.5).
    title_years:
        Optional (start, end) tuple used for a descriptive title.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if chosen_temps is None:
        chosen_temps = list(np.arange(-10.0, 40.5, 0.5))

    fig, (ax_hist, ax_dev) = plt.subplots(
        1, 2, figsize=(12, 5), constrained_layout=True
    )

    # (a) Histograms — overlayed, alpha=0.5, no stacking
    for label, df in temp_pairs:
        colour = _CITY_COLOURS.get(label, "black")
        temps = df["temp_c"].dropna()
        if temps.empty:
            logger.warning("No temperature data for %s — skipping histogram.", label)
            continue
        ax_hist.hist(temps, bins=40, alpha=0.5, color=colour, label=label, density=True)

    ax_hist.set_xlabel("Temperature (°C)")
    ax_hist.set_ylabel("Density")
    ax_hist.legend(fontsize=9, framealpha=0.9)
    ax_hist.spines[["top", "right"]].set_visible(False)
    ax_hist.grid(True, linestyle=":", alpha=0.6)

    # (b) Mean absolute deviation vs chosen temp
    for label, df in temp_pairs:
        colour = _CITY_COLOURS.get(label, "black")
        temps = df["temp_c"].dropna().to_numpy()
        if temps.size == 0:
            logger.warning("No temperature data for %s — skipping deviation plot.", label)
            continue
        mean_devs = [float(np.abs(temps - ct).mean()) for ct in chosen_temps]
        ax_dev.plot(chosen_temps, mean_devs, color=colour, linewidth=2, label=label)

    ax_dev.set_xlabel("Chosen temperature (°C)")
    ax_dev.set_ylabel("Mean absolute deviation (°C)")
    ax_dev.legend(fontsize=9, framealpha=0.9)
    ax_dev.spines[["top", "right"]].set_visible(False)
    ax_dev.grid(True, linestyle=":", alpha=0.6)

    # Title
    year_range = ""
    if title_years is not None and title_years[0] is not None:
        start, end = title_years
        year_range = f"  ({start}–{end})"

    fig.suptitle(f"Temperature distributions and deviation{year_range}", fontsize=13, fontweight="bold")

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out), dpi=150)
        logger.info("Saved temperature panels to %s", out)

    return fig


def plot_snow_vs_rain(
    annual_frames: list[pd.DataFrame],
    output_path: str | Path | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
) -> "Figure":  # type: ignore[name-defined]
    """Four-panel stacked-bar figure comparing snow and liquid-rain statistics.

    The figure has four panels arranged in a 2 × 2 grid:

    * **(a) Days per year** – stacked bars: liquid-rain days (solid) and snow
      days (hatched) for each city.  A mixed day (both liquid and snow hours)
      counts only in *snow days*, so the two categories are mutually exclusive.
    * **(b) Hours per year** – same stacking for liquid-rain hours vs snow hours.
    * **(c) Mean days per year** (single grouped bar per city) – average
      liquid-rain days and snow days across all years in the dataset.
    * **(d) Mean hours per year** (single grouped bar per city) – same for hours.

    London is drawn in red, NYC in blue, consistent with the rest of the module.

    Parameters
    ----------
    annual_frames:
        List of DataFrames as returned by
        :func:`lon_nyc.analysis.annual_summary`, one per city.  Each must have
        columns ``label``, ``year``, ``snow_days``, ``liquid_rain_days``,
        ``snow_hours``, ``liquid_rain_hours``.
    output_path:
        If given, the figure is saved here (PNG at 150 dpi).
    start_year, end_year:
        Used only in the figure title to indicate the data range.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    ax_days, ax_hours = axes[0]
    ax_mean_days, ax_mean_hours = axes[1]

    # Width for grouped bars — each city gets its own x position
    bar_width = 0.35

    # ── Per-year time-series stacked bars (panels a & b) ─────────────────────
    for df in annual_frames:
        if df.empty:
            continue
        label = df["label"].iloc[0]
        colour = _CITY_COLOURS.get(label, "black")
        years = df["year"].to_numpy()

        for ax, liq_col, snow_col, ylabel in [
            (ax_days, "liquid_rain_days", "snow_days", "Days per year"),
            (ax_hours, "liquid_rain_hours", "snow_hours", "Hours per year"),
        ]:
            liq = df[liq_col].to_numpy()
            snow = df[snow_col].to_numpy()
            ax.bar(years, liq, label=f"{label} – liquid rain", color=colour, alpha=0.75)
            ax.bar(
                years, snow, bottom=liq,
                label=f"{label} – snow", color=colour, alpha=0.95,
                hatch="//", edgecolor="white", linewidth=0.5,
            )
            ax.set_ylabel(ylabel, fontsize=10)
            ax.set_xlabel("Year", fontsize=10)
            ax.grid(True, axis="y", linestyle=":", linewidth=0.6, alpha=0.7)
            ax.spines[["top", "right"]].set_visible(False)

    # Add subtitles
    ax_days.set_title("(a) Precipitation days", fontsize=11)
    ax_hours.set_title("(b) Precipitation hours", fontsize=11)

    # ── Mean across years (panels c & d) ─────────────────────────────────────
    city_labels: list[str] = []
    for df in annual_frames:
        if df.empty:
            continue
        city_labels.append(df["label"].iloc[0])

    x_pos = np.arange(len(city_labels))

    for ax, liq_col, snow_col, ylabel in [
        (ax_mean_days, "liquid_rain_days", "snow_days", "Mean days per year"),
        (ax_mean_hours, "liquid_rain_hours", "snow_hours", "Mean hours per year"),
    ]:
        liq_means = []
        snow_means = []
        colours = []
        for df in annual_frames:
            if df.empty:
                liq_means.append(0.0)
                snow_means.append(0.0)
                colours.append("gray")
                continue
            label = df["label"].iloc[0]
            colours.append(_CITY_COLOURS.get(label, "black"))
            liq_means.append(float(df[liq_col].mean()))
            snow_means.append(float(df[snow_col].mean()))

        liq_arr = np.array(liq_means)
        snow_arr = np.array(snow_means)

        bars_liq = ax.bar(
            x_pos, liq_arr, width=bar_width * 1.8,
            color=colours, alpha=0.75,
            label="Liquid rain",
        )
        bars_snow = ax.bar(
            x_pos, snow_arr, bottom=liq_arr, width=bar_width * 1.8,
            color=colours, alpha=0.95,
            hatch="//", edgecolor="white", linewidth=0.5,
            label="Snow",
        )

        # Annotate each bar segment with its value
        for i, (liq, snow) in enumerate(zip(liq_arr, snow_arr)):
            ax.text(x_pos[i], liq / 2, f"{liq:.0f}", ha="center", va="center",
                    fontsize=9, color="white", fontweight="bold")
            if snow > 0:
                ax.text(x_pos[i], liq + snow / 2, f"{snow:.0f}", ha="center",
                        va="center", fontsize=9, color="white", fontweight="bold")

        ax.set_xticks(x_pos)
        ax.set_xticklabels(city_labels, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.grid(True, axis="y", linestyle=":", linewidth=0.6, alpha=0.7)
        ax.spines[["top", "right"]].set_visible(False)

    ax_mean_days.set_title("(c) Mean precipitation days", fontsize=11)
    ax_mean_hours.set_title("(d) Mean precipitation hours", fontsize=11)

    # Shared legend for panels a & b
    handles_a, labels_a = ax_days.get_legend_handles_labels()
    ax_days.legend(handles_a, labels_a, fontsize=8, framealpha=0.9, loc="upper right")

    # Shared legend for panels c & d showing hatch convention
    import matplotlib.patches as mpatches

    liq_patch = mpatches.Patch(facecolor="gray", alpha=0.75, label="Liquid rain")
    snow_patch = mpatches.Patch(
        facecolor="gray", alpha=0.95, hatch="//",
        edgecolor="white", label="Snow / frozen",
    )
    ax_mean_days.legend(handles=[liq_patch, snow_patch], fontsize=9, framealpha=0.9)

    year_range = ""
    if start_year is not None and end_year is not None:
        year_range = f"  ({start_year}–{end_year})"
    fig.suptitle(
        f"Snow vs liquid-rain precipitation{year_range}",
        fontsize=13,
        fontweight="bold",
    )

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out), dpi=150)
        logger.info("Saved snow vs rain plot to %s", out)

    return fig


def plot_long_term_trends(
    annual_frames: list[pd.DataFrame],
    temp_frames: list[pd.DataFrame],
    output_path: str | Path | None = None,
    rolling_window: int = 5,
) -> "Figure":  # type: ignore[name-defined]
    """Multi-panel time-series figure showing long-term precipitation and temperature trends.

    Six vertically stacked panels share a common year x-axis.  Annual values
    are shown as semi-transparent markers/bars, and a rolling mean (default
    5-year window, min 3 years) is overlaid as a solid line to reveal any
    secular drift.

    Panels (top to bottom):

    * **(a) Total precipitation (mm/yr)** — annual liquid-equivalent depth
    * **(b) Rainy hours / yr** — hours exceeding the 0.254 mm threshold
    * **(c) Rainy days / yr** — calendar days with at least one rainy hour
    * **(d) Snow days / yr** — calendar days with at least one snow hour
    * **(e) Sub-zero hours / yr** — hours with T < 0 °C
    * **(f) CDD (°C/obs)** — mean cooling degree-hour above 18 °C per obs

    London is drawn in red (``tab:red``), NYC in blue (``tab:blue``).
    A shaded band marks the ±1 std deviation of each city's rolling window.

    Parameters
    ----------
    annual_frames:
        List of DataFrames as returned by
        :func:`lon_nyc.analysis.annual_summary`, one per city.
    temp_frames:
        List of DataFrames as returned by
        :func:`lon_nyc.analysis.annual_temperature_summary`, one per city.
    output_path:
        If given, save the figure to this path (PNG at 150 dpi).
    rolling_window:
        Width of the rolling mean window in years (default 5).

    Returns
    -------
    matplotlib.figure.Figure
    """
    import matplotlib.ticker as mticker

    # ── Merge precip and temperature into per-city DataFrames ─────────────────
    # Build a dict: label → merged DataFrame with all columns
    city_data: dict[str, pd.DataFrame] = {}
    for df in annual_frames:
        if df.empty:
            continue
        label = df["label"].iloc[0]
        city_data[label] = df.set_index("year").copy()

    for df in temp_frames:
        if df.empty:
            continue
        label = df["label"].iloc[0]
        temp_indexed = df.set_index("year")
        if label in city_data:
            city_data[label] = city_data[label].join(
                temp_indexed[["mean_cdd_c", "sub_zero_hours"]], how="outer"
            )
        else:
            city_data[label] = temp_indexed[["mean_cdd_c", "sub_zero_hours"]].copy()

    # Panel specification: (column, y-label, panel-letter)
    panels = [
        ("total_precip_mm", "Total precip (mm/yr)", "a"),
        ("rainy_hours",     "Rainy hours / yr",     "b"),
        ("rainy_days",      "Rainy days / yr",      "c"),
        ("snow_days",       "Snow days / yr",       "d"),
        ("sub_zero_hours",  "Sub-zero hours / yr",  "e"),
        ("mean_cdd_c",      "CDD (°C/obs)",         "f"),
    ]
    n_panels = len(panels)

    fig, axes = plt.subplots(
        n_panels, 1,
        figsize=(12, 2.8 * n_panels),
        sharex=True,
        constrained_layout=True,
    )

    min_year = min(
        (int(df.index.min()) for df in city_data.values() if not df.empty),
        default=2005,
    )
    max_year = max(
        (int(df.index.max()) for df in city_data.values() if not df.empty),
        default=2024,
    )

    for ax, (col, ylabel, letter) in zip(axes, panels):
        for label, df in city_data.items():
            if col not in df.columns:
                continue
            colour = _CITY_COLOURS.get(label, "black")
            years = df.index.astype(int)
            values = df[col].astype(float)

            # Annual values as semi-transparent scatter / step
            ax.plot(
                years, values,
                color=colour, alpha=0.35, linewidth=1.0,
                marker="o", markersize=3, zorder=2,
                label=label,
            )

            # Rolling mean (min_periods=3 so early years still appear)
            roll = (
                pd.Series(values.values, index=years)
                .rolling(rolling_window, center=True, min_periods=3)
            )
            roll_mean = roll.mean()
            roll_std  = roll.std()

            ax.plot(
                years, roll_mean,
                color=colour, linewidth=2.2, zorder=3,
            )
            ax.fill_between(
                years,
                roll_mean - roll_std,
                roll_mean + roll_std,
                color=colour, alpha=0.12, zorder=1,
            )

        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(True, axis="y", linestyle=":", linewidth=0.6, alpha=0.6)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlim(min_year - 0.5, max_year + 0.5)
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=10))
        ax.text(
            0.01, 0.96, f"({letter})",
            transform=ax.transAxes, fontsize=9, fontweight="bold",
            va="top", ha="left",
        )

    # x-label only on bottom panel
    axes[-1].set_xlabel("Year", fontsize=10)

    # Legend on top panel
    handles, labels = axes[0].get_legend_handles_labels()
    axes[0].legend(handles, labels, fontsize=9, framealpha=0.9, loc="upper right")

    fig.suptitle(
        f"Long-term precipitation & temperature trends  ({min_year}–{max_year})\n"
        f"Thin line = annual value  ·  Thick line = {rolling_window}-year centred mean  ·  "
        f"Band = ±1 std",
        fontsize=11,
        fontweight="bold",
    )

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out), dpi=150)
        logger.info("Saved long-term trends plot to %s", out)

    return fig