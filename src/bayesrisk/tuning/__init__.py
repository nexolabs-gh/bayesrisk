"""Capa ``tuning`` de bayesrisk: búsqueda de hiperparámetros con Optuna (SDD-13).

Este ``__init__`` es **liviano**: reexporta la jerarquía de excepciones, las *specs* del espacio de
búsqueda y el config declarativo (:class:`TuningConfig`), y **puebla el hook diferido**
``_TUNING_CONFIG_CLS`` en :class:`~bayesrisk.core.config.BayesRiskConfig` para que la sección
``tuning`` se valide como sub-config real, **sin** arrastrar ``optuna``/``pandas``/``numpy`` ni
backends ML. Los DTOs de resultados (:mod:`bayesrisk.tuning.results`) se reexportan de forma
**perezosa** (vía ``__getattr__``) porque anotan ``MLConfig``/``MLChallenger`` y usan ``pandas``:
cargarlos traería ``bayesrisk.ml``, que se difiere hasta que el usuario los pida. Al final se
importa ``tuning.step`` para ejecutar ``@register('standard', domain='tuning')`` **sin** arrastrar
optuna/pandas/numpy ni los backends ML (el step los carga perezosamente dentro de ``execute``;
patrón idéntico a ``ml.__init__``). Nomenclatura en inglés técnico para APIs; docstrings y errores
en español.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.tuning.config import (
    TuningConfig,
    TuningMetric,
    TuningObjectiveConfig,
    TuningPruner,
    TuningSampler,
    TuningSamplerConfig,
    TuningValidationConfig,
    ValidationStrategy,
)
from bayesrisk.tuning.exceptions import (
    TuningConfigError,
    TuningDataError,
    TuningDeterminismError,
    TuningError,
    TuningOptimizeError,
    TuningSearchSpaceError,
)
from bayesrisk.tuning.search_space import (
    CategoricalSpec,
    FloatSpec,
    IntSpec,
    ParamSpec,
    SearchSpaceConfig,
    SuggestTrial,
    default_search_space,
    suggest_params,
)

# Registra la clase real del sub-config tuning en el hook de `core` (sin importar optuna/backends).
_schema._TUNING_CONFIG_CLS = TuningConfig

# Reexports perezosos: los DTOs de resultados anotan `MLConfig`/`MLChallenger`/`pandas`; cargarlos
# arrastraría `bayesrisk.ml`, así que se difieren hasta el primer acceso (import liviano).
_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "SamplerMetadata": ("bayesrisk.tuning.results", "SamplerMetadata"),
    "TuningCardSection": ("bayesrisk.tuning.results", "TuningCardSection"),
    "TuningOptimizer": ("bayesrisk.tuning.optimizer", "TuningOptimizer"),
    "TuningResult": ("bayesrisk.tuning.results", "TuningResult"),
    "TuningStep": ("bayesrisk.tuning.step", "TuningStep"),
    "TuningTrialRecord": ("bayesrisk.tuning.results", "TuningTrialRecord"),
}

__all__ = [
    "CategoricalSpec",
    "FloatSpec",
    "IntSpec",
    "ParamSpec",
    "SamplerMetadata",
    "SearchSpaceConfig",
    "SuggestTrial",
    "TuningCardSection",
    "TuningConfig",
    "TuningConfigError",
    "TuningDataError",
    "TuningDeterminismError",
    "TuningError",
    "TuningMetric",
    "TuningObjectiveConfig",
    "TuningOptimizeError",
    "TuningOptimizer",
    "TuningPruner",
    "TuningResult",
    "TuningSampler",
    "TuningSamplerConfig",
    "TuningSearchSpaceError",
    "TuningStep",
    "TuningTrialRecord",
    "TuningValidationConfig",
    "ValidationStrategy",
    "default_search_space",
    "suggest_params",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="tuning") al importar
# `bayesrisk.tuning`, sin arrastrar optuna/pandas/numpy ni los backends ML (el step los carga en
# `execute`; mismo patrón que `bayesrisk.ml.__init__`).
importlib.import_module("bayesrisk.tuning.step")


def __getattr__(name: str) -> Any:
    """Carga los DTOs de resultados bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.tuning' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
