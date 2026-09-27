"""Capa ``forward`` de bayesrisk: forward-looking macro y PIT/TTC (SDD-20).

Al importarse, registra :class:`ForwardConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.forward`` se valida como sub-config real
sin que ``import bayesrisk.core`` arrastre ``bayesrisk.forward`` ni dependencias estadísticas
opcionales. Este paquete no importa statsmodels, pmdarima, pandas ni scipy en top-level; los motores
concretos llegarán en B20.3-B20.6 y cargarán sus dependencias dentro de ``fit``/``execute``.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.forward.config import (
    ForwardConfig,
    ForwardInputConfig,
    ForwardValidationConfig,
    MacroModelConfig,
    MacroModelKind,
    MacroSourceConfig,
    MacroSourceType,
    PdBasisAssumption,
    SatelliteConfig,
    SatelliteMode,
    ScenarioConfig,
    ScenarioDefinitionConfig,
    TargetComponent,
    TermStructureSource,
    TtcAnchor,
    TtcReversionConfig,
    TtcReversionMethod,
)
from bayesrisk.forward.exceptions import (
    ForwardConfigError,
    ForwardError,
    ForwardFitError,
    ForwardInputError,
    ForwardPredictionError,
    ForwardScenarioError,
    MacroProjectionError,
    PitConsistencyError,
    SatelliteModelError,
)

# Registra la clase real del sub-config forward en el hook de `core`.
_schema._FORWARD_CONFIG_CLS = ForwardConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "FORWARD_ECL_CONTRACT_VERSION": ("bayesrisk.forward.results", "FORWARD_ECL_CONTRACT_VERSION"),
    "ForwardCard": ("bayesrisk.forward.results", "ForwardCard"),
    "ForwardDiagnostics": ("bayesrisk.forward.results", "ForwardDiagnostics"),
    "ForwardEclInput": ("bayesrisk.forward.results", "ForwardEclInput"),
    "ForwardResult": ("bayesrisk.forward.results", "ForwardResult"),
    "ForwardStep": ("bayesrisk.forward.step", "ForwardStep"),
    "MacroDiagnostics": ("bayesrisk.forward.results", "MacroDiagnostics"),
    "MacroProjectionResult": ("bayesrisk.forward.results", "MacroProjectionResult"),
    "SatelliteDiagnostics": ("bayesrisk.forward.results", "SatelliteDiagnostics"),
    "SatelliteResult": ("bayesrisk.forward.results", "SatelliteResult"),
    "ScenarioWeighting": ("bayesrisk.forward.scenarios", "ScenarioWeighting"),
    "ScenarioDiagnostics": ("bayesrisk.forward.results", "ScenarioDiagnostics"),
}

__all__ = [
    "FORWARD_ECL_CONTRACT_VERSION",
    "ForwardCard",
    "ForwardConfig",
    "ForwardConfigError",
    "ForwardDiagnostics",
    "ForwardEclInput",
    "ForwardError",
    "ForwardFitError",
    "ForwardInputConfig",
    "ForwardInputError",
    "ForwardPredictionError",
    "ForwardResult",
    "ForwardScenarioError",
    "ForwardStep",
    "ForwardValidationConfig",
    "MacroDiagnostics",
    "MacroModelConfig",
    "MacroModelKind",
    "MacroProjectionError",
    "MacroProjectionResult",
    "MacroSourceConfig",
    "MacroSourceType",
    "PdBasisAssumption",
    "PitConsistencyError",
    "SatelliteConfig",
    "SatelliteDiagnostics",
    "SatelliteMode",
    "SatelliteModelError",
    "SatelliteResult",
    "ScenarioConfig",
    "ScenarioDefinitionConfig",
    "ScenarioDiagnostics",
    "ScenarioWeighting",
    "TargetComponent",
    "TermStructureSource",
    "TtcAnchor",
    "TtcReversionConfig",
    "TtcReversionMethod",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="forward") al
# importar `bayesrisk.forward`, sin contaminar `import bayesrisk.core` ni cargar dependencias
# pesadas.
importlib.import_module("bayesrisk.forward.step")


def __getattr__(name: str) -> Any:
    """Carga DTOs forward bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.forward' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
