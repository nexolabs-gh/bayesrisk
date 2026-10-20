"""Lectura contextual aditiva de HL (D-HLC-1…8), sin recalcular el contraste histórico."""

from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bayesrisk.core.markers import MISSING_DATA_MARKER
from bayesrisk.validation.config import CalibrationValidationConfig, ValidationFamily
from bayesrisk.validation.exceptions import ValidationDataError
from bayesrisk.validation.results import (
    VALIDATION_FAMILY_LABELS,
    VALIDATION_STATUS_LABELS,
    CalibrationDecision,
    HlNotEvaluableReason,
    OverallStatus,
    ValidationResult,
    derive_overall_status,
    derive_test_counts,
)

if TYPE_CHECKING:
    import pandas as pd

    from bayesrisk.calibration.results import CalibrationCardSection, CalibrationParameters

POLICY_ID: Literal["hl_context_v1"] = "hl_context_v1"
HL_CONTEXT_WARNING = f"{MISSING_DATA_MARKER}-VAL-HL-CONTEXTO"
HL_STRUCTURAL_WARNINGS = frozenset({HL_CONTEXT_WARNING})
HL_CONTEXT_LABELS: dict[str, str] = {
    "same_calibration_sample": "Misma muestra que declara el ajuste de calibración",
    "other_calibration_sample": (
        "Muestra distinta de la declarada para calibrar; independencia y ausencia de "
        "reutilización no certificadas"
    ),
    "unknown": "Procedencia de ajuste no acreditada",
}
OE_RATIO_REASON_LABELS: dict[str, str] = {
    "non_representable_ratio": "No representable: razón observado/esperado demasiado grande",
    "zero_expected": "No definido: cero incumplimientos esperados",
}
CONTEXT_GAP_TEXT = (
    "La librería aún no dispone de un contraste de calibración validado para este contexto"
)
HISTORICAL_READING_TEXT = "Lectura histórica; contexto no disponible"
UNSUPPORTED_POLICY_TEXT = "Política de interpretación no soportada; se muestra la lectura histórica"
COMPARISON_HISTORICAL_TEXT = "El resumen guardado no permite aplicar la lectura contextual de HL"
CALIBRATION_COVERAGE_TEXT = (
    "La evaluación se limita a las familias ejecutadas; no certifica la calibración global "
    "ni la aprobación institucional del modelo"
)


class CalibrationTieGroup(BaseModel):
    """Grupo descriptivo de PD completas: sin p, gl, contribución ni decisión."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    partition: str
    group: int = Field(ge=1)
    pd_min: float = Field(gt=0, lt=1)
    pd_max: float = Field(gt=0, lt=1)
    n: int = Field(ge=1)
    observed_defaults: int = Field(ge=0)
    expected_defaults: float = Field(ge=0)
    observed_dr: float = Field(ge=0, le=1)
    mean_pd: float = Field(gt=0, lt=1)
    gap_pp: float
    oe_ratio: float | None = Field(ge=0)
    oe_ratio_reason: Literal["non_representable_ratio", "zero_expected"] | None
    expected_non_defaults: float = Field(ge=0)
    below_legacy_min_rows: bool

    @model_validator(mode="after")
    def _conserva_conteos(self) -> Self:
        """Las celdas describen el mismo grupo, incluso tras una carga persistida."""
        if self.pd_min > self.pd_max or self.observed_defaults > self.n:
            raise ValueError("Límites o eventos incoherentes en el grupo descriptivo.")
        expected = (
            (self.observed_dr, self.observed_defaults / self.n),
            (self.mean_pd, self.expected_defaults / self.n),
            (self.gap_pp, 100 * (self.observed_dr - self.mean_pd)),
            (self.expected_non_defaults, self.n - self.expected_defaults),
        )
        if any(not math.isclose(a, b, rel_tol=1e-14, abs_tol=0) for a, b in expected):
            raise ValueError("Las tasas y conteos del grupo descriptivo no concuerdan.")
        ratio = self.observed_defaults / self.expected_defaults if self.expected_defaults else None
        reason = (
            "zero_expected"
            if ratio is None
            else "non_representable_ratio"
            if not math.isfinite(ratio)
            else None
        )
        if (
            self.oe_ratio_reason != reason
            or (reason is None and self.oe_ratio != ratio)
            or (reason is not None and self.oe_ratio is not None)
        ):
            raise ValueError("La razón O/E no concuerda con sus conteos y causa.")
        return self


class HlInterpretation(BaseModel):
    """Procedencia declarada de calibración y copia del resultado convencional."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    partition: str
    context: Literal["same_calibration_sample", "other_calibration_sample", "unknown"]
    context_source: Literal["artifact_metadata", "none"]
    context_scope: Literal["calibration_only"] = "calibration_only"
    full_pipeline_independence_verified: Literal[False] = False
    context_reason: str | None
    legacy_statistic: float | None
    legacy_p_value: float | None
    legacy_alpha: float | None
    legacy_decision: CalibrationDecision
    legacy_not_evaluable_reason: HlNotEvaluableReason | None
    n: int = Field(ge=1)
    requested_groups: int = Field(ge=5, le=20)
    k_groups: int = Field(ge=1)
    legacy_boundary_splits_tie: bool
    diagnostic_status: Literal["available"] = "available"
    formal_inference: Literal["not_established"] = "not_established"

    @model_validator(mode="after")
    def _contexto_parcial(self) -> Self:
        if self.k_groups > min(self.n, self.requested_groups):
            raise ValueError("K excede el número de filas o grupos solicitados.")
        if self.context == "unknown":
            if self.context_source != "none" or not self.context_reason:
                raise ValueError("Contexto desconocido exige ausencia de fuente y una causa.")
        elif self.context_source != "artifact_metadata" or self.context_reason is not None:
            raise ValueError("Contexto declarado exige metadatos coherentes sin causa de ausencia.")
        return self


