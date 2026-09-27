"""Capa ``selection`` de bayesrisk: selección pre-modelo de variables WoE (SDD-07).

Al importarse, registra :class:`SelectionConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.selection`` se valida como sub-config
real sin que ``import bayesrisk.core`` arrastre ``bayesrisk.selection`` ni dependencias de scoring.
La lógica pesada de selección (``selector.py``) se carga bajo demanda; el paquete importa
``selection.step`` al final para ejecutar ``@register("standard", domain="selection")`` sin
arrastrar dependencias de scoring.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.selection.config import (
    CorrelationSelectionConfig,
    SelectionConfig,
    SelectionPriority,
    StabilitySelectionConfig,
    VifSelectionConfig,
)
from bayesrisk.selection.exceptions import (
    SelectionError,
    SelectionFitError,
    SelectionForcedVifConflictError,
    SelectionTransformError,
)

# Registra la clase real del sub-config selection en el hook de `core`.
_schema._SELECTION_CONFIG_CLS = SelectionConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "FeatureSelector": ("bayesrisk.selection.selector", "FeatureSelector"),
    "SelectionCardSection": ("bayesrisk.selection.results", "SelectionCardSection"),
    "SelectionDecisionReason": ("bayesrisk.selection.results", "SelectionDecisionReason"),
    "SelectionResult": ("bayesrisk.selection.results", "SelectionResult"),
    "SelectionStep": ("bayesrisk.selection.step", "SelectionStep"),
    "VariableSelectionDecision": (
        "bayesrisk.selection.results",
        "VariableSelectionDecision",
    ),
}

__all__ = [
    "CorrelationSelectionConfig",
    "FeatureSelector",
    "SelectionCardSection",
    "SelectionConfig",
    "SelectionDecisionReason",
    "SelectionError",
    "SelectionFitError",
    "SelectionForcedVifConflictError",
    "SelectionPriority",
    "SelectionResult",
    "SelectionStep",
    "SelectionTransformError",
    "StabilitySelectionConfig",
    "VariableSelectionDecision",
    "VifSelectionConfig",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="selection") al
# importar `bayesrisk.selection`, sin contaminar `import bayesrisk.core` ni cargar scoring.
importlib.import_module("bayesrisk.selection.step")


def __getattr__(name: str) -> Any:
    """Carga componentes pesados de selection bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.selection' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
