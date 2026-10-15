"""Capa ``comparison`` de bayesrisk: comparar modelos y provisiones (SDD-34, hito H2b).

Una corrida propia, sin ``data``, que pone lado a lado entre 2 y 10 corridas terminadas desde su
**resumen comparable** (``comparable.json``, que toda corrida de scorecard o de IFRS 9 deja desde
la 2.15.0): dice si se midieron sobre las mismas operaciones, cuáles son el mismo modelo, qué
diferencias de AUC son reales (DeLong pareada), quién reparte mejor sus tramos (el índice del BCE),
qué modelos no quedan superados por ninguno (la frontera) y cuál eligió la institución, con su
motivo (D-CMP-1…9). Al importarse, registra :class:`ComparisonConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema` y el paso con ``@register("standard", domain="comparison")``,
sin arrastrar pandas: el motor se carga al ejecutar.

**Estable (SemVer 2.x).** Desde la 2.16.0, con sus tres puertas (D-CMP-9).
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.comparison.config import ComparisonConfig
from bayesrisk.comparison.exceptions import ComparisonDataError, ComparisonError
from bayesrisk.core.config import schema as _schema

# Registra la clase real del sub-config en el hook de `core`.
_schema._COMPARISON_CONFIG_CLS = ComparisonConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "ComparisonCardSection": ("bayesrisk.comparison.results", "ComparisonCardSection"),
    "ComparisonResult": ("bayesrisk.comparison.results", "ComparisonResult"),
    "ComparisonStep": ("bayesrisk.comparison.step", "ComparisonStep"),
}

__all__ = [
    "ComparisonCardSection",
    "ComparisonConfig",
    "ComparisonDataError",
    "ComparisonError",
    "ComparisonResult",
    "ComparisonStep",
]

importlib.import_module("bayesrisk.comparison.step")


def __getattr__(name: str) -> Any:
    """Carga componentes bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.comparison' has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
