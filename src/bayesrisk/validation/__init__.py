"""Capa ``validation``: validación avanzada (calibración, backtesting, semáforo, SDD-22).

Al importarse, registra :class:`ValidationConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema` e importa :mod:`bayesrisk.validation.step` para ejecutar
``@register("standard", domain="validation")`` del :class:`ValidationStep`. Así
``BayesRiskConfig.validation`` se valida como sub-config real y el step queda en el ``REGISTRY`` sin
que ``import bayesrisk.core`` ni ``import bayesrisk.validation`` arrastren dependencias
tabulares/estadísticas (pandas/pandera/scipy/sklearn): el step importa el evaluador y pandas de
forma **perezosa** dentro de ``execute``. Los DTOs, el evaluador y el step se reexportan perezosos.
Nomenclatura en inglés técnico para APIs; docstrings y errores en español.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.validation.config import (
    BacktestingValidationConfig,
    BacktestParameter,
    CalibrationValidationConfig,
    DiscriminationPartition,
    DiscriminationValidationConfig,
    HlGrouping,
    PdTest,
    StabilityValidationConfig,
    ValidationConfig,
    ValidationFamily,
)

# Registra la clase real del sub-config validation en el hook de `core`.
_schema._VALIDATION_CONFIG_CLS = ValidationConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "BacktestError": ("bayesrisk.validation.exceptions", "BacktestError"),
    "CalibrationTestError": ("bayesrisk.validation.exceptions", "CalibrationTestError"),
    "ValidationConfigError": ("bayesrisk.validation.exceptions", "ValidationConfigError"),
    "ValidationDataError": ("bayesrisk.validation.exceptions", "ValidationDataError"),
    "ValidationError": ("bayesrisk.validation.exceptions", "ValidationError"),
    "BacktestRecord": ("bayesrisk.validation.results", "BacktestRecord"),
    "CalibrationTestRecord": ("bayesrisk.validation.results", "CalibrationTestRecord"),
    "DiscriminationRecord": ("bayesrisk.validation.results", "DiscriminationRecord"),
    "GradeBinomialRecord": ("bayesrisk.validation.results", "GradeBinomialRecord"),
    "ValidationCardSection": ("bayesrisk.validation.results", "ValidationCardSection"),
    "ValidationResult": ("bayesrisk.validation.results", "ValidationResult"),
    "ValidationEvaluator": ("bayesrisk.validation.evaluator", "ValidationEvaluator"),
    "ValidationStep": ("bayesrisk.validation.step", "ValidationStep"),
    "VALIDATION_ARTIFACTS": ("bayesrisk.validation.step", "VALIDATION_ARTIFACTS"),
}

__all__ = [
    "VALIDATION_ARTIFACTS",
    "BacktestError",
    "BacktestParameter",
    "BacktestRecord",
    "BacktestingValidationConfig",
    "CalibrationTestError",
    "CalibrationTestRecord",
    "CalibrationValidationConfig",
    "DiscriminationPartition",
    "DiscriminationRecord",
    "DiscriminationValidationConfig",
    "GradeBinomialRecord",
    "HlGrouping",
    "PdTest",
    "StabilityValidationConfig",
    "ValidationCardSection",
    "ValidationConfig",
    "ValidationConfigError",
    "ValidationDataError",
    "ValidationError",
    "ValidationEvaluator",
    "ValidationFamily",
    "ValidationResult",
    "ValidationStep",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="validation") al
# importar `bayesrisk.validation`, sin contaminar `import bayesrisk.core` ni cargar
# pandas/scipy/sklearn (el step importa el evaluador y pandas dentro de execute).
importlib.import_module("bayesrisk.validation.step")


def __getattr__(name: str) -> Any:
    """Carga componentes de validation bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.validation' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
