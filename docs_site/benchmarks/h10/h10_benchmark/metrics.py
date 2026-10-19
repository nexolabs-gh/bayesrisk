"""Métricas exteriores comunes; PD creciente de riesgo y bootstrap de grupos."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, roc_curve

from .contract import SEED


def measure(y: pd.Series, probability: pd.Series, reference: pd.Series) -> dict:
    """Rechaza desalineación antes de convertir a arrays; PSI sólo con cortes Desarrollo."""
    if not y.index.is_unique or not y.index.equals(probability.index):
        raise ValueError("índice/orden de etiquetas y predicciones diferentes")
    if set(y.unique()) != {0, 1}:
        raise ValueError("target requiere ambas clases 0/1")
    for values in (probability, reference):
        if not len(values) or not np.isfinite(values).all() or not values.between(0, 1).all():
            raise ValueError("PD ausente, no finita o fuera de rango")
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, 11)))
    if len(edges) < 2:
        raise ValueError("referencia PSI degenerada")
    edges[0], edges[-1] = -np.inf, np.inf
    a = np.maximum(np.histogram(reference, edges)[0] / len(reference), 1e-6)
    b = np.maximum(np.histogram(probability, edges)[0] / len(probability), 1e-6)
    a, b = a / a.sum(), b / b.sum()
    auc = float(roc_auc_score(y, probability))
    fpr, tpr, _ = roc_curve(y, probability)
    return {
        "n": len(y),
        "events": int(y.sum()),
        "auc": auc,
        "gini": 2 * auc - 1,
        "ks": float(max(tpr - fpr)),
        "brier": float(brier_score_loss(y, probability)),
        "logloss": float(log_loss(y, probability)),
        "observed": float(y.mean()),
        "mean_pd": float(probability.mean()),
        "psi": float(np.sum((a - b) * np.log(a / b))),
        "psi_bins": len(edges) - 1,
    }


def grouped_auc_difference(
    y: pd.Series, candidate: pd.Series, baseline: pd.Series, groups: pd.Series
) -> dict:
    """Intervalo exploratorio condicionado; una réplica inválida impide publicar el IC."""
    if not all(y.index.equals(v.index) for v in (candidate, baseline, groups)):
        raise ValueError("orden de bootstrap desalineado")
    positions = [np.flatnonzero(groups.to_numpy() == group) for group in pd.unique(groups)]
    rng = np.random.default_rng(SEED)
    deltas = []
    invalid = 0
    for _ in range(1000):
        ids = np.concatenate(
            [positions[i] for i in rng.integers(0, len(positions), len(positions))]
        )
        actual = y.iloc[ids]
        if actual.nunique() != 2:
            invalid += 1
        else:
            deltas.append(
                float(
                    roc_auc_score(actual, candidate.iloc[ids])
                    - roc_auc_score(actual, baseline.iloc[ids])
                )
            )
    interval = None if invalid else np.quantile(deltas, [0.025, 0.975]).tolist()
    return {
        "replicates": 1000,
        "invalid": invalid,
        "groups": len(positions),
        "seed": SEED,
        "delta_auc": float(roc_auc_score(y, candidate) - roc_auc_score(y, baseline)),
        "interval_95": interval,
        "limitation": (
            "Condicionado a modelos y partición; sin varianza de entrenamiento "
            "ni ajuste por multiplicidad."
        ),
    }
