"""Draws the three slide images for Nikhil's Phase 1 presentation. Run: python docs/images/make_nikhil_diagrams.py
Outputs (next to this file): nikhil_pipeline.png, nikhil_run_flow.png, nikhil_results.png. Plain matplotlib, no data."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).parent
MINE, OTHER, INK, GREY = "#0072B2", "#E8E8E8", "#222222", "#666666"


def box(ax, x, y, w, h, title, sub="", mine=False, size=13):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=MINE if mine else OTHER, ec=MINE if mine else "#AAAAAA", lw=1.5))
    colour = "white" if mine else INK
    ax.text(x + w / 2, y + h / 2 + (0.12 if sub else 0), title, ha="center", va="center", fontsize=size,
            fontweight="bold", color=colour)
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.22, sub, ha="center", va="center", fontsize=size - 3, color=colour)


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=18, lw=1.8, color=GREY))


def pipeline():
    fig, ax = plt.subplots(figsize=(15, 3.8))
    ax.set_xlim(0, 15); ax.set_ylim(0, 3.6); ax.axis("off")
    steps = [("Sources", "5 working,\n6 refused", False), ("Gate +\nCollector", "Ragini", False),
             ("Extract +\nClean", "Sachi", False), ("Filter", "Nikhil", True), ("Run +\nDatabricks", "Nikhil", True),
             ("Results", "JSON + log", False)]
    w, gap = 1.95, 0.5
    for i, (t, s, mine) in enumerate(steps):
        x = 0.25 + i * (w + gap)
        box(ax, x, 1.0, w, 1.5, t, s, mine, 12)
        if i < len(steps) - 1:
            arrow(ax, x + w + 0.03, 1.75, x + w + gap - 0.03, 1.75)
    ax.add_patch(FancyBboxPatch((0.25 + 3 * (w + gap) - 0.1, 0.75), 2 * w + gap + 0.2, 2.0,
                                boxstyle="round,pad=0.02,rounding_size=0.15", fc="none", ec=MINE, lw=2, ls="--"))
    ax.text(0.25 + 3 * (w + gap) + w + gap / 2, 0.45, "My part", ha="center", fontsize=13, fontweight="bold", color=MINE)
    ax.text(7.5, 3.4, "Where my part sits in the pipeline", ha="center", fontsize=16, fontweight="bold", color=INK)
    fig.savefig(OUT / "nikhil_pipeline.png", dpi=160, bbox_inches="tight", facecolor="white")


def run_flow():
    fig, ax = plt.subplots(figsize=(8, 9))
    ax.set_xlim(0, 8); ax.set_ylim(0, 9); ax.axis("off")
    ax.text(4, 8.7, "What one command does", ha="center", fontsize=16, fontweight="bold", color=INK)
    rows = [("python -m atlas.run", "one command", True),
            ("For each source", "Gate check > Collect > Extract > Clean > Filter", False),
            ("Save to Databricks", "raw/   clean/   facts/", True),
            ("Write results", "output/poc_<run>.json    logs/<run>.json", True),
            ("Final checks", "output valid?     no file on the laptop?", True)]
    for i, (t, s, mine) in enumerate(rows):
        y = 7.1 - i * 1.65
        box(ax, 0.8, y, 6.4, 1.1, t, s, mine, 14)
        if i < len(rows) - 1:
            arrow(ax, 4, y - 0.03, 4, y - 0.52)
    ax.text(4, 0.15, "Blue = built by me.  A failing source is logged and the run continues.", ha="center",
            fontsize=10, color=GREY)
    fig.savefig(OUT / "nikhil_run_flow.png", dpi=160, bbox_inches="tight", facecolor="white")


def results():
    names = ["Best Practices", "Quincy", "Sullair", "Pumps & Systems", "DOE newsroom"]
    kept, dropped = [5, 5, 5, 0, 0], [0, 0, 0, 5, 5]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.barh(names[::-1], kept[::-1], color=MINE, label="Kept (passed all four checks)")
    ax.barh(names[::-1], dropped[::-1], left=kept[::-1], color="#BBBBBB", label="Dropped (no compressor keyword)")
    for i, (k, d) in enumerate(zip(kept[::-1], dropped[::-1])):
        ax.text(k + d + 0.1, i, f"{k} of 5 kept", va="center", fontsize=11, color=INK)
    ax.set_xlim(0, 7); ax.set_xlabel("Pages collected (5 per source)", color=GREY)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False, fontsize=10)
    ax.set_title("Phase 1 run: what the filter kept from each source", fontsize=14, fontweight="bold", loc="left")
    fig.savefig(OUT / "nikhil_results.png", dpi=160, bbox_inches="tight", facecolor="white")


if __name__ == "__main__":
    pipeline(); run_flow(); results()
    print("wrote nikhil_pipeline.png, nikhil_run_flow.png, nikhil_results.png in", OUT)
