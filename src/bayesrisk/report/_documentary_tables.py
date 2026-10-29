"""Proyecciones de lectura D-DOC-SC; el soporte conserva todas las columnas originales."""

from typing import Any

from bayesrisk.binning.results import IV_BAND_LABELS
from bayesrisk.report.prose import (
    _ANCHOR_KINDS,
    _ANCHOR_SOURCES,
    _CALIBRATION_METHODS,
    _COMPARISON_LABELS,
    _MONOTONIC_LABELS,
    _PARTITION_LABELS,
)
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

_READING_HEADERS = {
    "eda.default_rate.by_period": {
        "period": "Período o cohorte",
        "n_total": "Observaciones",
        "n_eligible": "Observaciones elegibles",
        "n_bad": "Incumplimientos",
        "default_rate": "Tasa de incumplimiento",
        "low_confidence": "Baja confianza",
    },
    "eda.quality.by_column": {
        "col": "Variable",
        "dtype": "Tipo de dato",
        "missing_rate": "Proporción de ausentes",
        "cardinality": "Valores distintos",
        "near_constant": "Casi constante",
        "near_unique": "Casi única",
        "high_cardinality": "Alta cardinalidad",
    },
    "validation.discrimination": {
        "partition": "Muestra",
        "n_total": "Observaciones",
        "n_bad": "Incumplimientos",
        "auc": "AUC",
        "gini": "Gini",
        "ks": "KS",
        "source": "Procedencia",
        "status": "Estado",
    },
    "validation.calibration": {
        "partition": "Muestra",
        "test": "Prueba",
        "grade": "Grado",
        "n": "Observaciones",
        "observed_defaults": "Incumplimientos observados",
        "expected_pd": "PD esperada",
        "observed_dr": "Tasa observada",
        "statistic": "Estadístico o puntaje",
        "degrees_of_freedom": "Grados de libertad",
        "p_value": "p-valor",
        "alpha": "Nivel de significación",
        "decision": "Resultado",
        "traffic_light": "Semáforo",
    },
    "validation.stability": {
        "metric": "Medida",
        "comparison": "Comparación",
        "feature": "Variable",
        "value": "Valor",
        "stable_threshold": "Corte Estable",
        "review_threshold": "Corte Revisar",
        "band": "Banda",
        "action": "Acción",
        "source": "Procedencia",
        "status": "Estado",
        "decision": "Resultado",
    },
}
_CALIBRATION_FIELDS = {
    "method": "Método",
    "target_pd": "PD del ancla",
    "anchor_kind": "Tipo de ancla",
    "anchor_source": "Origen del ancla",
    "fit_partition": "Muestra de ajuste",
    "offset": "Desplazamiento del intercepto",
    "slope": "Pendiente",
    "intercept": "Intercepto",
    "isotonic_knots": "Nodos de la calibración isotónica",
    "post_offset": "Desplazamiento posterior",
    "target_tolerance": "Tolerancia del ajuste al ancla",
    "achieved_mean_pd_dev": "PD media calibrada en Desarrollo",
    "raw_mean_pd_dev": "PD media antes de calibrar en Desarrollo",
    "observed_default_rate_dev": "Tasa de incumplimiento observada en Desarrollo",
    "n_fit": "Observaciones del ajuste",
}


def label_reading_table(table: dict[str, Any]) -> dict[str, Any]:
    """Rótulos por esquema: no traducir identificadores de datos ni tablas de extensiones."""
    columns = table["columns"]
    key = table["key"]
    headers = _READING_HEADERS.get(key, {})
    rows = [list(row) for row in table["rows"]]
    if key == "eda.quality.by_column" and "dtype" in columns:
        position = columns.index("dtype")
        types = {
            "float64": "Número decimal (64 bits)",
            "int64": "Número entero (64 bits)",
            "object": "Objeto",
        }
        for row in rows:
            row[position] = types.get(row[position], row[position])
    if key == "calibration.parameters" and "Campo" in columns and "Valor" in columns:
        field_position, value_position = columns.index("Campo"), columns.index("Valor")
        enums = {
            "method": _CALIBRATION_METHODS,
            "anchor_kind": _ANCHOR_KINDS,
            "anchor_source": _ANCHOR_SOURCES,
            "fit_partition": _PARTITION_LABELS,
        }
        for row in rows:
            field = row[field_position]
            row[value_position] = enums.get(field, {}).get(row[value_position], row[value_position])
            row[field_position] = _CALIBRATION_FIELDS.get(field, field)
    return {
        **table,
        "columns": [headers.get(c, c) for c in columns],
        "rows": [tuple(row) for row in rows],
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
