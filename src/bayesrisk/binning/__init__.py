"""Capa ``binning`` de bayesrisk: binning supervisado óptimo, WoE e IV (SDD-06).

Al importarse, registra :class:`BinningConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.binning`` se valida como sub-config real
sin que ``import bayesrisk.core`` arrastre ``bayesrisk.binning`` ni dependencias de scoring.
El paquete importa ``binning.step`` al final para ejecutar ``@register("standard",
domain="binning")``; ese módulo mantiene imports pesados dentro de ``execute``.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.binning.config import BinningConfig, MonotonicTrend, VariableBinningConfig
from bayesrisk.binning.exceptions import BinningError, BinningFitError, BinningTransformError
from bayesrisk.core.config import schema as _schema

# Registra la clase real del sub-config binning en el hook de `core`.
_schema._BINNING_CONFIG_CLS = BinningConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "BinningCardSection": ("bayesrisk.binning.results", "BinningCardSection"),
    "BinningResult": ("bayesrisk.binning.results", "BinningResult"),
    "BinningStep": ("bayesrisk.binning.step", "BinningStep"),
    "BinningVariableSummary": ("bayesrisk.binning.results", "BinningVariableSummary"),
    "WoEBinner": ("bayesrisk.binning.transformer", "WoEBinner"),
    "iv_band": ("bayesrisk.binning.results", "iv_band"),
}

__all__ = [
    "BinningCardSection",
    "BinningConfig",
    "BinningError",
    "BinningFitError",
    "BinningResult",
    "BinningStep",
    "BinningTransformError",
    "BinningVariableSummary",
    "MonotonicTrend",
    "VariableBinningConfig",
    "WoEBinner",
    "iv_band",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="binning") al importar
# `bayesrisk.binning`, sin contaminar `import bayesrisk.core` ni cargar scoring.
importlib.import_module("bayesrisk.binning.step")


def __getattr__(name: str) -> Any:
    """Carga componentes pesados de binning bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.binning' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
