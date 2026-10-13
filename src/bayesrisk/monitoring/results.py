"""DTOs del monitoreo (SDD-33 §6.2): el veredicto, la ficha de la etapa y el resultado agregado.

Sólo contenedores; no importa ``pandas`` en runtime (el paquete se importa liviano).

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import pandas as pd

    DataFrameLike: TypeAlias = pd.DataFrame
else:
    DataFrameLike: TypeAlias = Any

__all__ = [
    "MonitoringAlert",
    "MonitoringCardSection",
    "MonitoringResult",
    "MonitoringVerdict",
    "PeriodKind",
    "VerdictCode",
]

#: Los veredictos de §3.5, del que menos al que más pide.
VerdictCode = Literal["no_outcome_yet", "no_action", "watch", "recalibrate", "redevelop"]
#: Cómo se leyó la columna de periodo: fecha agrupada por mes, número o texto (§7 paso 2).
PeriodKind = Literal["date_month", "number", "text"]


class MonitoringVerdict(BaseModel):
    """El veredicto de la corrida: el del último periodo, con su acción y su razón (§3.5).

    Si el último periodo no tiene desenlace, se informa además el del último que sí lo tiene.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: str
    verdict: VerdictCode
    rule: str
    action: str
    reason: str
    partial_evidence: bool
    not_evaluable: tuple[str, ...]
    last_with_outcome_period: str | None = None
    last_with_outcome_verdict: VerdictCode | None = None
    last_with_outcome_reason: str | None = None
    #: Lo que no se pudo evaluar en ese periodo: su evidencia parcial no se pierde porque lo siga
    #: uno sin desenlace (pasada 2 de Codex).
    last_with_outcome_not_evaluable: tuple[str, ...] = ()


class MonitoringAlert(BaseModel):
    """Un indicador en rojo en un periodo: lo que va al trail con ``accion="alertar"`` (§9)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: str
    indicator: str
    value: float | None
    grade: int | None = None
    direction: Literal["under", "over"] | None = None


class MonitoringCardSection(BaseModel):
    """La ficha de la etapa: la referencia usada, las constantes, los conteos y las alertas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle_hash: str
    bundle_schema: int
    n_grades: int
    grade_pd: tuple[float, ...]
    score_edges: tuple[float, ...]
    n_development: int
    auc_initial: float | None
    auc_initial_source: Literal["holdout", "desarrollo"]
    auc_initial_cause: str | None
    period_column: str
    default_column: str | None
    period_kind: PeriodKind
    periods: tuple[str, ...]
    n_rows: int
    n_rows_without_period: int
    n_not_scored: int
    not_scored_reasons: dict[str, int]
    constants: dict[str, float]
    alerts: tuple[MonitoringAlert, ...]
    verdict: MonitoringVerdict
    metric_sections: dict[str, Any] = Field(default_factory=dict)


class MonitoringResult(BaseModel):
    """Los artefactos de la etapa (§6.2) juntos, como los publica el paso."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    periods: DataFrameLike
    grades_by_period: DataFrameLike
    variables_by_period: DataFrameLike
    verdict: MonitoringVerdict
    card: MonitoringCardSection
