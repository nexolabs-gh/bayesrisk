"""Capa ``ml`` de bayesrisk: challenger de machine learning (SDD-12).

Al importarse, registra :class:`MLConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema` (``_ML_CONFIG_CLS``) para que ``BayesRiskConfig.ml`` se valide
como sub-config real, **sin** que ``import bayesrisk.core`` ni ``import bayesrisk.ml`` arrastren
dependencias de machine learning (scikit-learn/xgboost/lightgbm/catboost) ni tabulares
(pandas/numpy): los backends y el estimador se importan de forma **perezosa** en bloques posteriores
(B12.2+). Las excepciones se reexportan perezosas. Al final se importa ``ml.step`` para ejecutar
``@register('standard', domain='ml')`` sin arrastrar ``pandas``/``numpy`` ni los backends ML (el
step los carga perezosamente dentro de ``execute``). Nomenclatura en inglés técnico para APIs;
docstrings y errores en español.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.ml.config import (
    CatBoostParams,
    ClassWeight,
    ComparisonMetric,
    FeatureSource,
    LightGBMParams,
    MLBackendName,
    MLComparisonConfig,
    MLConfig,
    MLOutputConfig,
    MLTrainConfig,
    MonotonicConfig,
    MonotonicMode,
    RandomForestParams,
    SvmParams,
    XGBoostParams,
)

# Registra la clase real del sub-config ml en el hook de `core` (sin importar backends ML).
_schema._ML_CONFIG_CLS = MLConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "MLBackendMetadata": ("bayesrisk.ml.results", "MLBackendMetadata"),
    "MLCardSection": ("bayesrisk.ml.results", "MLCardSection"),
    "MLChallenger": ("bayesrisk.ml.estimator", "MLChallenger"),
    "MLComparisonRecord": ("bayesrisk.ml.results", "MLComparisonRecord"),
    "MLResult": ("bayesrisk.ml.results", "MLResult"),
    "MLStep": ("bayesrisk.ml.step", "MLStep"),
    "MLBackendError": ("bayesrisk.ml.exceptions", "MLBackendError"),
    "MLComparisonError": ("bayesrisk.ml.exceptions", "MLComparisonError"),
    "MLConfigError": ("bayesrisk.ml.exceptions", "MLConfigError"),
    "MLDataError": ("bayesrisk.ml.exceptions", "MLDataError"),
    "MLDeterminismError": ("bayesrisk.ml.exceptions", "MLDeterminismError"),
    "MLError": ("bayesrisk.ml.exceptions", "MLError"),
    "MLFitError": ("bayesrisk.ml.exceptions", "MLFitError"),
    "MLMonotonicError": ("bayesrisk.ml.exceptions", "MLMonotonicError"),
    "MLPredictError": ("bayesrisk.ml.exceptions", "MLPredictError"),
}

__all__ = [
    "CatBoostParams",
    "ClassWeight",
    "ComparisonMetric",
    "FeatureSource",
    "LightGBMParams",
    "MLBackendError",
    "MLBackendMetadata",
    "MLBackendName",
    "MLCardSection",
    "MLChallenger",
    "MLComparisonConfig",
    "MLComparisonError",
    "MLComparisonRecord",
    "MLConfig",
    "MLConfigError",
    "MLDataError",
    "MLDeterminismError",
    "MLError",
    "MLFitError",
    "MLMonotonicError",
    "MLOutputConfig",
    "MLPredictError",
    "MLResult",
    "MLStep",
    "MLTrainConfig",
    "MonotonicConfig",
    "MonotonicMode",
    "RandomForestParams",
    "SvmParams",
    "XGBoostParams",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="ml") al importar
# `bayesrisk.ml`, sin arrastrar pandas/numpy ni los backends ML (el step los carga en `execute`).
importlib.import_module("bayesrisk.ml.step")


def __getattr__(name: str) -> Any:
    """Carga las excepciones de ``ml`` bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.ml' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
