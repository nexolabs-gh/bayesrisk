"""Escalamiento log-odds a puntos de scorecard (SDD-09 §4/§7).

``PointsScaler`` deriva una tabla de puntos auditable desde coeficientes logísticos WoE y tablas
de binning ya fiteadas. La transformación casa el WoE de cada fila con la fila de puntos de su
variable **más cercana a 1e-12 o menos** (D-BPT-1): la exacta siempre gana y, a igual distancia,
la primera en el orden publicado por ``scorecard_``. El WoE que recalcula OptBinning al transformar
difiere del de la tabla en el último bit; exigir igualdad exacta mandaba esas filas a la fórmula,
donde un ajuste manual de puntos no llegaba. Los tramos que la búsqueda no distingue —WoE a 1e-12
o menos entre sí— publican los puntos del primero, y un ajuste manual sobre cualquiera de ellos se
rechaza al ajustar.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, TypeAlias, cast

from pydantic import ValidationError

from bayesrisk.core.base import BayesRiskTransformer
from bayesrisk.core.config import BayesRiskBaseConfig
from bayesrisk.core.exceptions import ConfigError, MissingDependencyError
from bayesrisk.scorecard.config import (
    InterceptAllocation,
    PointOverrideConfig,
    RoundingMethod,
    ScorecardConfig,
    ScoreDirection,
)
from bayesrisk.scorecard.exceptions import ScorecardFitError, ScorecardTransformError

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    from bayesrisk.core.audit import AuditSink

    DataFrame: TypeAlias = pd.DataFrame
    NDArrayFloat: TypeAlias = np.ndarray[Any, np.dtype[np.float64]]
    Series: TypeAlias = pd.Series[Any]
else:
    AuditSink: TypeAlias = Any
    DataFrame: TypeAlias = Any
    NDArrayFloat: TypeAlias = Any
    Series: TypeAlias = Any

__all__ = ["PointsScaler"]

_SCORING_EXTRA_MESSAGE = "PointsScaler requiere pandas/numpy; instale bayesrisk[scoring]."
_REQUIRED_COEFFICIENT_COLUMNS = frozenset({"feature", "woe_column", "beta"})
_REQUIRED_BINNING_COLUMNS = frozenset({"Bin", "WoE"})
_INTERCEPT_FEATURE = "intercept"
_INTERCEPT_WOE_COLUMN = "const"
# D-BPT-1: distancia máxima para que un WoE case con una fila de puntos. Constante, no perilla: está
# cuatro órdenes sobre el ruido medido entre la transformación y la tabla (2,2e-16) y nueve bajo el
# par de tramos reales más cercano medido (0,0051 en el preset, 0,0059 en la muestra SBA).
_TOLERANCIA_WOE = 1e-12
# D-BPT-1 (revisión del código, pasada 2): los tramos de un grupo indistinguible publican los
# puntos del primero sólo si sus puntos crudos difieren a lo sumo en una millonésima de punto. Con
# un coeficiente real (|β| < 10) dos WoE a 1e-12 dan puntos a menos de 3e-10; superar 1e-6 exige
# |β| > 3e4, un coeficiente fuera de escala: el ajuste se rechaza en vez de mover el puntaje.
_TOLERANCIA_PUNTOS_DEL_GRUPO = 1e-6


class PointsScaler(BayesRiskTransformer):
    """Escala componentes log-odds de una logística WoE a puntos de scorecard."""

    config_cls: ClassVar[type[ScorecardConfig]] = ScorecardConfig

    def __init__(
        self,
        *,
        pdo: float = 20.0,
        target_score: float = 600.0,
        target_odds: float = 50.0,
        score_direction: ScoreDirection = "higher_is_lower_risk",
        intercept_allocation: InterceptAllocation = "uniform",
        rounding_method: RoundingMethod = "nearest_integer",
        output_suffix: str = "__points",
        score_column: str = "score",
        min_score: float | None = None,
        max_score: float | None = None,
        clip: bool = False,
        point_overrides: tuple[PointOverrideConfig, ...] = (),
    ) -> None:
        """Asigna hiperparámetros sin lógica para preservar ``clone`` de sklearn."""
        self.pdo = pdo
        self.target_score = target_score
        self.target_odds = target_odds
        self.score_direction = score_direction
        self.intercept_allocation = intercept_allocation
        self.rounding_method = rounding_method
        self.output_suffix = output_suffix
        self.score_column = score_column
        self.min_score = min_score
        self.max_score = max_score
        self.clip = clip
        self.point_overrides = point_overrides

    @classmethod
    def from_config(cls, cfg: BayesRiskBaseConfig) -> PointsScaler:
        """Construye ``PointsScaler`` desde ``ScorecardConfig`` excluyendo ``type``."""
        if not isinstance(cfg, ScorecardConfig):
            cfg = ScorecardConfig.model_validate(cfg)
        kwargs = cfg.model_dump(exclude={"type"})
        kwargs["point_overrides"] = cfg.point_overrides
        return cls(**kwargs)

    def fit(
        self,
        *,
        coefficients: DataFrame,
        final_features: tuple[str, ...],
        final_woe_columns: tuple[str, ...],
        binning_tables: Mapping[str, DataFrame],
        woe_column_map: Mapping[str, str],
        audit: AuditSink | None = None,
        assigned_bins: Mapping[str, Collection[str]] | None = None,
        bin_edges: DataFrame | None = None,
    ) -> Self:
        """Deriva puntos por bin desde coeficientes y tablas WoE sin mutar entradas.

        ``assigned_bins`` nombra, por variable, los bins auxiliares cuyo WoE asignó el binning
        (D-FAL-1). Comparten los puntos de su tramo de referencia —la primera fila con su mismo
        WoE, la que usa la búsqueda de puntos—: heredan su ajuste manual y no admiten uno propio.

        ``bin_edges`` son los bordes efectivos que publica ``binning`` (D-CPY-3): con ellos, un
        ajuste manual de puntos casa con la etiqueta del motor **o** con el rótulo legible que
        muestran las tablas. Un ajuste que no casa con ninguno se declara en el trail
        (``point_override_sin_casar``); antes se ignoraba en silencio.
        """
        pd = _import_pandas()
        np = _import_numpy()
        _validate_runtime_config(self)
        if audit is not None:
            self._audit = audit

        features, woe_columns = _validate_feature_mapping(
            final_features=final_features,
            final_woe_columns=final_woe_columns,
            woe_column_map=woe_column_map,
        )
        coefficients_frame = _normalize_coefficients(coefficients, pd=pd)
        coefficient_specs, alpha = _coefficient_specs(
            coefficients_frame,
            features=features,
            woe_columns=woe_columns,
        )
        tables = _copy_binning_tables(
            binning_tables,
            features=features,
            pd=pd,
            np=np,
        )

        n_variables = len(features)
        factor = _normalize_float(float(self.pdo) / math.log(2.0))
        offset = _normalize_float(
            float(self.target_score) - factor * math.log(float(self.target_odds))
        )
        intercept_share = _normalize_float(alpha / n_variables)
        offset_share = _normalize_float(offset / n_variables)
        overrides = _override_map(self.point_overrides)
        legibles = _rotulos_legibles(binning_tables, bin_edges, features=features)
        casados: set[tuple[str, str]] = set()
        igualados: dict[tuple[str, int], float | int] = {}
        rows = _scorecard_rows(
            estimator=self,
            features=features,
            woe_columns=woe_columns,
            coefficients=coefficient_specs,
            tables=tables,
            overrides=overrides,
            factor=factor,
            offset_share=offset_share,
            intercept_share=intercept_share,
            assigned_bins=assigned_bins or {},
            legibles=legibles,
            casados=casados,
            igualados=igualados,
        )
        for clave, override in overrides.items():
            if clave in casados:
                continue
            self.log_decision(
                regla="point_override_sin_casar",
                umbral=override.reason,
                valor={"feature": override.feature, "bin_label": override.bin_label},
                accion="no_aplicar",
            )
        scorecard = _normalize_float_frame(pd.DataFrame(rows), pd=pd)
        duplicate_woe = _filas_repetidas(scorecard, igualados)
        if duplicate_woe:
            self.log_decision(
                regla="woe_duplicado",
                umbral="primera_aparicion_feature_woe",
                valor=duplicate_woe,
                accion="usar_punto_determinista",
            )
        if self.rounding_method != "none":
            rounding_delta = scorecard["rounding_delta"].astype("float64")
            self.log_decision(
                regla="scorecard_rounding",
                umbral=self.rounding_method,
                valor={
                    "n_variables": n_variables,
                    "delta_max_abs": _normalize_float(float(rounding_delta.abs().max())),
                    "delta_suma": _normalize_float(float(rounding_delta.sum())),
                },
                accion="publicar_puntos_redondeados",
            )

        self.factor_ = factor
        self.offset_ = offset
        self.pdo_ = _normalize_float(float(self.pdo))
        self.target_score_ = _normalize_float(float(self.target_score))
        self.target_odds_ = _normalize_float(float(self.target_odds))
        self.score_direction_ = self.score_direction
        self.rounding_method_ = self.rounding_method
        self.intercept_allocation_ = self.intercept_allocation
        self.final_features_ = features
        self.final_woe_columns_ = woe_columns
        self.points_columns_ = tuple(f"{feature}{self.output_suffix}" for feature in features)
        self.coefficients_ = coefficients_frame.copy(deep=True)
        self.scorecard_ = scorecard.copy(deep=True)
        self.feature_points_ = {
            feature: scorecard.loc[scorecard["feature"].eq(feature)].copy(deep=True)
            for feature in features
        }
        self.dependency_versions_ = _dependency_versions(self)
        self.intercept_ = alpha
        self.intercept_share_ = intercept_share
        self.beta_by_feature_ = {feature: coefficient_specs[feature].beta for feature in features}
        self._duplicate_woe_keys_ = tuple(duplicate_woe)
        return self

    def transform(self, woe_frame: DataFrame) -> DataFrame:
        """Publica columnas de puntos y score total desde un frame WoE ya validado."""
        self._check_fitted()
        pd = _import_pandas()
        np = _import_numpy()
        frame = _as_dataframe(woe_frame, pd, context="transform")
        _validate_unique_columns(frame, error_cls=ScorecardTransformError)
        _validate_transform_columns(
            frame,
            final_woe_columns=self.final_woe_columns_,
            output_columns=(*self.points_columns_, self.score_column),
        )

        result = frame.copy(deep=True)
        unseen_counts: dict[str, int] = {}
        filas_por_variable = _filas_por_variable(self.scorecard_)
        for feature, woe_column, points_column in zip(
            self.final_features_,
            self.final_woe_columns_,
            self.points_columns_,
            strict=True,
        ):
            values = _finite_woe_array(
                frame[woe_column],
                feature=feature,
                woe_column=woe_column,
                np=np,
            )
            points, unseen_count = _points_for_values(
                estimator=self,
                filas=filas_por_variable.get(feature, ()),
                values=values,
                beta=self.beta_by_feature_[feature],
            )
            result[points_column] = pd.Series(points, index=frame.index).map(_normalize_point)
            if unseen_count:
                unseen_counts[feature] = unseen_count
                self.log_decision(
                    regla="bin_no_visto",
                    umbral="woe_tabular",
                    valor={"feature": feature, "conteo": unseen_count},
                    accion="calcular_por_formula",
                )

        score = result.loc[:, list(self.points_columns_)].sum(axis=1)
        score = score.map(lambda value: _normalize_float(float(value)))
        score = _apply_score_limits(self, score, pd=pd)
        result[self.score_column] = score.map(lambda value: _normalize_float(float(value)))
        self.unseen_bins_ = dict(unseen_counts)
        return result


@dataclass(frozen=True)
class CoefficientSpec:
    """Coeficiente beta trazable para una feature final."""

    feature: str
    woe_column: str
    beta: float


def _import_pandas() -> Any:
    """Importa pandas localmente y traduce ausencias a un mensaje accionable."""
    try:
        return importlib.import_module("pandas")
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_SCORING_EXTRA_MESSAGE) from exc


def _import_numpy() -> Any:
    """Importa numpy localmente y traduce ausencias a un mensaje accionable."""
    try:
        return importlib.import_module("numpy")
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_SCORING_EXTRA_MESSAGE) from exc


def _validate_runtime_config(estimator: PointsScaler) -> None:
    """Revalida hiperparámetros planos contra ``ScorecardConfig``."""
    try:
        ScorecardConfig(
            pdo=estimator.pdo,
            target_score=estimator.target_score,
            target_odds=estimator.target_odds,
            score_direction=estimator.score_direction,
            intercept_allocation=estimator.intercept_allocation,
            rounding_method=estimator.rounding_method,
            output_suffix=estimator.output_suffix,
            score_column=estimator.score_column,
            min_score=estimator.min_score,
            max_score=estimator.max_score,
            clip=estimator.clip,
            point_overrides=estimator.point_overrides,
        )
    except (ConfigError, ValidationError) as exc:
        raise ConfigError(f"Hiperparámetros inválidos para PointsScaler: {exc}") from exc


def _validate_feature_mapping(
    *,
    final_features: tuple[str, ...],
    final_woe_columns: tuple[str, ...],
    woe_column_map: Mapping[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Valida el mapping 1:1 ``feature -> columna WoE`` preservando orden."""
    if len(final_features) != len(final_woe_columns):
        raise ScorecardFitError(
            "final_features y final_woe_columns deben tener el mismo largo: "
            f"len(final_features)={len(final_features)}, "
            f"len(final_woe_columns)={len(final_woe_columns)}."
        )
    if not final_features:
        raise ScorecardFitError("Scorecard requiere al menos una variable final.")
    if len(set(final_features)) != len(final_features):
        raise ScorecardFitError(f"final_features contiene duplicados: {final_features!r}.")
    if len(set(final_woe_columns)) != len(final_woe_columns):
        raise ScorecardFitError(f"final_woe_columns contiene duplicados: {final_woe_columns!r}.")

    for feature, woe_column in zip(final_features, final_woe_columns, strict=True):
        observed = woe_column_map.get(feature)
        if observed is None:
            raise ScorecardFitError(
                "woe_column_map no contiene una feature final: "
                f"feature='{feature}', disponibles={sorted(woe_column_map)}."
            )
        if observed != woe_column:
            raise ScorecardFitError(
                "woe_column_map no coincide con model.final_woe_columns: "
                f"feature='{feature}', esperado='{woe_column}', observado='{observed}'."
            )
    return final_features, final_woe_columns


