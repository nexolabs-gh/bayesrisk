"""Capa ``eda`` de bayesrisk: diagnóstico exploratorio orientado a riesgo (SDD-27).

Al importarse, registra :class:`EdaConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.eda`` se valida como sub-config real sin
que ``import bayesrisk.core`` arrastre ``bayesrisk.eda`` ni dependencias tabulares. El paquete
importa ``eda.step`` al final para ejecutar ``@register("standard", domain="eda")``; el resto de la
superficie pública se mantiene en el mapa de reexportación perezosa.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.eda.config import (
    DefaultRateConfig,
    EdaConfig,
    QualityConfig,
    SamplingConfig,
    TemporalStabilityConfig,
    UnivariateConfig,
)
from bayesrisk.eda.exceptions import EdaError

if TYPE_CHECKING:
    from bayesrisk.eda.card import EdaCardSection
    from bayesrisk.eda.default_rate import DefaultRateAnalyzer, DefaultRateResult
    from bayesrisk.eda.figures import FigureSpec
    from bayesrisk.eda.quality import DataQualityProfiler, QualityResult
    from bayesrisk.eda.stability import StabilityResult, TemporalStabilityAnalyzer
    from bayesrisk.eda.step import EdaResult, EdaStep
    from bayesrisk.eda.univariate import UnivariateProfiler, UnivariateResult

# Registra la clase real del sub-config EDA en el hook de `core`.
_schema._EDA_CONFIG_CLS = EdaConfig

_LAZY_EXPORTS: Final = {
    "DataQualityProfiler": ("bayesrisk.eda.quality", "DataQualityProfiler"),
    "DefaultRateAnalyzer": ("bayesrisk.eda.default_rate", "DefaultRateAnalyzer"),
    "DefaultRateResult": ("bayesrisk.eda.default_rate", "DefaultRateResult"),
    "EdaCardSection": ("bayesrisk.eda.card", "EdaCardSection"),
    "EdaResult": ("bayesrisk.eda.step", "EdaResult"),
    "EdaStep": ("bayesrisk.eda.step", "EdaStep"),
    "FigureSpec": ("bayesrisk.eda.figures", "FigureSpec"),
    "QualityResult": ("bayesrisk.eda.quality", "QualityResult"),
    "StabilityResult": ("bayesrisk.eda.stability", "StabilityResult"),
    "TemporalStabilityAnalyzer": ("bayesrisk.eda.stability", "TemporalStabilityAnalyzer"),
    "UnivariateProfiler": ("bayesrisk.eda.univariate", "UnivariateProfiler"),
    "UnivariateResult": ("bayesrisk.eda.univariate", "UnivariateResult"),
}

__all__ = [
    "DataQualityProfiler",
    "DefaultRateAnalyzer",
    "DefaultRateConfig",
    "DefaultRateResult",
    "EdaCardSection",
    "EdaConfig",
    "EdaError",
    "EdaResult",
    "EdaStep",
    "FigureSpec",
    "QualityConfig",
    "QualityResult",
    "SamplingConfig",
    "StabilityResult",
    "TemporalStabilityAnalyzer",
    "TemporalStabilityConfig",
    "UnivariateConfig",
    "UnivariateProfiler",
    "UnivariateResult",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="eda") al importar
# `bayesrisk.eda`, sin contaminar `import bayesrisk.core`.
importlib.import_module("bayesrisk.eda.step")


def __getattr__(name: str) -> Any:
    """Carga analizadores EDA bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.eda' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
