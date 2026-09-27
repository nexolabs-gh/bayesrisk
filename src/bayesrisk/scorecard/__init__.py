"""Capa ``scorecard`` de bayesrisk: escalamiento log-odds a puntos (SDD-09).

Al importarse, registra :class:`ScorecardConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.scorecard`` se valida como sub-config
real sin que ``import bayesrisk.core`` arrastre ``bayesrisk.scorecard`` ni dependencias de scoring.
El paquete importa ``scorecard.step`` al final para ejecutar ``@register("standard",
domain="scorecard")`` sin arrastrar pandas/sklearn; los transformadores y DTOs tabulares se
reexportan de forma perezosa.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.scorecard.config import (
    InterceptAllocation,
    PointOverrideConfig,
    RoundingMethod,
    ScorecardConfig,
    ScoreDirection,
)
from bayesrisk.scorecard.exceptions import (
    ScorecardBundleError,
    ScorecardError,
    ScorecardFitError,
    ScorecardTransformError,
)

# Registra la clase real del sub-config scorecard en el hook de `core`.
_schema._SCORECARD_CONFIG_CLS = ScorecardConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "BatchApplicationResult": ("bayesrisk.scorecard.bundle", "BatchApplicationResult"),
    "FittedScorecardBundle": ("bayesrisk.scorecard.bundle", "FittedScorecardBundle"),
    "PointsScaler": ("bayesrisk.scorecard.scaler", "PointsScaler"),
    "ScorecardApplicationResult": (
        "bayesrisk.scorecard.bundle",
        "ScorecardApplicationResult",
    ),
    "Scorecard": ("bayesrisk.scorecard.transformer", "Scorecard"),
    "ScorecardBinPoint": ("bayesrisk.scorecard.results", "ScorecardBinPoint"),
    "ScorecardCardSection": ("bayesrisk.scorecard.results", "ScorecardCardSection"),
    "ScorecardResult": ("bayesrisk.scorecard.results", "ScorecardResult"),
    "ScorecardStep": ("bayesrisk.scorecard.step", "ScorecardStep"),
    "apply": ("bayesrisk.scorecard.bundle", "apply"),
    "fit_scorecard_bundle": ("bayesrisk.scorecard.bundle", "fit_scorecard_bundle"),
}

__all__ = [
    "BatchApplicationResult",
    "FittedScorecardBundle",
    "InterceptAllocation",
    "PointOverrideConfig",
    "PointsScaler",
    "RoundingMethod",
    "ScoreDirection",
    "Scorecard",
    "ScorecardApplicationResult",
    "ScorecardBinPoint",
    "ScorecardBundleError",
    "ScorecardCardSection",
    "ScorecardConfig",
    "ScorecardError",
    "ScorecardFitError",
    "ScorecardResult",
    "ScorecardStep",
    "ScorecardTransformError",
    "apply",
    "fit_scorecard_bundle",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="scorecard") al
# importar `bayesrisk.scorecard`, sin contaminar `import bayesrisk.core` ni cargar pandas/sklearn.
importlib.import_module("bayesrisk.scorecard.step")


def __getattr__(name: str) -> Any:
    """Carga componentes pesados de scorecard bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.scorecard' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
