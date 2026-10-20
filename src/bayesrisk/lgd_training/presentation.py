"""Rótulos compartidos de los diagnósticos; nunca recalcula métricas."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

_SAMPLES = {"train": "Entrenamiento", "evaluation": "Evaluación", "excluded": "Excluida"}


def readable_evaluation(table: pd.DataFrame) -> pd.DataFrame:
    """Tabla descriptiva de ambas muestras y su referencia fija."""
    result = table.copy(deep=True)
    result["sample"] = result["sample"].map(_SAMPLES)
    result["predictor"] = result["predictor"].map(
        {"fitted": "Modelo ajustado", "train_mean": "Media de entrenamiento"}
    )
    return result.rename(
        columns={
            "sample": "Muestra",
            "predictor": "Predictor",
            "n": "Operaciones",
            "observed_mean": "Media observada",
            "predicted_mean": "Media predicha",
            "bias": "Sesgo medio",
            "mae": "Error absoluto medio",
            "rmse": "Raíz del error cuadrático medio",
        }
    )


def readable_population(table: pd.DataFrame) -> pd.DataFrame:
    """Conteos con motivos legibles; filas excluidas siguen visibles."""
    result = table.copy(deep=True)
    result["sample"] = result["sample"].map(_SAMPLES)
    result["reason"] = result["reason"].map(
        {
            "declared_excluded": "Exclusión declarada",
            "not_default": "Sin incumplimiento",
            "unresolved": "Resultado no disponible",
            "eligible": "Elegible",
        }
    )
    return result.rename(
        columns={
            "sample": "Muestra",
            "default": "Incumplimiento",
            "resolved": "Resultado disponible",
            "reason": "Motivo",
            "missing_target": "Objetivo ausente",
            "missing_features": "Covariable ausente",
            "n": "Operaciones",
        }
    )


def report_tables(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Vistas legibles; el transporte canónico se conserva aparte, sin modificarlo."""
    import pandas as pd

    from bayesrisk.lgd_training.model import LgdModel

    model = LgdModel.from_frame(tables["lgd_training.model_table"])
    return {
        "lgd_training.coefficients": pd.DataFrame(
            {
                "Término": ["Intercepto", *model.features],
                "Coeficiente": [model.intercept, *model.coefficients],
            }
        ),
        "lgd_training.evaluation_readable": readable_evaluation(tables["lgd_training.evaluation"]),
        "lgd_training.population_readable": readable_population(tables["lgd_training.population"]),
    }
