"""Entrenamiento LGD con historia separada.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any

from bayesrisk.core.config import schema as _schema
from bayesrisk.lgd_training.config import LgdTrainingConfig
from bayesrisk.lgd_training.exceptions import LgdTrainingConfigError, LgdTrainingError

_schema._LGD_TRAINING_CONFIG_CLS = LgdTrainingConfig
importlib.import_module("bayesrisk.lgd_training.step")

__all__ = [
    "LgdModel",
    "LgdTrainingConfig",
    "LgdTrainingConfigError",
    "LgdTrainingError",
    "LgdTrainingStep",
]


def __getattr__(name: str) -> Any:
    """Mantiene pandas/numpy/statsmodels fuera del import declarativo."""
    modules = {"LgdModel": "model", "LgdTrainingStep": "step"}
    if name not in modules:
        raise AttributeError(name)
    value = getattr(importlib.import_module(f"bayesrisk.lgd_training.{modules[name]}"), name)
    globals()[name] = value
    return value
