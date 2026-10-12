"""Capa ``master_scale`` de bayesrisk: escala maestra y puntos de corte (SDD-32, hito H5).

Al importarse, registra :class:`MasterScaleConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema` y el paso con ``@register("standard", domain="master_scale")``,
sin arrastrar pandas/scipy/OptBinning: el motor se carga al ejecutar.

**Experimental (fuera de la garantía SemVer 2.x).**
La etapa sale por la puerta guiada y la completa en la 2.11.0 (capa A del SDD-32) y deja de
serlo cuando la pantalla cierre sus tres puertas (capa B).
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.master_scale.config import MasterScaleConfig
from bayesrisk.master_scale.exceptions import MasterScaleError, MasterScaleFitError

# Registra la clase real del sub-config en el hook de `core`.
_schema._MASTER_SCALE_CONFIG_CLS = MasterScaleConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "MasterScaleCardSection": ("bayesrisk.master_scale.results", "MasterScaleCardSection"),
    "MasterScaleResult": ("bayesrisk.master_scale.results", "MasterScaleResult"),
    "MasterScaleStep": ("bayesrisk.master_scale.step", "MasterScaleStep"),
}

__all__ = [
    "MasterScaleCardSection",
    "MasterScaleConfig",
    "MasterScaleError",
    "MasterScaleFitError",
    "MasterScaleResult",
    "MasterScaleStep",
]

importlib.import_module("bayesrisk.master_scale.step")


def __getattr__(name: str) -> Any:
    """Carga componentes bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.master_scale' has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
