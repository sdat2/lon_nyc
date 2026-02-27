"""Plotting helpers for lon_nyc analysis results."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
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
