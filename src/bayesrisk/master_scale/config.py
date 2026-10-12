"""Config declarativo de la capa ``master_scale`` (SDD-32 §5).

:class:`MasterScaleConfig` es la sección ``master_scale`` de
:class:`~bayesrisk.core.config.BayesRiskConfig`. Tiene **dos hojas y ninguna perilla de método**:
las dos son decisiones de la institución que no tienen default defendible (§13) —sus cortes de
tramo (``set_grades``) y su puntaje de aprobación (``set_cutoff``)—. Las reglas de formación, la de
la PD del tramo, el contraste y las columnas de la tabla de cortes son constantes del motor
(§5.2). La sección es computacional: declarada, entra al ``config_hash``; ausente, no se serializa
(D-ESC-7).

**Experimental (fuera de la garantía SemVer 2.x).**
La etapa sale por la puerta guiada y la completa en la 2.11.0 y deja de serlo cuando la pantalla
cierre sus tres puertas (D-SIM-1, capa B).
"""

from __future__ import annotations

import math
from typing import Self

from pydantic import Field, field_validator, model_validator

from bayesrisk.core.config import BayesRiskBaseConfig
from bayesrisk.core.exceptions import ConfigError

__all__ = ["MasterScaleConfig"]

#: Prefijo del ``loc`` de los errores de esta sección (D-EXI-5): la ruta absoluta desde la raíz.
_LOC_SECCION: tuple[str, ...] = ("master_scale",)


class MasterScaleConfig(BayesRiskBaseConfig):
    """Los tramos de riesgo del puntaje, su PD y el punto de corte de la institución."""

    # SDD-32 D-ESC-1…5. El docstring de la clase es la descripción del schema: copy público.

    grade_edges: tuple[float, ...] | None = Field(
        default=None,
        title="Cortes de los tramos",
        description=(
            "Los cortes en puntos con que la institución fija sus tramos. Vacío, los tramos los "
            "forman los datos: al menos el 5 % de Desarrollo cada uno, con tasas de malos "
            "distintas de las de sus vecinos, ordenados y hasta diez."
        ),
    )
    approval_cutoff: float | None = Field(
        default=None,
        title="Puntaje de aprobación",
        description=(
            "El puntaje desde el que la institución aprueba: se aprueba el lado de menor riesgo "
            "del corte. Vacío, no hay decisión y la tabla de cortes muestra todos los posibles."
        ),
    )

    @field_validator("grade_edges", mode="before")
    @classmethod
    def _ordena_los_cortes(cls, valor: object) -> object:
        """Los cortes llegan en cualquier orden y se guardan ordenados (§4.2)."""
        if valor is None or isinstance(valor, str | bytes):
            return valor
        try:
            numeros = [float(v) for v in valor]  # type: ignore[attr-defined]
        except (TypeError, ValueError):
            return valor
        return tuple(sorted(numeros))

    @model_validator(mode="after")
    def _check_cortes(self) -> Self:
        """Al menos un corte, finitos y distintos; el puntaje de aprobación, finito (§5.1)."""
        if self.grade_edges is not None:
            if not self.grade_edges:
                raise ConfigError(
                    "grade_edges necesita al menos un corte: con ninguno la escala sería un solo "
                    "tramo. Déjalo vacío para que los tramos los formen los datos.",
                    loc=(*_LOC_SECCION, "grade_edges"),
                )
            if not all(math.isfinite(c) for c in self.grade_edges):
                raise ConfigError(
                    "grade_edges sólo admite números finitos.",
                    loc=(*_LOC_SECCION, "grade_edges"),
                )
            if len(set(self.grade_edges)) != len(self.grade_edges):
                raise ConfigError(
                    f"grade_edges repite un corte: {list(self.grade_edges)}.",
                    loc=(*_LOC_SECCION, "grade_edges"),
                )
        if self.approval_cutoff is not None and not math.isfinite(self.approval_cutoff):
            raise ConfigError(
                "approval_cutoff debe ser un número finito.",
                loc=(*_LOC_SECCION, "approval_cutoff"),
            )
        return self
