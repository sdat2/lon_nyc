"""Plotting helpers for lon_nyc analysis results.

Two figures are currently supported:

* :func:`plot_threshold_sensitivity` — two-panel rainfall threshold sweep
  (rainy hours / rainy days vs threshold mm, log scale).
* :func:`plot_temperature_hist_and_deviation` — side-by-side temperature
  density histogram (a) and mean absolute deviation vs chosen temperature (b).

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