class ValidationInterpretation(BaseModel):
    """Política versionada, separada del DTO histórico; tablas inmutables serializables.

    ``calibration_tie_groups`` conserva las filas tipadas para persistencia y API standalone.
    El Step proyecta esas mismas filas a la clave tabular homónima; no vuelve a agrupar.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    schema_version: Literal[1] = 1
    policy_id: Literal["hl_context_v1"] = POLICY_ID
    overall_status: OverallStatus
    n_tests: int = Field(ge=0)
    n_failed: int = Field(ge=0)
    legacy_status: OverallStatus
    legacy_n_tests: int = Field(ge=0)
    legacy_n_failed: int = Field(ge=0)
    families_run: tuple[ValidationFamily, ...]
    hl: tuple[HlInterpretation, ...]
    coverage_gap: bool
    warning_codes: tuple[str, ...]
    calibration_tie_groups: tuple[CalibrationTieGroup, ...]

    @model_validator(mode="after")
    def _reconcilia_grupos(self) -> Self:
        if self.n_failed > self.n_tests or self.legacy_n_failed > self.legacy_n_tests:
            raise ValueError("Los rechazos no pueden superar las pruebas evaluables.")
        if self.warning_codes != ((HL_CONTEXT_WARNING,) if self.coverage_gap else ()):
            raise ValueError("La cobertura y la deuda estructural deben concordar.")
        if self.coverage_gap and self.overall_status == "pass":
            raise ValueError("La ausencia de contraste contextual no puede publicarse como Pasa.")
        parts = [entry.partition for entry in self.hl]
        if len(parts) != len(set(parts)):
            raise ValueError("Partición HL duplicada.")
        if self.hl and not self.coverage_gap:
            raise ValueError("Los registros HL requieren la ausencia inferencial declarada.")
        if set(g.partition for g in self.calibration_tie_groups) != set(parts):
            raise ValueError("Los grupos descriptivos no corresponden a las entradas HL.")
        for entry in self.hl:
            groups = [g for g in self.calibration_tie_groups if g.partition == entry.partition]
            if (
                len(groups) != entry.k_groups
                or sum(g.n for g in groups) != entry.n
                or [g.group for g in groups] != list(range(1, entry.k_groups + 1))
                or any(a.pd_max >= b.pd_min for a, b in pairwise(groups))
            ):
                raise ValueError("Los grupos pierden filas, orden o dividen PD iguales.")
        return self

    def groups_frame(self) -> pd.DataFrame:
        """Copia tabular defensiva de las filas; nulos reales, nunca inf/NaN en O/E."""
        import pandas as pd

        rows = [row.model_dump() for row in self.calibration_tie_groups]
        frame = pd.DataFrame(rows, columns=list(CalibrationTieGroup.model_fields))
        for column in ("oe_ratio", "oe_ratio_reason"):
            frame[column] = pd.Series([row[column] for row in rows], dtype=object)
        return frame


def interpret_validation(
    result: ValidationResult,
    *,
    calibrated_pd: pd.DataFrame | None,
    calibration_config: CalibrationValidationConfig,
    calibration_parameters: CalibrationParameters | Mapping[str, Any] | None = None,
    calibration_card: CalibrationCardSection | Mapping[str, Any] | None = None,
) -> ValidationInterpretation:
    """Interpreta un resultado y sus pares analíticos originales sin ejecutar HL otra vez.

    La concordancia de agregados y configuración se comprueba; los agregados históricos no
    prueban por sí solos la identidad fila a fila. El llamante standalone debe proporcionar
    los pares originales. El Step usa exactamente su frame analítico recién evaluado.
    Metadatos ausentes o discordantes dejan contexto desconocido; datos contradictorios fallan.
    """
    # Revalidar también objetos construidos con model_copy/update (no valida por sí mismo).
    try:
        result = ValidationResult.model_validate(result.model_dump())
        calibration_config = CalibrationValidationConfig.model_validate(
            calibration_config.model_dump()
        )
    except ValueError as exc:
        raise ValidationDataError(
            f"Resultado/configuración de validación incoherente: {exc}"
        ) from exc
    cfg = calibration_config
    records = tuple(r for r in result.calibration_records if r.test == "hosmer_lemeshow")
    active = "calibration" in result.card.families_run
    gap = active and cfg.hosmer_lemeshow
    if records and not gap:
        raise ValidationDataError("Hay resultados HL pero la configuración no lo solicita.")
    if active:
        minimum = result.card.metric_sections.get("validation", {}).get("min_rows_per_group")
        if minimum != cfg.min_rows_per_group:
            raise ValidationDataError("El mínimo configurado contradice el resultado histórico.")
    rows: list[CalibrationTieGroup] = []
    entries: list[HlInterpretation] = []
    if records:
        from bayesrisk.validation.evaluator import _validate_calibration_frame

        if calibrated_pd is None:
            raise ValidationDataError(
                "La interpretación HL requiere sus pares analíticos originales."
            )
        frame = _validate_calibration_frame(
            calibrated_pd.copy(deep=True),
            partition_column=cfg.partition_column,
            target_column=cfg.target_column,
            pd_column=cfg.pd_column,
        )
        parts = frame[cfg.partition_column]
        if not all(isinstance(p, str) and p.strip() for p in parts):
            raise ValidationDataError("Las particiones analíticas deben ser nombres no vacíos.")
        by_partition = {r.partition: r for r in records}
        if len(by_partition) != len(records) or set(parts) != set(by_partition):
            raise ValidationDataError(
                "Las particiones del frame no concuerdan con los registros HL."
            )
        fit, reason = _calibration_provenance(frame, cfg, calibration_parameters, calibration_card)
        order = {"desarrollo": 0, "holdout": 1, "oot": 2}
        for partition in sorted(by_partition, key=lambda p: (order.get(p, 3), p)):
            record = by_partition[partition]
            subset = frame.loc[parts == partition]
            _check_partition(result, subset, cfg, record)
            groups, splits = _tie_groups(subset, partition, cfg)
            rows.extend(groups)
            context: Literal["unknown", "same_calibration_sample", "other_calibration_sample"] = (
                "unknown"
                if fit is None
                else "same_calibration_sample"
                if partition == fit
                else "other_calibration_sample"
            )
            entries.append(
                HlInterpretation(
                    partition=partition,
                    context=context,
                    context_source="none" if fit is None else "artifact_metadata",
                    context_reason=reason,
                    legacy_statistic=record.statistic,
                    legacy_p_value=record.p_value,
                    legacy_alpha=record.alpha,
                    legacy_decision=record.decision,
                    legacy_not_evaluable_reason=record.not_evaluable_reason,
                    n=len(subset),
                    requested_groups=cfg.hl_n_groups,
                    k_groups=len(groups),
                    legacy_boundary_splits_tie=splits,
                )
            )
    elif gap and calibrated_pd is not None and len(calibrated_pd):
        raise ValidationDataError(
            "HL solicitado con pares presentes pero sin registros históricos."
        )
    counts = derive_test_counts(
        calibration_records=(),
        grade_records=result.grade_records,
        backtest_records=result.backtest_records,
    )
    status = derive_overall_status(
        calibration_records=(),
        grade_records=result.grade_records,
        backtest_records=result.backtest_records,
        stability_frame=result.stability,
    )
    if status == "pass" and gap:
        status = "warn"
    return ValidationInterpretation(
        overall_status=status,
        n_tests=counts[0],
        n_failed=counts[1],
        legacy_status=result.card.overall_status,
        legacy_n_tests=result.card.n_tests,
        legacy_n_failed=result.card.n_failed,
        families_run=cast(tuple[ValidationFamily, ...], result.card.families_run),
        hl=tuple(entries),
        coverage_gap=gap,
        warning_codes=(HL_CONTEXT_WARNING,) if gap else (),
        calibration_tie_groups=tuple(rows),
    )


def _calibration_provenance(
    frame: pd.DataFrame,
    cfg: CalibrationValidationConfig,
    parameters: Any,
    card: Any,
) -> tuple[str | None, str | None]:
    from bayesrisk.calibration.results import CalibrationCardSection, CalibrationParameters

    if parameters is None or card is None:
        return None, "Faltan parámetros o ficha del ajuste de calibración."
    try:
        p = CalibrationParameters.model_validate(
            parameters.model_dump() if isinstance(parameters, CalibrationParameters) else parameters
        )
        c = CalibrationCardSection.model_validate(
            card.model_dump() if isinstance(card, CalibrationCardSection) else card
        )
    except (ValueError, TypeError):
        return None, "Los metadatos de calibración no tienen un formato válido."
    if (p.method, p.fit_partition, p.n_fit) != (c.method, c.fit_partition, c.n_fit):
        return None, "Parámetros y ficha discrepan sobre el ajuste de calibración."
    n = int((frame[cfg.partition_column] == p.fit_partition).sum())
    if n == 0 or n != p.n_fit:
        return None, "La muestra declarada de calibración no concuerda con los pares analíticos."
    return p.fit_partition, None


def _check_partition(
    result: ValidationResult, frame: pd.DataFrame, cfg: CalibrationValidationConfig, record: Any
) -> None:
    import numpy as np

    if record.n_groups != cfg.hl_n_groups:
        raise ValidationDataError("G configurado contradice el registro HL.")
    # En el histórico, alpha sólo se resella cuando hay un veredicto.
    if record.decision != "not_evaluable" and record.alpha != cfg.alpha:
        raise ValidationDataError("Alfa configurado contradice el registro HL.")
    historic = result.calibration
    historic = historic.loc[
        (historic["test"] == "hosmer_lemeshow") & (historic["partition"] == record.partition)
    ]
    if len(historic) != 1:
        raise ValidationDataError("Se requiere exactamente una fila histórica por partición HL.")
    row = historic.iloc[0]
    y = np.asarray(frame[cfg.target_column], dtype=np.float64)
    p = np.asarray(frame[cfg.pd_column], dtype=np.float64)
    if (
        int(row["n"]) != len(frame)
        or int(row["observed_defaults"]) != int(y.sum())
        or not math.isclose(float(row["expected_pd"]), float(p.mean()), rel_tol=1e-14, abs_tol=0)
        or float(row["observed_dr"]) != float(y.sum() / len(frame))
    ):
        raise ValidationDataError("Los pares analíticos contradicen los agregados históricos HL.")


def _tie_groups(
    frame: pd.DataFrame, partition: str, cfg: CalibrationValidationConfig
) -> tuple[list[CalibrationTieGroup], bool]:
    import numpy as np

    p = np.asarray(frame[cfg.pd_column], dtype=np.float64)
    y = np.asarray(frame[cfg.target_column], dtype=np.float64)
    order = np.argsort(p, kind="stable")
    p, y = p[order], y[order]
    n = len(p)
    q, r = divmod(n, cfg.hl_n_groups)
    nominal = [j * q + min(j, r) for j in range(1, cfg.hl_n_groups)]
    interior = [b for b in nominal if 0 < b < n]
    splits = any(p[b - 1] == p[b] for b in interior)
    ends = sorted({int(np.searchsorted(p, p[b - 1], side="right")) for b in interior} - {n})
    rows: list[CalibrationTieGroup] = []
    start = 0
    for group, end in enumerate([*ends, n], start=1):
        size = end - start
        expected = math.fsum(float(v) for v in p[start:end])
        observed = int(y[start:end].sum())
        ratio = observed / expected if expected > 0 else None
        reason: Literal["zero_expected", "non_representable_ratio"] | None = (
            "zero_expected" if expected == 0 else None
        )
        if ratio is not None and not math.isfinite(ratio):
            ratio, reason = None, "non_representable_ratio"
        rows.append(
            CalibrationTieGroup(
                partition=partition,
                group=group,
                pd_min=float(p[start]),
                pd_max=float(p[end - 1]),
                n=size,
                observed_defaults=observed,
                expected_defaults=expected,
                observed_dr=observed / size,
                mean_pd=expected / size,
                gap_pp=100 * (observed / size - expected / size),
                oe_ratio=ratio,
                oe_ratio_reason=reason,
                expected_non_defaults=size - expected,
                below_legacy_min_rows=size < cfg.min_rows_per_group,
            )
        )
        start = end
    return rows, splits


def read_interpretation(value: Any) -> ValidationInterpretation | None:
    """Lee DTO o mapping persistido conocido. Nunca acepta una política futura por defecto."""
    if value is None:
        return None
    if isinstance(value, ValidationInterpretation):
        value = value.model_dump()
    if isinstance(value, Mapping) and value.get("policy_id") != POLICY_ID:
        return None
    return ValidationInterpretation.model_validate(value)


def interpretation_lines(value: ValidationInterpretation) -> tuple[str, ...]:
    """Una sola explicación para guiada, pantalla e informe; no deriva decisiones."""
    status = VALIDATION_STATUS_LABELS[value.overall_status]
    if value.coverage_gap and value.overall_status == "not_evaluable":
        status += ": falta un contraste de calibración validado"
    elif value.coverage_gap and value.overall_status == "warn":
        status += ": calibración pendiente"
    return (
        f"Evaluación contextual: {status}.",
        f"{value.n_tests} pruebas evaluables sin HL; {value.n_failed} rechazos. "
        "Familias ejecutadas: "
        + ", ".join(VALIDATION_FAMILY_LABELS[f] for f in value.families_run)
        + ".",
        CALIBRATION_COVERAGE_TEXT + ".",
        *((CONTEXT_GAP_TEXT + ".",) if value.coverage_gap else ()),
    )


def interpretation_details(value: ValidationInterpretation) -> tuple[str, ...]:
    """Procedencia parcial y empates en palabras; una línea por muestra."""
    from bayesrisk.report.prose import _PARTITION_LABELS

    return tuple(
        f"{_PARTITION_LABELS.get(h.partition, h.partition)}: {HL_CONTEXT_LABELS[h.context]}. "
        + (
            f"{h.context_reason} "
            if h.context_reason
            else "Fuente: parámetros y ficha del ajuste de calibración; "
            "no acredita independencia del pipeline completo. "
        )
        + f"{h.n} observaciones; {h.k_groups} grupos descriptivos "
        f"de {h.requested_groups} solicitados."
        + (
            " El agrupamiento convencional separa PD iguales y puede depender de su orden; "
            "no se ha medido un cambio de veredicto en esta muestra."
            if h.legacy_boundary_splits_tie
            else ""
        )
        for h in value.hl
    )


def diagnostic_tables(value: ValidationInterpretation) -> dict[str, pd.DataFrame]:
    """Tablas editoriales completas compartidas por resumen, informe y Excel."""
    import pandas as pd

    tables = {}
    for entry in value.hl:
        rows = [
            {
                "Grupo": g.group,
                "PD mínima": g.pd_min,
                "PD máxima": g.pd_max,
                "Observaciones": g.n,
                "Malos observados": g.observed_defaults,
                "Malos esperados": g.expected_defaults,
                "Tasa observada (%)": 100 * g.observed_dr,
                "PD media (%)": 100 * g.mean_pd,
                "Diferencia (pp)": g.gap_pp,
                "O/E": g.oe_ratio,
                "Ausencia de O/E": OE_RATIO_REASON_LABELS.get(g.oe_ratio_reason or "", ""),
                "No incumplimientos esperados": g.expected_non_defaults,
                "Bajo mínimo histórico": "Sí" if g.below_legacy_min_rows else "No",
            }
            for g in value.calibration_tie_groups
            if g.partition == entry.partition
        ]
        frame = pd.DataFrame(rows)
        frame["O/E"] = pd.Series([r["O/E"] for r in rows], dtype=object)
        tables[entry.partition] = frame
    return tables


def study_interpretation(study: Any) -> tuple[Any, ValidationInterpretation | None]:
    """Lee la clave aditiva y exige concordancia con la card y la tabla de origen."""
    if not study.artifacts.has("validation", "interpretation"):
        return None, None
    raw = study.artifacts.get("validation", "interpretation")
    value = read_interpretation(raw)
    if value is not None:
        card = study.artifacts.get("validation", "card")
        card = card if isinstance(card, Mapping) else card.model_dump()
        if (
            value.legacy_status != card["overall_status"]
            or value.legacy_n_tests != card["n_tests"]
            or value.legacy_n_failed != card["n_failed"]
            or value.families_run != tuple(card["families_run"])
        ):
            raise ValidationDataError("La interpretación no concuerda con su card histórica.")
        if study.artifacts.has("validation", "calibration_tie_groups"):
            import pandas as pd

            try:
                pd.testing.assert_frame_equal(
                    value.groups_frame(),
                    study.artifacts.get("validation", "calibration_tie_groups"),
                    check_exact=True,
                )
            except AssertionError as exc:
                raise ValidationDataError(
                    "Los grupos publicados contradicen la interpretación."
                ) from exc
    return raw, value
