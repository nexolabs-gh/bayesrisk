"""Proyecciones de lectura D-DOC-SC; el soporte conserva todas las columnas originales."""

from typing import Any

from bayesrisk.binning.results import IV_BAND_LABELS
from bayesrisk.report.prose import _COMPARISON_LABELS, _MONOTONIC_LABELS, _PARTITION_LABELS
from bayesrisk.selection.results import REASON_LABELS
from bayesrisk.stability.results import BAND_LABELS, STABILITY_METRIC_LABELS, TEMPORAL_AXIS_LABELS

# Su juicio y sus cifras globales ya están en las tablas resumidas del mismo capítulo.
DETAIL_SUMMARIES = {
    "selection.vif_table": "selection.selection_table",
    "performance.performance_table": "performance.discriminant_metrics",
    "stability.psi_table": "stability.stability_metrics",
}
_REQUIRED = {
    "binning.summary": {"name", "iv_band"},
    "selection.selection_table": {"feature", "included", "reason"},
    "model.coefficients": {"feature", "beta"},
    "scorecard.scorecard": {"feature", "bin_label", "points"},
    "performance.discriminant_metrics": {"partition", "auc"},
    "stability.stability_metrics": {"metric", "value", "band"},
}

_PROJECTIONS = {
    "binning.summary": (
        "name",
        "selected",
        "n_bins",
        "iv",
        "iv_band",
        "monotonic_trend",
        "skipped_reason",
    ),
    "selection.selection_table": ("feature", "included", "reason", "iv", "vif", "detail"),
    "model.coefficients": (
        "feature",
        "beta",
        "standard_error",
        "p_value",
        "conf_low",
        "conf_high",
        "sign_ok",
    ),
    "scorecard.scorecard": ("feature", "bin_label", "woe", "points"),
    "performance.discriminant_metrics": ("partition", "n_total", "n_bad", "auc", "gini", "ks"),
    "stability.stability_metrics": (
        "metric",
        "comparison",
        "feature",
        "value",
        "stable_threshold",
        "review_threshold",
        "band",
    ),
}
_LABELS = {
    "name": "Variable",
    "feature": "Variable",
    "selected": "Seleccionada",
    "n_bins": "Tramos",
    "iv": "IV",
    "iv_band": "Poder predictivo",
    "monotonic_trend": "Tendencia",
    "skipped_reason": "Motivo de omisión",
    "included": "Incluida",
    "reason": "Motivo",
    "vif": "VIF",
    "detail": "Detalle de la decisión",
    "beta": "Coeficiente",
    "standard_error": "Error estándar",
    "p_value": "p-valor",
    "conf_low": "Límite inferior del IC",
    "conf_high": "Límite superior del IC",
    "sign_ok": "Cumple el signo esperado",
    "bin_label": "Tramo",
    "woe": "WoE",
    "points": "Puntos",
    "partition": "Muestra",
    "n_total": "Observaciones",
    "n_bad": "Incumplimientos",
    "auc": "AUC",
    "gini": "Gini",
    "ks": "KS",
    "metric": "Medida",
    "comparison": "Comparación",
    "value": "Valor",
    "stable_threshold": "Corte Estable",
    "review_threshold": "Corte Revisar",
    "band": "Banda",
}


def reading_projection(table: dict[str, Any], source: Any) -> dict[str, Any] | None:
    """Proyecta sólo esquemas conocidos; no interpreta texto libre ni cambia las filas."""
    key = table["key"]
    requested = _PROJECTIONS.get(key)
    diagnostic = key.startswith("validation.calibration_tie_groups.")
    if diagnostic or key.startswith("validation.hosmer_lemeshow_groups."):
        requested = (
            "Grupo",
            "Observaciones",
            "Tasa observada (%)",
            "PD media (%)",
            "Diferencia (pp)",
            "O/E",
            "Bajo mínimo histórico" if diagnostic else "Contribución al estadístico",
        )
    if requested is None:
        return None
    columns = table["columns"]
    if not _REQUIRED.get(key, set()).issubset(columns):
        return None
    positions = [columns.index(c) for c in requested if c in columns]
    if not positions:
        return None
    labels: dict[str, dict[str, str]] = {}
    if key == "binning.summary":
        labels = {"iv_band": IV_BAND_LABELS, "monotonic_trend": _MONOTONIC_LABELS}
    elif key == "selection.selection_table":
        labels = {"reason": REASON_LABELS}
    elif key == "performance.discriminant_metrics":
        labels = {"partition": _PARTITION_LABELS}
    elif key == "stability.stability_metrics":
        labels = {
            "metric": STABILITY_METRIC_LABELS,
            "band": BAND_LABELS,
            "comparison": {**_COMPARISON_LABELS, **TEMPORAL_AXIS_LABELS},
        }

    def cell(row: Any, position: int, row_number: int) -> str:
        column = columns[position]
        value = row[position]
        if column in labels:
            # El formateador general toma el literal "none" como ausencia. En un enum IV
            # significa "sin poder": traducir su original, sin tocar texto libre ni cifras.
            original = source.iloc[row_number][column]
            if isinstance(original, str):
                value = labels[column].get(original, value)
        if diagnostic and column == "O/E" and value == "—" and "Ausencia de O/E" in columns:
            reason = row[columns.index("Ausencia de O/E")]
            if reason != "—":
                value = f"No disponible: {reason}"
        return str(value)

    return {
        **table,
        "columns": [_LABELS.get(columns[p], columns[p]) for p in positions],
        "numeric": [table["numeric"][p] for p in positions],
        "rows": [tuple(cell(row, p, n) for p in positions) for n, row in enumerate(table["rows"])],
    }
