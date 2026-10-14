"""Capa ``monitoring`` de bayesrisk: monitoreo del modelo y de la cartera (SDD-33, hito H4).

Una corrida propia que parte de la tarjeta guardada (esquema 4) y de la cartera nueva por periodo,
y dice por periodo si cambió la población, si el modelo sigue ordenando y si cada tramo acierta su
PD, con un veredicto y su acción (D-MNT-1…10). Al importarse, registra :class:`MonitoringConfig`
en el hook diferido de :mod:`bayesrisk.core.config.schema` y el paso con
``@register("standard", domain="monitoring")``, sin arrastrar pandas/scipy: el motor se carga al
ejecutar.

**Estable (SemVer 2.x).**
Salió en la 2.13.0 por la puerta guiada (``bayesrisk.Monitor``) y el config completo (capa A del
SDD-33) y es estable desde la 2.14.0, al cerrar sus tres puertas: la pantalla, el informe y el
Excel (capa B, D-MNT-8).
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.monitoring.config import MonitoringConfig
from bayesrisk.monitoring.exceptions import MonitoringError, MonitoringInputError

# Registra la clase real del sub-config en el hook de `core`.
_schema._MONITORING_CONFIG_CLS = MonitoringConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "MonitoringCardSection": ("bayesrisk.monitoring.results", "MonitoringCardSection"),
    "MonitoringResult": ("bayesrisk.monitoring.results", "MonitoringResult"),
    "MonitoringStep": ("bayesrisk.monitoring.step", "MonitoringStep"),
    "MonitoringVerdict": ("bayesrisk.monitoring.results", "MonitoringVerdict"),
}

__all__ = [
    "MonitoringCardSection",
    "MonitoringConfig",
    "MonitoringError",
    "MonitoringInputError",
    "MonitoringResult",
    "MonitoringStep",
    "MonitoringVerdict",
]

importlib.import_module("bayesrisk.monitoring.step")


def __getattr__(name: str) -> Any:
    """Carga componentes bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.monitoring' has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
