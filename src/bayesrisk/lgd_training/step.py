"""Paso experimental LGD: data → ajuste de historia → artefactos e informe."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from bayesrisk.core.config import config_hash
from bayesrisk.core.mixins import AuditableMixin
from bayesrisk.core.registry import register
from bayesrisk.core.steps import ArtifactKey, ContextoDeResolucion
from bayesrisk.lgd_training.config import LgdTrainingConfig
from bayesrisk.lgd_training.exceptions import LgdTrainingConfigError, LgdTrainingError

if TYPE_CHECKING:
    import numpy as np

    from bayesrisk.core.study import Study

LGD_TRAINING_ARTIFACTS: Final = (
    "fitted_model",
    "model_table",
    "predictions",
    "evaluation",
    "population",
    "card",
)


@register("standard", domain="lgd_training")
class LgdTrainingStep(AuditableMixin):
    """Publica el predictor sólo después de completar ajuste y diagnóstico."""

    name = "lgd_training"
    requires: tuple[ArtifactKey, ...] = (("data", "frame"), ("data", "data_hash"))
    provides: tuple[ArtifactKey, ...] = tuple(
        ("lgd_training", name) for name in LGD_TRAINING_ARTIFACTS
    )

    def __init__(self, config: LgdTrainingConfig) -> None:
        """Recibe los seis roles ya validados."""
        self.config = config

    @classmethod
    def from_config(cls, cfg: LgdTrainingConfig) -> LgdTrainingStep:
        """Construye el paso sin ajustar ni cargar librerías numéricas."""
        return cls(cfg)

    @classmethod
    def from_config_with_context(
        cls, cfg: LgdTrainingConfig, *, contexto: ContextoDeResolucion
    ) -> LgdTrainingStep:
        """Rechaza la mezcla de historia y cartera antes de ejecutar cualquier paso."""
        if "provisioning_internal" in contexto.dominios_activos:
            raise LgdTrainingConfigError(
                "Entrenar LGD requiere otro Study, separado de la cartera de provisión; "
                "aplique después la tabla del predictor como entrada externa."
            )
        return cls(cfg)

    def execute(self, study: Study, rng: np.random.Generator) -> dict[str, Any]:
        """Ajusta sólo la historia declarada, sin consumir azar."""
        from bayesrisk.lgd_training.engine import declaration, fit_history

        del rng
        data = study.config.data
        if data is None or data.target is not None or data.partition is not None:
            raise LgdTrainingError(
                "La historia LGD exige data.target=null y data.partition=null; "
                "usa las muestras LGD declaradas."
            )
        status, text = declaration(study.config.governance)
        context = study.run_context
        if context is None or context.run_id is None:
            raise LgdTrainingError("El ajuste LGD exige una corrida trazada.")
        result = fit_history(
            study.artifacts.get("data", "frame"),
            self.config,
            provenance={
                "source_config_hash": config_hash(study.config),
                "source_data_hash": study.artifacts.get("data", "data_hash"),
                "source_run_id": context.run_id,
                "declaration_status": status,
                "declaration_text": text,
            },
            id_columns=tuple(data.schema_.unique_keys or ()),
            index_name=data.schema_.index_col,
        )
        self.log_decision(
            regla="lgd_training_population",
            umbral="muestras declaradas, entidades disjuntas",
            valor={key: result["card"][key] for key in ("n_train", "n_evaluation", "n_excluded")},
            accion="ajustar_solo_train_y_evaluar_sin_reajuste",
        )
        for key, value in result.items():
            study.artifacts.set(self.name, key, value)
        return result

    @staticmethod
    def metric_sections(study: Study) -> dict[str, Any]:
        """Contexto descriptivo; ninguna métrica equivale a validación de calidad."""
        if not study.artifacts.has("lgd_training", "card"):
            return {}
        return {"lgd_training": study.artifacts.get("lgd_training", "card")}