def _as_dataframe(df: object, pd: Any, *, context: Literal["fit", "transform"]) -> DataFrame:
    """Valida y copia defensivamente una entrada tabular."""
    if not isinstance(df, pd.DataFrame):
        error_cls = ScorecardFitError if context == "fit" else ScorecardTransformError
        raise error_cls(
            f"PointsScaler.{context} requiere pandas.DataFrame; tipo observado={type(df).__name__}."
        )
    if len(df.index) == 0:
        error_cls = ScorecardFitError if context == "fit" else ScorecardTransformError
        raise error_cls(f"PointsScaler.{context} recibió un DataFrame vacío.")
    return cast(DataFrame, df.copy(deep=True))


def _validate_unique_columns(frame: DataFrame, *, error_cls: type[Exception]) -> None:
    """Rechaza columnas duplicadas para evitar ambigüedad."""
    duplicated = frame.columns[frame.columns.duplicated()].astype(str).tolist()
    if duplicated:
        joined = ", ".join(f"'{column}'" for column in duplicated)
        raise error_cls(f"PointsScaler requiere nombres de columnas únicos; duplicadas: {joined}.")


def _normalize_coefficients(coefficients: DataFrame, *, pd: Any) -> DataFrame:
    """Copia, valida columnas mínimas y normaliza betas finitos."""
    frame = _as_dataframe(coefficients, pd, context="fit")
    _validate_unique_columns(frame, error_cls=ScorecardFitError)
    missing = sorted(_REQUIRED_COEFFICIENT_COLUMNS - set(frame.columns))
    if missing:
        raise ScorecardFitError(f"coefficients no contiene columnas requeridas: {missing}.")
    frame["feature"] = frame["feature"].astype(str)
    frame["woe_column"] = frame["woe_column"].astype(str)
    frame["beta"] = [
        _finite_float(value, label="beta", error_cls=ScorecardFitError)
        for value in frame["beta"].tolist()
    ]
    return frame.copy(deep=True)


