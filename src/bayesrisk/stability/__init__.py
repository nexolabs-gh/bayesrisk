"""Capa ``stability`` de bayesrisk: estabilidad post-modelo (SDD-11).

Al importarse, registra :class:`StabilityConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.stability`` se valida como sub-config
real sin que ``import bayesrisk.core`` arrastre ``bayesrisk.stability`` ni dependencias
tabulares/scoring. El paquete importa ``stability.step`` al final para ejecutar
``@register("standard", domain="stability")`` sin arrastrar pandas/pandera/sklearn; los DTOs
tabulares se reexportan de forma perezosa.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.stability.config import (
    CsiSource,
    ScoreDirection,
    StabilityComparison,
    StabilityConfig,
    TemporalAxis,
    TemporalFrequency,
)

# Registra la clase real del sub-config stability en el hook de `core`.
_schema._STABILITY_CONFIG_CLS = StabilityConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "CsiRecord": ("bayesrisk.stability.results", "CsiRecord"),
    "PsiRecord": ("bayesrisk.stability.results", "PsiRecord"),
    "StabilityCardSection": ("bayesrisk.stability.results", "StabilityCardSection"),
    "StabilityDataError": ("bayesrisk.stability.exceptions", "StabilityDataError"),
    "StabilityError": ("bayesrisk.stability.exceptions", "StabilityError"),
    "StabilityMetricError": ("bayesrisk.stability.exceptions", "StabilityMetricError"),
    "StabilityMetricRecord": ("bayesrisk.stability.results", "StabilityMetricRecord"),
    "StabilityResult": ("bayesrisk.stability.results", "StabilityResult"),
    "StabilityStep": ("bayesrisk.stability.step", "StabilityStep"),
    "TemporalStabilityRecord": ("bayesrisk.stability.results", "TemporalStabilityRecord"),
}

__all__ = [
    "CsiRecord",
    "CsiSource",
    "PsiRecord",
    "ScoreDirection",
    "StabilityCardSection",
    "StabilityComparison",
    "StabilityConfig",
    "StabilityDataError",
    "StabilityError",
    "StabilityMetricError",
    "StabilityMetricRecord",
    "StabilityResult",
    "StabilityStep",
    "TemporalAxis",
    "TemporalFrequency",
    "TemporalStabilityRecord",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="stability") al
# importar `bayesrisk.stability`, sin contaminar `import bayesrisk.core` ni cargar
# pandas/pandera/sklearn.
importlib.import_module("bayesrisk.stability.step")


def __getattr__(name: str) -> Any:
    """Carga componentes de stability bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.stability' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
