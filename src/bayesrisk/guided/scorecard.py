"""``bayesrisk.Scorecard``: la puerta guiada del scorecard (D-FLU-1…D-FLU-4, D-FLU-9).

Se construye con lo institucional, infiere y declara el resto, corre con :func:`bayesrisk.run` y
cuenta cada etapa. **No es un segundo orquestador**: arma un ``BayesRiskConfig`` a partir del preset
F1 y de sus argumentos, y todo lo que calcula lo calcula el motor. ``sc.config`` es la verdad;
``sc.config_hash``, la identidad; ``run()`` sobre ese config por la puerta completa reproduce los
mismos resultados (D-SIM-1).

La maquinaria que no es del scorecard —proyecto en disco, candado, informe por intento,
``run(until=)``/``resume()``, registro de decisiones y empaquetado— vive en
:mod:`bayesrisk.guided._puerta`, compartida con ``bayesrisk.Ecl``; aquí queda lo que infiere y lo
que decide el scorecard.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, ClassVar, Final, Literal

import pandas as pd

from bayesrisk.core.exceptions import BayesRiskError, ConfigError
from bayesrisk.guided._puerta import (
    _LOCK_NAME,
    _bloquear_carpeta,
    _liberar_carpeta,
    _PuertaGuiada,
)
from bayesrisk.guided.inference import (
    Inferencia,
    columnas_categoricas,
    columnas_esquema,
    columnas_predictoras,
    dtype_logico,
    sugerir_oot_cohorts,
    sugerir_oot_from,
)
from bayesrisk.guided.summaries import (
    StageSummary,
    build_final_summary,
    partition_label,
)
from bayesrisk.report.prose import _miles, _plural

__all__ = ["Scorecard", "ScorecardInputError", "ScorecardRunError"]

#: Paso con que la puerta firma sus eventos en el trail (D-FLU-3: ``step="scorecard_guided"``).
GUIDED_STEP: Final = "scorecard_guided"

_TargetRule = Mapping[str, Any]

# Los tres se reexportan para los tests del candado, que los importan desde este módulo.
_REEXPORTADOS = (_LOCK_NAME, _bloquear_carpeta, _liberar_carpeta)


@dataclass(frozen=True)
class _Target:
    """Las tres reglas del target que la puerta arma, las columnas que las definen y los vacíos.

    Con ``good_rule`` vacía el motor toma por bueno todo lo que no es malo, **incluidos los
    resultados vacíos** (operaciones sin desempeño maduro): entrarían al ajuste como no-default
    sin error alguno (pasada de cierre de Codex sobre la capa A). Un resultado vacío es
    desconocido: queda indeterminado, se puntúa y no entra al ajuste.
    """

    bad_rule: dict[str, Any]
    good_rule: dict[str, Any] | None
    indeterminate_rule: dict[str, Any]
    columnas: tuple[str, ...]
    n_vacios: int


class ScorecardInputError(ConfigError):
    """Lo que la puerta guiada rechaza **antes de correr**.

    Falta una decisión institucional o un argumento no casa con el archivo.
    """


class ScorecardRunError(BayesRiskError):
    """La corrida terminó fallida y se pidió ``raise_on_error=True`` (D-FLU-4, hallazgo #4).

    También cuando la corrida no pudo empezar porque otra tiene la carpeta del proyecto.
    """


@dataclass(frozen=True, slots=True)
class _Muestras:
    """Cómo se separa la muestra, ya resuelto, y las particiones que existirán."""

    strategy: dict[str, Any]
    partitions: tuple[str, ...]
    comparisons: tuple[str, ...]
    label: str
    time_column: str | None
    time_axis: Literal["none", "period", "cohort"]


class Scorecard(_PuertaGuiada):
    """Un scorecard de comportamiento de punta a punta, con la entrada mínima (D-FLU-1).

    Parameters
    ----------
    data
        Ruta a un CSV, Parquet o Excel, o un ``pandas.DataFrame``. Los datos se copian al
        proyecto —un archivo, tal cual; un DataFrame, como Parquet— bajo
        ``<run_dir>/<name>/input/`` con su huella en el nombre, y el config referencia esa copia:
        la inferencia y cada corrida leen exactamente los mismos bytes, y ``config.yaml`` +
        ``input/`` reproducen la corrida por sí solos.
    target
        La columna 0/1 (o verdadero/falso) que dice quién es «malo», o una regla
        ``{"col": "dias_mora", "op": ">", "value": 90}`` con los operadores del motor.
    id
        Identificador de cada operación, opcional y recomendado: una columna (llave de unicidad)
        o el nombre del índice del archivo. Sin él se usa el índice del archivo y se declara.
    date, cohort, partition
        El eje temporal: ``date=`` particiona por fecha de corte, ``cohort=`` por añada; sin eje,
        ``partition="random"`` explícito (D-OBL-5: la estrategia no se siembra). Exactamente uno.
    oot_from, oot_cohorts
        La frontera fuera de tiempo, **obligatoria** con ``date`` (fecha ISO) o con ``cohort``
        (las cohortes reservadas). Si falta, la puerta se detiene antes de correr con el rango
        del archivo y el valor que usaría.
    holdout
        Proporción reservada como Holdout dentro de la muestra de desarrollo (0,2 de fábrica).
    name, run_dir
        Nombre de la versión del proyecto y carpeta raíz: la evidencia queda en
        ``<run_dir>/<name>/`` (§8-8: ``"bayesrisk-runs"`` y ``"scorecard"`` de fábrica).
    purpose, owner, review_every
        Con ``purpose`` se enciende la gobernanza y la ficha del modelo (D-GOB-8); sin él no hay
        ficha. ``owner`` y ``review_every`` (meses) completan la ficha.
    track
        Ruta o URI de MLflow: enciende el registro de la corrida (D-FLU-9). Apagado sin él.
    features, categorical
        Las predictoras y cuáles son categóricas. Si no se dan, se infieren y se declaran.
    max_bins, min_bin_size, monotonic, min_iv, max_correlation, max_vif, stepwise, p_enter,
    p_exit, sign_policy, pdo, target_score, target_odds, anchor, target_pd, deciles,
    psi_thresholds, validation, document, formats
        Los campos esenciales de cada etapa (§3.8 de la enmienda), con los valores del preset F1
        de fábrica. Cada uno escribe una hoja existente del config; lo que no está aquí se
        alcanza por ``sc.config`` (la puerta completa).
    """

    _PUERTA: ClassVar[str] = "Scorecard"
    _GUIDED_STEP: ClassVar[str] = GUIDED_STEP
    _InputError: ClassVar[type[ConfigError]] = ScorecardInputError
    _RunError: ClassVar[type[BayesRiskError]] = ScorecardRunError
    _FAMILIA: ClassVar[str] = "scorecard"

    def __init__(
        self,
        data: str | Path | pd.DataFrame,
        target: str | _TargetRule,
        *,
        id: str | None = None,
        date: str | None = None,
        cohort: str | None = None,
        partition: str | None = None,
        oot_from: str | None = None,
        oot_cohorts: Sequence[str] | None = None,
        holdout: float = 0.2,
        name: str = "scorecard",
        run_dir: str | Path = "bayesrisk-runs",
        purpose: str | None = None,
        owner: str | None = None,
        review_every: int = 12,
        track: str | Path | None = None,
        features: Sequence[str] | None = None,
        categorical: Sequence[str] | None = None,
        max_bins: int = 6,
        min_bin_size: float = 0.05,
        monotonic: str | None = "auto_asc_desc",
        min_iv: float = 0.02,
        max_correlation: float = 0.75,
        max_vif: float = 5.0,
        stepwise: bool = True,
        p_enter: float = 0.05,
        p_exit: float = 0.05,
        sign_policy: str = "flag",
        pdo: float = 20.0,
        target_score: float = 600.0,
        target_odds: float = 50.0,
        anchor: str = "development_observed",
        target_pd: float | None = None,
        deciles: int = 10,
        psi_thresholds: tuple[float, float] = (0.10, 0.25),
        validation: Sequence[str] | None = ("discrimination", "calibration", "stability"),
        document: Mapping[str, str] | None = None,
        formats: Sequence[str] | None = None,
    ) -> None:
        self._iniciar(name, run_dir)
        try:
            frame, source, source_label = self._cargar(data)
            self._construir(
                frame,
                source,
                source_label,
                target=target,
                id=id,
                date=date,
                cohort=cohort,
                partition=partition,
                oot_from=oot_from,
                oot_cohorts=oot_cohorts,
                holdout=holdout,
                purpose=purpose,
                owner=owner,
                review_every=review_every,
                track=track,
                features=features,
                categorical=categorical,
                max_bins=max_bins,
                min_bin_size=min_bin_size,
                monotonic=monotonic,
                min_iv=min_iv,
                max_correlation=max_correlation,
                max_vif=max_vif,
                stepwise=stepwise,
                p_enter=p_enter,
                p_exit=p_exit,
                sign_policy=sign_policy,
                pdo=pdo,
                target_score=target_score,
                target_odds=target_odds,
                anchor=anchor,
                target_pd=target_pd,
                deciles=deciles,
                psi_thresholds=psi_thresholds,
                validation=validation,
                document=document,
                formats=formats,
            )
        except BaseException:
            self._descartar_snapshot()
            raise

    def _construir(
        self,
        frame: pd.DataFrame,
        source: str,
        source_label: str,
        *,
        target: str | _TargetRule,
        id: str | None,
        date: str | None,
        cohort: str | None,
        partition: str | None,
        oot_from: str | None,
        oot_cohorts: Sequence[str] | None,
        holdout: float,
        purpose: str | None,
        owner: str | None,
        review_every: int,
        track: str | Path | None,
        features: Sequence[str] | None,
        categorical: Sequence[str] | None,
        max_bins: int,
        min_bin_size: float,
        monotonic: str | None,
        min_iv: float,
        max_correlation: float,
        max_vif: float,
        stepwise: bool,
        p_enter: float,
        p_exit: float,
        sign_policy: str,
        pdo: float,
        target_score: float,
        target_odds: float,
        anchor: str,
        target_pd: float | None,
        deciles: int,
        psi_thresholds: tuple[float, float],
        validation: Sequence[str] | None,
        document: Mapping[str, str] | None,
        formats: Sequence[str] | None,
    ) -> None:
        """Infiere, arma el config y lo comprueba; el snapshot se publica al final."""
        inferencias: list[Inferencia] = []

        # ── identificador ────────────────────────────────────────────────────────────────
        index_col, unique_keys, id_label = self._resolver_id(frame, id)
        if id is None:
            inferencias.append(
                Inferencia(
                    regla="inferencia_identificador",
                    valor="índice del archivo",
                    motivo="no se declaró id=: cada fila se identifica por su posición",
                )
            )

        # ── target ───────────────────────────────────────────────────────────────────────
        objetivo = self._regla_del_target(frame, target)
        columnas_target = objetivo.columnas
        target_col = "target" if "target" not in frame.columns else "target_bayesrisk"
        if objetivo.n_vacios:
            inferencias.append(
                Inferencia(
                    regla="inferencia_resultado_vacio",
                    valor={"columnas": list(columnas_target), "filas": objetivo.n_vacios},
                    motivo=(
                        "un resultado vacío es desconocido, no bueno: la fila queda "
                        "indeterminada, se puntúa y no entra al ajuste"
                    ),
                )
            )

        # ── muestras ─────────────────────────────────────────────────────────────────────
        muestras = self._resolver_muestras(
            frame,
            date=date,
            cohort=cohort,
            partition=partition,
            oot_from=oot_from,
            oot_cohorts=oot_cohorts,
            holdout=holdout,
        )

        # ── esquema, predictoras y categóricas ───────────────────────────────────────────
        fechas = (date,) if date is not None else ()
        textos = (cohort,) if cohort is not None and dtype_logico(frame[cohort]) != "str" else ()
        esquema = columnas_esquema(frame, fechas=fechas, textos=textos)
        n_texto = sum(1 for c in esquema if c["dtype"] in {"str", "category", "bool"})
        inferencias.append(
            Inferencia(
                regla="inferencia_esquema",
                valor={c["name"]: c["dtype"] for c in esquema},
                motivo="tipos leídos de los datos; nullable sólo donde hay vacíos",
            )
        )
        excluidas: dict[str, str] = {}
        if id is not None and unique_keys is not None:
            excluidas[id] = "identificador"
        for columna in columnas_target:
            excluidas[columna] = "define el incumplimiento, sería una fuga de información"
        if date is not None:
            excluidas[date] = "eje temporal de la partición"
        if cohort is not None:
            excluidas[cohort] = "cohorte de la partición"
        if features is None:
            predictoras, motivos = columnas_predictoras(frame, excluidas=excluidas)
            if not predictoras:
                raise ScorecardInputError(
                    "No queda ninguna columna predictora después de apartar el identificador, "
                    "el target y el eje temporal. Pasa features= con las columnas a modelar."
                )
            inferencias.append(
                Inferencia(
                    regla="inferencia_predictoras",
                    valor={"incluidas": list(predictoras), "excluidas": motivos},
                    motivo=(
                        "todas las columnas menos el identificador, las que definen el "
                        "incumplimiento, el eje temporal y las fechas"
                    ),
                )
            )
        else:
            predictoras = tuple(str(c) for c in features)
            faltan = [c for c in predictoras if c not in frame.columns]
            if faltan:
                raise ScorecardInputError(
                    f"features= nombra columnas que el archivo no trae: {', '.join(faltan)}."
                )
            fugas = [c for c in predictoras if c in columnas_target]
            if fugas:
                raise ScorecardInputError(
                    "features= incluye columnas que definen el incumplimiento: "
                    f"{', '.join(fugas)}. "
                    "Entrarían como predictoras de sí mismas (fuga de información)."
                )
            motivos = {}
        if categorical is None:
            categoricas = columnas_categoricas(frame, predictoras)
            inferencias.append(
                Inferencia(
                    regla="inferencia_categoricas",
                    valor=list(categoricas),
                    motivo="predictoras de texto, categoría o verdadero/falso",
                )
            )
        else:
            categoricas = tuple(str(c) for c in categorical)
            fuera = [c for c in categoricas if c not in predictoras]
            if fuera:
                raise ScorecardInputError(
                    f"categorical= nombra columnas que no son predictoras: {', '.join(fuera)}."
                )
        inferencias.append(
            Inferencia(
                regla="inferencia_muestras",
                valor={
                    "muestras": list(muestras.partitions),
                    "comparaciones": list(muestras.comparisons),
                    "eje_temporal": muestras.time_axis,
                },
                motivo="las listas de desempeño, validación y estabilidad se ajustan a las "
                "muestras que la partición declarada produce",
            )
        )
        self._inferences: tuple[Inferencia, ...] = tuple(inferencias)
        self._partition_label = muestras.label
        self._source_label = source_label
        self._inference_lines = self._lineas_de_inferencia(
            esquema=esquema,
            n_texto=n_texto,
            predictoras=predictoras,
            categoricas=categoricas,
            motivos=motivos,
            id_label=id_label,
            n_vacios_target=objetivo.n_vacios,
            columnas_target=columnas_target,
        )

        # ── el config ────────────────────────────────────────────────────────────────────
        cfg = _config_base()
        cfg["name"] = self._name
        cfg["data"] = {
            "type": "standard",
            "load": {
                "source": source,
                "file_format": "auto",
                "backend": "pandas",
                "csv_options": {"sep": ",", "decimal": ".", "encoding": "utf-8"},
            },
            "schema": {
                "columns": esquema,
                "strict": False,
                "ordered": False,
                "index_col": index_col,
                "unique_keys": unique_keys,
            },
            "missing": {"special_values": [], "max_missing_rate": 0.99},
            "target": {
                "target_col": target_col,
                "bad_rule": objetivo.bad_rule,
                "good_rule": objetivo.good_rule,
                "indeterminate_rule": objetivo.indeterminate_rule,
                "exclusion_rules": [],
                "window": None,
            },
            "partition": {
                "strategy": muestras.strategy,
                "ttd_includes_excluded": True,
                "min_bads_per_partition": 30,
            },
        }
        eda = cfg["eda"]
        if muestras.time_axis == "period":
            eda["default_rate"] = {"axis": "period", "date_col": muestras.time_column}
        elif muestras.time_axis == "cohort":
            eda["default_rate"] = {"axis": "cohort", "cohort_col": muestras.time_column}
        else:
            # Sin eje temporal la tasa se agrupa por la cohorte de la partición si existe; con
            # partición aleatoria no hay ninguna y el motor lo declara «no evaluable» (SDD-31 §8).
            eda["default_rate"] = {"axis": "period"}
        eda["univariate"] = {"columns": list(predictoras)}
        binning = cfg["binning"]
        binning["feature_columns"] = list(predictoras)
        binning["categorical_columns"] = list(categoricas)
        binning["max_n_bins"] = max_bins
        binning["min_bin_size"] = min_bin_size
        binning["monotonic_trend"] = monotonic
        selection = cfg["selection"]
        selection["min_iv"] = min_iv
        selection["correlation"]["threshold"] = max_correlation
        selection["vif"]["threshold"] = max_vif
        model = cfg["model"]
        model["stepwise"]["enabled"] = stepwise
        model["stepwise"]["entry_p_value"] = p_enter
        model["stepwise"]["exit_p_value"] = p_exit
        model["sign_policy"]["action"] = sign_policy
        scorecard = cfg["scorecard"]
        scorecard["pdo"] = pdo
        scorecard["target_score"] = target_score
        scorecard["target_odds"] = target_odds
        calibration = cfg["calibration"]
        calibration["anchor_source"] = anchor
        calibration["target_pd"] = target_pd
        performance = cfg["performance"]
        performance["n_deciles"] = deciles
        performance["partitions"] = list(muestras.partitions)
        stability = cfg["stability"]
        stability["psi_stable_threshold"], stability["psi_review_threshold"] = psi_thresholds
        stability["comparisons"] = list(muestras.comparisons)
        stability["temporal_axis"] = muestras.time_axis
        stability["temporal_column"] = muestras.time_column
        if validation is None:
            cfg["validation"] = None
        else:
            cfg["validation"]["families"] = list(validation)
            cfg["validation"]["discrimination"]["partitions"] = list(muestras.partitions)
            cfg["validation"]["stability"]["psi_stable_threshold"] = psi_thresholds[0]
            cfg["validation"]["stability"]["psi_review_threshold"] = psi_thresholds[1]
        report = cfg["report"]
        report["output_dir"] = str(self._reports_dir)
        if document:
            report["document"] = {**report.get("document", {}), **dict(document)}
        if formats is not None:
            report["formats"] = list(formats)
        if purpose is not None:
            if not str(purpose).strip():
                raise ScorecardInputError(
                    "purpose= está en blanco: la ficha del modelo exige un propósito escrito "
                    "por la institución. Omite el argumento si no quieres ficha."
                )
            cfg["governance"] = {
                "model_name": self._name,
                "purpose": str(purpose),
                "author": owner,
                "review_period_months": review_every,
            }
        if track is not None:
            cfg["tracking"] = {"enabled": True, "tracking_uri": str(track)}
        self._config = self._validar_config(cfg)
        self._config, self._steps = self._resolver_pipeline(self._config)
        self._publicar_snapshot()

    # ── construcción ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _regla_del_target(frame: pd.DataFrame, target: str | _TargetRule) -> _Target:
        if isinstance(target, Mapping):
            faltan = [k for k in ("col", "op", "value") if k not in target]
            if faltan:
                raise ScorecardInputError(
                    "target= como regla necesita las claves col, op y value "
                    f"(faltan {', '.join(faltan)}); por ejemplo "
                    '{"col": "dias_mora", "op": ">", "value": 90}.'
                )
            columna = str(target["col"])
            if columna not in frame.columns:
                raise ScorecardInputError(
                    f"La regla del target usa la columna {columna!r}, que el archivo no trae."
                )
            predicado = {"col": columna, "op": target["op"], "value": target["value"]}
            return _Target(
                bad_rule={"all_of": [predicado], "any_of": []},
                good_rule=None,  # bueno es todo lo que no es malo, indeterminado ni excluido
                indeterminate_rule=_regla_de_vacios(columna),
                columnas=(columna,),
                n_vacios=int(frame[columna].isna().sum()),
            )
        columna = str(target)
        if columna not in frame.columns:
            raise ScorecardInputError(
                f"target={columna!r} no es una columna del archivo. Columnas disponibles: "
                f"{', '.join(str(c) for c in frame.columns)}."
            )
        serie = frame[columna]
        malo: Any
        bueno: Any
        if dtype_logico(serie) == "bool":
            malo, bueno = True, False
        else:
            valores = set(pd.unique(serie.dropna()))
            if not valores or not valores <= {0, 1}:
                raise ScorecardInputError(
                    f"target={columna!r} tiene que ser una columna 0/1 (o verdadero/falso); trae "
                    f"otros valores. Para definir «malo» con una condición pasa una regla: "
                    f'target={{"col": "{columna}", "op": ">=", "value": 90}}.'
                )
            malo, bueno = 1, 0
        return _Target(
            bad_rule={"all_of": [{"col": columna, "op": "==", "value": malo}], "any_of": []},
            good_rule={"all_of": [{"col": columna, "op": "==", "value": bueno}], "any_of": []},
            indeterminate_rule=_regla_de_vacios(columna),
            columnas=(columna,),
            n_vacios=int(serie.isna().sum()),
        )

    @staticmethod
    def _resolver_muestras(
        frame: pd.DataFrame,
        *,
        date: str | None,
        cohort: str | None,
        partition: str | None,
        oot_from: str | None,
        oot_cohorts: Sequence[str] | None,
        holdout: float,
    ) -> _Muestras:
        declarados = [
            n
            for n, v in (("date", date), ("cohort", cohort), ("partition", partition))
            if v is not None
        ]
        if len(declarados) > 1:
            raise ScorecardInputError(
                f"Declara un solo eje: {', '.join(declarados)} no pueden ir juntos. Usa date= "
                'para partir por fecha, cohort= por añada, o partition="random" sin eje temporal.'
            )
        if not 0.0 <= float(holdout) < 1.0:
            raise ScorecardInputError("holdout= tiene que estar entre 0 y 1 (0,2 de fábrica).")
        if date is not None:
            if date not in frame.columns:
                raise ScorecardInputError(f"date={date!r} no es una columna del archivo.")
            if oot_from is None:
                try:
                    primera, ultima, meses, sugerida = sugerir_oot_from(frame[date])
                except ValueError as exc:
                    raise ScorecardInputError(f"date={date!r}: {exc}") from exc
                raise ScorecardInputError(
                    f"Falta la frontera fuera de tiempo: oot_from=. El archivo cubre de {primera} "
                    f"a {ultima} ({meses} meses). Con los últimos "
                    f"{'12 meses' if meses >= 24 else 'meses del último cuarto'} como muestra "
                    f"fuera de tiempo la frontera sería oot_from={sugerida!r}. Es una decisión de "
                    "la institución: pásala explícita."
                )
            if pd.isna(pd.to_datetime(oot_from, errors="coerce")):
                raise ScorecardInputError(
                    f"oot_from={oot_from!r} no es una fecha legible; escríbela en ISO 8601 "
                    "(por ejemplo 2024-01-01)."
                )
            partitions = ("desarrollo",) + (("holdout",) if holdout > 0 else ()) + ("oot",)
            strategy: dict[str, Any] = {
                "type": "temporal",
                "date_col": date,
                "oot_from": str(oot_from),
                "holdout_fraction": float(holdout),
            }
            return _Muestras(
                strategy=strategy,
                partitions=partitions,
                comparisons=_comparaciones(partitions),
                label=partition_label(strategy),
                time_column=date,
                time_axis="period",
            )
        if cohort is not None:
            if cohort not in frame.columns:
                raise ScorecardInputError(f"cohort={cohort!r} no es una columna del archivo.")
            try:
                distintas, sugeridas = sugerir_oot_cohorts(frame[cohort])
            except ValueError as exc:
                raise ScorecardInputError(f"cohort={cohort!r}: {exc}") from exc
            if oot_cohorts is None:
                raise ScorecardInputError(
                    f"Falta la frontera fuera de tiempo: oot_cohorts=. El archivo trae "
                    f"{len(distintas)} cohortes ({', '.join(distintas)}). Reservando el último "
                    f"cuarto como muestra fuera de tiempo sería oot_cohorts={sugeridas!r}. Es una "
                    "decisión de la institución: pásala explícita."
                )
            reservadas = [str(c) for c in oot_cohorts]
            ausentes = [c for c in reservadas if c not in distintas]
            if not reservadas or ausentes:
                raise ScorecardInputError(
                    "oot_cohorts= nombra cohortes que el archivo no trae: "
                    f"{', '.join(ausentes) or '(vacío)'}. "
                    f"Cohortes disponibles: {', '.join(distintas)}."
                )
            partitions = ("desarrollo",) + (("holdout",) if holdout > 0 else ()) + ("oot",)
            strategy = {
                "type": "cohort",
                "cohort_col": cohort,
                "oot_cohorts": reservadas,
                "holdout_fraction": float(holdout),
            }
            return _Muestras(
                strategy=strategy,
                partitions=partitions,
                comparisons=_comparaciones(partitions),
                label=partition_label(strategy),
                time_column=cohort,
                time_axis="cohort",
            )
        if partition is not None:
            if partition != "random":
                raise ScorecardInputError(
                    f"partition={partition!r} no existe en la puerta guiada: sin eje temporal la "
                    'única opción es partition="random". Con eje, usa date= o cohort=.'
                )
            if holdout <= 0.0:
                raise ScorecardInputError(
                    'partition="random" necesita holdout > 0: sin muestra fuera de tiempo, el '
                    "Holdout es la única muestra con que comparar el modelo."
                )
            dev = round(1.0 - float(holdout), 10)
            strategy = {
                "type": "random",
                "dev_fraction": dev,
                "holdout_fraction": float(holdout),
                "oot_fraction": 0.0,
                "stratify_by": None,
            }
            return _Muestras(
                strategy=strategy,
                partitions=("desarrollo", "holdout"),
                comparisons=("dev_vs_holdout",),
                label=partition_label(strategy),
                time_column=None,
                time_axis="none",
            )
        raise ScorecardInputError(
            "Falta el eje temporal: pasa date= (con oot_from=) o cohort= (con oot_cohorts=). Si "
            'tus datos no tienen eje temporal, declara partition="random".'
        )

    @staticmethod
    def _lineas_de_inferencia(
        *,
        esquema: list[dict[str, Any]],
        n_texto: int,
        predictoras: Sequence[str],
        categoricas: Sequence[str],
        motivos: Mapping[str, str],
        id_label: str,
        n_vacios_target: int,
        columnas_target: Sequence[str],
    ) -> tuple[str, ...]:
        fuera = ", ".join(f"{c} ({m})" for c, m in motivos.items())
        lineas = [
            (
                f"Se infirió: esquema de {len(esquema)} columnas ({len(esquema) - n_texto} "
                f"numéricas o de fecha, {n_texto} de texto); {len(predictoras)} "
                f"{_plural(len(predictoras), 'predictora', 'predictoras')} "
                f"({len(categoricas)} {_plural(len(categoricas), 'categórica', 'categóricas')})"
                + (f"; fuera: {fuera}" if fuera else "")
            ),
            f"Identificador: {id_label}",
        ]
        if n_vacios_target:
            lineas.append(
                f"Resultado vacío en {_miles(n_vacios_target)} "
                f"{_plural(n_vacios_target, 'fila', 'filas')} ({', '.join(columnas_target)}): "
                "quedan indeterminadas: no entran al ajuste y la tarjeta las puntúa aparte"
            )
        return tuple(lineas)

    # ── decidir (D-FLU-3) ───────────────────────────────────────────────────────────────

    def exclude(self, columns: str | Sequence[str], *, reason: str) -> Scorecard:
        """Descarta variables en toda la corrida siguiente, con motivo.

        Escribe ``binning.exclude_columns`` (D-EXC-1): la variable no se tramifica, no aparece en
        las tablas y no puede detener la corrida en «Tramos y WoE». La retira de las listas
        forzadas de selección y modelo —las dos rechazan forzar una variable que el binning ya no
        publica— (la última decisión sobre una variable gana). Sus tramos fijados con
        ``set_bins()``/``merge_bins()`` quedan en suspenso, y ``keep()`` los reactiva. La corrida
        siguiente (``resume()``) emite al trail **un** evento ``decision`` con autor ``usuario`` y
        este motivo.
        """
        return self._decidir("exclude", columns, reason=reason)

    def keep(self, columns: str | Sequence[str], *, reason: str) -> Scorecard:
        """Fuerza variables a entrar al modelo, con motivo.

        Escribe ``selection.force_include`` **y** ``model.force_include`` (sólo con la primera,
        ``model`` no vería una variable que ``selection`` descartó por IV, correlación o VIF) y
        las retira de las listas contrarias y de ``binning.exclude_columns``. Una variable forzada
        que falle una validación dura del motor —signo invertido con la política en ``fail``—
        sigue fallando: ``keep`` no apaga ninguna guarda.
        """
        return self._decidir("keep", columns, reason=reason)

    def _decidir(self, accion: str, columns: str | Sequence[str], *, reason: str) -> Scorecard:
        motivo = str(reason).strip() if reason is not None else ""
        if not motivo:
            raise ScorecardInputError(
                f"{accion}() exige reason=: la decisión queda en el registro de auditoría con su "
                "motivo, y un motivo en blanco no le sirve a quien valide."
            )
        nombres = [columns] if isinstance(columns, str) else [str(c) for c in columns]
        if not nombres:
            raise ScorecardInputError(f"{accion}() necesita al menos una variable.")
        if len(set(nombres)) != len(nombres):
            # Antes de mutar: el registro rechaza variables repetidas y el config quedaba con el
            # efecto escrito sin su motivo (pasada 1 de Codex sobre la capa A de IFRS 9).
            raise ScorecardInputError(f"{accion}() repite una variable: {nombres}.")
        binning = self._config.binning
        predictoras = tuple(binning.feature_columns) if binning is not None else ()
        desconocidas = [c for c in nombres if c not in predictoras]
        if desconocidas:
            raise ScorecardInputError(
                f"{accion}(): {', '.join(desconocidas)} no está entre las predictoras de esta "
                f"corrida ({', '.join(predictoras)})."
            )
        # D-EXC-1: `exclude` escribe SÓLO `binning.exclude_columns` —la variable no se tramifica
        # y no puede detener la corrida allí— y la retira de las cuatro listas forzadas: selección
        # y modelo rechazan forzar una variable que el binning no publica (revisión adversarial
        # de la enmienda, pasada 1). `keep` la retira de `binning.exclude_columns` y escribe
        # `force_include` en las dos secciones (sólo con `selection`, `model` no vería una
        # variable que la selección descartó). La última decisión gana.
        hojas: dict[str, list[str]] = {}
        excluidas = [c for c in binning.exclude_columns if c not in nombres] if binning else []
        if accion == "exclude":
            excluidas += nombres
            hojas["binning.exclude_columns"] = list(excluidas)
        self._actualizar_seccion("binning", {"exclude_columns": tuple(excluidas)})
        for seccion in ("selection", "model"):
            actual = getattr(self._config, seccion)
            campos: dict[str, Any] = {
                lista: tuple(c for c in getattr(actual, lista) if c not in nombres)
                for lista in ("force_include", "force_exclude")
            }
            if accion == "keep":
                campos["force_include"] = (*campos["force_include"], *nombres)
                hojas[f"{seccion}.force_include"] = list(campos["force_include"])
            self._actualizar_seccion(seccion, campos)
        self._registrar_decision(accion, nombres, motivo, hojas)
        self._pending_decisions = True
        self._config, self._steps = self._resolver_pipeline(self._config)
        self._final = None
        self._echo(
            f"Decisión registrada: {accion} {', '.join(nombres)} — «{motivo}». Se aplica en la "
            "corrida siguiente: resume()."
        )
        return self

    # ── tramos: merge_bins / set_bins (§8-9 (a), Cami 2026-09-20) ──────────────────────

    def bins(self, column: str) -> pd.DataFrame:
        """Los tramos de una variable numérica en la última corrida, numerados desde 1.

        Es la tabla con la que se decide ``merge_bins``/``set_bins``: número, rango, filas,
        malos, tasa de malos y WoE, leídos de la tabla de binning que el motor publicó (sin los
        tramos ``Special``/``Missing``, que no tienen corte).
        """
        tabla = self._tabla_de_tramos(column)
        from bayesrisk.core.tramos import rotulos_por_fila

        bordes = (
            self._study.artifacts.get("binning", "bin_edges")
            if self._study.artifacts.has("binning", "bin_edges")
            else None
        )
        # D-CPY-3: el rango con los bordes efectivos, en es-CL; la etiqueta del motor sigue siendo
        # la clave de todo lo que casa por tramo.
        legibles = rotulos_por_fila(tabla, bordes, column)
        filas: list[dict[str, Any]] = []
        for numero, (_indice, fila) in enumerate(tabla.iterrows(), start=1):
            filas.append(
                {
                    "Tramo": numero,
                    "Rango": legibles[numero - 1],
                    "Filas": int(fila.get("Count", 0)),
                    "Malos": int(fila.get("Event", 0)),
                    "Tasa de malos": float(fila.get("Event rate", float("nan"))),
                    "WoE": float(fila.get("WoE", float("nan"))),
                }
            )
        from bayesrisk.guided.summaries import TablaDeEtapa

        return TablaDeEtapa.de(
            pd.DataFrame(filas),
            {"Tramo": "int", "Filas": "int", "Malos": "int", "Tasa de malos": "pct", "WoE": "num3"},
        )

    def merge_bins(self, column: str, bins: Sequence[int], *, reason: str) -> Scorecard:
        """Junta dos tramos **adyacentes** de una variable numérica, con motivo.

        Los tramos se numeran como en :meth:`bins` (desde 1). Escribe la hoja
        ``binning.variable_overrides[<column>].user_splits`` con los cortes vigentes menos el
        que separaba esos dos tramos, todos fijados (``user_splits_fixed``): en la corrida
        siguiente el motor tramifica exactamente así y calcula el WoE de los tramos que resultan.
        """
        motivo = self._motivo(reason, "merge_bins")
        cortes = self._cortes_vigentes(column)
        numeros = [int(b) for b in bins]
        if len(numeros) != 2:
            raise ScorecardInputError(
                f"merge_bins() junta exactamente dos tramos adyacentes; recibió {numeros}. "
                f"Los tramos de «{column}» son:\n{self._rangos_en_texto(column)}"
            )
        primero, segundo = sorted(numeros)
        n_tramos = len(cortes) + 1
        if primero < 1 or segundo > n_tramos:
            raise ScorecardInputError(
                f"merge_bins(): el tramo {segundo if segundo > n_tramos else primero} no existe "
                f"en «{column}» ({n_tramos} tramos). Los tramos son:\n"
                f"{self._rangos_en_texto(column)}"
            )
        if segundo != primero + 1:
            raise ScorecardInputError(
                f"merge_bins(): los tramos {primero} y {segundo} de «{column}» no son adyacentes; "
                "el motor sólo junta tramos vecinos (el corte entre ellos es el que desaparece). "
                f"Los tramos son:\n{self._rangos_en_texto(column)}"
            )
        if n_tramos == 2:
            raise ScorecardInputError(
                f"merge_bins(): «{column}» tiene dos tramos; juntarlos dejaría un solo tramo, sin "
                "poder predictivo. Descarta la variable con exclude() o fija otros cortes con "
                "set_bins()."
            )
        nuevos = tuple(c for i, c in enumerate(cortes, start=1) if i != primero)
        return self._fijar_cortes(column, nuevos, accion="merge_bins", motivo=motivo)

    def set_bins(self, column: str, cuts: Sequence[float], *, reason: str) -> Scorecard:
        """Fija los cortes de una variable numérica (los límites entre tramos), con motivo.

        Escribe ``binning.variable_overrides[<column>].user_splits`` con esos cortes, todos
        fijados: en la corrida siguiente el motor tramifica exactamente así. Un tramo fijado que
        viole el tamaño mínimo o la monotonía declarada hace que el motor no tramifique la
        variable, y el resumen de «Tramos y WoE» lo dice.
        """
        motivo = self._motivo(reason, "set_bins")
        self._exigir_corrida("set_bins")
        self._exigir_numerica(column)
        try:
            nuevos = tuple(float(c) for c in cuts)
        except (TypeError, ValueError) as exc:
            raise ScorecardInputError(
                f"set_bins(): los cortes tienen que ser números; recibió {list(cuts)!r}."
            ) from exc
        if not nuevos:
            raise ScorecardInputError("set_bins() necesita al menos un corte.")
        if any(b <= a for a, b in pairwise(nuevos)):
            raise ScorecardInputError(
                f"set_bins(): los cortes tienen que ser estrictamente crecientes; recibió "
                f"{list(nuevos)}."
            )
        return self._fijar_cortes(column, nuevos, accion="set_bins", motivo=motivo)

    def _fijar_cortes(
        self, column: str, cortes: tuple[float, ...], *, accion: str, motivo: str
    ) -> Scorecard:
        """Escribe la hoja de cortes de ``column`` y registra la decisión para el trail."""
        binning = self._config.binning
        if binning is None:  # inalcanzable: `_exigir_numerica` ya lo comprobó
            raise ScorecardInputError("La corrida no tiene sección binning.")
        overrides = [o.model_dump(mode="python") for o in binning.variable_overrides]
        propio = next((o for o in overrides if o.get("name") == column), None)
        if propio is None:
            propio = {"name": column}
            overrides.append(propio)
        propio["user_splits"] = list(cortes)
        propio["user_splits_fixed"] = [True] * len(cortes)
        # Con más tramos fijados que el máximo vigente el solver no tendría solución: el tope
        # propio de la variable sube justo a los tramos que resultan, y queda declarado en la
        # misma hoja.
        tope = propio.get("max_n_bins") or binning.max_n_bins
        if tope is not None and len(cortes) + 1 > tope:
            propio["max_n_bins"] = len(cortes) + 1
        self._actualizar_seccion("binning", {"variable_overrides": overrides})
        vigente = self._config.binning
        assert vigente is not None  # recién validada
        hoja = next(
            o.model_dump(mode="python") for o in vigente.variable_overrides if o.name == column
        )
        self._registrar_decision(accion, [column], motivo, {"binning.variable_overrides": [hoja]})
        self._pending_decisions = True
        self._config, self._steps = self._resolver_pipeline(self._config)
        self._final = None
        self._echo(
            f"Decisión registrada: {accion} {column} → cortes {list(cortes)} — «{motivo}». Se "
            "aplica en la corrida siguiente: resume()."
        )
        return self

    def _exigir_corrida(self, accion: str) -> None:
        if self._study is None or not self._study.artifacts.has("binning", "tables"):
            raise ScorecardInputError(
                f"{accion}() decide sobre los tramos de la última corrida: llama a run() primero "
                "(al menos hasta «Tramos y WoE»)."
            )

    def _exigir_numerica(self, column: str) -> None:
        binning = self._config.binning
        predictoras = tuple(binning.feature_columns) if binning is not None else ()
        if column not in predictoras:
            raise ScorecardInputError(
                f"«{column}» no está entre las predictoras de esta corrida "
                f"({', '.join(predictoras)})."
            )
        if binning is not None and column in tuple(binning.categorical_columns):
            raise ScorecardInputError(
                f"«{column}» es categórica: los cortes fijados sólo aplican a variables "
                "numéricas. Para una categórica, agrupa sus niveles antes de cargar los datos."
            )

    def _tabla_de_tramos(self, column: str) -> pd.DataFrame:
        """La tabla de binning de ``column`` sin ``Special``/``Missing``/``Totals``."""
        self._exigir_corrida("bins")
        self._exigir_numerica(column)
        tablas = self._study.artifacts.get("binning", "tables")
        tabla = tablas.get(column) if isinstance(tablas, Mapping) else None
        if not isinstance(tabla, pd.DataFrame):
            raise ScorecardInputError(
                f"«{column}» no quedó tramificada en la última corrida (el resumen de «Tramos y "
                "WoE» dice por qué): no hay tramos que decidir."
            )
        etiquetas = tabla["Bin"].astype(str) if "Bin" in tabla.columns else pd.Series(dtype=str)
        fuera = etiquetas.isin(["Special", "Missing"]) | (tabla.index.astype(str) == "Totals")
        return tabla.loc[~fuera]

    def _cortes_vigentes(self, column: str) -> tuple[float, ...]:
        """Los cortes con que el motor tramificó ``column`` en la última corrida."""
        self._exigir_corrida("merge_bins")
        self._exigir_numerica(column)
        binner = self._study.artifacts.get("binning", "process")
        proceso = getattr(binner, "process_", None)
        try:
            if proceso is None:
                raise AttributeError("el binner no publicó su proceso ajustado")
            variable = proceso.get_binned_variable(column)
        except Exception as exc:
            raise ScorecardInputError(
                f"«{column}» no quedó tramificada en la última corrida (el resumen de «Tramos y "
                "WoE» dice por qué): no hay tramos que juntar."
            ) from exc
        return tuple(float(c) for c in getattr(variable, "splits", ()))

    def _rangos_en_texto(self, column: str) -> str:
        tabla = self.bins(column)
        return "\n".join(f"  {int(f['Tramo'])}: {f['Rango']}" for _, f in tabla.iterrows())

    # ── exportar (D-FLU-5) ──────────────────────────────────────────────────────────────

    def export_excel(self) -> tuple[Path, ...]:
        """Un libro Excel por etapa, numerado, en ``<run_dir>/<name>/excel/`` (D-FLU-5, D-SIM-7).

        ``01 Datos y muestras.xlsx`` … ``10 Validación formal.xlsx`` para las etapas que corrieron
        —cada uno con el resumen, la tabla de decisión y las tablas completas que el informe
        publica para ese dominio, con la misma protección de celdas que los exports del informe—
        más ``11 Decisiones.xlsx`` con las decisiones del registro de auditoría (humanas, de la
        puerta y del motor). Opcional: nunca es la vía para ver un resultado. Exige el extra
        ``excel`` (``openpyxl``); sin él se detiene con el comando de instalación.
        """
        from bayesrisk.guided.export import EXCEL_SUBDIR, write_stage_workbooks

        # Bajo el candado y sobre la evidencia PROPIA: otro Scorecard con el mismo `run_dir/name`
        # puede haber consolidado su corrida en `run/` —el trail que este libro leería—, y este
        # objeto escribiría sus tablas en memoria junto a decisiones ajenas (pasada 3 de Codex
        # sobre la capa B).
        candado = self._tomar_candado("exportar")
        try:
            self._exigir_evidencia_propia("export_excel")
            escritos = write_stage_workbooks(
                self._study,
                self._stage_summaries,
                directory=self._project_dir / EXCEL_SUBDIR,
                report_config=self._config.report,
                trail_path=self._context().trail_path,
            )
        finally:
            _liberar_carpeta(candado)
        self._echo(
            f"Excel por etapa: {len(escritos)} "
            f"{_plural(len(escritos), 'libro', 'libros')} en {self._project_dir / EXCEL_SUBDIR}"
        )
        return escritos

    # ── comparar (D-FLU-6) ──────────────────────────────────────────────────────────────

    def compare(self, other: Scorecard) -> StageSummary:
        """Dos corridas lado a lado: cifras clave, variables finales y decisiones humanas."""
        if self._study is None or other._study is None:
            raise ScorecardInputError("compare() necesita que las dos corridas hayan corrido.")
        propio = build_final_summary(self._study, (), self._context())
        ajeno = build_final_summary(other._study, (), other._context())
        # Dos corridas pueden llevar el mismo `name` (el de fábrica, en carpetas distintas): las
        # columnas se rotulan sin ambigüedad o la tabla perdería una de las dos en silencio
        # (pasada de Codex sobre A2).
        mio, suyo = self._name, other._name
        if mio == suyo:
            mio, suyo = f"{self._name} (esta)", f"{other._name} (otra)"
        filas: list[dict[str, Any]] = [
            {"Cifra": "Ejecución", mio: propio.execution, suyo: ajeno.execution},
            {"Cifra": "Validación técnica", mio: propio.validation, suyo: ajeno.validation},
        ]
        mias = dict(propio.figures)
        suyas = dict(ajeno.figures)
        for rotulo in dict.fromkeys([*mias, *suyas]):
            filas.append(
                {"Cifra": rotulo, mio: mias.get(rotulo, "—"), suyo: suyas.get(rotulo, "—")}
            )
        filas.append(
            {
                "Cifra": "Variables finales",
                mio: ", ".join(_variables_finales(self._study)) or "—",
                suyo: ", ".join(_variables_finales(other._study)) or "—",
            }
        )
        filas.append(
            {
                "Cifra": "Decisiones humanas",
                mio: "; ".join(propio.decisions) or "ninguna",
                suyo: "; ".join(ajeno.decisions) or "ninguna",
            }
        )
        filas.append(
            {"Cifra": "Carpeta", mio: str(self._project_dir), suyo: str(other._project_dir)}
        )
        lines = (
            f"{mio}: {propio.execution} · validación técnica {propio.validation}",
            f"{suyo}: {ajeno.execution} · validación técnica {ajeno.validation}",
        )
        return StageSummary(
            stage="compare",
            label=f"Comparación: {mio} frente a {suyo}",
            lines=lines,
            table=pd.DataFrame(filas),
        )


def _variables_finales(study: Any) -> tuple[str, ...]:
    if study is None or not study.artifacts.has("model", "final_features"):
        return ()
    return tuple(str(v) for v in study.artifacts.get("model", "final_features"))


def _regla_de_vacios(columna: str) -> dict[str, Any]:
    """La regla «resultado vacío → indeterminado» sobre la columna que define el target."""
    return {"all_of": [{"col": columna, "op": "isna", "value": None}], "any_of": []}


def _comparaciones(partitions: Sequence[str]) -> tuple[str, ...]:
    """Las comparaciones de estabilidad que existen con estas muestras."""
    return tuple(
        c
        for c, muestra in (("dev_vs_holdout", "holdout"), ("dev_vs_oot", "oot"))
        if muestra in partitions
    )


def _config_base() -> dict[str, Any]:
    """El preset F1 (con análisis exploratorio) como punto de partida de los defaults."""
    from bayesrisk.ui.presets import standard_preset

    return deepcopy(standard_preset()["config"])