def _coefficient_specs(
    coefficients: DataFrame,
    *,
    features: tuple[str, ...],
    woe_columns: tuple[str, ...],
) -> tuple[dict[str, CoefficientSpec], float]:
    """Extrae betas finales y el intercepto único ``alpha``."""
    intercept_mask = coefficients["feature"].eq(_INTERCEPT_FEATURE) | coefficients["woe_column"].eq(
        _INTERCEPT_WOE_COLUMN
    )
    intercept_rows = coefficients.loc[intercept_mask]
    if len(intercept_rows.index) > 1:
        raise ScorecardFitError("coefficients contiene más de una fila de intercepto.")
    alpha = 0.0
    if len(intercept_rows.index) == 1:
        alpha = _normalize_float(float(intercept_rows["beta"].iloc[0]))

    non_intercept = coefficients.loc[~intercept_mask].copy(deep=True)
    specs: dict[str, CoefficientSpec] = {}
    for feature, woe_column in zip(features, woe_columns, strict=True):
        match = non_intercept.loc[
            non_intercept["feature"].eq(feature) | non_intercept["woe_column"].eq(woe_column)
        ]
        if len(match.index) == 0:
            raise ScorecardFitError(f"Feature final sin coeficiente: feature='{feature}'.")
        if len(match.index) > 1:
            raise ScorecardFitError(f"Coeficiente ambiguo para feature='{feature}'.")
        row = match.iloc[0]
        observed_feature = str(row["feature"])
        observed_woe = str(row["woe_column"])
        if observed_feature != feature or observed_woe != woe_column:
            raise ScorecardFitError(
                "La fila de coefficients no coincide con el mapping final: "
                f"feature='{feature}', woe_column='{woe_column}', "
                f"observado=('{observed_feature}', '{observed_woe}')."
            )
        specs[feature] = CoefficientSpec(
            feature=feature,
            woe_column=woe_column,
            beta=_normalize_float(float(row["beta"])),
        )
    return specs, alpha


