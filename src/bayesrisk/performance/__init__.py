"""Capa ``performance`` de bayesrisk: desempeño post-modelo (SDD-11).

Al importarse, registra :class:`PerformanceConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.performance`` se valida como sub-config
real sin que ``import bayesrisk.core`` arrastre ``bayesrisk.performance`` ni dependencias de
scoring. El paquete importa ``performance.step`` al final para ejecutar ``@register("standard",
domain="performance")`` sin arrastrar pandas/pandera/sklearn; los DTOs tabulares se reexportan de
forma perezosa.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.performance.config import (
    EvaluationSource,
    PerformanceConfig,
    PerformancePartition,
    ScoreDirection,
)
from bayesrisk.performance.exceptions import (
    PerformanceDataError,
    PerformanceError,
    PerformanceMetricError,
)

# Registra la clase real del sub-config performance en el hook de `core`.
_schema._PERFORMANCE_CONFIG_CLS = PerformanceConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "DecilePerformanceRecord": ("bayesrisk.performance.results", "DecilePerformanceRecord"),
    "DiscriminantMetricRecord": ("bayesrisk.performance.results", "DiscriminantMetricRecord"),
    "PerformanceCardSection": ("bayesrisk.performance.results", "PerformanceCardSection"),
    "PerformanceResult": ("bayesrisk.performance.results", "PerformanceResult"),
    "PerformanceStep": ("bayesrisk.performance.step", "PerformanceStep"),
}

__all__ = [
    "DecilePerformanceRecord",
    "DiscriminantMetricRecord",
    "EvaluationSource",
    "PerformanceCardSection",
    "PerformanceConfig",
    "PerformanceDataError",
    "PerformanceError",
    "PerformanceMetricError",
    "PerformancePartition",
    "PerformanceResult",
    "PerformanceStep",
    "ScoreDirection",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="performance") al
# importar `bayesrisk.performance`, sin contaminar `import bayesrisk.core` ni cargar
# pandas/pandera/sklearn.
importlib.import_module("bayesrisk.performance.step")


def __getattr__(name: str) -> Any:
    """Carga componentes de performance bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.performance' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
