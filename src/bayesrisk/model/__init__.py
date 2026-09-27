"""Capa ``model`` de bayesrisk: regresión logística PD sobre variables WoE (SDD-08).

Al importarse, registra :class:`ModelConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.model`` se valida como sub-config real
sin que ``import bayesrisk.core`` arrastre ``bayesrisk.model`` ni dependencias de scoring. La lógica
pesada de estimación (``estimator.py``) se carga bajo demanda; el paquete importa ``model.step`` al
final para ejecutar ``@register("standard", domain="model")`` sin arrastrar dependencias de scoring.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.model.config import (
    IvContributionConfig,
    ModelConfig,
    ModelEngine,
    ModelOptimizer,
    ModelPolicyAction,
    SignPolicyConfig,
    StepwiseConfig,
    StepwiseCriterion,
    StepwiseDirection,
)
from bayesrisk.model.exceptions import ModelError, ModelFitError, ModelTransformError

# Registra la clase real del sub-config model en el hook de `core`.
_schema._MODEL_CONFIG_CLS = ModelConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "CoefficientRecord": ("bayesrisk.model.results", "CoefficientRecord"),
    "LogisticPDModel": ("bayesrisk.model.estimator", "LogisticPDModel"),
    "ModelCardSection": ("bayesrisk.model.results", "ModelCardSection"),
    "ModelFitStatistics": ("bayesrisk.model.results", "ModelFitStatistics"),
    "ModelResult": ("bayesrisk.model.results", "ModelResult"),
    "ModelStep": ("bayesrisk.model.step", "ModelStep"),
    "StepwiseDecision": ("bayesrisk.model.results", "StepwiseDecision"),
}

__all__ = [
    "CoefficientRecord",
    "IvContributionConfig",
    "LogisticPDModel",
    "ModelCardSection",
    "ModelConfig",
    "ModelEngine",
    "ModelError",
    "ModelFitError",
    "ModelFitStatistics",
    "ModelOptimizer",
    "ModelPolicyAction",
    "ModelResult",
    "ModelStep",
    "ModelTransformError",
    "SignPolicyConfig",
    "StepwiseConfig",
    "StepwiseCriterion",
    "StepwiseDecision",
    "StepwiseDirection",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="model") al importar
# `bayesrisk.model`, sin contaminar `import bayesrisk.core` ni cargar scoring.
importlib.import_module("bayesrisk.model.step")


def __getattr__(name: str) -> Any:
    """Carga componentes pesados de model bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.model' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