def _copy_binning_tables(
    binning_tables: Mapping[str, DataFrame],
    *,
    features: tuple[str, ...],
    pd: Any,
    np: Any,
) -> dict[str, DataFrame]:
    """Copia y valida tablas WoE por feature final."""
    tables: dict[str, DataFrame] = {}
    for feature in features:
        if feature not in binning_tables:
            raise ScorecardFitError(
                "Feature final sin tabla de binning: "
                f"feature='{feature}', disponibles={sorted(binning_tables)}."
            )
        table = _as_dataframe(binning_tables[feature], pd, context="fit")
        _validate_unique_columns(table, error_cls=ScorecardFitError)
        missing = sorted(_REQUIRED_BINNING_COLUMNS - set(table.columns))
        if missing:
            raise ScorecardFitError(
                f"binning_tables['{feature}'] no contiene columnas requeridas: {missing}."
            )
        model_rows = table.loc[~_total_row_mask(table)].copy(deep=True)
        if model_rows.empty:
            raise ScorecardFitError(f"binning_tables['{feature}'] no contiene bins publicables.")
        woe = pd.to_numeric(model_rows["WoE"], errors="coerce")
        finite = np.isfinite(woe.to_numpy(dtype="float64", copy=True))
        if not bool(finite.all()):
            observed = model_rows.loc[~finite, "WoE"].iloc[0]
            raise ScorecardFitError(
                "WoE no finito en tabla de binning: "
                f"feature='{feature}', valor observado={observed!r}."
            )
        model_rows["WoE"] = [_normalize_float(float(value)) for value in woe.tolist()]
        model_rows["Bin"] = model_rows["Bin"].astype(str)
        tables[feature] = model_rows.copy(deep=True)
    return tables


def _total_row_mask(table: DataFrame) -> Series:
    """Identifica filas auxiliares de totales sin depender de bytes del backend."""
    index_is_total = table.index.astype(str) == "Totals"
    bin_is_total = table["Bin"].astype(str).isin({"Totals", "Total"})
    return cast(Series, index_is_total | bin_is_total)


