"""Config declarativo de la capa ``comparison`` (SDD-34 §5).

:class:`ComparisonConfig` es la sección ``comparison`` de
:class:`~bayesrisk.core.config.BayesRiskConfig`. Tiene **una sola hoja**, ``runs``: las corridas
que se comparan, en orden, la primera es la referencia (§13). Qué muestra se compara, la receta
del PSI de la frontera, el corte de la prueba de DeLong, la ponderación del índice y el tope de
corridas son constantes del motor (§5.2). La sección nació después de la 2.10.0: ausente, no se
serializa (D-ESC-7); declarada, entra al ``config_hash`` **sin** las rutas, porque qué se comparó
lo identifica la huella de cada resumen en el lineage (§5.3, §9).

**Estable (API pública bajo SemVer 2.x) desde la 2.16.0.**
"""

from __future__ import annotations

from typing import Final, Self

from pydantic import ConfigDict, Field, model_validator

from bayesrisk.core.config import BayesRiskBaseConfig, declara_esenciales
from bayesrisk.core.exceptions import ConfigError

__all__ = ["MAX_RUNS", "MIN_RUNS", "ComparisonConfig"]

#: Prefijo del ``loc`` de los errores de esta sección (D-EXI-5): la ruta absoluta desde la raíz.
_LOC_SECCION: tuple[str, ...] = ("comparison",)
#: Una comparación pone al menos dos corridas lado a lado.
MIN_RUNS: Final = 2
#: El tope de corridas (§5.2): la tabla de variables pone una columna por modelo y con más no se
#: lee en el informe. Constante, no perilla.
MAX_RUNS: Final = 10


class ComparisonConfig(BayesRiskBaseConfig):
    """Pone lado a lado entre 2 y 10 corridas guardadas, la primera como referencia."""

    model_config = ConfigDict(json_schema_extra=declara_esenciales)

    runs: tuple[str, ...] = Field(
        ...,
        title="Corridas",
        description=(
            "Las corridas que se comparan, en orden: la primera es la referencia (el modelo en "
            "uso). Cada una es la carpeta de una corrida terminada o su resumen comparable."
        ),
        json_schema_extra={"ui_essential": True, "ui_widget": "text_list"},
    )

    @model_validator(mode="after")
    def _check_runs(self) -> Self:
        """Entre 2 y 10 corridas, cada una escrita (§5.1, §8)."""
        if not MIN_RUNS <= len(self.runs) <= MAX_RUNS:
            raise ConfigError(
                f"comparison.runs lleva {len(self.runs)} corridas: se comparan entre {MIN_RUNS} y "
                f"{MAX_RUNS}.",
                loc=(*_LOC_SECCION, "runs"),
            )
        for posicion, ruta in enumerate(self.runs):
            if not str(ruta).strip():
                raise ConfigError(
                    f"comparison.runs[{posicion}] está en blanco: cada corrida es una carpeta o "
                    "un resumen comparable.",
                    loc=(*_LOC_SECCION, "runs"),
                )
        return self
