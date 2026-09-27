"""Capa ``markov`` de bayesrisk: migración de estados y PD lifetime (SDD-19).

Al importarse, registra :class:`MarkovConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.markov`` se valida como sub-config real
sin que ``import bayesrisk.core`` arrastre ``bayesrisk.markov`` ni dependencias numéricas
opcionales. Este paquete registra su step público sin importar scipy, pandas ni numpy en top-level;
los motores concretos cargan sus dependencias dentro de ``fit``/``execute``.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.markov.config import (
    EmbeddingPolicy,
    MarkovConfig,
    MarkovDynamicsConfig,
    MarkovEstimationConfig,
    MarkovInputConfig,
    MarkovMethod,
    MarkovStateConfig,
    MarkovValidationConfig,
    ProjectionMode,
)
from bayesrisk.markov.exceptions import (
    InvalidGeneratorError,
    MarkovConfigError,
    MarkovEmbeddingError,
    MarkovError,
    MarkovFitError,
    MarkovInputError,
    MarkovTransformError,
    NonStochasticMatrixError,
)

# Registra la clase real del sub-config markov en el hook de `core`.
_schema._MARKOV_CONFIG_CLS = MarkovConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "aalen_johansen": ("bayesrisk.markov.term_structure", "aalen_johansen"),
    "chapman_kolmogorov": ("bayesrisk.markov.term_structure", "chapman_kolmogorov"),
    "diagnose_embedding": ("bayesrisk.markov.term_structure", "diagnose_embedding"),
    "markov_term_structure": ("bayesrisk.markov.term_structure", "markov_term_structure"),
    "MarkovStep": ("bayesrisk.markov.step", "MarkovStep"),
    "TransitionMatrixEstimator": (
        "bayesrisk.markov.transition",
        "TransitionMatrixEstimator",
    ),
    "validate_generator": ("bayesrisk.markov.term_structure", "validate_generator"),
    "validate_transition_matrix": (
        "bayesrisk.markov.term_structure",
        "validate_transition_matrix",
    ),
}

__all__ = [
    "EmbeddingPolicy",
    "InvalidGeneratorError",
    "MarkovConfig",
    "MarkovConfigError",
    "MarkovDynamicsConfig",
    "MarkovEmbeddingError",
    "MarkovError",
    "MarkovEstimationConfig",
    "MarkovFitError",
    "MarkovInputConfig",
    "MarkovInputError",
    "MarkovMethod",
    "MarkovStateConfig",
    "MarkovStep",
    "MarkovTransformError",
    "MarkovValidationConfig",
    "NonStochasticMatrixError",
    "ProjectionMode",
    "TransitionMatrixEstimator",
    "aalen_johansen",
    "chapman_kolmogorov",
    "diagnose_embedding",
    "markov_term_structure",
    "validate_generator",
    "validate_transition_matrix",
]

# Registra `MarkovStep` para preservar el contrato público de `import bayesrisk.markov`.
importlib.import_module("bayesrisk.markov.step")


def __getattr__(name: str) -> Any:
    """Carga estimadores Markov bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.markov' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