def _scorecard_rows(
    *,
    estimator: PointsScaler,
    features: tuple[str, ...],
    woe_columns: tuple[str, ...],
    coefficients: Mapping[str, CoefficientSpec],
    tables: Mapping[str, DataFrame],
    overrides: Mapping[tuple[str, str], PointOverrideConfig],
    factor: float,
    offset_share: float,
    intercept_share: float,
    assigned_bins: Mapping[str, Collection[str]],
    legibles: Mapping[str, list[str]] | None = None,
    casados: set[tuple[str, str]] | None = None,
    igualados: dict[tuple[str, int], float | int] | None = None,
) -> list[dict[str, object]]:
    """Construye filas de puntos en orden estable feature/bin.

    Un ajuste manual casa con la etiqueta del motor o con el rótulo legible del tramo (D-CPY-3);
    las claves que casaron se anotan en ``casados``. Un tramo de un grupo indistinguible por WoE
    publica los puntos del primero del grupo (D-BPT-1); los suyos por fórmula quedan en
    ``igualados``, por ``(feature, bin_index)``.
    """
    from bayesrisk.core.tramos import filas_que_casan

    legibles = legibles or {}
    casados = casados if casados is not None else set()
    igualados = igualados if igualados is not None else {}
    crudas = {
        feature: [str(valor) for valor in tables[feature]["Bin"]]
        for feature in features
        if feature in tables
    }
    # Primero TODAS las etiquetas del motor, después los rótulos legibles: un tramo que ya tiene
    # su ajuste por la etiqueta del motor lo conserva, como antes, aunque otro ajuste lo nombre por
    # su rótulo; ése queda sin casar y se declara (revisión adversarial del código, pasada 2).
    destino: dict[tuple[str, int], tuple[str, str]] = {}
    for por_etiqueta_del_motor in (True, False):
        for clave in overrides:
            feature, etiqueta = clave
            propias = crudas.get(feature, [])
            if (etiqueta in propias) is not por_etiqueta_del_motor:
                continue
            for posicion in filas_que_casan(etiqueta, propias, list(legibles.get(feature, []))):
                destino.setdefault((feature, posicion), clave)

    def _override_de(feature: str, posicion: int) -> PointOverrideConfig | None:
        clave = destino.get((feature, posicion))
        if clave is None:
            return None
        casados.add(clave)
        return overrides[clave]

    rows: list[dict[str, object]] = []
    for feature, woe_column in zip(features, woe_columns, strict=True):
        beta = coefficients[feature].beta
        table = tables[feature]
        asignados = set(assigned_bins.get(feature, ()))
        primero_de = _grupos_indistinguibles(
            feature=feature,
            table=table,
            asignados=asignados,
            con_ajuste={posicion for variable, posicion in destino if variable == feature},
            legibles=list(legibles.get(feature, [])),
        )
        filas_de_la_variable: list[dict[str, object]] = []
        por_posicion: dict[int, dict[str, object]] = {}
        for bin_index, row in enumerate(table.to_dict(orient="records")):
            bin_label = str(row["Bin"])
            woe = _finite_float(row["WoE"], label="WoE", error_cls=ScorecardFitError)
            referencia = (
                _reference_row(filas_de_la_variable, woe) if bin_label in asignados else None
            )
            if referencia is not None:
                if _override_de(feature, bin_index) is not None:
                    raise ScorecardFitError(
                        f"El bin «{bin_label}» de «{feature}» comparte los puntos de su tramo de "
                        f"referencia «{referencia['bin_label']}», del que tomó el WoE: el ajuste "
                        "manual de puntos se hace sobre ese tramo."
                    )
                heredada = {
                    **referencia,
                    "bin_label": bin_label,
                    "bin_index": int(bin_index),
                }
                if referencia["source"] == "override":
                    estimator.log_decision(
                        regla="point_override_heredado",
                        umbral=str(referencia["bin_label"]),
                        valor={
                            "feature": feature,
                            "bin_label": bin_label,
                            "puntos_nuevo": referencia["points"],
                        },
                        accion="heredar_override",
                    )
                rows.append(heredada)
                filas_de_la_variable.append(heredada)
                continue
            raw_points = _raw_points(
                direction=estimator.score_direction,
                factor=factor,
                offset_share=offset_share,
                beta=beta,
                woe=woe,
                intercept_share=intercept_share,
            )
            points = _published_points(raw_points, estimator.rounding_method)
            source = "binning_table"
            override = _override_de(feature, bin_index)
            if override is not None:
                previous = points
                points = _normalize_point(override.points)
                source = "override"
                estimator.log_decision(
                    regla="point_override",
                    umbral=override.reason,
                    valor={
                        "feature": feature,
                        "bin_label": bin_label,
                        "puntos_anterior": previous,
                        "puntos_nuevo": points,
                    },
                    accion="aplicar_override",
                )
            primero = primero_de.get(bin_index)
            if primero is not None:
                # D-BPT-1 (revisión del código, pasada 1): la búsqueda no distingue los tramos de
                # un grupo, así que todos publican los puntos del primero —como el bin asignado de
                # D-FAL-1 comparte los de su referencia—. Sin esto, dos tramos a un ulp junto a un
                # borde de redondeo publicaban enteros distintos y la corrida daba a las filas del
                # segundo los del primero, y el bundle los suyos. Ningún ajuste manual llega aquí:
                # se rechazó arriba.
                referencia_del_grupo = por_posicion[primero]
                distancia = abs(raw_points - float(cast(float, referencia_del_grupo["raw_points"])))
                if distancia > _TOLERANCIA_PUNTOS_DEL_GRUPO:
                    raise ScorecardFitError(
                        f"Los tramos «{referencia_del_grupo['bin_label']}» y «{bin_label}» de "
                        f"«{feature}» tienen el mismo WoE (a 1e-12 o menos) pero sus puntos "
                        f"crudos difieren en {distancia:.6g}: el coeficiente de la variable "
                        f"({beta!r}) está fuera de escala para una logística sobre WoE. Revisa el "
                        "modelo antes de construir la tabla de puntos."
                    )
                igualados[(feature, int(bin_index))] = points
                points = cast(float | int, referencia_del_grupo["points"])
            rows.append(
                {
                    "feature": feature,
                    "woe_column": woe_column,
                    "bin_label": bin_label,
                    "bin_index": int(bin_index),
                    "woe": woe,
                    "beta": beta,
                    "intercept_share": intercept_share,
                    "raw_points": raw_points,
                    "points": points,
                    "rounding_delta": _normalize_float(float(points) - raw_points),
                    "source": source,
                }
            )
            filas_de_la_variable.append(rows[-1])
            por_posicion[int(bin_index)] = rows[-1]
    return rows


