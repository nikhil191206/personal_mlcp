"""Slide images for Nikhil's Phase 2 pages (deck pages 16 onward). Run: python docs/images/make_nikhil_diagrams.py
Style matches the scouting slides (black outlines, RULES / HUMAN pills). My steps get a grey fill and a thick border.
Outputs next to this file: nikhil_run_order.png, nikhil_filter.png, nikhil_switching.png, nikhil_loop.png,
nikhil_results.png. Plain matplotlib; the only data is the final demo run's numbers, typed in below."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).parent
INK, GREY, MID, RED, GREEN = "#111111", "#EDEDED", "#666666", "#C0392B", "#2E7D32"


def new(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, title, sub="", mine=False, dashed=False, edge=INK, fill=None, tsize=12, ssize=9.5, tcolor=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.1",
                                fc=fill or (GREY if mine else "white"), ec=edge, lw=2.6 if mine else 1.4,
                                ls="--" if dashed else "-"))
    top = y + h - 0.32 if sub else y + h / 2
    ax.text(x + w / 2, top, title, ha="center", va="center", fontsize=tsize, fontweight="bold", color=tcolor)
    if sub:
        ax.text(x + w / 2, y + (h - 0.5) / 2, sub, ha="center", va="center", fontsize=ssize, color=MID, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, color=INK):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=16, lw=1.6, color=color))


def pill(ax, x, y, text, color=INK):
    ax.add_patch(FancyBboxPatch((x, y), 0.95, 0.3, boxstyle="round,pad=0.01,rounding_size=0.14", fc="white", ec=color, lw=1.3))
    ax.text(x + 0.475, y + 0.15, text, ha="center", va="center", fontsize=8, fontweight="bold", color=color)


def heading(ax, h, text):
    ax.text(0.2, h - 0.15, text, fontsize=14, fontweight="bold", va="top", color=INK)


def run_order():
    w, h = 15, 3.9
    fig, ax = new(w, h)
    heading(ax, h, "One command, python -m atlas.run: the order, and which steps are mine")
    steps = [("Settings", "what to look for", True), ("Discovery", "the scout", False), ("Compliance\nGate", "allowed?", False),
             ("Collect", "RSS or list", False), ("Extract", "facts, not text", False), ("Clean", "duplicates", False),
             ("Filter", "4 checks +\nyour rules", True), ("Switching", "if a source\nsaid no", True),
             ("Stories", "same event,\nseveral items", True), ("Save", "Databricks", True)]
    bw, gap = 1.28, 0.2
    for i, (t, s, mine) in enumerate(steps):
        x = 0.2 + i * (bw + gap)
        box(ax, x, 1.1, bw, 1.75, t, s, mine=mine, tsize=10.5, ssize=8.5)
        if i < len(steps) - 1:
            arrow(ax, x + bw + 0.01, 1.97, x + bw + gap - 0.01, 1.97)
    ax.text(0.2, 0.62, "Grey, thick border = built by me.   White = other team members' steps (scouting: Ragini, extraction: Sachi).",
            fontsize=10, color=MID)
    ax.text(0.2, 0.22, "A refused source or a failing step is recorded in the log and the run continues. Exit code 0 means no error.",
            fontsize=10, color=MID)
    fig.savefig(OUT / "nikhil_run_order.png", dpi=170, bbox_inches="tight", facecolor="white")


def filter_diagram():
    w, h = 13, 4.7
    fig, ax = new(w, h)
    heading(ax, h, "The filter reads the saved settings")
    box(ax, 0.2, 0.9, 3.4, 2.9, "Saved settings", "regions\nhow many months back\ntechnologies, news types\nwords to include or leave out\n'industrial only'\nsource types", mine=True)
    pill(ax, 1.4, 1.0, "HUMAN")
    box(ax, 4.5, 0.9, 4.3, 2.9, "Filter", "4 original checks:\ncompressor, North America,\ncredible source, recent\n+ 6 rules from the settings", mine=True)
    pill(ax, 6.2, 1.0, "RULES")
    box(ax, 9.7, 2.3, 3.0, 1.5, "Kept", "goes into the results", fill="white", edge=GREEN, tcolor=GREEN)
    box(ax, 9.7, 0.9, 3.0, 1.3, "Dropped", "kept in clean/ with every\nreason listed", fill="white", edge=RED, tcolor=RED)
    arrow(ax, 3.65, 2.35, 4.45, 2.35)
    arrow(ax, 8.85, 3.0, 9.65, 3.0, GREEN)
    arrow(ax, 8.85, 1.7, 9.65, 1.55, RED)
    ax.text(0.2, 0.35, "No AI. Nothing is deleted by the filter; every dropped item says why.", fontsize=10, color=MID)
    fig.savefig(OUT / "nikhil_filter.png", dpi=170, bbox_inches="tight", facecolor="white")


def switching():
    w, h = 14, 5.2
    fig, ax = new(w, h)
    heading(ax, h, "Switching: when a source says no, follow the same company elsewhere")
    box(ax, 0.2, 2.5, 2.5, 1.7, "A source gives\nnothing", "refused by the gate\nzero pages\nrate limit (429)", mine=True, tsize=11)
    box(ax, 3.4, 2.5, 2.5, 1.7, "Is its company\non the watchlist?", "name or alias\nmust match", mine=True, tsize=11)
    box(ax, 6.6, 2.5, 3.1, 1.7, "Look in the other\nallowed sources", "keep only items that name\nthe company", mine=True, tsize=11)
    box(ax, 10.4, 2.5, 3.3, 1.7, "Label and show", "via_fallback + a 'switched'\nrow + a log line", mine=True, tsize=11)
    for x1, x2 in ((2.75, 3.35), (5.95, 6.55), (9.75, 10.35)):
        arrow(ax, x1, 3.35, x2, 3.35)
    box(ax, 3.4, 0.85, 2.5, 1.2, "If not", "logged: nothing to\nswitch to", ssize=9)
    arrow(ax, 4.65, 2.45, 4.65, 2.1)
    box(ax, 6.6, 0.55, 7.1, 1.5, "Never reached, by any route", "the refused site and its subdomains, web archives, caches,\ntranslation pages, proxies. A block is never bypassed.",
        edge=RED, tcolor=RED, ssize=9.5)
    ax.text(0.2, 0.2, "Same gate rules apply: robots.txt, 3 s between requests, stop on 429.", fontsize=10, color=MID)
    fig.savefig(OUT / "nikhil_switching.png", dpi=170, bbox_inches="tight", facecolor="white")


def loop():
    w, h = 14, 5.6
    fig, ax = new(w, h)
    heading(ax, h, "The simple app: every save reruns the system")
    box(ax, 0.2, 3.2, 2.6, 1.6, "Dashboard", "change the filters,\npress Done", mine=True, tsize=11)
    box(ax, 3.5, 3.2, 2.6, 1.6, "Save settings", "checked before saving", mine=True, tsize=11)
    box(ax, 6.8, 3.2, 2.6, 1.6, "Rerun", "python -m atlas.run\nstarted by the app", mine=True, tsize=11)
    box(ax, 10.1, 3.2, 3.6, 1.6, "New results", "table of facts on the\nDashboard", mine=True, tsize=11)
    for x1, x2 in ((2.85, 3.45), (6.15, 6.75), (9.45, 10.05)):
        arrow(ax, x1, 4.0, x2, 4.0)
    box(ax, 0.2, 0.6, 4.2, 1.9, "Facts page", "mark each fact Important\nor Not important, press Save", mine=True, tsize=11)
    pill(ax, 1.83, 0.72, "HUMAN")
    box(ax, 5.0, 0.6, 4.0, 1.9, "Sources page", "Confirm a source\n(team decision only)", mine=True, tsize=11)
    pill(ax, 6.53, 0.72, "HUMAN")
    box(ax, 9.6, 0.6, 4.1, 1.9, "Report page", "brief: facts, sources,\nwhy it matters", mine=True, tsize=11)
    arrow(ax, 2.3, 2.55, 7.3, 3.15)
    arrow(ax, 7.0, 2.55, 8.1, 3.15)
    arrow(ax, 11.9, 3.15, 11.9, 2.55)
    ax.text(0.2, 0.2, "A saved decision starts a rerun. If a run is already going, one more starts right after it. Denied facts leave the output.",
            fontsize=10, color=MID)
    fig.savefig(OUT / "nikhil_loop.png", dpi=170, bbox_inches="tight", facecolor="white")


def results():
    w, h = 13, 6.0
    fig, ax = new(w, h)
    heading(ax, h, "Final demo run: what the system produced")
    tiles = [("47", "facts kept"), ("7", "sources read"), ("7", "sources refused,\nshown with reasons"),
             ("46", "stories (1 seen in\n2 or more sources)"), ("0", "errors"), ("0", "files on a laptop")]
    for i, (n, lab) in enumerate(tiles):
        box(ax, 0.2 + i * 2.1, 3.55, 1.95, 1.7, n, lab, tsize=26, ssize=9)
    names = ["Best Practices", "Quincy", "Sullair", "FS-Elliott", "Burckhardt", "Pumps & Systems", "DOE"]
    kept = [16, 10, 10, 10, 1, 0, 0]
    inner = fig.add_axes([0.2, 0.06, 0.62, 0.36])
    inner.barh(names[::-1], kept[::-1], color="#444444")
    for i, k in enumerate(kept[::-1]):
        inner.text(k + 0.3, i, str(k), va="center", fontsize=10)
    inner.set_xlim(0, 19); inner.spines[["top", "right"]].set_visible(False)
    inner.set_title("Facts kept per source", loc="left", fontsize=11, fontweight="bold")
    fig.savefig(OUT / "nikhil_results.png", dpi=170, bbox_inches="tight", facecolor="white")


if __name__ == "__main__":
    for fn in (run_order, filter_diagram, switching, loop, results):
        fn()
    print("wrote 5 images in", OUT)
