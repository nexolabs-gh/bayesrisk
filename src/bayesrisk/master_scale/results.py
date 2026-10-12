"""DTOs de la escala maestra (SDD-32 §6.2): la ficha de la etapa y el resultado agregado.

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
    "GradeSource",
    "MasterScaleCardSection",
    "MasterScaleResult",
    "SampleDiagnostics",
]

#: De dónde salieron los cortes: los formaron los datos (D-ESC-1) o los fijó la institución.
GradeSource = Literal["formed", "institution"]


class SampleDiagnostics(BaseModel):
    """Lo que la escala dice de una muestra: monotonía, concentración y semáforos (D-ESC-3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    monotonic: bool
    inversions: tuple[tuple[int, int], ...]
    hhi: float | None
    max_share: float | None
    max_share_grade: int | None
    red_grades: tuple[int, ...]
    amber_grades: tuple[int, ...]
    not_evaluable_grades: tuple[int, ...]


class MasterScaleCardSection(BaseModel):
    """La sección de la ficha de la etapa: la escala, su PD y su lectura por muestra."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_grades: int
    source: GradeSource
    cuts: tuple[float, ...]
    score_direction: Literal["higher_is_lower_risk", "higher_is_higher_risk"]
    integer_card: bool
    solver_status: str | None
    formation_cause: str | None
    pd: tuple[float, ...]
    anchor: float
    anchor_source: str
    delta: float
    equalized_grades: tuple[tuple[int, ...], ...]
    neighbours_not_distinct: tuple[tuple[int, int, float | None], ...]
    approval_cutoff: float | None
    cutoff_out_of_range: bool
    samples: tuple[str, ...]
    diagnostics: dict[str, SampleDiagnostics]
    metric_sections: dict[str, Any] = Field(default_factory=dict)


class MasterScaleResult(BaseModel):
    """Los artefactos de la etapa (§6.2) juntos, como los publica el paso."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    grades: DataFrameLike
    grade_table: DataFrameLike
    cutoff_table: DataFrameLike
    assignment: DataFrameLike
    card: MasterScaleCardSection