def _reference_row(rows: list[dict[str, object]], woe: float) -> dict[str, object] | None:
    """La primera fila ya construida con ese WoE: el tramo del que un bin asignado lo tomó."""
    return next((row for row in rows if row["woe"] == woe), None)


def _grupos_indistinguibles(
    *,
    feature: str,
    table: DataFrame,
    asignados: Collection[str],
    con_ajuste: Collection[int],
    legibles: list[str],
) -> dict[int, int]:
    """Los tramos que la búsqueda por WoE no distingue (D-BPT-1): posición → primera de su grupo.

    Un grupo son dos o más tramos de la variable con WoE a 1e-12 o menos entre sí —encadenados, sea
    cual sea su posición—: la corrida casa cada operación con la fila más cercana y no sabe de qué
    tramo vino. Un ajuste manual sobre cualquiera de ellos se rechaza: llegaría en la corrida al
    otro, o a ninguno, y en el bundle —que puntúa por tramo— no. Sin ajuste, cada tramo del grupo
    publica los puntos del primero (el de menor posición). El bin asignado de D-FAL-1 no cuenta:
    comparte por construcción el WoE exacto de su referencia (la misma prueba que
    ``_reference_row``) y hereda sus puntos. Los tramos auxiliares vacíos (WoE 0) sí cuentan.
    """
    miembros: list[tuple[float, int, str]] = []
    anteriores: list[float] = []
    for posicion, row in enumerate(table.to_dict(orient="records")):
        woe = _finite_float(row["WoE"], label="WoE", error_cls=ScorecardFitError)
        etiqueta = str(row["Bin"])
        if not (etiqueta in asignados and woe in anteriores):
            miembros.append((woe, posicion, etiqueta))
        anteriores.append(woe)

    def _rotulo(posicion: int, etiqueta: str) -> str:
        return legibles[posicion] if posicion < len(legibles) and legibles[posicion] else etiqueta

    primero_de: dict[int, int] = {}

    def _revisar(grupo: list[tuple[float, int, str]]) -> None:
        if len(grupo) < 2:
            return
        en_orden = sorted(grupo, key=lambda miembro: miembro[1])
        for _, posicion, _ in en_orden:
            primero_de[posicion] = en_orden[0][1]
        ajustados = [miembro for miembro in grupo if miembro[1] in con_ajuste]
        if not ajustados:
            return
        nombres = ", ".join(f"«{_rotulo(pos, etiqueta)}»" for _, pos, etiqueta in en_orden)
        _, posicion, etiqueta = min(ajustados, key=lambda miembro: miembro[1])
        raise ScorecardFitError(
            f"El ajuste manual de puntos sobre «{_rotulo(posicion, etiqueta)}» de «{feature}» no "
            f"se puede aplicar: los tramos {nombres} tienen el mismo WoE (a 1e-12 o menos) y la "
            "corrida no distingue a qué tramo pertenece cada operación, así que el ajuste no "
            "llegaría igual a la corrida y al bundle. Une esos tramos o quita el ajuste."
        )

    grupo: list[tuple[float, int, str]] = []
    for miembro in sorted(miembros):
        if grupo and miembro[0] - grupo[-1][0] > _TOLERANCIA_WOE:
            _revisar(grupo)
            grupo = []
        grupo.append(miembro)
    _revisar(grupo)
    return {posicion: primera for posicion, primera in primero_de.items() if posicion != primera}


def _rotulos_legibles(
    binning_tables: Mapping[str, DataFrame],
    bin_edges: DataFrame | None,
    *,
    features: tuple[str, ...],
) -> dict[str, list[str]]:
    """El rótulo legible de cada tramo de las variables finales, en el orden de sus filas.

    Desde las tablas **originales**, sin la fila de totales —la misma máscara que las filas de
    puntos—: la copia de trabajo convierte ``Bin`` a texto y una categoría se leería ``['norte']``.
    """
    from bayesrisk.core.tramos import rotulos_por_fila

    salida: dict[str, list[str]] = {}
    for feature in features:
        tabla = binning_tables.get(feature)
        if tabla is None or "Bin" not in tabla.columns:
            continue
        filas = tabla.loc[~_total_row_mask(tabla)]
        salida[feature] = rotulos_por_fila(filas, bin_edges, feature)
    return salida


def _override_map(
    overrides: tuple[PointOverrideConfig, ...],
) -> dict[tuple[str, str], PointOverrideConfig]:
    """Indexa overrides ya validados por config."""
    return {(override.feature, override.bin_label): override for override in overrides}


