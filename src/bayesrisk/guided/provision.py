"""Provisión interna guiada (H3): cliente del motor y sus artefactos.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import hashlib
import io
import os
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from bayesrisk.core.exceptions import BayesRiskError, ConfigError
from bayesrisk.guided._puerta import _PuertaGuiada
from bayesrisk.guided.inference import Inferencia, columnas_esquema
from bayesrisk.lgd_training.model import LgdModel


class ProvisionInputError(ConfigError):
    """Entrada declarada incompatible con la cartera o con el proyecto de destino."""


class ProvisionRunError(BayesRiskError):
    """La provisión falló y se solicitó propagar su diagnóstico."""


class Provision(_PuertaGuiada):
    """Provisión interna experimental con PD/LGD declaradas, sin reajustar esas entradas.

    ``pd`` y ``lgd`` nombran columnas. La fórmula es la de grupos del motor vigente, y el
    detalle distribuye el total grupal por exposición. Sin ``id`` sólo se verifica el índice
    técnico; no se acredita unicidad económica. ``from_scorecard`` compone el pipeline de PD
    como un proyecto distinto, con cobertura completa y sin modificar evidencia del original.

    **Experimental (fuera de la garantía SemVer 2.x).**
    """

    _PUERTA: ClassVar[str] = "Provision"
    _GUIDED_STEP: ClassVar[str] = "provision_guided"
    _InputError: ClassVar[type[ConfigError]] = ProvisionInputError
    _RunError: ClassVar[type[BayesRiskError]] = ProvisionRunError
    _FAMILIA: ClassVar[str] = "provision_interna"

    def __init__(
        self,
        data: str | Path | pd.DataFrame,
        *,
        as_of: str,
        portfolio: str,
        exposure: str,
        pd: str,
        lgd: str | LgdModel,
        id: str | None = None,
        name: str = "provision",
        run_dir: str | Path = "bayesrisk-runs",
        purpose: str | None = None,
        owner: str | None = None,
        review_every: int = 12,
        track: str | Path | None = None,
        document: Mapping[str, str] | None = None,
        formats: Sequence[str] | None = None,
    ) -> None:
        self._iniciar(name, run_dir)
        self._external_files: list[tuple[Path, str]] = []
        try:
            frame, source, label = self._cargar(data)
            self._validar_columnas(
                frame, [as_of, portfolio, exposure, pd, *self._columnas_lgd(lgd)]
            )
            index_col, unique_keys, id_label = self._resolver_id(frame, id)
            esquema = columnas_esquema(frame)
            cfg: dict[str, Any] = {
                "name": name,
                "audit": {"enabled": True},
                "data": {
                    "load": {"source": source},
                    "schema": {
                        "columns": esquema,
                        "strict": False,
                        "ordered": False,
                        "index_col": index_col,
                        "unique_keys": unique_keys,
                    },
                    "missing": {"special_values": [], "max_missing_rate": 0.99},
                    "target": None,
                    "partition": None,
                },
                "provisioning_internal": self._seccion(as_of, portfolio, exposure, lgd),
                "report": {
                    "output_dir": str(self._reports_dir),
                    "basename": "provision_interna_report",
                    "sections": {"required_sections": []},
                },
            }
            if formats is not None:
                cfg["report"]["formats"] = list(formats)
            if document:
                cfg["report"]["document"] = dict(document)
            if purpose is not None:
                cfg["governance"] = {
                    "model_name": name,
                    "purpose": purpose,
                    "author": owner,
                    "review_period_months": review_every,
                }
            if track is not None:
                cfg["tracking"] = {"enabled": True, "tracking_uri": str(track)}
            tabla_pd = frame[[pd]].rename(columns={pd: "pd_calibrated"}).copy(deep=True)
            self._artifacts = {("calibration", "calibrated_pd_frame"): tabla_pd}
            if isinstance(lgd, LgdModel):
                self._artifacts[("lgd_training", "model_table")] = lgd.validated().to_frame()
            self._inferencias(label, id_label, len(esquema))
            self._config, self._steps = self._resolver_pipeline(
                self._validar_config(cfg), artifacts=self._artifacts
            )
            self._publicar_snapshot()
            self._guardar_entradas()
        except BaseException:
            self._descartar_snapshot()
            raise

    @classmethod
    def from_scorecard(
        cls,
        scorecard: Any,
        *,
        as_of: str,
        portfolio: str,
        exposure: str,
        lgd: str | LgdModel,
        name: str = "provision",
        run_dir: str | Path = "bayesrisk-runs",
    ) -> Provision:
        """Compone PD y provisión en otro proyecto; no reutiliza resultados de una corrida."""
        from bayesrisk.guided.scorecard import Scorecard

        if not isinstance(scorecard, Scorecard):
            raise ProvisionInputError("from_scorecard exige un Scorecard construido.")
        obj = _ProvisionScorecard.__new__(_ProvisionScorecard)
        obj._iniciar(name, run_dir)
        obj._external_files = []
        if (
            obj.project_dir == scorecard.project_dir
            or obj.project_dir in scorecard.project_dir.parents
            or scorecard.project_dir in obj.project_dir.parents
        ):
            raise ProvisionInputError(
                "El destino coincide con el proyecto del scorecard; usa otro name o run_dir."
            )
        scorecard._verificar_fuente()
        data_config = scorecard.config.data
        if data_config is None or data_config.load.source is None:
            raise ProvisionInputError("El Scorecard no declara una fuente de datos reproducible.")
        try:
            frame, source, label = obj._cargar(Path(data_config.load.source))
            obj._validar_columnas(frame, [as_of, portfolio, exposure, *cls._columnas_lgd(lgd)])
            cfg = deepcopy(scorecard.config.model_dump(mode="python", by_alias=True))
            cfg["name"] = name
            cfg["run"] = {"steps": None}
            cfg["data"]["load"]["source"] = source
            cfg["provisioning_internal"] = obj._seccion(as_of, portfolio, exposure, lgd)
            cfg["provisioning_internal"]["type"] = "full_population"
            if cfg.get("report") is not None:
                cfg["report"]["output_dir"] = str(obj._reports_dir)
            obj._inferences = scorecard.inferences
            obj._source_label = label
            obj._partition_label = scorecard._partition_label
            obj._inference_lines = (
                *scorecard._inference_lines,
                "Proyecto nuevo: la provisión consume toda la población con PD disponible",
            )
            if isinstance(lgd, LgdModel):
                obj._artifacts[("lgd_training", "model_table")] = lgd.validated().to_frame()
            obj._config, obj._steps = obj._resolver_pipeline(
                obj._validar_config(cfg), artifacts=obj._artifacts
            )
            obj._publicar_snapshot()
            obj._guardar_entradas()
            return obj
        except BaseException:
            obj._descartar_snapshot()
            raise

    @staticmethod
    def _columnas_lgd(lgd: str | LgdModel) -> tuple[str, ...]:
        if isinstance(lgd, LgdModel):
            return lgd.validated().features
        if not isinstance(lgd, str):
            raise ProvisionInputError("lgd exige una columna o un LgdModel validado.")
        return (lgd,)

    @staticmethod
    def _seccion(as_of: str, portfolio: str, exposure: str, lgd: str | LgdModel) -> dict[str, Any]:
        return {
            "as_of_date_col": as_of,
            "portfolio_col": portfolio,
            "exposure_col": exposure,
            "lgd": {"method": "fitted"}
            if isinstance(lgd, LgdModel)
            else {"method": "provided", "lgd_col": lgd},
        }

    @staticmethod
    def _validar_columnas(frame: pd.DataFrame, columns: Sequence[str]) -> None:
        if not frame.columns.is_unique or not frame.index.is_unique:
            raise ProvisionInputError("La cartera exige columnas e índice técnico únicos.")
        missing = [c for c in columns if not isinstance(c, str) or not c.strip() or c not in frame]
        if missing:
            raise ProvisionInputError(f"La cartera no trae las columnas declaradas: {missing}.")

    def _inferencias(self, label: str, id_label: str, n_columns: int) -> None:
        self._source_label = label
        self._partition_label = ""
        self._inference_lines = (
            f"Esquema inferido: {n_columns} columnas",
            f"Identificador: {id_label}",
            "PD externa declarada; esta corrida no ajusta ni calibra la PD",
        )
        self._inferences = (
            Inferencia(
                regla="inferencia_provision",
                valor={"id": id_label},
                motivo="la puerta usa PD y LGD declaradas y no inventa muestras",
            ),
        )

    def _guardar_entradas(self) -> None:
        """Entradas externas en el proyecto: el config por sí solo no las reconstruye."""
        for (domain, key), table in self._artifacts.items():
            buffer = io.BytesIO()
            table.to_parquet(buffer)
            content = buffer.getvalue()
            digest = hashlib.sha256(content).hexdigest()
            path = self.project_dir / "input" / f"external-{domain}-{key}-{digest[:16]}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
                temporary.write_bytes(content)
                os.replace(temporary, path)
            self._external_files.append((path, digest))

    def _verificar_fuente(self) -> None:
        super()._verificar_fuente()
        for path, digest in self._external_files:
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ProvisionInputError(
                    "Una entrada externa cambió; construye un Provision nuevo."
                )

    def export_excel(self) -> tuple[Path, ...]:
        """Libros de las etapas realizadas, con resumen y tablas completas."""
        return self._exportar_excel()


class _ProvisionScorecard(Provision):
    """La misma puerta con los rótulos de la cadena combinada, sin cambiar el scorecard."""

    _FAMILIA: ClassVar[str] = "pd_provision"
