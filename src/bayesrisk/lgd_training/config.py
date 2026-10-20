"""Seis mapeos esenciales para la historia LGD experimental; estimador fijo."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from bayesrisk.core.config import BayesRiskBaseConfig, declara_esenciales
from bayesrisk.lgd_training.exceptions import LgdTrainingConfigError


def _field(title: str, description: str, order: int, *, many: bool = False) -> Any:
    return Field(
        title=title,
        description=description,
        json_schema_extra={
            "ui_essential": True,
            "column_role": "input",
            "ui_widget": "multiselect" if many else "text_input",
            "ui_group": "Historia declarada",
            "ui_order": order,
        },
    )


class LgdTrainingConfig(BayesRiskBaseConfig):
    """Ajusta LGD fraccional con muestras declaradas y evalúa sin volver a ajustar."""

    model_config = ConfigDict(json_schema_extra=declara_esenciales)
    schema_version: Literal["1.0.0"] = Field(
        default="1.0.0", title="Versión del esquema", json_schema_extra={"ui_widget": "hidden"}
    )
    type: Literal["standard"] = Field(
        default="standard", title="Tipo de entrenamiento", json_schema_extra={"ui_widget": "hidden"}
    )
    target_col: str = _field(
        "LGD observada",
        "Columna de severidad observada, entre cero y uno, en las operaciones elegibles.",
        1,
    )
    covariate_cols: tuple[str, ...] = _field(
        "Covariables crudas",
        "Columnas numéricas disponibles para aplicar el predictor. No se transforman ni imputan.",
        2,
        many=True,
    )
    entity_col: str = _field(
        "Entidad de separación",
        "Identifica al deudor: puede repetirse dentro de una muestra, "
        "nunca entre entrenamiento y evaluación elegibles.",
        3,
    )
    sample_col: str = _field(
        "Muestra declarada",
        "Columna con train, evaluation o excluded. "
        "La institución fija las muestras antes del ajuste.",
        4,
    )
    default_col: str = _field(
        "Incumplimiento observado",
        "Marca booleana o 0/1, sin nulos. Sólo se ajustan incumplimientos declarados.",
        5,
    )
    resolved_col: str = _field(
        "Resultado disponible",
        "Marca booleana o 0/1 de resultado completo según definición institucional. "
        "No certifica cierre económico ni ausencia de sesgo.",
        6,
    )

    @model_validator(mode="after")
    def _roles(self) -> Self:
        """Nombres distintos y sin objetivos/roles como predictores."""
        roles = (
            self.target_col,
            self.entity_col,
            self.sample_col,
            self.default_col,
            self.resolved_col,
        )
        if any(not name.strip() for name in (*roles, *self.covariate_cols)):
            raise LgdTrainingConfigError("Los nombres de columna LGD no pueden estar en blanco.")
        if len(set(roles)) != len(roles):
            raise LgdTrainingConfigError(
                "Objetivo, entidad, muestra y flags LGD exigen columnas distintas."
            )
        if not self.covariate_cols or len(set(self.covariate_cols)) != len(self.covariate_cols):
            raise LgdTrainingConfigError(
                "Declara al menos una covariable LGD, sin repeticiones.",
                loc=("lgd_training", "covariate_cols"),
            )
        if set(roles) & set(self.covariate_cols):
            raise LgdTrainingConfigError(
                "Las covariables LGD no pueden incluir objetivo, entidad, muestra ni flags.",
                loc=("lgd_training", "covariate_cols"),
            )
        return self
