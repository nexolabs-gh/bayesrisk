"""Paso orquestable de la capa ``monitoring`` (SDD-33 §2, §6, §7; CT-1).

``MonitoringStep`` corre en una corrida propia (D-MNT-1): requiere sólo la cartera que publicó
``data`` —sin target ni partición— y la tarjeta guardada de ``monitoring.bundle``. Aplica la
tarjeta **por periodo**, con sus guardas intactas, y mide en cada periodo, contra la referencia de
Desarrollo que la tarjeta congeló (esquema 4, D-MNT-2), los cuatro indicadores de §3 y el
veredicto de §3.5. No corre ninguna etapa del scorecard, no reajusta nada y no escribe en la
tarjeta ni en ninguna corrida anterior (IHN-004, IHN-011).

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import datetime as dt
import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TypeAlias, cast

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.core.mixins import AuditableMixin
from bayesrisk.core.registry import register
from bayesrisk.core.steps import ArtifactKey
from bayesrisk.monitoring.config import MonitoringConfig
from bayesrisk.monitoring.exceptions import MonitoringInputError

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    from bayesrisk.core.audit import AuditEvent
    from bayesrisk.core.study import Study
    from bayesrisk.monitoring.engine import Semaforo
    from bayesrisk.monitoring.results import MonitoringResult, PeriodKind
    from bayesrisk.scorecard.bundle import FittedScorecardBundle

    DataFrame: TypeAlias = pd.DataFrame
else:
    AuditEvent: TypeAlias = Any
    DataFrame: TypeAlias = Any
    MonitoringResult: TypeAlias = Any
    FittedScorecardBundle: TypeAlias = Any
    PeriodKind: TypeAlias = Any
    Semaforo: TypeAlias = Any

__all__ = [
    "INDICE_DEL_PANEL",
    "MONITORING_ARTIFACTS",
    "MonitoringStep",
    "cargar_tarjeta_monitoreable",
    "exigir_tarjeta_monitoreable",
]

MONITORING_ARTIFACTS: Final[tuple[str, ...]] = (
    "periods",
    "grades_by_period",
    "variables_by_period",
    "verdict",
    "result",
    "card",
)
_SCORING_EXTRA_MESSAGE: Final = (
    "MonitoringStep requiere pandas/numpy/scipy; instale bayesrisk[scoring]."
)
#: §8: cómo se obtiene una tarjeta que sí se puede monitorear.
_COMO_OBTENERLA: Final = (
    "Vuelve a correr el desarrollo con esta versión de bayesrisk —mismo config, mismo "
    "config_hash, mismo modelo— y guarda la tarjeta de nuevo: desde la 2.13.0 la tarjeta congela "
    "la referencia de Desarrollo que el monitoreo compara."
)

PERIODS_COLUMNS: Final[tuple[str, ...]] = (
    "period",
    "n_rows",
    "n_scored",
    "n_not_scored",
    "n_with_outcome",
    "n_bad",
    "psi_score",
    "psi_score_light",
    "psi_grades",
    "psi_grades_light",
    "population_light",
    "mean_pd_scored",
    "bad_rate",
    "expected_pd",
    "p_value_under",
    "light_under",
    "p_value_over",
    "light_over",
    "portfolio_light",
    "portfolio_direction",
    "auc",
    "auc_std",
    "auc_initial",
    "auc_statistic",
    "auc_p_value",
    "auc_light",
    "slope",
    "slope_std_error",
    "slope_p_value",
    "slope_light",
    "red_grades",
    "not_evaluable",
    "partial_evidence",
    "verdict",
    "verdict_rule",
)
VARIABLES_COLUMNS: Final[tuple[str, ...]] = ("period", "feature", "csi", "csi_light")
#: La columna con que la puerta guiada conserva el índice de un panel que se repite entre periodos,
#: con su dtype (pasadas 4 a 6 de Codex). Su presencia dice que el índice que queda es de posición:
#: el paso vuelve a poner el original como índice de cada periodo cuando la tarjeta identifica por
#: él, y uno de posición del tipo que la tarjeta congeló cuando identifica por columnas. El nombre
#: está reservado: la puerta rechaza una cartera que ya traiga una columna así (pasada 5).
INDICE_DEL_PANEL: Final = "__bayesrisk_indice__"


@register("standard", domain="monitoring")
class MonitoringStep(AuditableMixin):
    """Monitorea una tarjeta en uso: población, calibración y discriminación por periodo."""

    name: str = "monitoring"
    requires: tuple[ArtifactKey, ...] = (("data", "frame"),)
    provides: tuple[ArtifactKey, ...] = tuple(("monitoring", key) for key in MONITORING_ARTIFACTS)

    def __init__(self, config: MonitoringConfig) -> None:
        """Construye el paso desde la sección ``MonitoringConfig`` ya validada."""
        self.config = config

    @classmethod
    def from_config(cls, cfg: MonitoringConfig) -> MonitoringStep:
        """Construye ``MonitoringStep`` desde ``BayesRiskConfig.monitoring``."""
        return cls(cfg)

    def emit(self, event: AuditEvent) -> None:
        """Permite pasar el paso como ``AuditSink``."""
        self._audit.emit(event)

    def execute(self, study: Study, rng: np.random.Generator) -> MonitoringResult:
        """Aplica la tarjeta por periodo, mide los cuatro indicadores y publica el veredicto."""
        del rng
        pd = _importar("pandas")
        np = _importar("numpy")
        from bayesrisk.master_scale.engine import tabla_por_tramo
        from bayesrisk.monitoring import engine
        from bayesrisk.monitoring.results import (
            MonitoringAlert,
            MonitoringCardSection,
            MonitoringResult,
            MonitoringVerdict,
        )
        from bayesrisk.monitoring.textos import INDICADORES, accion, razon

        cfg = _config_desde_study(study, respaldo=self.config)
        frame = study.artifacts.get("data", "frame")
        if not isinstance(frame, pd.DataFrame):
            raise MonitoringInputError("El artefacto ('data', 'frame') debe ser una tabla.")
        tarjeta = cargar_tarjeta_monitoreable(cfg.bundle)
        manifest = tarjeta.manifest
        escala = manifest["master_scale"]
        referencia = manifest["monitoring_reference"]
        pd_tramo = [float(p) for p in escala["grade_pd"]]
        k = len(pd_tramo)
        faltan = [c for c in (cfg.period, cfg.default) if c is not None and c not in frame.columns]
        if faltan:
            raise MonitoringInputError(
                f"La cartera no trae {', '.join(faltan)}. Columnas disponibles: "
                f"{', '.join(str(c) for c in frame.columns)}."
            )
        etiquetas, tipo, orden = _periodos(frame[cfg.period], pd)
        desenlace = _desenlace(frame[cfg.default], cfg.default, pd) if cfg.default else None
        sin_periodo = int(etiquetas.isna().sum())
        if not orden:
            raise MonitoringInputError(
                f"La columna de periodo {cfg.period!r} no trae ningún valor: no hay periodos que "
                "monitorear."
            )

        ref_puntaje = [int(c) for c in referencia["score_counts"]]
        cortes = [float(c) for c in referencia["score_edges"]]
        ref_tramos = [int(c) for c in referencia["grade_counts"]]
        n_dev = int(referencia["n_development"])
        auc_ref = referencia["auc_initial"]
        # §3.4: la prueba usa la varianza del PERIODO; la de Holdout no entra. Un AUC inicial con
        # varianza nula (todo Holdout en un tramo, o separado) sigue siendo el AUC inicial; sólo
        # falta si no se pudo calcular (pocos malos o buenos). Pasada 1 de Codex.
        auc_inicial = None if auc_ref["auc"] is None else float(auc_ref["auc"])
        reglas = tarjeta._rules
        soporte = {
            str(f): {str(b): int(s) for b, s in zip(g["bin_id"], g["support"], strict=True)}
            for f, g in reglas.groupby("feature", sort=False)
        }

        filas: list[dict[str, Any]] = []
        tablas: list[DataFrame] = []
        variables: list[dict[str, Any]] = []
        alertas: list[MonitoringAlert] = []
        no_puntuables: dict[str, int] = {}
        veredictos: list[tuple[str, Any, bool, list[str]]] = []
        rojos_previos: frozenset[int] = frozenset()
        for etiqueta in orden:
            mascara = (etiquetas == etiqueta).to_numpy()
            sub = frame.loc[mascara]
            aplicado, traza = _aplicar(tarjeta, sub, etiqueta, pd)
            puntuada = (aplicado["scoring_status"] == "scored").to_numpy()
            for motivo, n in (
                aplicado.loc[~puntuada, "not_scorable_reason"].astype(str).value_counts().items()
            ):
                no_puntuables[str(motivo)] = no_puntuables.get(str(motivo), 0) + int(n)
            puntajes = aplicado["score"].to_numpy(dtype="float64", na_value=np.nan)[puntuada]
            tramos = aplicado["grade"].to_numpy(dtype="float64", na_value=np.nan)[puntuada]
            tramos = tramos.astype("int64")
            pd_filas = aplicado["grade_pd"].to_numpy(dtype="float64", na_value=np.nan)[puntuada]
            y = (
                desenlace.to_numpy(dtype="float64")[mascara][puntuada]
                if desenlace is not None
                else np.full(int(puntuada.sum()), np.nan)
            )
            con_desenlace = np.isfinite(y)

            # ── población (§3.2) ──
            psi_puntaje = engine.psi(ref_puntaje, engine.conteos_por_corte(puntajes, cortes))
            conteo_tramos = [int(np.sum(tramos == g)) for g in range(1, k + 1)]
            psi_tramos = engine.psi(ref_tramos, conteo_tramos)
            luz_psi_p = engine.semaforo_psi(psi_puntaje)
            luz_psi_t = engine.semaforo_psi(psi_tramos)
            poblacion = engine.peor(luz_psi_p, luz_psi_t)
            no_evaluable: list[str] = []
            if luz_psi_p == "not_evaluable":
                no_evaluable.append("psi_score:no_scored_rows")

            # ── calibración por tramo, con las dos colas (§3.3, D-MNT-10) ──
            tabla = tabla_por_tramo(
                {etiqueta: pd.DataFrame({"grade": tramos, "target": y})}, pd_tramo
            ).rename(columns={"sample": "period"})
            colas = [engine.dos_colas(_float(p)) for p in tabla["jeffreys_p_value"]]
            tabla["share_development"] = [c / n_dev for c in ref_tramos]
            tabla["jeffreys_p_value_over"] = [c[0] for c in colas]
            tabla["traffic_light_over"] = [c[2] for c in colas]
            tabla["direction"] = [c[4] for c in colas]
            tabla["traffic_light_consolidated"] = [c[3] for c in colas]
            tablas.append(tabla)
            luces_tramo = {
                int(g): cast("Semaforo", str(luz))
                for g, luz in zip(tabla["grade"], tabla["traffic_light_consolidated"], strict=True)
            }

            hay_desenlace = bool(con_desenlace.any())
            if hay_desenlace:
                yt, gt = y[con_desenlace], tramos[con_desenlace]
                cartera = engine.calibracion_de_cartera(pd_filas[con_desenlace], yt)
                malos = [int(np.sum((gt == g) & (yt == 1.0))) for g in range(1, k + 1)]
                buenos = [int(np.sum((gt == g) & (yt == 0.0))) for g in range(1, k + 1)]
                auc = engine.auc_sobre_tramos(malos, buenos)
                prueba = (
                    engine.prueba_del_bce(auc_inicial, auc)
                    if auc_inicial is not None
                    else engine.PruebaDelBce(
                        None, None, "not_evaluable", cause="initial_not_evaluable"
                    )
                )
                pendiente = engine.pendiente_de_calibracion(
                    [m + b for m, b in zip(malos, buenos, strict=True)], malos, pd_tramo
                )
                if cartera.cause:
                    no_evaluable.append(f"portfolio:{cartera.cause}")
                if prueba.cause:
                    no_evaluable.append(f"auc_test:{prueba.cause}")
                if pendiente.cause:
                    no_evaluable.append(f"slope:{pendiente.cause}")
                no_evaluable.extend(
                    f"grade_{g}:few_outcomes"
                    for g, luz in luces_tramo.items()
                    if luz == "not_evaluable"
                )
            else:
                cartera = engine.calibracion_de_cartera(np.array([]), np.array([]))
                auc = engine.AucSobreTramos(None, None, 0, 0, cause="few_bads")
                prueba = engine.PruebaDelBce(None, None, "not_evaluable", cause="few_bads")
                pendiente = engine.Pendiente(
                    None, None, None, None, None, "not_evaluable", cause="few_bads"
                )

            estado = engine.EstadoDelPeriodo(
                population=poblacion,
                with_outcome=hay_desenlace,
                portfolio=cartera.light,
                grades=luces_tramo if hay_desenlace else {},
                previous_red_grades=rojos_previos,
                auc_test=prueba.light,
                slope=pendiente.light,
            )
            veredicto = engine.veredicto_del_periodo(estado)
            rojos_previos = frozenset(veredicto.red_grades)
            veredictos.append((etiqueta, veredicto, hay_desenlace, no_evaluable))

            # ── alertas rojas (§9) ──
            for indicador, valor, luz in (
                ("psi_score", psi_puntaje, luz_psi_p),
                ("psi_grades", psi_tramos, luz_psi_t),
            ):
                if luz == "red":
                    alertas.append(
                        MonitoringAlert(period=etiqueta, indicator=indicador, value=valor)
                    )
            if cartera.light == "red":
                alertas.append(
                    MonitoringAlert(
                        period=etiqueta,
                        indicator="portfolio",
                        value=cartera.p_under if cartera.direction == "under" else cartera.p_over,
                        direction=cartera.direction,
                    )
                )
            if hay_desenlace:
                for fila in tabla.to_dict(orient="records"):
                    if fila["traffic_light_consolidated"] == "red":
                        alertas.append(
                            MonitoringAlert(
                                period=etiqueta,
                                indicator="grade",
                                grade=int(fila["grade"]),
                                value=_float(
                                    fila["jeffreys_p_value"]
                                    if fila["direction"] == "under"
                                    else fila["jeffreys_p_value_over"]
                                ),
                                direction=fila["direction"],
                            )
                        )
            if prueba.light == "red":
                alertas.append(
                    MonitoringAlert(period=etiqueta, indicator="auc_test", value=prueba.p_value)
                )
            if pendiente.light == "red":
                alertas.append(
                    MonitoringAlert(period=etiqueta, indicator="slope", value=pendiente.p_value)
                )

            # ── CSI por variable (diagnóstico, §3.2) ──
            variables.extend(_csi(traza, aplicado, puntuada, soporte, etiqueta, engine, pd))

            filas.append(
                {
                    "period": etiqueta,
                    "n_rows": int(mascara.sum()),
                    "n_scored": int(puntuada.sum()),
                    "n_not_scored": int((~puntuada).sum()),
                    "n_with_outcome": int(con_desenlace.sum()),
                    "n_bad": int(np.sum(y[con_desenlace])) if hay_desenlace else 0,
                    "psi_score": psi_puntaje,
                    "psi_score_light": luz_psi_p,
                    "psi_grades": psi_tramos,
                    "psi_grades_light": luz_psi_t,
                    "population_light": poblacion,
                    "mean_pd_scored": float(np.mean(pd_filas)) if pd_filas.size else None,
                    "bad_rate": cartera.bad_rate,
                    "expected_pd": cartera.expected_pd,
                    "p_value_under": cartera.p_under,
                    "light_under": cartera.light_under,
                    "p_value_over": cartera.p_over,
                    "light_over": cartera.light_over,
                    "portfolio_light": cartera.light,
                    "portfolio_direction": cartera.direction,
                    "auc": auc.auc,
                    "auc_std": (
                        float(np.sqrt(auc.variance))
                        if auc.variance is not None and auc.variance >= 0
                        else None
                    ),
                    "auc_initial": auc_inicial,
                    "auc_statistic": prueba.statistic,
                    "auc_p_value": prueba.p_value,
                    "auc_light": prueba.light,
                    "slope": pendiente.slope,
                    "slope_std_error": pendiente.std_error,
                    "slope_p_value": pendiente.p_value,
                    "slope_light": pendiente.light,
                    "red_grades": ", ".join(str(g) for g in veredicto.red_grades),
                    "not_evaluable": "; ".join(no_evaluable),
                    "partial_evidence": bool(no_evaluable),
                    "verdict": veredicto.verdict,
                    "verdict_rule": veredicto.rule,
                }
            )

        periodos = pd.DataFrame(filas, columns=list(PERIODS_COLUMNS))
        # Por registros y no con `pd.concat`: un periodo sin desenlace trae columnas vacías, y
        # concatenarlas emite el aviso de pandas sobre columnas «all-NA».
        tramos_por_periodo = pd.DataFrame(
            [fila for tabla in tablas for fila in tabla.to_dict(orient="records")],
            columns=list(tablas[0].columns),
        )
        variables_por_periodo = pd.DataFrame(variables, columns=list(VARIABLES_COLUMNS))

        def frase(etiqueta: str, v: Any) -> str:
            fila = periodos.loc[periodos["period"] == etiqueta].iloc[0]
            pruebas = [
                INDICADORES[n]
                for n, luz in (("auc_test", fila["auc_light"]), ("slope", fila["slope_light"]))
                if luz == "red"
            ]
            ambar = [
                INDICADORES[n]
                for n, luz in (
                    ("psi_score", fila["psi_score_light"]),
                    ("psi_grades", fila["psi_grades_light"]),
                    ("portfolio", fila["portfolio_light"]),
                    ("auc_test", fila["auc_light"]),
                    ("slope", fila["slope_light"]),
                )
                if luz == "amber"
            ]
            return razon(
                v.rule,
                tramos_rojos=v.red_grades,
                repetidos=v.repeated_red_grades,
                direccion=fila["portfolio_direction"],
                pruebas_rojas=pruebas,
                ambar=ambar,
                poblacion=fila["population_light"],
            )

        ultimo, v_ultimo, con_ultimo, ne_ultimo = veredictos[-1]
        con_desenlace_previo = [x for x in veredictos if x[2]]
        extra: dict[str, Any] = {}
        if not con_ultimo and con_desenlace_previo:
            p_previo, v_previo, _, _ = con_desenlace_previo[-1]
            extra = {
                "last_with_outcome_period": p_previo,
                "last_with_outcome_verdict": v_previo.verdict,
                "last_with_outcome_reason": frase(p_previo, v_previo),
                "last_with_outcome_not_evaluable": tuple(con_desenlace_previo[-1][3]),
            }
        veredicto_corrida = MonitoringVerdict(
            period=ultimo,
            verdict=v_ultimo.verdict,
            rule=v_ultimo.rule,
            action=accion(v_ultimo.verdict, parcial=bool(ne_ultimo)),
            reason=frase(ultimo, v_ultimo),
            partial_evidence=bool(ne_ultimo),
            not_evaluable=tuple(ne_ultimo),
            **extra,
        )
        ficha = MonitoringCardSection(
            bundle_hash=tarjeta.bundle_hash,
            bundle_schema=int(manifest["schema_version"]),
            n_grades=k,
            grade_pd=tuple(pd_tramo),
            score_edges=tuple(cortes),
            n_development=n_dev,
            auc_initial=auc_inicial,
            auc_initial_source=auc_ref["source"],
            auc_initial_cause=auc_ref["cause"],
            period_column=cfg.period,
            default_column=cfg.default,
            period_kind=tipo,
            periods=tuple(orden),
            n_rows=len(frame.index),
            n_rows_without_period=sin_periodo,
            n_not_scored=int(periodos["n_not_scored"].sum()),
            not_scored_reasons=dict(sorted(no_puntuables.items())),
            constants={
                "psi_green": engine.PSI_VERDE,
                "psi_red": engine.PSI_ROJO,
                "alpha_green": engine.ALFA_VERDE,
                "alpha_red": engine.ALFA_ROJO,
                "deciles": float(engine.DECILES),
                "smoothing": engine.SUAVIZADO,
                "min_rows_per_grade": float(engine.MIN_ROWS_EVALUABLE),
                "min_bads_auc": float(engine.MIN_MALOS_AUC),
            },
            alerts=tuple(alertas),
            verdict=veredicto_corrida,
        )
        resultado = MonitoringResult(
            periods=periodos,
            grades_by_period=tramos_por_periodo,
            variables_by_period=variables_por_periodo,
            verdict=veredicto_corrida,
            card=ficha,
        )
        self._publicar(study, resultado, bundle_hash=tarjeta.bundle_hash)
        self._registrar(ficha, auc_ref)
        return resultado

    # ── trail ───────────────────────────────────────────────────────────────────────────

    def _registrar(self, ficha: Any, auc_ref: Mapping[str, Any]) -> None:
        """La referencia usada, una decisión por alerta roja y el veredicto (§9)."""
        self.log_decision(
            regla="monitoring_reference",
            umbral=dict(ficha.constants),
            valor={
                "bundle_hash": ficha.bundle_hash,
                "auc_inicial": ficha.auc_initial,
                "fuente_auc_inicial": auc_ref["source"],
                "n_desarrollo": ficha.n_development,
                "tramos": ficha.n_grades,
            },
            accion="usar_referencia_de_la_tarjeta",
        )
        for alerta in ficha.alerts:
            self.log_decision(
                regla="monitoring_alerta",
                umbral=alerta.period,
                valor={
                    "indicador": alerta.indicator,
                    "valor": alerta.value,
                    "tramo": alerta.grade,
                    "direccion": alerta.direction,
                },
                accion="alertar",
            )
        veredicto = ficha.verdict
        self.log_decision(
            regla="monitoring_veredicto",
            umbral=veredicto.period,
            valor={
                "veredicto": veredicto.verdict,
                "regla": veredicto.rule,
                "evidencia_parcial": veredicto.partial_evidence,
                "no_evaluable": list(veredicto.not_evaluable),
            },
            accion=veredicto.verdict,
        )

    def _publicar(self, study: Study, resultado: MonitoringResult, *, bundle_hash: str) -> None:
        """Publica los seis artefactos de §6.2 y ancla al lineage la huella de su tarjeta.

        D-MNT-1 (§5.3, §9): la ruta de la tarjeta queda fuera del ``config_hash`` y su contenido lo
        identifica su huella, en el lineage. La huella se escribe si y sólo si ESTE intento dejó
        guardado algún artefacto —también si la publicación quedó a medias, porque el almacén
        guarda antes de auditar y un registro que falla deja la tabla—, y nunca si no guardó nada:
        un ``run_step`` repetido sobre una corrida terminada choca con su evidencia y no puede
        cambiarle la huella (pasadas 2 y 3 de Codex; IHN-011). Se reconcilia por identidad del
        objeto guardado: ``ArtifactStore.get`` devuelve el mismo objeto.
        """
        objetos: tuple[tuple[str, Any], ...] = (
            ("periods", resultado.periods.copy(deep=True)),
            ("grades_by_period", resultado.grades_by_period.copy(deep=True)),
            ("variables_by_period", resultado.variables_by_period.copy(deep=True)),
            ("verdict", resultado.verdict.model_copy(deep=True)),
            ("result", resultado),
            ("card", resultado.card.model_copy(deep=True)),
        )
        try:
            for clave, objeto in objetos:
                study.artifacts.set("monitoring", clave, objeto)
        finally:
            propios = any(
                study.artifacts.has("monitoring", clave)
                and study.artifacts.get("monitoring", clave) is objeto
                for clave, objeto in objetos
            )
            lineage = study.run_context.lineage
            if propios and lineage is not None:
                lineage.bundle_hash = bundle_hash


# ── la tarjeta ──────────────────────────────────────────────────────────────────────────


def cargar_tarjeta_monitoreable(ruta: str | Path) -> FittedScorecardBundle:
    """La tarjeta de ``ruta``, o el error de §8 si no se puede monitorear (D-MNT-2).

    Una tarjeta de esquema ≤ 3 (la 2.11 o la 2.12) o sin escala maestra se sigue leyendo y
    aplicando igual; el monitoreo la rechaza con el camino para obtener una que sí.
    """
    from bayesrisk.scorecard.bundle import FittedScorecardBundle
    from bayesrisk.scorecard.exceptions import ScorecardBundleError

    try:
        tarjeta = FittedScorecardBundle.load(ruta)
    except ScorecardBundleError as exc:
        raise MonitoringInputError(f"No se pudo leer la tarjeta {str(ruta)!r}: {exc}") from exc
    return exigir_tarjeta_monitoreable(tarjeta)


def exigir_tarjeta_monitoreable(tarjeta: FittedScorecardBundle) -> FittedScorecardBundle:
    """La misma tarjeta si se puede monitorear: con escala maestra y esquema 4 con su referencia."""
    manifest = tarjeta.manifest
    if "master_scale" not in manifest:
        raise MonitoringInputError(
            "La tarjeta no trae escala maestra: el monitoreo mide cada tramo contra su PD. Corre "
            "el desarrollo con la escala (la puerta guiada la corre por defecto) y guarda la "
            "tarjeta de esa corrida."
        )
    if int(manifest["schema_version"]) < 4 or "monitoring_reference" not in manifest:
        raise MonitoringInputError(
            f"La tarjeta es de esquema {manifest['schema_version']} y no congela la referencia de "
            "Desarrollo —los cortes del puntaje, la participación por tramo y el AUC inicial— "
            f"contra la que el monitoreo compara. {_COMO_OBTENERLA}"
        )
    return tarjeta


def _aplicar(
    tarjeta: FittedScorecardBundle, sub: DataFrame, etiqueta: str, pd: Any
) -> tuple[DataFrame, DataFrame]:
    """Aplica la tarjeta a un periodo con **sólo sus predictores y sus llaves** (§7 paso 3).

    Una tarjeta estricta (``extra_columns="forbid"``) rechazaría el periodo y el desenlace; y sobre
    toda la cartera, una misma operación en dos periodos (un panel) violaría sus llaves únicas. El
    resultado vuelve alineado por posición con las filas del periodo; una llave repetida dentro de
    un mismo periodo falla con el mensaje de la tarjeta.
    """
    from bayesrisk.scorecard.exceptions import ScorecardBundleError

    manifest = tarjeta.manifest
    identidad = manifest["row_identity"]
    columnas = list(dict.fromkeys([*manifest["model"]["features"], *identidad["unique_keys"]]))
    entrada = sub.loc[:, [c for c in columnas if c in sub.columns]]
    indice = identidad["index_name"]
    # El índice vuelve desde su columna con su dtype (``.array``: un categórico sigue siéndolo;
    # ``to_numpy()`` lo dejaba en texto y la tarjeta lo rechazaba, pasada 5 de Codex).
    if indice is not None and indice in sub.columns and sub.index.name != indice:
        entrada = entrada.set_axis(pd.Index(sub[indice].array, name=indice), axis=0)
    elif indice is None and INDICE_DEL_PANEL in sub.columns:
        if not identidad["unique_keys"]:
            # Sin llaves (``id=None``) el índice ES la identidad: vuelve tal cual y la tarjeta
            # comprueba su unicidad dentro del periodo (pasada 4 de Codex).
            entrada = entrada.set_axis(pd.Index(sub[INDICE_DEL_PANEL].array, name=None), axis=0)
        else:
            # Con la identidad en columnas el índice del panel es auxiliar —puede repetirse dentro
            # de un periodo, como en lotes con sus índices locales—: la tarjeta recibe uno de
            # posición del tipo que congeló y comprueba sus llaves (pasadas 5 y 6 de Codex). El
            # resultado vuelve alineado por posición: ese índice no llega a ningún artefacto.
            entrada = entrada.set_axis(
                _indice_de_posicion(len(entrada), str(identidad["index_dtype"]), etiqueta, pd),
                axis=0,
            )
    try:
        resultado = tarjeta.apply(entrada)
    except ScorecardBundleError as exc:
        raise MonitoringInputError(
            f"La tarjeta no puede puntuar el periodo {etiqueta}: {exc}"
        ) from exc
    aplicado = resultado.application_frame.copy()
    aplicado.index = sub.index
    return aplicado, resultado.trace_frame


def _indice_de_posicion(n: int, tipo: str, etiqueta: str, pd: Any) -> Any:
    """Un índice único de ``n`` posiciones con el tipo lógico ``tipo`` que congeló la tarjeta."""
    posiciones = pd.RangeIndex(n)
    if tipo == "int":
        return posiciones
    if tipo == "float":
        return pd.Index(posiciones.astype("float64"))
    if tipo == "str":
        return pd.Index(posiciones.astype(str), dtype=object)
    if tipo == "category":
        return pd.CategoricalIndex(posiciones.astype(str))
    if tipo == "datetime":
        return pd.DatetimeIndex(pd.to_datetime(posiciones, unit="s"))
    # Un índice booleano no tiene más de dos valores distintos: no hay uno único que darle.
    raise MonitoringInputError(
        f"La tarjeta no puede puntuar el periodo {etiqueta}: identifica cada operación por "
        f"columnas, pero exige un índice de tipo {tipo!r} y el de la cartera se repite; guarda "
        "la cartera con un índice único."
    )


def _csi(
    traza: DataFrame,
    aplicado: DataFrame,
    puntuada: Any,
    soporte: Mapping[str, Mapping[str, int]],
    etiqueta: str,
    engine: Any,
    pd: Any,
) -> list[dict[str, Any]]:
    """El CSI de cada variable del periodo contra el ``support`` de Desarrollo de sus bins."""
    posiciones = set(aplicado["input_position"].to_numpy()[puntuada].tolist())
    traza = traza.loc[traza["input_position"].isin(posiciones)]
    salida: list[dict[str, Any]] = []
    for variable, bins in soporte.items():
        orden = list(bins)
        actuales = traza.loc[traza["feature"] == variable, "bin_id"].astype(str).value_counts()
        valor = engine.psi([bins[b] for b in orden], [int(actuales.get(b, 0)) for b in orden])
        salida.append(
            {
                "period": etiqueta,
                "feature": variable,
                "csi": valor,
                "csi_light": engine.semaforo_psi(valor),
            }
        )
    return salida


# ── la cartera ──────────────────────────────────────────────────────────────────────────


def _periodos(serie: Any, pd: Any) -> tuple[Any, PeriodKind, list[str]]:
    """El rótulo de periodo de cada fila, cómo se leyó la columna y los periodos en orden (§7-2).

    Una fecha se agrupa por mes (``AAAA-MM``); un número se ordena como número; un texto, como
    texto (la misma lectura que ``stability``). Una fila sin periodo queda fuera y se cuenta.
    """
    if es_fecha(serie, pd):
        # Un CSV con fechas ISO llega como objetos ``datetime.date`` (pasada 2 de Codex): son
        # fechas, no textos diarios.
        serie = pd.to_datetime(serie)
        etiquetas = serie.dt.strftime("%Y-%m")
        etiquetas = etiquetas.where(serie.notna(), None)
        return etiquetas, "date_month", sorted(str(e) for e in etiquetas.dropna().unique())
    if pd.api.types.is_float_dtype(serie) and bool((serie.abs() >= 2**53).any()):
        # Un float no distingue dos enteros mayores que 2⁵³: un CSV con vacíos los lee así y dos
        # periodos distintos ya llegan iguales (pasada 3 de Codex). Se detiene, no se adivina.
        raise MonitoringInputError(
            f"La columna de periodo {serie.name!r} trae números de 2⁵³ o más leídos como "
            "decimales, que no distinguen dos periodos consecutivos (un archivo con vacíos los "
            "lee así). Guárdala como texto o como entero sin vacíos."
        )
    if pd.api.types.is_numeric_dtype(serie) and not pd.api.types.is_bool_dtype(serie):
        # Sin pasar por float: dos enteros distintos mayores que 2⁵³ darían el mismo float y sus
        # periodos se fundirían, contados dos veces (pasada 1 de Codex). Se ordena el valor exacto.
        valores = sorted(set(serie.dropna().tolist()))
        rotulo = {v: _rotulo_numerico(v) for v in valores}
        # `astype(object)`: un entero nullable con vacíos pasaría por float64 en el `map` de pandas
        # y se fundiría igual (pasada 2 de Codex).
        etiquetas = serie.astype(object).map(lambda v: None if pd.isna(v) else rotulo[v])
        return etiquetas, "number", [rotulo[v] for v in valores]
    etiquetas = serie.map(lambda v: None if pd.isna(v) else str(v))
    return etiquetas, "text", sorted(str(e) for e in etiquetas.dropna().unique())


def es_fecha(serie: Any, pd: Any) -> bool:
    """Si la columna de periodo es una fecha: ``datetime64`` u objetos fecha de Python."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return True
    if not pd.api.types.is_object_dtype(serie):
        return False
    valores = serie.dropna()
    return bool(len(valores.index)) and all(isinstance(v, dt.date) for v in valores)


