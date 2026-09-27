"""Capa ``calibration`` de bayesrisk: calibración de PD cruda (SDD-10).

Al importarse, registra :class:`CalibrationConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.calibration`` se valida como sub-config
real sin que ``import bayesrisk.core`` arrastre ``bayesrisk.calibration`` ni dependencias de
scoring. El paquete importa ``calibration.step`` al final para ejecutar ``@register("standard",
domain="calibration")`` sin arrastrar pandas/scipy/sklearn; el motor y DTOs se reexportan de forma
perezosa.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.calibration.config import (
    AnchorKind,
    AnchorSource,
    CalibrationConfig,
    CalibrationMethod,
)
from bayesrisk.calibration.exceptions import (
    CalibrationError,
    CalibrationFitError,
    CalibrationOffsetExceededError,
    CalibrationTransformError,
)
from bayesrisk.core.config import schema as _schema

# Registra la clase real del sub-config calibration en el hook de `core`.
_schema._CALIBRATION_CONFIG_CLS = CalibrationConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "CalibrationCardSection": ("bayesrisk.calibration.results", "CalibrationCardSection"),
    "CalibrationParameters": ("bayesrisk.calibration.results", "CalibrationParameters"),
    "CalibrationResult": ("bayesrisk.calibration.results", "CalibrationResult"),
    "CalibrationStep": ("bayesrisk.calibration.step", "CalibrationStep"),
    "PDCalibrator": ("bayesrisk.calibration.calibrator", "PDCalibrator"),
}

__all__ = [
    "AnchorKind",
    "AnchorSource",
    "CalibrationCardSection",
    "CalibrationConfig",
    "CalibrationError",
    "CalibrationFitError",
    "CalibrationMethod",
    "CalibrationOffsetExceededError",
    "CalibrationParameters",
    "CalibrationResult",
    "CalibrationStep",
    "CalibrationTransformError",
    "PDCalibrator",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="calibration") al
# importar `bayesrisk.calibration`, sin contaminar `import bayesrisk.core` ni cargar
# pandas/scipy/sklearn.
importlib.import_module("bayesrisk.calibration.step")


def __getattr__(name: str) -> Any:
    """Carga componentes pesados de calibration bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.calibration' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