def _raw_points(
    *,
    direction: ScoreDirection,
    factor: float,
    offset_share: float,
    beta: float,
    woe: float,
    intercept_share: float,
) -> float:
    """Calcula puntos crudos para la dirección de score configurada."""
    component = _normalize_float((beta * woe) + intercept_share)
    if direction == "higher_is_lower_risk":
        value = offset_share - factor * component
    else:
        value = offset_share + factor * component
    if not math.isfinite(value):
        raise ScorecardFitError(f"raw_points no es finito: valor={value!r}.")
    return _normalize_float(value)


def _published_points(raw_points: float, method: RoundingMethod) -> float | int:
    """Aplica el redondeo configurado de forma determinista."""
    if method == "none":
        return _normalize_float(raw_points)
    if method == "nearest_integer":
        return round(raw_points)
    if method == "floor_integer":
        return math.floor(raw_points)
    return math.ceil(raw_points)


def _filas_por_variable(
    scorecard: DataFrame,
) -> dict[str, tuple[tuple[float, dict[str, object]], ...]]:
    """Por variable, sus filas de puntos ``(woe, fila)`` en el orden de la tabla."""
    salida: dict[str, list[tuple[float, dict[str, object]]]] = {}
    for row in scorecard.to_dict(orient="records"):
        fila = {str(campo): valor for campo, valor in row.items()}
        woe = _normalize_float(float(cast(float, fila["woe"])))
        salida.setdefault(str(fila["feature"]), []).append((woe, fila))
    return {feature: tuple(filas) for feature, filas in salida.items()}


def _fila_mas_cercana(
    filas: tuple[tuple[float, dict[str, object]], ...], woe: float
) -> dict[str, object] | None:
    """La fila de puntos de un WoE (D-BPT-1): la más cercana a 1e-12 o menos, o ninguna.

    La exacta siempre gana (distancia 0) y, a igual distancia, la primera en el orden de la tabla
    —la regla que ya resolvía los WoE duplicados—. Es la única búsqueda: la usan la corrida y la
    referencia de las categorías no vistas que congela el bundle.
    """
    mejor: dict[str, object] | None = None
    distancia_mejor = math.inf
    for woe_fila, fila in filas:
        distancia = abs(woe - woe_fila)
        if distancia <= _TOLERANCIA_WOE and distancia < distancia_mejor:
            mejor, distancia_mejor = fila, distancia
    return mejor


def _filas_repetidas(
    scorecard: DataFrame, igualados: Mapping[tuple[str, int], float | int]
) -> list[dict[str, object]]:
    """Las filas de puntos que no son la primera de su WoE, para el evento ``woe_duplicado``.

    Un WoE **exactamente** repetido —también el del bin asignado de D-FAL-1— como siempre, y
    además cada tramo de un grupo indistinguible a 1e-12 que publica los puntos del primero
    (D-BPT-1): ``points_usados`` son los que publica, ``points_descartados`` los suyos por fórmula.
    """
    primeras: dict[tuple[str, float], dict[str, object]] = {}
    duplicate_rows: list[dict[str, object]] = []
    for row in scorecard.to_dict(orient="records"):
        feature = str(row["feature"])
        woe = _normalize_float(float(row["woe"]))
        key = (feature, woe)
        igualado = (feature, int(row["bin_index"])) in igualados
        if key in primeras or igualado:
            usados = primeras[key]["points"] if key in primeras else row["points"]
            duplicate_rows.append(
                {
                    "feature": feature,
                    "woe": woe,
                    "bin_label": str(row["bin_label"]),
                    "points_usados": usados,
                    "points_descartados": cast(
                        float | int,
                        igualados.get((feature, int(row["bin_index"])), row["points"]),
                    ),
                }
            )
            if key in primeras:
                continue
        primeras.setdefault(key, {str(campo): valor for campo, valor in row.items()})
    return duplicate_rows


def filas_de_referencia_no_vista(
    scorecard: DataFrame, referencias: Mapping[str, Any]
) -> dict[str, dict[str, object]]:
    """Por variable de la tabla de puntos, la fila que recibe una categoría no vista (D-NOV-1).

    ``referencias`` es ``unseen_reference_`` del binner: por variable categórica, su tramo de
    referencia con el WoE exacto de la tabla. La fila es la que devuelve para ese WoE la búsqueda
    de :meth:`PointsScaler.transform` (``_fila_mas_cercana``, D-BPT-1: con el WoE exacto, la
    primera con ese WoE), con su ajuste manual y su redondeo: con ella el bundle congela la
    referencia y el resumen y el informe escriben su línea, así que la corrida, el bundle y los
    documentos dan los mismos puntos (§1.1).
    """
    salida: dict[str, dict[str, object]] = {}
    for feature, filas in _filas_por_variable(scorecard).items():
        referencia = referencias.get(feature)
        if referencia is None:
            continue
        fila = _fila_mas_cercana(filas, _normalize_float(float(referencia.woe)))
        if fila is not None:
            salida[feature] = fila
    return salida


def _validate_transform_columns(
    frame: DataFrame,
    *,
    final_woe_columns: tuple[str, ...],
    output_columns: tuple[str, ...],
) -> None:
    """Valida columnas de entrada y evita sobrescrituras de salida."""
    missing = [column for column in final_woe_columns if column not in frame.columns]
    if missing:
        joined = ", ".join(f"'{column}'" for column in missing)
        raise ScorecardTransformError(f"Faltan columnas WoE finales para scorecard: {joined}.")
    collisions = [column for column in output_columns if column in frame.columns]
    if collisions:
        joined = ", ".join(f"'{column}'" for column in collisions)
        raise ScorecardTransformError(
            f"Scorecard.transform no sobrescribe columnas existentes; colisiones: {joined}."
        )


