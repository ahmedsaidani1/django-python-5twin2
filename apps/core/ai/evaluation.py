"""Helpers shared by the ``evaluate_<feature>`` management commands."""

import time
from datetime import datetime
from pathlib import Path

import numpy as np
from django.conf import settings

DOCS_AI_DIR = Path(settings.BASE_DIR) / "docs" / "ai"


class LatencyTimer:
    """Collects per-call latencies in milliseconds."""

    def __init__(self):
        self.samples: list[float] = []

    def time(self, fn, *args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        self.samples.append((time.perf_counter() - start) * 1000)
        return result

    def summary(self) -> dict:
        if not self.samples:
            return {"mean_ms": 0.0, "p95_ms": 0.0, "n": 0}
        arr = np.array(self.samples)
        return {"mean_ms": float(arr.mean()), "p95_ms": float(np.percentile(arr, 95)), "n": len(arr)}


def confusion_matrix_png(cm, labels: list[str], filename: str, title: str) -> Path:
    """Write a confusion-matrix heatmap to docs/ai/<filename> and return the path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    DOCS_AI_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(4.8, 4.2), dpi=120)
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels=labels)
    ax.set_yticks(range(len(labels)), labels=labels)
    ax.set_xlabel("Prédit")
    ax.set_ylabel("Réel")
    ax.set_title(title)
    vmax = cm.max() if cm.size else 0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j,
                i,
                int(cm[i, j]),
                ha="center",
                va="center",
                color="white" if cm[i, j] > vmax / 2 else "#0B2A5B",
                fontsize=12,
            )
    fig.tight_layout()
    path = DOCS_AI_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def md_table(headers: list[str], rows: list[list]) -> str:
    def fmt(v):
        return f"{v:.3f}" if isinstance(v, float) else str(v)

    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def cm_markdown(cm, labels: list[str]) -> str:
    return md_table(["réel \\ prédit", *labels], [[lab, *map(int, cm[i])] for i, lab in enumerate(labels)])


def write_report(feature: str, title: str, sections: list[tuple[str, str]], latency: dict) -> Path:
    DOCS_AI_DIR.mkdir(parents=True, exist_ok=True)
    parts = [
        f"# {title}",
        "",
        f"_Rapport généré automatiquement par `python manage.py evaluate_{feature}` le "
        f"{datetime.now():%d/%m/%Y à %H:%M}._",
        "",
    ]
    for heading, body in sections:
        parts += [f"## {heading}", "", body.strip(), ""]
    parts += [
        "## Latence",
        "",
        md_table(
            ["appels", "moyenne (ms)", "p95 (ms)"],
            [[latency["n"], round(latency["mean_ms"], 3), round(latency["p95_ms"], 3)]],
        ),
        "",
        "Mesurée sur l'inférence locale (sans réseau), un appel par exemple du jeu d'évaluation.",
        "",
    ]
    path = DOCS_AI_DIR / f"{feature}.md"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
