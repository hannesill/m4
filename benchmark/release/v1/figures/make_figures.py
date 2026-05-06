#!/usr/bin/env python3
"""Generate matplotlib figures for the manuscript.

Outputs PDF figures into figures/. Data sources:

- gpt-oss-20b per-task deltas: taken from planning/final_oss_runs.csv when
  present; otherwise hardcoded from the last exploratory local run snapshot.
- Codex per-task deltas: taken from tables/codex_skill_gains.tex and
  tables/codex_skill_declines.tex (top 10 + bottom 8 covered).
- Claude per-task deltas: taken from tables/claude_task_deltas.tex.
- Schema-probe values: taken from the final exploratory OSS rerun snapshot.

Figures produced:

  figures/skill_delta_forest_v1.pdf       per-task forest plot, 3 providers
  figures/skill_delta_forest_v2.pdf       heatmap, tasks x providers
  figures/schema_probe_slopes_v1.pdf      slope graph, native -> obf -> rest
  figures/schema_probe_slopes_v2.pdf      grouped bar chart, by task

The figures are designed for grayscale-friendly double-blind submissions.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

# Make sure matplotlib finds a writable cache directory.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/m4bench-mpl-cache")
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

M4_DIR = Path(
    os.environ.get("M4BENCH_M4_DIR", Path(__file__).resolve().parents[4])
).resolve()
PAPER_DIR = Path(
    os.environ.get("M4BENCH_PAPER_DIR", M4_DIR.parent / "m4bench-paper")
).resolve()
FIG_DIR = PAPER_DIR / "figures"
FIG_DIR.mkdir(exist_ok=True)

OSS_RUNS_CSV = PAPER_DIR / "planning/final_oss_runs.csv"

CODEX_DELTAS = {
    "mimic-urine-output-rate": 0.508,
    "mimic-urine-output-rate-raw": 0.500,
    "mimic-meld-24h": 0.328,
    "mimic-meld-24h-raw": 0.322,
    "mimic-suspicion-infection-raw": 0.260,
    "mimic-creatinine-baseline": 0.246,
    "mimic-ventilation": 0.243,
    "mimic-creatinine-baseline-raw": 0.217,
    "mimic-suspicion-infection": 0.115,
    "eicu-oasis": 0.103,
    "mimic-vasopressor-equivalents-raw": -0.026,
    "mimic-sofa-24h-raw": -0.018,
    "mimic-charlson-raw": -0.008,
    "mimic-kdigo-48h": 0.007,
    "mimic-sapsii-24h-raw": 0.007,
    "mimic-vasopressor-equivalents": 0.007,
    "mimic-ventilation-raw": 0.014,
    "mimic-sirs-24h-raw": 0.015,
}

CLAUDE_DELTAS = {
    "mimic-urine-output-rate-raw": 0.426,
    "mimic-ventilation": 0.229,
    "mimic-creatinine-baseline-raw": 0.204,
    "mimic-suspicion-infection": 0.148,
    "mimic-oasis-24h": 0.113,
    "mimic-vasopressor-equivalents-raw": 0.085,
    "mimic-sepsis3-raw": 0.035,
    "mimic-sofa-24h-raw": -0.002,
}


def load_task_deltas_from_runs(
    path: Path, fallback: dict[str, float]
) -> dict[str, float]:
    """Load task-balanced native skill deltas from generated final run CSVs."""
    if not path.exists():
        return dict(fallback)
    groups: dict[tuple[str, str, str], list[float]] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("schema") != "native":
                continue
            condition = row.get("condition")
            if condition not in {"no-skill", "with-skill"}:
                continue
            reward = row.get("reward")
            if reward in {"", None}:
                continue
            key = (row["task"], row["model"], condition)
            groups.setdefault(key, []).append(float(reward))
    tasks = sorted({task for task, _, _ in groups})
    out: dict[str, float] = {}
    for task in tasks:
        model_deltas = []
        for model in sorted({model for t, model, _ in groups if t == task}):
            no_skill = groups.get((task, model, "no-skill"), [])
            with_skill = groups.get((task, model, "with-skill"), [])
            if no_skill and with_skill:
                model_deltas.append(
                    sum(with_skill) / len(with_skill) - sum(no_skill) / len(no_skill)
                )
        if model_deltas:
            out[task] = sum(model_deltas) / len(model_deltas)
    return out or dict(fallback)


CODEX_DELTAS = load_task_deltas_from_runs(
    PAPER_DIR / "planning/final_codex_runs.csv", CODEX_DELTAS
)
CLAUDE_DELTAS = load_task_deltas_from_runs(
    PAPER_DIR / "planning/final_claude_runs.csv", CLAUDE_DELTAS
)

PI_FALLBACK = {
    "mimic-creatinine-baseline-raw": 0.105,
    "mimic-oasis-24h": -0.048,
    "mimic-sepsis3-raw": 0.000,
    "mimic-sofa-24h-raw": -0.124,
    "mimic-suspicion-infection": 0.154,
    "mimic-urine-output-rate-raw": 0.171,
    "mimic-vasopressor-equivalents-raw": -0.165,
    "mimic-ventilation": -0.026,
}


def compute_pi_deltas() -> dict[str, float]:
    """Load exploratory local gpt-oss native skill deltas."""
    return load_task_deltas_from_runs(OSS_RUNS_CSV, PI_FALLBACK)


def family_of(task: str) -> str:
    base = task.replace("-raw", "")
    parts = base.split("-")
    if parts[0] in {"mimic", "eicu"}:
        parts = parts[1:]
    family = parts[0]
    if family in {"creatinine", "kdigo", "urine"}:
        return "renal"
    if family in {"sofa", "sapsii", "apsiii", "oasis", "sirs"}:
        return "severity"
    if family in {"sepsis3", "suspicion"}:
        return "infection"
    if family in {"meld"}:
        return "liver"
    if family in {"ventilation", "vasopressor"}:
        return "respiratory/cv"
    if family in {"gcs"}:
        return "neuro"
    if family in {"charlson"}:
        return "comorbidity"
    return family


def short_name(task: str) -> str:
    name = task.replace("mimic-", "").replace("eicu-", "")
    return name


def fig_skill_delta_forest_v1() -> None:
    pi = compute_pi_deltas()
    all_tasks = sorted(
        set(list(pi.keys()) + list(CODEX_DELTAS.keys()) + list(CLAUDE_DELTAS.keys()))
    )

    by_family: dict[str, list[str]] = {}
    for task in all_tasks:
        by_family.setdefault(family_of(task), []).append(task)
    family_order = [
        "renal",
        "severity",
        "infection",
        "liver",
        "respiratory/cv",
        "neuro",
        "comorbidity",
    ]
    ordered_tasks: list[str] = []
    for fam in family_order:
        for task in by_family.get(fam, []):
            ordered_tasks.append(task)

    n = len(ordered_tasks)
    fig, ax = plt.subplots(figsize=(7.6, 0.27 * n + 1.6))

    style = {
        "Codex": dict(marker="s", color="#1f4e79", label="Codex (top/bottom 18 tasks)"),
        "Claude": dict(marker="^", color="#7a4f9c", label="Claude (8-task sentinel)"),
        "gpt-oss-20b": dict(
            marker="o", color="#a14a3a", label="gpt-oss-20b (8-task local)"
        ),
    }

    yticks = []
    yticklabels = []
    for i, task in enumerate(ordered_tasks):
        y = n - 1 - i
        yticks.append(y)
        label = f"{short_name(task)}  [{family_of(task)}]"
        yticklabels.append(label)
        for label_p, deltas in [
            ("Codex", CODEX_DELTAS),
            ("Claude", CLAUDE_DELTAS),
            ("gpt-oss-20b", pi),
        ]:
            if task not in deltas:
                continue
            d = deltas[task]
            offset = {"Codex": 0.18, "Claude": 0.0, "gpt-oss-20b": -0.18}[label_p]
            ax.scatter(
                [d],
                [y + offset],
                s=42,
                zorder=3,
                **{k: v for k, v in style[label_p].items() if k != "label"},
            )

    ax.axvline(0.0, color="black", linewidth=0.6, linestyle="--", zorder=1)
    ax.set_yticks(yticks)
    ax.set_yticklabels(yticklabels, fontsize=8)
    ax.set_xlabel("Task-level skill delta (with-skill minus no-skill, mean reward)")
    ax.set_xlim(-0.6, 0.6)
    ax.grid(axis="x", linewidth=0.3, alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    handles = [
        plt.Line2D(
            [0],
            [0],
            marker=v["marker"],
            color=v["color"],
            linestyle="None",
            label=v["label"],
            markersize=6,
        )
        for v in style.values()
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.04),
        bbox_transform=ax.transAxes,
        ncol=3,
        fontsize=8,
        frameon=False,
        handletextpad=0.4,
        columnspacing=1.6,
    )

    plt.tight_layout()
    plt.savefig(FIG_DIR / "skill_delta_forest_v1.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_skill_delta_forest_v2() -> None:
    pi = compute_pi_deltas()
    providers = ["Codex", "Claude", "gpt-oss-20b"]
    sources = {"Codex": CODEX_DELTAS, "Claude": CLAUDE_DELTAS, "gpt-oss-20b": pi}
    all_tasks = sorted(
        set(list(pi.keys()) + list(CODEX_DELTAS.keys()) + list(CLAUDE_DELTAS.keys()))
    )
    by_family: dict[str, list[str]] = {}
    for task in all_tasks:
        by_family.setdefault(family_of(task), []).append(task)
    family_order = [
        "renal",
        "severity",
        "infection",
        "liver",
        "respiratory/cv",
        "neuro",
        "comorbidity",
    ]
    ordered_tasks: list[str] = []
    for fam in family_order:
        for task in by_family.get(fam, []):
            ordered_tasks.append(task)
    matrix = np.full((len(ordered_tasks), len(providers)), np.nan)
    for i, task in enumerate(ordered_tasks):
        for j, prov in enumerate(providers):
            if task in sources[prov]:
                matrix[i, j] = sources[prov][task]
    fig, ax = plt.subplots(figsize=(4.0, 0.27 * len(ordered_tasks) + 1.0))
    vmax = 0.55
    cmap = matplotlib.colormaps["RdBu_r"]
    cmap.set_bad(color="white")
    masked = np.ma.array(matrix, mask=np.isnan(matrix))
    im = ax.imshow(masked, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            if np.isnan(v):
                ax.text(j, i, "-", ha="center", va="center", fontsize=7, color="black")
            else:
                txt_color = "white" if abs(v) > 0.30 else "black"
                ax.text(
                    j,
                    i,
                    f"{v:+.2f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color=txt_color,
                )
    ax.set_xticks(range(len(providers)))
    ax.set_xticklabels(providers, fontsize=8)
    ax.set_yticks(range(len(ordered_tasks)))
    ax.set_yticklabels(
        [f"{short_name(t)}  [{family_of(t)}]" for t in ordered_tasks], fontsize=7
    )
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("Skill delta", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    ax.set_title("Skill delta heatmap (task x provider)", fontsize=10)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "skill_delta_forest_v2.pdf", bbox_inches="tight")
    plt.close(fig)


CODEX_SCHEMA = {
    "suspected infection": (0.605, 0.063, 0.239),
    "Sepsis-3 raw": (0.395, 0.144, 0.113),
    "KDIGO-48h": (0.925, 0.644, 0.694),
    "MELD-24h": (0.779, 0.503, 0.544),
    "ventilation": (0.455, 0.274, 0.242),
    "vasopressor equivalents": (0.982, 0.826, 0.798),
}
PI_SCHEMA = {
    "SOFA-24h raw": (0.124, 0.000, 0.000),
}


def fig_schema_slopes_v1() -> None:
    fig, axes = plt.subplots(
        1, 2, figsize=(9.5, 3.8), sharey=True, gridspec_kw={"wspace": 0.06}
    )
    xs = np.array([0, 1, 2])
    xticklabels = ["native", "obfuscated", "restructured"]
    palette = [
        "#1f4e79",
        "#2e75b6",
        "#7a4f9c",
        "#a14a3a",
        "#e08a3c",
        "#3f7d3f",
        "#7d6b3f",
    ]
    markers = ["o", "s", "^", "D", "v", ">", "<"]

    for ax, title, data in [
        (axes[0], "Codex (6 contamination tasks)", CODEX_SCHEMA),
        (axes[1], "gpt-oss-20b (1 matched task)", PI_SCHEMA),
    ]:
        for i, (label, vals) in enumerate(data.items()):
            ax.plot(
                xs,
                vals,
                marker=markers[i % len(markers)],
                linewidth=1.1,
                color=palette[i % len(palette)],
                alpha=0.85,
                markersize=5,
                label=label,
            )
        mean_y = np.array([np.mean([v[i] for v in data.values()]) for i in range(3)])
        ax.plot(
            xs,
            mean_y,
            marker="s",
            linewidth=2.6,
            color="black",
            label="mean over tasks",
            zorder=4,
            markersize=6,
        )
        ax.set_xticks(xs)
        ax.set_xticklabels(xticklabels, fontsize=9)
        ax.set_xlim(-0.15, 2.15)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", linewidth=0.3, alpha=0.4)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            fontsize=7.5,
            frameon=False,
            handlelength=1.6,
            borderpad=0.2,
            labelspacing=0.35,
        )
    axes[0].set_ylabel("No-skill mean reward")
    axes[0].set_ylim(-0.02, 1.05)
    fig.suptitle(
        "Schema-perturbation effect (no-skill, native ground-truth values preserved)",
        fontsize=10,
    )
    plt.savefig(FIG_DIR / "schema_probe_slopes_v1.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_schema_slopes_v2() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.6), sharey=True)
    schemas = ["native", "obfuscated", "restructured"]
    schema_colors = ["#444444", "#888888", "#cccccc"]
    for ax, title, data in [
        (axes[0], "Codex (6 contamination tasks)", CODEX_SCHEMA),
        (axes[1], "gpt-oss-20b (1 matched task)", PI_SCHEMA),
    ]:
        labels = list(data.keys())
        x = np.arange(len(labels))
        width = 0.27
        for i, schema in enumerate(schemas):
            ys = [data[label][i] for label in labels]
            ax.bar(
                x + (i - 1) * width,
                ys,
                width,
                label=schema,
                color=schema_colors[i],
                edgecolor="black",
                linewidth=0.4,
            )
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", linewidth=0.3, alpha=0.4)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    axes[0].set_ylabel("No-skill mean reward")
    axes[0].set_ylim(0, 1.0)
    axes[1].legend(loc="upper right", fontsize=8, frameon=False)
    fig.suptitle("Schema-perturbation effect, grouped by task", fontsize=10)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(FIG_DIR / "schema_probe_slopes_v2.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    fig_skill_delta_forest_v1()
    fig_skill_delta_forest_v2()
    fig_schema_slopes_v1()
    fig_schema_slopes_v2()
    print("wrote:")
    for p in sorted(FIG_DIR.glob("*.pdf")):
        print(" ", p.relative_to(PAPER_DIR))


if __name__ == "__main__":
    main()
