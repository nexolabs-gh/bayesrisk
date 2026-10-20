"""Historia LGD guiada, separada de la cartera de aplicación.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from bayesrisk.core.exceptions import BayesRiskError, ConfigError
from bayesrisk.guided._puerta import _PuertaGuiada
from bayesrisk.guided.inference import Inferencia
from bayesrisk.lgd_training.model import LgdModel


class LgdInputError(ConfigError):
    """La historia o sus roles declarados no permiten construir el proyecto."""


class LgdRunError(BayesRiskError):
    """El entrenamiento LGD no terminó y se pidió propagar el diagnóstico."""


class Lgd(_PuertaGuiada):
    """Ajusta sobre train declarado y evalúa aparte, sin partición automática.

    **Experimental (fuera de la garantía SemVer 2.x).**
    """

    _PUERTA: ClassVar[str] = "Lgd"
    _GUIDED_STEP: ClassVar[str] = "lgd_guided"
    _InputError: ClassVar[type[ConfigError]] = LgdInputError
    _RunError: ClassVar[type[BayesRiskError]] = LgdRunError
    _FAMILIA: ClassVar[str] = "lgd"

    def __init__(
        self,
        history: str | Path | pd.DataFrame,
        *,
        target: str,
        features: Sequence[str],
        entity: str,
        sample: str,
        default: str,
        resolved: str,
        id: str | None = None,
        purpose: str | None = None,
        assumptions: Sequence[str] = (),
        limitations: Sequence[str] = (),
        name: str = "lgd",
        run_dir: str | Path = "bayesrisk-runs",
        owner: str | None = None,
        review_every: int = 12,
        track: str | Path | None = None,
        document: Mapping[str, str] | None = None,
        formats: Sequence[str] | None = None,
    ) -> None:
        self._iniciar(name, run_dir)
        try:
            if (
                isinstance(features, str)
                or isinstance(assumptions, str)
                or isinstance(limitations, str)
            ):
                raise LgdInputError(
                    "features, assumptions y limitations exigen secuencias, no texto único."
                )
            if (assumptions or limitations) and purpose is None:
                raise LgdInputError(
                    "Aportar supuestos o limitaciones exige purpose; "
                    "la institución declara el propósito."
                )
            frame, source, label = self._cargar(history)
            from bayesrisk.guided.provision import Provision

            Provision._validar_columnas(
                frame, [target, *features, entity, sample, default, resolved]
            )
            index_col, unique_keys, id_label = self._resolver_id(frame, id)
            cfg: dict[str, Any] = {
                "name": name,
                "audit": {"enabled": True},
                "data": {
                    "load": {"source": source},
                    # El dominio valida contenido después de clasificar la población. Inferir
                    # tipos globales aquí impondría el objetivo también a procesos abiertos.
                    "schema": {
                        "columns": [],
                        "strict": False,
                        "ordered": False,
                        "index_col": index_col,
                        "unique_keys": unique_keys,
                    },
                    "missing": {"special_values": [], "max_missing_rate": 0.99},
                    "target": None,
                    "partition": None,
                },
                "lgd_training": {
                    "target_col": target,
                    "covariate_cols": list(features),
                    "entity_col": entity,
                    "sample_col": sample,
                    "default_col": default,
                    "resolved_col": resolved,
                },
                "report": {
                    "output_dir": str(self._reports_dir),
                    "basename": "lgd_report",
                    "sections": {"required_sections": []},
                },
            }
            if purpose is not None:
                cfg["governance"] = {
                    "model_name": name,
                    "purpose": purpose,
                    "author": owner,
                    "review_period_months": review_every,
                    "assumptions": list(assumptions),
                    "limitations": list(limitations),
                }
            if formats is not None:
                cfg["report"]["formats"] = list(formats)
            if document:
                cfg["report"]["document"] = dict(document)
            if track is not None:
                cfg["tracking"] = {"enabled": True, "tracking_uri": str(track)}
            self._source_label, self._partition_label = label, "muestras declaradas"
            self._inference_lines = (
                f"Identificador: {id_label}",
                "Se conserva toda la historia; las exclusiones se cuentan antes del ajuste",
            )
            self._inferences = (
                Inferencia(
                    regla="inferencia_lgd",
                    valor={"id": id_label},
                    motivo="muestras y población declaradas, sin partición automática",
                ),
            )
            self._config, self._steps = self._resolver_pipeline(self._validar_config(cfg))
            self._publicar_snapshot()
        except BaseException:
            self._descartar_snapshot()
            raise

    @property
    def model_(self) -> LgdModel:
        """Predictor validado de un ajuste terminado; nunca el de un intento anterior."""
        if (
            self._study is None
            or self._study.run_context.status != "done"
            or not self._study.artifacts.has("lgd_training", "fitted_model")
        ):
            raise LgdRunError("El modelo LGD sólo está disponible tras un ajuste terminado.")
        model = self._study.artifacts.get("lgd_training", "fitted_model")
        if type(model) is not LgdModel:
            raise LgdRunError("El artefacto del modelo LGD no es un predictor reconocido.")
        return model.validated()

    def export_excel(self) -> tuple[Path, ...]:
        """Libros de historia y ajuste con diagnóstico, población y predictor completo."""
        return self._exportar_excel()
