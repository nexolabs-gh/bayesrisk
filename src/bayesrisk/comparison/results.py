"""DTOs de la comparación (SDD-34 §6.2): la ficha de la etapa y el resultado agregado.

Sólo contenedores; no importa ``pandas`` en runtime (el paquete se importa liviano).

**Estable (SemVer 2.x).** Desde la 2.16.0 (capa B del SDD-34).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import pandas as pd

    DataFrameLike: TypeAlias = pd.DataFrame
else:
    DataFrameLike: TypeAlias = Any

__all__ = ["ComparisonCardSection", "ComparisonResult"]


class ComparisonCardSection(BaseModel):
    """La ficha de la etapa: qué se comparó, cómo, la frontera, la elección y las constantes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    family: Literal["scorecard", "ifrs9"]
    names: tuple[str, ...]
    summary_hashes: tuple[str, ...]
    #: El nivel de comparabilidad de cada corrida contra la referencia (§3.3); la primera es
    #: ``"referencia"``.
    levels: tuple[str, ...]
    #: ``{nombre: nombre del primer modelo idéntico}`` (§3.3): misma huella computacional, o en
    #: IFRS 9 el mismo ECL por etapa.
    same_as: dict[str, str]
    frontier_stability: tuple[str, ...]
    frontier_concentration: tuple[str, ...]
    n_tests: int
    n_paired_tests: int
    chosen: str | None
    chosen_reason: str | None
    #: Las constantes de §5.2 con que se decidió: el corte de la prueba y la receta del PSI común.
    constants: dict[str, Any]
    #: §3.5: N(N-1)/2 pruebas sin corrección por multiplicidad, declarado.
    multiplicity_correction: bool = False
    reading: tuple[str, ...]
    metric_sections: dict[str, Any] = Field(default_factory=dict)


class ComparisonResult(BaseModel):
    """Los artefactos de la etapa (§6.2) juntos, como los publica el paso."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    runs: DataFrameLike
    models: DataFrameLike
    tests: DataFrameLike
    samples: DataFrameLike
    variables: DataFrameLike
    provision: DataFrameLike
    reading: tuple[str, ...]
    card: ComparisonCardSection
