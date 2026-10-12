"""Config declarativo de la capa ``master_scale`` (SDD-32 §5).

:class:`MasterScaleConfig` es la sección ``master_scale`` de
:class:`~bayesrisk.core.config.BayesRiskConfig`. Tiene **dos hojas y ninguna perilla de método**:
las dos son decisiones de la institución que no tienen default defendible (§13) —sus cortes de
tramo (``set_grades``) y su puntaje de aprobación (``set_cutoff``)—. Las reglas de formación, la de
la PD del tramo, el contraste y las columnas de la tabla de cortes son constantes del motor
(§5.2). La sección es computacional: declarada, entra al ``config_hash``; ausente, no se serializa
(D-ESC-7).

**Estable (SemVer 2.x).**
Salió en la 2.11.0 como adelanto experimental por la puerta guiada y la completa, y es estable
desde que la pantalla cerró sus tres puertas (D-SIM-1, capa B del SDD-32, 2.12.0).
"""

from __future__ import annotations

import math
from typing import Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from bayesrisk.core.config import BayesRiskBaseConfig, declara_esenciales
from bayesrisk.core.exceptions import ConfigError

__all__ = ["MasterScaleConfig"]

#: Prefijo del ``loc`` de los errores de esta sección (D-EXI-5): la ruta absoluta desde la raíz.
_LOC_SECCION: tuple[str, ...] = ("master_scale",)


class MasterScaleConfig(BayesRiskBaseConfig):
    """Los tramos de riesgo del puntaje, su PD y el punto de corte de la institución."""

    # SDD-32 D-ESC-1…5. El docstring de la clase es la descripción del schema: copy público.
    # Las dos hojas son esenciales (§13): son las dos decisiones de la institución y la sección no
    # tiene «Avanzado».
    model_config = ConfigDict(json_schema_extra=declara_esenciales)

    grade_edges: tuple[float, ...] | None = Field(
        default=None,
        title="Cortes de los tramos",
        description=(
            "Los cortes en puntos con que la institución fija sus tramos. Vacío, los tramos los "
            "forman los datos: al menos el 5 % de Desarrollo cada uno, con tasas de malos "
            "distintas de las de sus vecinos, ordenados y hasta diez."
        ),
        json_schema_extra={
            "ui_essential": True,
            "ui_widget": "number_list",
            "ui_group": "Decisiones de la institución",
            "ui_order": 1,
            "ui_help": "Los límites entre tramos que la institución ya usa, en puntos (por "
            "ejemplo 563, 541, 520 y 498). Cada valor cierra un tramo y abre el siguiente; el "
            "tramo 1 es el de menor riesgo. En blanco, los tramos los forman los datos.",
        },
    )
    approval_cutoff: float | None = Field(
        default=None,
        title="Puntaje de aprobación",
        description=(
            "El puntaje desde el que la institución aprueba: el lado de menor riesgo del corte. "
            "Vacío, la tabla de cortes muestra todos los posibles."
        ),
        json_schema_extra={
            "ui_essential": True,
            "ui_widget": "number_input",
            "ui_group": "Decisiones de la institución",
            "ui_order": 2,
            "ui_help": "El corte de aprobación es apetito de riesgo: ningún valor de fábrica es "
            "defendible. Se aprueba el lado de menor riesgo del corte y no tiene que ser un límite "
            "de tramo. Vacío, no hay decisión: la tabla de puntos de corte muestra, para cada "
            "límite, cuánto se aprueba, la tasa de malos, los malos evitados y los buenos "
            "rechazados.",
        },
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
