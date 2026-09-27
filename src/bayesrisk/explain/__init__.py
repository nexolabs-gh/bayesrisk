"""Capa ``explain`` de bayesrisk: explicabilidad unificada scorecard + SHAP (SDD-14).

Este ``__init__`` es **liviano**: reexporta la jerarquía de excepciones y el config declarativo
(:class:`ExplainConfig` con sus sub-schemas y alias de tipos), **puebla el hook diferido**
``_EXPLAIN_CONFIG_CLS`` en :class:`~bayesrisk.core.config.BayesRiskConfig` para que la sección
``explain`` se valide como sub-config real, y al final hace
``importlib.import_module('bayesrisk.explain.step')`` para ejecutar
``@register('standard', domain='explain')``. Todo ello **sin** que ``import bayesrisk.core`` ni
``import bayesrisk.explain`` arrastren ``shap``/``matplotlib``/``numba``/``llvmlite``/``sklearn``/
``pandas``/``numpy``: el motor y los explainers importan lo pesado de forma **perezosa** dentro de
sus métodos, y los DTOs/resultados se reexportan perezosos (molde idéntico a ``ml.__init__``).
Nomenclatura en inglés técnico para APIs; docstrings y errores en español.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.explain.config import (
    ContributionSpace,
    ExplainConfig,
    ExplainOutputConfig,
    ExplainTargets,
    LocalScope,
    LocalScopeConfig,
    MLExplainerChoice,
    MLExplainerConfig,
    ReasonCodesConfig,
    ScorecardBaseline,
    ScorecardExplainConfig,
    TreePerturbation,
)
from bayesrisk.explain.exceptions import (
    ExplainBackendError,
    ExplainConfigError,
    ExplainDataError,
    ExplainDeterminismError,
    ExplainError,
    ExplainExplainerError,
    ExplainReasonCodeError,
)

# Registra la clase real del sub-config explain en el hook de `core` (sin importar shap/tabulares).
_schema._EXPLAIN_CONFIG_CLS = ExplainConfig

# Reexports perezosos de los DTOs, el motor y el step (evitan arrastrar shap/pandas/numpy al
# importar el paquete): sólo se resuelven la primera vez que se acceden por atributo.
_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "UnifiedExplainer": ("bayesrisk.explain.engine", "UnifiedExplainer"),
    "resolve_explainer": ("bayesrisk.explain.explainers", "resolve_explainer"),
    "build_reason_codes": ("bayesrisk.explain.reason_codes", "build_reason_codes"),
    "DriverComparisonRecord": ("bayesrisk.explain.results", "DriverComparisonRecord"),
    "ExplainCardSection": ("bayesrisk.explain.results", "ExplainCardSection"),
    "ExplainResult": ("bayesrisk.explain.results", "ExplainResult"),
    "ExplainerMetadata": ("bayesrisk.explain.results", "ExplainerMetadata"),
    "LocalExplanationRecord": ("bayesrisk.explain.results", "LocalExplanationRecord"),
    "ReasonCode": ("bayesrisk.explain.results", "ReasonCode"),
    "ShapGlobalRecord": ("bayesrisk.explain.results", "ShapGlobalRecord"),
    "ExplainStep": ("bayesrisk.explain.step", "ExplainStep"),
}

__all__ = [
    "ContributionSpace",
    "DriverComparisonRecord",
    "ExplainBackendError",
    "ExplainCardSection",
    "ExplainConfig",
    "ExplainConfigError",
    "ExplainDataError",
    "ExplainDeterminismError",
    "ExplainError",
    "ExplainExplainerError",
    "ExplainOutputConfig",
    "ExplainReasonCodeError",
    "ExplainResult",
    "ExplainStep",
    "ExplainTargets",
    "ExplainerMetadata",
    "LocalExplanationRecord",
    "LocalScope",
    "LocalScopeConfig",
    "MLExplainerChoice",
    "MLExplainerConfig",
    "ReasonCode",
    "ReasonCodesConfig",
    "ScorecardBaseline",
    "ScorecardExplainConfig",
    "ShapGlobalRecord",
    "TreePerturbation",
    "UnifiedExplainer",
    "build_reason_codes",
    "resolve_explainer",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="explain") al importar
# `bayesrisk.explain`, sin arrastrar shap/matplotlib/pandas/numpy (el step los carga en `execute`).
importlib.import_module("bayesrisk.explain.step")


def __getattr__(name: str) -> Any:
    """Carga perezosa de DTOs/motor/step de ``explain`` para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.explain' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
