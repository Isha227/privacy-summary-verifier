from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "019ff723-17a0-7bf2-84ad-aacfae5c5b43" / "final_analysis"
df = pd.read_csv(OUT / "opp115_summary_level_metrics.csv")

NAVY, BLUE, ORANGE, GREEN, RED = "#173F6B", "#4C78A8", "#F58518", "#54A24B", "#E45756"
GRID, TEXT, MUTED, WHITE = "#D9E1E8", "#172033", "#5E6B7A", "#FFFFFF"


def font(size: int, bold: bool = False):
    name = "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


F_TITLE, F_SUB, F_AXIS, F_SMALL, F_NOTE = font(42, True), font(27, True), font(21), font(18), font(16)


def bootstrap_ci(values: np.ndarray, seed: int) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    boot = rng.choice(values, size=(10000, values.size), replace=True).mean(axis=1)
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return float(values.mean()), float(lo), float(hi)


def new_canvas(title: str, subtitle: str = ""):
    image = Image.new("RGB", (2200, 1500), WHITE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 2200, 135), fill=NAVY)
    draw.text((75, 38), title, font=F_TITLE, fill=WHITE)
    if subtitle:
        draw.text((75, 155), subtitle, font=F_AXIS, fill=MUTED)
    return image, draw


def panel_box(draw, box, title):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=16, fill="#FAFCFE", outline=GRID, width=2)
    draw.text((x0 + 28, y0 + 22), title, font=F_SUB, fill=TEXT)
    return (x0 + 90, y0 + 100, x1 - 45, y1 - 85)


def nice_limits(values, rate=False):
    lo, hi = min(values), max(values)
    span = max(hi - lo, 0.05 if rate else 1.0)
    low = max(0.0, lo - span * 0.35) if rate else lo - span * 0.35
    high = min(1.0, hi + span * 0.35) if rate else hi + span * 0.35
    if high <= low:
        high = low + (0.1 if rate else 1.0)
    return low, high


def draw_point_panel(draw, box, labels, means, lows, highs, colors, rate=False):
    x0, y0, x1, y1 = box
    low, high = nice_limits(lows + highs, rate=rate)
    for step in range(5):
        value = low + (high - low) * step / 4
        y = y1 - (value - low) / (high - low) * (y1 - y0)
        draw.line((x0, y, x1, y), fill=GRID, width=2)
        label = f"{value:.0%}" if rate else f"{value:.1f}"
        draw.text((x0 - 18, y), label, font=F_SMALL, fill=MUTED, anchor="rm")
    for i, (label, mean, lo, hi, color) in enumerate(zip(labels, means, lows, highs, colors)):
        x = x0 + (i + 1) * (x1 - x0) / (len(labels) + 1)
        y = y1 - (mean - low) / (high - low) * (y1 - y0)
        ylo = y1 - (lo - low) / (high - low) * (y1 - y0)
        yhi = y1 - (hi - low) / (high - low) * (y1 - y0)
        draw.line((x, yhi, x, ylo), fill=color, width=7)
        draw.line((x - 18, yhi, x + 18, yhi), fill=color, width=5)
        draw.line((x - 18, ylo, x + 18, ylo), fill=color, width=5)
        draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=color, outline=WHITE, width=3)
        draw.text((x, y1 + 22), label, font=F_AXIS, fill=TEXT, anchor="ma")
        value_text = f"{mean:.1%}" if rate else f"{mean:.1f}"
        draw.text((x, yhi - 18), value_text, font=F_SMALL, fill=color, anchor="ms")


def prompt_set_figure():
    image, draw = new_canvas("Effect of safety-focused prompting", "Policy-blocked means and 95% bootstrap confidence intervals; n = 27 policies")
    panels = [("flesch_reading_ease", "Flesch Reading Ease", False), ("gemini_source_alignment_rate", "Supported-sentence rate", True), ("weighted_coverage_rate", "Weighted information coverage", True), ("omission_rate", "Omission rate", True)]
    boxes = [(65, 225, 1075, 820), (1125, 225, 2135, 820), (65, 865, 1075, 1460), (1125, 865, 2135, 1460)]
    for pidx, ((column, title, rate), outer) in enumerate(zip(panels, boxes)):
        inner = panel_box(draw, outer, title)
        policy = df.groupby(["policy_id", "prompt_set"])[column].mean().reset_index()
        means, lows, highs = [], [], []
        for i, prompt_set in enumerate(["Basic", "Safety-focused"]):
            vals = policy.loc[policy["prompt_set"] == prompt_set, column].to_numpy()
            mean, lo, hi = bootstrap_ci(vals, 20260830 + pidx * 10 + i)
            means.append(mean); lows.append(lo); highs.append(hi)
        draw_point_panel(draw, inner, ["Basic", "Safety-focused"], means, lows, highs, [BLUE, ORANGE], rate)
    image.save(OUT / "figure_prompt_set_effects.png")


