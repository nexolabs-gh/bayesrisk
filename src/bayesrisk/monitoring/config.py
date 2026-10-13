"""Config declarativo de la capa ``monitoring`` (SDD-33 §5).

:class:`MonitoringConfig` es la sección ``monitoring`` de
:class:`~bayesrisk.core.config.BayesRiskConfig`. Tiene **tres hojas y ninguna perilla de método**:
las tres son entradas de la institución —la tarjeta que monitorea, la columna de periodo y la de
desenlace— (§13). Las bandas del PSI, los cortes del semáforo, los deciles, el suavizado, los
mínimos y la tabla de decisión son constantes del motor (§5.2, D-MNT-6). La sección nació después
de la 2.10.0: ausente, no se serializa (D-ESC-7); declarada, entra al ``config_hash`` sin la ruta
de la tarjeta, que identifica su ``bundle_hash`` en el lineage (§5.3).

**Experimental (fuera de la garantía SemVer 2.x).**
Sale en la 2.13.0 por la puerta guiada y la completa (capa A del SDD-33); se declara estable
cuando la pantalla, el informe y el Excel cierren sus tres puertas (capa B, D-MNT-8).
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from bayesrisk.core.config import BayesRiskBaseConfig
from bayesrisk.core.exceptions import ConfigError

__all__ = ["MonitoringConfig"]

#: Prefijo del ``loc`` de los errores de esta sección (D-EXI-5): la ruta absoluta desde la raíz.
_LOC_SECCION: tuple[str, ...] = ("monitoring",)


class MonitoringConfig(BayesRiskBaseConfig):
    """Monitorea una tarjeta en uso: población, orden y PD de sus tramos, periodo a periodo."""

    # SDD-33 D-MNT-1. El docstring de la clase es la descripción del schema: copy público.
    bundle: str = Field(
        ...,
        title="Tarjeta",
        description=(
            "La carpeta de la tarjeta guardada que se monitorea, con su escala maestra y la "
            "referencia de Desarrollo que congela al guardarse."
        ),
    )
    period: str = Field(
        ...,
        title="Columna de periodo",
        description=(
            "La columna que dice a qué periodo pertenece cada operación: texto, número o fecha "
            "(una fecha se agrupa por mes)."
        ),
    )
    default: str | None = Field(
        default=None,
        title="Columna de desenlace",
        description=(
            "La marca de incumplimiento de cada operación: 1 malo, 0 bueno y vacío si todavía no "
            "madura. Sin ella sólo se mide la población."
        ),
    )

    @model_validator(mode="after")
    def _check_columnas(self) -> Self:
        """Las tres entradas, escritas y distintas (§5.1)."""
        if not self.bundle.strip():
            raise ConfigError(
                "monitoring.bundle no puede estar en blanco.", loc=(*_LOC_SECCION, "bundle")
            )
        if not self.period.strip():
            raise ConfigError(
                "monitoring.period no puede estar en blanco.", loc=(*_LOC_SECCION, "period")
            )
        if self.default is not None:
            if not self.default.strip():
                raise ConfigError(
                    "monitoring.default no puede estar en blanco: omítelo si la cartera no trae "
                    "desenlace.",
                    loc=(*_LOC_SECCION, "default"),
                )
            if self.default == self.period:
                raise ConfigError(
                    f"monitoring.default y monitoring.period son la misma columna "
                    f"({self.period!r}): el desenlace no puede ser el periodo.",
                    loc=(*_LOC_SECCION, "default"),
                )
        return self