def _rotulo_numerico(valor: Any) -> str:
    """El rótulo exacto de un periodo numérico: un entero (o un float entero) sin decimales."""
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else repr(valor)
    return str(int(valor))


def _desenlace(serie: Any, nombre: str, pd: Any) -> Any:
    """La columna de desenlace como 0/1 o vacío; cualquier otro valor se rechaza (§6.1)."""
    if pd.api.types.is_bool_dtype(serie):
        return serie.astype("float64")
    numeros = pd.to_numeric(serie, errors="coerce")
    invalidos = serie.notna() & ~numeros.isin([0, 1])
    if bool(invalidos.any()):
        ejemplos = ", ".join(repr(v) for v in pd.unique(serie[invalidos])[:5])
        raise MonitoringInputError(
            f"La columna de desenlace {nombre!r} trae valores que no son 0, 1 ni vacío: {ejemplos}."
        )
    return numeros.astype("float64")


def _float(valor: Any) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero == numero else None


def _importar(nombre: str) -> Any:
    try:
        return importlib.import_module(nombre)
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_SCORING_EXTRA_MESSAGE) from exc


def _config_desde_study(study: Study, *, respaldo: MonitoringConfig) -> MonitoringConfig:
    crudo = getattr(study.config, "monitoring", None)
    if crudo is None:
        return respaldo
    if isinstance(crudo, MonitoringConfig):
        return crudo
    return MonitoringConfig.model_validate(crudo)
