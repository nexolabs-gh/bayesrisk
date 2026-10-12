"""Paso orquestable de la capa ``master_scale`` (SDD-32 §2, §6, §7; CT-1).

``MasterScaleStep`` corre al final del scorecard —después de ``validation`` y antes de ``report``—
sobre lo que ya publicaron ``scorecard`` y ``calibration``: el puntaje por operación, la tarjeta
(sus puntos y sus límites, para los rótulos), la PD calibrada y el ancla efectiva de la
calibración. No consume ni modifica nada más.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Final, TypeAlias, cast

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.core.mixins import AuditableMixin
from bayesrisk.core.registry import register
from bayesrisk.core.steps import ArtifactKey, campo_de_card
from bayesrisk.master_scale.config import MasterScaleConfig
from bayesrisk.master_scale.exceptions import MasterScaleFitError

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    from bayesrisk.core.audit import AuditEvent
    from bayesrisk.core.study import Study
    from bayesrisk.master_scale.results import MasterScaleResult

    DataFrame: TypeAlias = pd.DataFrame
else:
    AuditEvent: TypeAlias = Any
    DataFrame: TypeAlias = Any
    MasterScaleResult: TypeAlias = Any

__all__ = ["MASTER_SCALE_ARTIFACTS", "MasterScaleStep"]

MASTER_SCALE_ARTIFACTS: Final[tuple[str, ...]] = (
    "grades",
    "grade_table",
    "cutoff_table",
    "assignment",
    "result",
    "card",
)
#: Las muestras del ajuste, en su orden de lectura, y la de las operaciones fuera del ajuste.
_MUESTRAS_DEL_AJUSTE: Final[tuple[str, ...]] = ("desarrollo", "holdout", "oot")
_FUERA_DEL_AJUSTE: Final = "fuera_de_modelo"
_DESARROLLO: Final = "desarrollo"
_MAYOR_ES_MENOR_RIESGO: Final = "higher_is_lower_risk"
_SCORING_EXTRA_MESSAGE: Final = (
    "MasterScaleStep requiere pandas/numpy/scipy; instale bayesrisk[scoring]."
)
#: Las reglas de formación, tal como van al trail (constantes, §5.2).
_REGLA_DE_FORMACION: Final[dict[str, Any]] = {
    "participacion_minima": 0.05,
    "p_valor_maximo_entre_vecinos": 0.05,
    "tramos_maximos": 10,
    "monotona": True,
}


@register("standard", domain="master_scale")
class MasterScaleStep(AuditableMixin):
    """Forma la escala maestra, le da su PD y publica la tabla de puntos de corte."""

    name: str = "master_scale"
    requires: tuple[ArtifactKey, ...] = (
        ("scorecard", "score"),
        ("scorecard", "scorecard"),
        ("scorecard", "card"),
        ("calibration", "calibrated_pd_frame"),
        ("calibration", "parameters"),
    )
    #: Las solicitudes fuera del ajuste (D-TTD) entran como una muestra más si existen (§3.5).
    optional_requires: tuple[ArtifactKey, ...] = (("scorecard", "out_of_model_score"),)
    provides: tuple[ArtifactKey, ...] = tuple(
        ("master_scale", key) for key in MASTER_SCALE_ARTIFACTS
    )

    def __init__(self, config: MasterScaleConfig) -> None:
        """Construye el paso desde la sección ``MasterScaleConfig`` ya validada."""
        self.config = config

    @classmethod
    def from_config(cls, cfg: MasterScaleConfig) -> MasterScaleStep:
        """Construye ``MasterScaleStep`` desde ``BayesRiskConfig.master_scale``."""
        return cls(cfg)

    def emit(self, event: AuditEvent) -> None:
        """Permite pasar el paso como ``AuditSink``."""
        self._audit.emit(event)

    def execute(self, study: Study, rng: np.random.Generator) -> MasterScaleResult:
        """Forma la escala sobre Desarrollo, la lee en cada muestra y publica sus artefactos."""
        del rng
        pd = _importar("pandas")
        np = _importar("numpy")
        from bayesrisk.master_scale import engine
        from bayesrisk.master_scale.results import (
            MasterScaleCardSection,
            MasterScaleResult,
            SampleDiagnostics,
        )

        cfg = _config_desde_study(study, respaldo=self.config)
        puntaje = _como_frame(study.artifacts.get("scorecard", "score"), pd, "scorecard.score")
        tarjeta = _como_frame(
            study.artifacts.get("scorecard", "scorecard"), pd, "scorecard.scorecard"
        )
        ficha = study.artifacts.get("scorecard", "card")
        pd_frame = _como_frame(
            study.artifacts.get("calibration", "calibrated_pd_frame"),
            pd,
            "calibration.calibrated_pd_frame",
        )
        parametros = study.artifacts.get("calibration", "parameters")

        direccion = str(campo_de_card(ficha, "score_direction") or _MAYOR_ES_MENOR_RIESGO)
        mayor_es_menor_riesgo = direccion == _MAYOR_ES_MENOR_RIESGO
        columna = str(campo_de_card(ficha, "score_column") or "score")
        _exigir_columnas(puntaje, ("partition", "target", columna), "scorecard.score")
        if not pd_frame.index.equals(puntaje.index):
            raise MasterScaleFitError(
                "El puntaje y la PD calibrada no tienen el mismo índice: la escala no puede "
                "alinear cada operación con su PD."
            )
        ancla = _numero(campo_de_card(parametros, "target_pd"), "calibration.parameters.target_pd")
        fuente_ancla = str(campo_de_card(parametros, "anchor_source") or "")

        base = pd.DataFrame(
            {
                "partition": puntaje["partition"].astype("string").astype(str),
                "target": pd.to_numeric(puntaje["target"], errors="coerce").astype("float64"),
                "score": pd.to_numeric(puntaje[columna], errors="coerce").astype("float64"),
            },
            index=puntaje.index,
        )
        desarrollo = base.loc[(base["partition"] == _DESARROLLO) & base["target"].notna()]
        desarrollo = desarrollo.loc[desarrollo["score"].notna()]
        if desarrollo.empty:
            raise MasterScaleFitError(
                "La escala maestra se forma sobre Desarrollo y la muestra no trae operaciones "
                "puntuadas con desenlace."
            )

        # ── los cortes (D-ESC-1 o los de la institución) ─────────────────────────────────
        if cfg.grade_edges is not None:
            cortes = tuple(float(c) for c in cfg.grade_edges)
            fuente = "institution"
            formacion = None
        else:
            formacion = engine.formar_cortes(
                desarrollo["score"].to_numpy(),
                desarrollo["target"].to_numpy(),
                mayor_es_menor_riesgo=mayor_es_menor_riesgo,
            )
            cortes = formacion.cuts
            fuente = "formed"
        k = len(cortes) + 1
        tramos_dev = engine.asignar_tramos(
            desarrollo["score"].to_numpy(), cortes, mayor_es_menor_riesgo=mayor_es_menor_riesgo
        )
        objetivo_dev = desarrollo["target"].to_numpy(dtype="float64")
        n = [int(np.sum(tramos_dev == g)) for g in range(1, k + 1)]
        d = [int(np.sum(objetivo_dev[tramos_dev == g])) for g in range(1, k + 1)]
        vacios = [g for g, n_g in enumerate(n, 1) if n_g == 0]
        if vacios:
            limites = _limites(cortes, mayor_es_menor_riesgo=mayor_es_menor_riesgo)
            g = vacios[0]
            raise MasterScaleFitError(
                f"Los cortes dejan el tramo {g} sin operaciones de Desarrollo "
                f"({_rango_en_texto(*limites[g - 1])}); el puntaje de Desarrollo va de "
                f"{_corto(float(desarrollo['score'].min()))} a "
                f"{_corto(float(desarrollo['score'].max()))}."
            )

        # ── la PD de cada tramo (D-ESC-2) ────────────────────────────────────────────────
        pd_tramos = engine.pd_por_tramo(n, d, ancla=ancla)
        no_distintos = engine.vecinos_que_no_se_distinguen(n, d)

        # ── las muestras (D-ESC-3) ───────────────────────────────────────────────────────
        muestras: dict[str, DataFrame] = {}
        for muestra in _MUESTRAS_DEL_AJUSTE:
            sub = base.loc[(base["partition"] == muestra) & base["score"].notna()].copy()
            if sub.empty:
                continue
            sub["grade"] = engine.asignar_tramos(
                sub["score"].to_numpy(), cortes, mayor_es_menor_riesgo=mayor_es_menor_riesgo
            )
            muestras[muestra] = sub
        fuera = _fuera_del_ajuste(study, pd, columna)
        if fuera is not None and not fuera.empty:
            fuera = fuera.copy()
            fuera["grade"] = engine.asignar_tramos(
                fuera["score"].to_numpy(), cortes, mayor_es_menor_riesgo=mayor_es_menor_riesgo
            )
            muestras[_FUERA_DEL_AJUSTE] = fuera
        tabla_tramos = engine.tabla_por_tramo(muestras, pd_tramos.pd)
        diagnosticos = engine.diagnostico_por_muestra(tabla_tramos)
        tabla_cortes = engine.tabla_de_cortes(
            muestras,
            cortes,
            pd_tramos.pd,
            mayor_es_menor_riesgo=mayor_es_menor_riesgo,
            corte_declarado=cfg.approval_cutoff,
        )

        # ── la calculadora, la asignación y la ficha ─────────────────────────────────────
        enteros = _tarjeta_solo_enteros(tarjeta, getattr(study.config, "scorecard", None))
        tramos = _tabla_de_tramos(
            pd,
            cortes,
            pd_tramos.pd,
            n,
            d,
            enteros=enteros,
            fuente=fuente,
            mayor_es_menor_riesgo=mayor_es_menor_riesgo,
        )
        asignacion = pd.DataFrame(index=puntaje.index.copy())
        asignacion["partition"] = base["partition"]
        asignacion["score"] = base["score"]
        todos = engine.asignar_tramos(
            base["score"].to_numpy(), cortes, mayor_es_menor_riesgo=mayor_es_menor_riesgo
        )
        asignacion["grade"] = pd.array(np.where(todos > 0, todos, None), dtype="Int64")
        asignacion["grade_pd"] = pd.array(
            [float(pd_tramos.pd[g - 1]) if g > 0 else None for g in todos], dtype="Float64"
        )
        fuera_de_rango = bool(
            cfg.approval_cutoff is not None
            and (
                float(cfg.approval_cutoff) <= float(desarrollo["score"].min())
                or float(cfg.approval_cutoff) > float(desarrollo["score"].max())
            )
        )
        ficha_escala = MasterScaleCardSection(
            n_grades=k,
            source=fuente,  # type: ignore[arg-type]  # «formed» o «institution»
            cuts=cortes,
            score_direction=direccion,  # type: ignore[arg-type]  # validada por scorecard
            integer_card=enteros,
            solver_status=None if formacion is None else formacion.status,
            formation_cause=None if formacion is None else formacion.cause,
            pd=pd_tramos.pd,
            anchor=pd_tramos.anchor,
            anchor_source=fuente_ancla,
            delta=pd_tramos.delta,
            equalized_grades=pd_tramos.equalized,
            neighbours_not_distinct=no_distintos,
            approval_cutoff=cfg.approval_cutoff,
            cutoff_out_of_range=fuera_de_rango,
            samples=tuple(muestras),
            diagnostics={
                muestra: SampleDiagnostics(
                    monotonic=diag.monotonic,
                    inversions=diag.inversions,
                    hhi=diag.hhi,
                    max_share=diag.max_share,
                    max_share_grade=diag.max_share_grade,
                    red_grades=diag.red_grades,
                    amber_grades=diag.amber_grades,
                    not_evaluable_grades=diag.not_evaluable_grades,
                )
                for muestra, diag in diagnosticos.items()
            },
        )
        resultado = MasterScaleResult(
            grades=tramos,
            grade_table=tabla_tramos,
            cutoff_table=tabla_cortes,
            assignment=asignacion,
            card=ficha_escala,
        )
        self._registrar(ficha_escala, tabla_cortes)
        self._publicar(study, resultado)
        return resultado

    # ── trail ───────────────────────────────────────────────────────────────────────────

    def _registrar(self, ficha: Any, tabla_cortes: DataFrame) -> None:
        """Las decisiones de la etapa al trail (§7 paso 7 y §9)."""
        if ficha.source == "formed":
            self.log_decision(
                regla="master_scale_grades",
                umbral=dict(_REGLA_DE_FORMACION),
                valor={
                    "cortes": list(ficha.cuts),
                    "origen": ficha.source,
                    "tramos": ficha.n_grades,
                    "estado_del_solver": ficha.solver_status,
                    "causa": ficha.formation_cause,
                },
                accion="formar_tramos",
            )
        else:
            self.log_decision(
                regla="master_scale_grades",
                umbral="institution",
                valor={
                    "cortes": list(ficha.cuts),
                    "origen": ficha.source,
                    "tramos": ficha.n_grades,
                },
                accion="usar_cortes_de_la_institucion",
            )
        self.log_decision(
            regla="master_scale_pd",
            umbral=ficha.anchor_source or None,
            valor={
                "pd": list(ficha.pd),
                "delta": ficha.delta,
                "ancla": ficha.anchor,
                "igualados": [list(b) for b in ficha.equalized_grades],
            },
            accion="asignar_pd_por_tramo",
        )
        if ficha.approval_cutoff is not None:
            declaradas = tabla_cortes.loc[tabla_cortes["declared"]]
            self.log_decision(
                regla="master_scale_cutoff",
                umbral=ficha.approval_cutoff,
                valor={
                    "aprobados": {
                        str(fila.sample): fila.approved_share for fila in declaradas.itertuples()
                    },
                    "fuera_de_rango": ficha.cutoff_out_of_range,
                },
                accion="declarar_corte",
            )
        for muestra, diag in ficha.diagnostics.items():
            if muestra == _DESARROLLO:
                continue
            for tramo in diag.red_grades:
                self.log_decision(
                    regla="master_scale_tramo_rojo",
                    umbral=muestra,
                    valor={"tramo": tramo},
                    accion="alertar",
                )
            for a, b in diag.inversions:
                self.log_decision(
                    regla="master_scale_inversion",
                    umbral=muestra,
                    valor={"tramos": [a, b]},
                    accion="alertar",
                )

    def _publicar(self, study: Study, resultado: MasterScaleResult) -> None:
        """Publica los seis artefactos de §6.2."""
        study.artifacts.set("master_scale", "grades", resultado.grades.copy(deep=True))
        study.artifacts.set("master_scale", "grade_table", resultado.grade_table.copy(deep=True))
        study.artifacts.set("master_scale", "cutoff_table", resultado.cutoff_table.copy(deep=True))
        study.artifacts.set("master_scale", "assignment", resultado.assignment.copy(deep=True))
        study.artifacts.set("master_scale", "result", resultado)
        study.artifacts.set("master_scale", "card", resultado.card.model_copy(deep=True))


def _importar(nombre: str) -> Any:
    try:
        return importlib.import_module(nombre)
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_SCORING_EXTRA_MESSAGE) from exc


def _config_desde_study(study: Study, *, respaldo: MasterScaleConfig) -> MasterScaleConfig:
    crudo = getattr(study.config, "master_scale", None)
    if crudo is None:
        return respaldo
    if isinstance(crudo, MasterScaleConfig):
        return crudo
    return MasterScaleConfig.model_validate(crudo)


def _como_frame(valor: object, pd: Any, artefacto: str) -> DataFrame:
    if isinstance(valor, pd.DataFrame):
        return cast("DataFrame", valor)
    raise MasterScaleFitError(
        f"El artefacto '{artefacto}' debe ser una tabla; llegó {type(valor).__name__}."
    )


def _exigir_columnas(frame: DataFrame, columnas: Sequence[str], artefacto: str) -> None:
    faltan = [c for c in columnas if c not in frame.columns]
    if faltan:
        raise MasterScaleFitError(
            f"El artefacto '{artefacto}' no trae las columnas {', '.join(faltan)}."
        )


def _numero(valor: object, nombre: str) -> float:
    try:
        numero = float(cast(Any, valor))
    except (TypeError, ValueError) as exc:
        raise MasterScaleFitError(f"{nombre} no es un número: {valor!r}.") from exc
    if not math.isfinite(numero):
        raise MasterScaleFitError(f"{nombre} no es finito: {numero!r}.")
    return numero


def _fuera_del_ajuste(study: Study, pd: Any, columna: str) -> DataFrame | None:
    """Las operaciones fuera del ajuste con puntaje (D-TTD), o ``None`` si no hay."""
    if not study.artifacts.has("scorecard", "out_of_model_score"):
        return None
    fuera = study.artifacts.get("scorecard", "out_of_model_score")
    if not isinstance(fuera, pd.DataFrame) or fuera.empty or columna not in fuera.columns:
        return None
    objetivo = (
        pd.to_numeric(fuera["target"], errors="coerce").astype("float64")
        if "target" in fuera.columns
        else pd.Series(float("nan"), index=fuera.index)
    )
    salida = pd.DataFrame(
        {
            "partition": _FUERA_DEL_AJUSTE,
            "target": objetivo,
            "score": pd.to_numeric(fuera[columna], errors="coerce").astype("float64"),
        },
        index=fuera.index,
    )
    return cast("DataFrame", salida.loc[salida["score"].notna()])


def _es_entero(valor: object) -> bool:
    try:
        numero = float(cast(Any, valor))
    except (TypeError, ValueError):
        return False
    return math.isfinite(numero) and numero == math.floor(numero)


def _hoja(seccion: object, nombre: str) -> Any:
    if isinstance(seccion, Mapping):
        return seccion.get(nombre)
    return getattr(seccion, nombre, None)


def _tarjeta_solo_enteros(tarjeta: DataFrame, scorecard: object) -> bool:
    """Si todo puntaje posible de la tarjeta es entero (§3.2): de la tarjeta, no de los datos.

    Todos sus puntos por atributo —también los de tramos que ninguna muestra trae—, sus ajustes
    manuales y, si recorta, sus límites. Un puntaje es la suma de los puntos de sus atributos (más
    el recorte, si está encendido).
    """
    if "points" not in tarjeta.columns or not all(_es_entero(p) for p in tarjeta["points"]):
        return False
    for ajuste in _hoja(scorecard, "point_overrides") or ():
        if not _es_entero(_hoja(ajuste, "points")):
            return False
    if bool(_hoja(scorecard, "clip")):
        for limite in (_hoja(scorecard, "min_score"), _hoja(scorecard, "max_score")):
            if limite is not None and not _es_entero(limite):
                return False
    return True


def _limites(
    cortes: Sequence[float], *, mayor_es_menor_riesgo: bool
) -> list[tuple[float | None, float | None]]:
    """``[inferior, superior)`` de cada tramo (1 = menor riesgo); ``None`` es un extremo abierto."""
    ordenados = sorted(float(c) for c in cortes)
    bordes: list[float | None] = [None, *ordenados, None]
    intervalos = list(pairwise(bordes))  # de menor a mayor puntaje
    return list(reversed(intervalos)) if mayor_es_menor_riesgo else intervalos


def _corto(valor: float) -> str:
    from bayesrisk.core.tramos import formatear_borde

    return formatear_borde(valor)


def _rango_en_texto(inferior: float | None, superior: float | None) -> str:
    from bayesrisk.core.tramos import rotulo_de_tramo_de_puntaje

    return rotulo_de_tramo_de_puntaje(inferior, superior, enteros=False)


def _tabla_de_tramos(
    pd: Any,
    cortes: Sequence[float],
    pd_tramo: Sequence[float],
    n: Sequence[int],
    d: Sequence[int],
    *,
    enteros: bool,
    fuente: str,
    mayor_es_menor_riesgo: bool,
) -> DataFrame:
    """La «calculadora»: límites en puntos y PD de cada tramo (§6.2 ``grades``)."""
    from bayesrisk.core.tramos import rotulo_de_tramo_de_puntaje

    total = sum(n)
    filas = []
    for g, (inferior, superior) in enumerate(
        _limites(cortes, mayor_es_menor_riesgo=mayor_es_menor_riesgo), 1
    ):
        filas.append(
            {
                "grade": g,
                "score_min": inferior,
                "score_max": superior,
                "label": rotulo_de_tramo_de_puntaje(inferior, superior, enteros=enteros),
                "pd": float(pd_tramo[g - 1]),
                "n_development": int(n[g - 1]),
                "share_development": n[g - 1] / total,
                "n_bad_development": int(d[g - 1]),
                "bad_rate_development": d[g - 1] / n[g - 1],
                "source": fuente,
            }
        )
    return cast("DataFrame", pd.DataFrame(filas))