def failure_figure():
    failure = pd.read_csv(OUT / "claim_failure_counts_by_prompt_set.csv")
    coverage = pd.read_csv(OUT / "coverage_counts_by_prompt_set.csv")
    categories = ["Distortion", "Unsupported /\ncontradicted", "Omission"]
    values = {"Basic": [], "Safety-focused": []}
    for prompt_set in values:
        f = failure.loc[failure["prompt_set"] == prompt_set].iloc[0]
        c = coverage.loc[coverage["prompt_set"] == prompt_set].iloc[0]
        values[prompt_set] = [f["Partially supported rate"], f["Unsupported rate"] + f["Contradicted rate"], c["Not covered rate"]]
    image, draw = new_canvas("Observed failure rates by prompt set", "Distortion and unsupported rates use generated sentences; omission uses source-unit comparisons")
    x0, y0, x1, y1, max_value = 170, 330, 2080, 1260, 0.30
    for step in range(7):
        value = step * 0.05
        y = y1 - value / max_value * (y1 - y0)
        draw.line((x0, y, x1, y), fill=GRID, width=2)
        draw.text((x0 - 38, y), f"{value:.0%}", font=F_AXIS, fill=MUTED, anchor="rm")
    group_width, bar_width = (x1 - x0) / 3, 170
    for i, category in enumerate(categories):
        center = x0 + group_width * (i + 0.5)
        for offset, prompt_set, color in [(-95, "Basic", BLUE), (95, "Safety-focused", ORANGE)]:
            value = values[prompt_set][i]
            height = value / max_value * (y1 - y0)
            bx0, bx1 = center + offset - bar_width/2, center + offset + bar_width/2
            draw.rounded_rectangle((bx0, y1-height, bx1, y1), radius=10, fill=color)
            draw.text((center + offset, y1-height-15), f"{value:.1%}", font=F_AXIS, fill=color, anchor="ms")
        draw.multiline_text((center, y1 + 34), category, font=F_AXIS, fill=TEXT, anchor="ma", align="center", spacing=4)
    draw.rectangle((700, 210, 745, 245), fill=BLUE); draw.text((760, 226), "Basic", font=F_AXIS, fill=TEXT, anchor="lm")
    draw.rectangle((1040, 210, 1085, 245), fill=ORANGE); draw.text((1100, 226), "Safety-focused", font=F_AXIS, fill=TEXT, anchor="lm")
    image.save(OUT / "figure_failure_rates.png")


def model_figure():
    image, draw = new_canvas("Model-family comparison", "Means averaged within each policy, with 95% bootstrap confidence intervals; n = 27 policies")
    panels = [("flesch_reading_ease", "Flesch Reading Ease", False), ("gemini_source_alignment_rate", "Supported-sentence rate", True), ("weighted_coverage_rate", "Weighted information coverage", True), ("omission_rate", "Omission rate", True)]
    boxes = [(65, 225, 1075, 820), (1125, 225, 2135, 820), (65, 865, 1075, 1460), (1125, 865, 2135, 1460)]
    for pidx, ((column, title, rate), outer) in enumerate(zip(panels, boxes)):
        inner = panel_box(draw, outer, title)
        policy = df.groupby(["policy_id", "model_family"])[column].mean().reset_index()
        means, lows, highs = [], [], []
        for i, model in enumerate(["gpt", "llama", "mistral"]):
            vals = policy.loc[policy["model_family"] == model, column].to_numpy()
            mean, lo, hi = bootstrap_ci(vals, 20260930 + pidx * 10 + i)
            means.append(mean); lows.append(lo); highs.append(hi)
        draw_point_panel(draw, inner, ["GPT", "Llama", "Mistral"], means, lows, highs, [BLUE, GREEN, RED], rate)
    image.save(OUT / "figure_model_comparison.png")


def interpolate_color(value, limit):
    neutral = np.array([245, 247, 250], dtype=float)
    target = np.array([33, 102, 172], dtype=float) if value >= 0 else np.array([202, 55, 55], dtype=float)
    strength = min(1.0, abs(value) / limit) if limit else 0
    rgb = neutral * (1 - strength) + target * strength
    return tuple(int(x) for x in rgb)


def heatmap_figure():
    image, draw = new_canvas("Safety-focused minus basic prompt effects", "Positive values mean the safety-focused prompt increased the metric")
    metrics = [("gemini_source_alignment_rate", "Supported sentences"), ("weighted_coverage_rate", "Coverage"), ("omission_rate", "Omission"), ("flesch_reading_ease", "Reading ease")]
    for left, (column, title) in zip([35, 585, 1135, 1685], metrics):
        draw.rounded_rectangle((left, 250, left+500, 1250), radius=15, fill="#FAFCFE", outline=GRID, width=2)
        draw.text((left+250, 300), title, font=F_SUB, fill=TEXT, anchor="ma")
        cell = df.groupby(["model_family", "prompting_strategy", "prompt_set"])[column].mean().unstack()
        delta = (cell["Safety-focused"] - cell["Basic"]).unstack("prompting_strategy")
        delta = delta.reindex(index=["gpt", "llama", "mistral"], columns=["Zero-shot", "Role-based", "Structured"])
        values, limit = delta.to_numpy(), float(np.max(np.abs(delta.to_numpy()))) or 1.0
        x0, y0, cell_w, cell_h = left+120, 470, 115, 165
        for c, label in enumerate(["Zero", "Role", "Structured"]):
            draw.text((x0+c*cell_w+cell_w/2, y0-35), label, font=F_SMALL, fill=MUTED, anchor="ma")
        for r, model in enumerate(["GPT", "Llama", "Mistral"]):
            draw.text((x0-18, y0+r*cell_h+cell_h/2), model, font=F_SMALL, fill=MUTED, anchor="rm")
            for c in range(3):
                value = float(values[r, c])
                box = (x0+c*cell_w, y0+r*cell_h, x0+(c+1)*cell_w-5, y0+(r+1)*cell_h-5)
                draw.rounded_rectangle(box, radius=8, fill=interpolate_color(value, limit))
                text_color = WHITE if abs(value) / limit > 0.55 else TEXT
                draw.text(((box[0]+box[2])/2, (box[1]+box[3])/2), f"{value:+.3f}", font=F_SMALL, fill=text_color, anchor="mm")
        draw.text((left+250, 1070), "Red = decrease   Blue = increase", font=F_NOTE, fill=MUTED, anchor="ma")
    image.save(OUT / "figure_safety_effect_heatmaps.png")


prompt_set_figure()
failure_figure()
model_figure()
heatmap_figure()
print("Created 4 report-ready figures")
