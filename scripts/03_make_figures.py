"""Render the POS error-analysis results as static PNG images (for sharing outside the artifact)."""
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path

OUT = Path("/Users/vincenzomula/Documents/hiwi_gloria/figures")
OUT.mkdir(exist_ok=True)

# Palette (validated categorical set, light mode)
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
RED = "#e34948"
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#898781"
GRIDLINE = "#e1e0d9"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "axes.edgecolor": GRIDLINE,
    "text.color": TEXT_PRIMARY,
    "axes.labelcolor": TEXT_SECONDARY,
    "xtick.color": TEXT_MUTED,
    "ytick.color": TEXT_PRIMARY,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def hbar(filename, title, subtitle, labels, values, display, colors, figsize=(8, None), xmax=None):
    n = len(labels)
    h = figsize[1] or max(2.2, 0.55 * n + 1.2)
    fig, ax = plt.subplots(figsize=(figsize[0], h), dpi=200)
    y = range(n)[::-1]
    bars = ax.barh(list(y), values, color=colors, height=0.6, zorder=3)
    for yi, v, d in zip(y, values, display):
        ax.text(v + (xmax or max(values)) * 0.015, yi, d, va="center", ha="left",
                fontsize=10.5, color=TEXT_PRIMARY)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=10.5)
    ax.set_xlim(0, xmax or max(values) * 1.18)
    ax.set_xticks([])
    for spine in ["top", "right", "bottom", "left"]:
        ax.spines[spine].set_visible(False)
    ax.grid(axis="x", color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    fig.suptitle(title, x=0.02, ha="left", fontsize=14, fontweight="bold", color=TEXT_PRIMARY, y=0.98)
    ax.set_title(subtitle, loc="left", fontsize=10, color=TEXT_SECONDARY, pad=14)
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig(OUT / filename, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / filename}")


def grouped_hbar(filename, title, subtitle, categories, series_labels, series_values, series_colors, xmax=None):
    n = len(categories)
    fig, ax = plt.subplots(figsize=(8, max(3, 0.5 * n + 1.5)), dpi=200)
    bar_h = 0.35
    y = list(range(n))[::-1]
    for i, (label, values, color) in enumerate(zip(series_labels, series_values, series_colors)):
        offset = (i - (len(series_labels) - 1) / 2) * bar_h
        yy = [yi + offset for yi in y]
        bars = ax.barh(yy, values, height=bar_h * 0.92, color=color, label=label, zorder=3)
        for yi, v in zip(yy, values):
            if v > 0:
                ax.text(v + (xmax or max(max(sv) for sv in series_values)) * 0.02, yi, str(v),
                        va="center", ha="left", fontsize=9, color=TEXT_PRIMARY)
    ax.set_yticks(y)
    ax.set_yticklabels(categories, fontsize=10.5)
    ax.set_xlim(0, xmax or max(max(sv) for sv in series_values) * 1.2)
    ax.set_xticks([])
    for spine in ["top", "right", "bottom", "left"]:
        ax.spines[spine].set_visible(False)
    ax.grid(axis="x", color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", frameon=False, fontsize=10)
    fig.suptitle(title, x=0.02, ha="left", fontsize=14, fontweight="bold", color=TEXT_PRIMARY, y=0.98)
    ax.set_title(subtitle, loc="left", fontsize=10, color=TEXT_SECONDARY, pad=14)
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig(OUT / filename, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / filename}")


def example_table(filename, title, subtitle, rows):
    """rows: list of (gold, dropped_part, predicted, pos)"""
    n = len(rows)
    fig, ax = plt.subplots(figsize=(11, 0.62 * n + 1.6), dpi=200)
    ax.axis("off")
    fig.suptitle(title, x=0.02, ha="left", fontsize=14, fontweight="bold", color=TEXT_PRIMARY, y=0.985)
    ax.set_title(subtitle, loc="left", fontsize=10, color=TEXT_SECONDARY, pad=0)

    col_x = [0.0, 0.60, 0.80]
    headers = ["Gold span (dropped text struck through)", "GLiNER predicted", "Dropped POS"]
    row_h = 1.0 / (n + 1)
    top = 0.90

    for cx, htext in zip(col_x, headers):
        ax.text(cx, top, htext, fontsize=9, color=TEXT_MUTED, fontweight="bold",
                transform=ax.transAxes, va="bottom")
    ax.plot([0, 1], [top - 0.015, top - 0.015], color=TEXT_MUTED, linewidth=1,
            transform=ax.transAxes)

    for i, (gold, dropped, pred, pos) in enumerate(rows):
        y = top - 0.015 - row_h * (i + 1) + row_h * 0.35
        # gold span with strike-through segment
        parts = gold.split(dropped) if dropped in gold else [gold]
        x = col_x[0]
        if len(parts) == 2 and dropped:
            pre, post = parts
            if pre.strip():
                t = ax.text(x, y, pre, fontsize=9.5, family="monospace", color=TEXT_PRIMARY,
                            transform=ax.transAxes, va="center")
                fig.canvas.draw()
                bbox = t.get_window_extent(renderer=fig.canvas.get_renderer())
                x = ax.transAxes.inverted().transform((bbox.x1, 0))[0] + 0.003
            t2 = ax.text(x, y, dropped, fontsize=9.5, family="monospace", color=RED,
                         transform=ax.transAxes, va="center",
                         bbox=dict(boxstyle="square,pad=0.15", fc="#fbe4e3", ec="none"))
            t2.set_path_effects([])
            # strike-through line
            fig.canvas.draw()
            bbox2 = t2.get_window_extent(renderer=fig.canvas.get_renderer())
            x0, x1 = ax.transAxes.inverted().transform((bbox2.x0, 0))[0], ax.transAxes.inverted().transform((bbox2.x1, 0))[0]
            ax.plot([x0, x1], [y, y], color=RED, linewidth=1.3, transform=ax.transAxes, zorder=5)
            if post.strip():
                x2 = ax.transAxes.inverted().transform((bbox2.x1, 0))[0] + 0.003
                ax.text(x2, y, post, fontsize=9.5, family="monospace", color=TEXT_PRIMARY,
                        transform=ax.transAxes, va="center")
        else:
            ax.text(x, y, gold, fontsize=9.5, family="monospace", color=TEXT_PRIMARY,
                    transform=ax.transAxes, va="center")

        ax.text(col_x[1], y, pred, fontsize=9.5, family="monospace", color=BLUE,
                transform=ax.transAxes, va="center")
        ax.text(col_x[2], y, pos, fontsize=8.5, family="monospace", color=TEXT_MUTED,
                transform=ax.transAxes, va="center")
        if i < n - 1:
            ax.plot([0, 1], [y - row_h * 0.5, y - row_h * 0.5], color=GRIDLINE, linewidth=0.7,
                    transform=ax.transAxes)

    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig(OUT / filename, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / filename}")


# 1. Match distribution
hbar(
    "01_match_distribution.png",
    "Match distribution",
    "Of 1,783 gold entities (48 matched BioRED docs), share exactly matched, partially matched, or missed",
    ["Unmatched (missed)", "Partial match", "Exact match"],
    [1466, 156, 161],
    ["1,466 (82.2%)", "156 (8.8%)", "161 (9.0%)"],
    [RED, YELLOW, BLUE],
)

# 2. Boundary error direction
hbar(
    "02_boundary_error_direction.png",
    "Boundary-error direction",
    "Among 156 partial matches, which side of the span GLiNER got wrong",
    ["BOTH sides", "LEFT trimmed", "RIGHT trimmed"],
    [38, 45, 73],
    ["38 (24.4%)", "45 (28.9%)", "73 (46.8%)"],
    [AQUA, BLUE, ORANGE],
)

# 3. POS omitted, left vs right
pos_data = [
    ("NOUN", 67, 115), ("ADJ", 34, 11), ("PUNCT", 14, 10), ("NUM", 6, 21),
    ("CCONJ", 4, 7), ("PART", 7, 0), ("ADP", 2, 9), ("VERB", 2, 1), ("PROPN", 2, 1),
]
grouped_hbar(
    "03_pos_omitted_left_vs_right.png",
    "POS of omitted tokens, by side",
    "Part-of-speech of every gold token GLiNER dropped in a partial match",
    [p[0] for p in pos_data],
    ["Dropped from LEFT", "Dropped from RIGHT"],
    [[p[1] for p in pos_data], [p[2] for p in pos_data]],
    [BLUE, ORANGE],
)

# 4. Recall by entity type
entity_data = [
    ("CellLine", 0.0), ("SequenceVariant", 11.9), ("GeneOrGeneProduct", 12.4),
    ("OrganismTaxon", 14.7), ("ChemicalEntity", 20.1), ("DiseaseOrPhenotypicFeature", 26.6),
]
hbar(
    "04_recall_by_entity_type.png",
    "Recall by gold entity type",
    "Share of each BioRED entity type matched (exact + partial) by GLiNER",
    [e[0] for e in entity_data],
    [e[1] for e in entity_data],
    [f"{e[1]:.1f}%" for e in entity_data],
    [RED if e[1] == 0 else BLUE for e in entity_data],
    xmax=32,
)

# 5. Top POS transformations
transform_data = [
    ("NOUN PART NOUN -> NOUN", 4), ("NOUN NOUN NOUN -> NOUN", 7), ("ADJ NOUN NOUN -> NOUN", 9),
    ("ADJ NOUN -> NOUN", 11), ("ADJ -> ADJ", 11), ("NOUN -> NOUN", 11),
    ("ADJ NOUN -> ADJ", 17), ("NOUN NOUN -> NOUN", 30),
]
hbar(
    "05_top_pos_transformations.png",
    "Most common POS transformations",
    "Gold POS sequence -> predicted POS sequence (partial matches only, top 8)",
    [t[0] for t in transform_data],
    [t[1] for t in transform_data],
    [str(t[1]) for t in transform_data],
    [AQUA] * len(transform_data),
)

# 6. Example tables
example_table(
    "06_examples_right_boundary_drops.png",
    "Example: RIGHT-boundary drops",
    "Real rows from pos_analysis_test_500.csv — GLiNER cuts off the tail noun chain",
    [
        ("thiazide-sensitive Na(+)-Cl(-) cotransporter", "Na(+)-Cl(-) cotransporter", "thiazide-sensitive", "NOUN PUNCT NOUN"),
        ("epithelial Na channel (ENaC) subunit", "Na channel (ENaC) subunit", "epithelial", "PROPN NOUN PUNCT NOUN PUNCT NOUN"),
        ("myocardial dysfunction", "dysfunction", "myocardial", "NOUN"),
        ("rhesus monkeys", "monkeys", "rhesus", "NOUN"),
        ("dengue virus type 2", "virus type 2", "dengue", "NOUN NOUN NUM"),
        ("breast cancer", "cancer", "breast", "NOUN"),
        ("colon cancer", "cancer", "colon", "NOUN"),
        ("histidine 626-to-arginine", "626-to-arginine", "histidine", "NOUN"),
    ],
)

example_table(
    "07_examples_left_boundary_drops.png",
    "Example: LEFT-boundary drops",
    "Real rows from pos_analysis_test_500.csv — GLiNER cuts off leading adjectives/modifiers",
    [
        ("autosomal dominant hypercholesterolemia", "autosomal dominant", "hypercholesterolemia", "ADJ ADJ"),
        ("low-density lipoprotein receptor", "low-density lipoprotein", "receptor", "ADJ NOUN"),
        ("impaired glucose tolerance", "impaired glucose", "tolerance", "ADJ NOUN"),
        ("Impaired insulin secretion", "Impaired insulin", "secretion", "ADJ NOUN"),
        ("Chinese hamster", "Chinese", "hamster", "ADJ"),
        ("pegylated interferon", "pegylated", "interferon", "ADJ"),
        ("hepatocellular carcinoma", "hepatocellular", "carcinoma", "ADJ"),
        ("end-stage liver disease", "end-stage liver", "disease", "ADJ NOUN"),
    ],
)

print("\nAll figures written to", OUT)