def _finite_woe_array(
    series: Series,
    *,
    feature: str,
    woe_column: str,
    np: Any,
) -> NDArrayFloat:
    """Devuelve valores WoE finitos como float64."""
    values = series.to_numpy(dtype="float64", copy=True)
    finite = np.isfinite(values)
    if not bool(finite.all()):
        observed = series.loc[~finite].iloc[0]
        raise ScorecardTransformError(
            "Scorecard.transform recibió WoE no finita: "
            f"feature='{feature}', columna='{woe_column}', valor observado={observed!r}."
        )
    return cast(NDArrayFloat, np.asarray([_normalize_float(float(value)) for value in values]))


def _points_for_values(
    *,
    estimator: PointsScaler,
    filas: tuple[tuple[float, dict[str, object]], ...],
    values: NDArrayFloat,
    beta: float,
) -> tuple[list[float | int], int]:
    """Mapea WoE a los puntos de su fila (D-BPT-1) o, sin fila a 1e-12, por fórmula directa."""
    points: list[float | int] = []
    unseen_count = 0
    resueltos: dict[float, tuple[float | int, bool]] = {}
    for value in values.tolist():
        woe = _normalize_float(float(value))
        resuelto = resueltos.get(woe)
        if resuelto is None:
            fila = _fila_mas_cercana(filas, woe)
            if fila is not None:
                resuelto = (cast(float | int, fila["points"]), False)
            else:
                raw_points = _raw_points(
                    direction=estimator.score_direction_,
                    factor=estimator.factor_,
                    offset_share=_normalize_float(
                        estimator.offset_ / len(estimator.final_features_)
                    ),
                    beta=beta,
                    woe=woe,
                    intercept_share=estimator.intercept_share_,
                )
                resuelto = (_published_points(raw_points, estimator.rounding_method_), True)
            resueltos[woe] = resuelto
        points.append(resuelto[0])
        unseen_count += int(resuelto[1])
    return points, unseen_count


def _apply_score_limits(estimator: PointsScaler, score: Series, *, pd: Any) -> Series:
    """Aplica o audita límites de score según ``clip``."""
    lower = estimator.min_score
    upper = estimator.max_score
    if lower is None and upper is None:
        return score
    below = score.lt(lower) if lower is not None else pd.Series(False, index=score.index)
    above = score.gt(upper) if upper is not None else pd.Series(False, index=score.index)
    affected = int((below | above).sum())
    if affected == 0:
        return score
    if estimator.clip:
        clipped = score.clip(lower=lower, upper=upper)
        estimator.log_decision(
            regla="score_clip",
            umbral={"min_score": lower, "max_score": upper},
            valor={"filas_afectadas": affected},
            accion="recortar_score",
        )
        return clipped.map(lambda value: _normalize_float(float(value)))
    estimator.log_decision(
        regla="score_fuera_de_rango",
        umbral={"min_score": lower, "max_score": upper},
        valor={
            "filas_afectadas": affected,
            "min_observado": _normalize_float(float(score.min())),
            "max_observado": _normalize_float(float(score.max())),
        },
        accion="publicar_sin_recorte",
    )
    return score


def _normalize_float_frame(frame: DataFrame, *, pd: Any) -> DataFrame:
    """Normaliza ``-0.0`` en columnas float sin alterar enteros publicados."""
    result = frame.copy(deep=True)
    for column in result.columns:
        if pd.api.types.is_float_dtype(result[column]):
            result[column] = result[column].map(lambda value: _normalize_float(float(value)))
    return result


def _dependency_versions(estimator: PointsScaler) -> dict[str, str]:
    """Publica versiones que afectan el scorecard; sklearn sólo si está en el MRO."""
    modules = {
        "numpy": "numpy",
        "pandas": "pandas",
    }
    if _inherits_sklearn_base(estimator):
        modules["scikit-learn"] = "sklearn"

    versions: dict[str, str] = {}
    for public_name, module_name in modules.items():
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise MissingDependencyError(_SCORING_EXTRA_MESSAGE) from exc
        versions[public_name] = str(getattr(module, "__version__", "unknown"))
    return {name: versions[name] for name in sorted(versions)}


def _inherits_sklearn_base(estimator: PointsScaler) -> bool:
    """Detecta herencia sklearn sin importar nuevos módulos."""
    return any(cls.__module__.startswith("sklearn.") for cls in type(estimator).mro())


def _finite_float(
    value: object,
    *,
    label: str,
    error_cls: type[Exception],
) -> float:
    """Convierte un escalar a float finito normalizado."""
    try:
        candidate = float(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise error_cls(f"{label} no es numérico: {value!r}.") from exc
    if not math.isfinite(candidate):
        raise error_cls(f"{label} no es finito: {candidate!r}.")
    return _normalize_float(candidate)


def _normalize_point(value: float | int) -> float | int:
    """Normaliza ``-0.0`` en puntos sin convertir enteros."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return _normalize_float(float(value))


def _normalize_float(value: float) -> float:
    """Normaliza ``-0.0`` a ``0.0`` sin redondear otros valores."""
    if value == 0.0:
        return 0.0
    return value
