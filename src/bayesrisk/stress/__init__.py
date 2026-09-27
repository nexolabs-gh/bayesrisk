"""Capa ``stress`` de bayesrisk: stress testing, sensibilidad y reverse stress (SDD-21).

Al importarse, registra :class:`StressConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.stress`` se valida como sub-config real
sin que ``import bayesrisk.core`` importe ``bayesrisk.stress`` ni motores económicos futuros. En
B21.2 los DTOs de resultados se exportan bajo demanda para no arrastrar ``pandas`` ni engines.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.stress.config import (
    ReverseStressConfig,
    SensitivitySweepConfig,
    StressConfig,
    StressDirection,
    StressInputConfig,
    StressMetric,
    StressOperation,
    StressOutputConfig,
    StressScenarioConfig,
    StressShockConfig,
    StressTargetConfig,
    StressValidationConfig,
)
from bayesrisk.stress.exceptions import (
    NonMonotonicStressError,
    ReverseStressError,
    StressConfigError,
    StressDependencyError,
    StressEngineError,
    StressError,
    StressFaltaDatoError,
    StressInputError,
    StressOutputError,
    StressScenarioError,
)

# Registra la clase real del sub-config stress en el hook de `core`.
_schema._STRESS_CONFIG_CLS = StressConfig

# Exports perezosos: DTOs de resultados, engine y el paso orquestable. El módulo destino se importa
# sólo al acceder al nombre, para no arrastrar `pandas`/engines al importar `bayesrisk.stress`.
_RESULT_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "EclEngineLike": ("bayesrisk.stress.engine", "EclEngineLike"),
    "ProvisionEngineLike": ("bayesrisk.stress.engine", "ProvisionEngineLike"),
    "ReverseStressResult": ("bayesrisk.stress.results", "ReverseStressResult"),
    "StressCard": ("bayesrisk.stress.results", "StressCard"),
    "StressDiagnostics": ("bayesrisk.stress.results", "StressDiagnostics"),
    "StressResult": ("bayesrisk.stress.results", "StressResult"),
    "StressScenarioResult": ("bayesrisk.stress.results", "StressScenarioResult"),
    "StressSensitivityResult": ("bayesrisk.stress.results", "StressSensitivityResult"),
    "StressStep": ("bayesrisk.stress.step", "StressStep"),
    "StressTestEngine": ("bayesrisk.stress.engine", "StressTestEngine"),
}

__all__ = [
    "EclEngineLike",
    "NonMonotonicStressError",
    "ProvisionEngineLike",
    "ReverseStressConfig",
    "ReverseStressError",
    "ReverseStressResult",
    "SensitivitySweepConfig",
    "StressCard",
    "StressConfig",
    "StressConfigError",
    "StressDependencyError",
    "StressDiagnostics",
    "StressDirection",
    "StressEngineError",
    "StressError",
    "StressFaltaDatoError",
    "StressInputConfig",
    "StressInputError",
    "StressMetric",
    "StressOperation",
    "StressOutputConfig",
    "StressOutputError",
    "StressResult",
    "StressScenarioConfig",
    "StressScenarioError",
    "StressScenarioResult",
    "StressSensitivityResult",
    "StressShockConfig",
    "StressStep",
    "StressTargetConfig",
    "StressTestEngine",
    "StressValidationConfig",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="stress") al importar
# `bayesrisk.stress`, sin contaminar `import bayesrisk.core` ni cargar pandas/engines/results.
importlib.import_module("bayesrisk.stress.step")


def __getattr__(name: str) -> Any:
    """Carga DTOs de resultados, engine y el paso orquestable bajo demanda."""
    if name not in _RESULT_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.stress' has no attribute {name!r}")

    module_name, attribute_name = _RESULT_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
