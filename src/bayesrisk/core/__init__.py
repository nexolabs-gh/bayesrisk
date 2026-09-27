"""Núcleo (``core``) de bayesrisk: fundación *stateful* y agnóstica al dominio (SDD-01).

Aloja el estado del experimento (``Study``), el config declarativo, el ``Registry``, la
siembra determinista (:class:`~bayesrisk.core.seeding.SeedManager`), el lineage y la jerarquía de
excepciones. ``core`` no depende de scikit-learn ni de ningún backend pesado (D-CORE-1). La
superficie pública se re-exporta aquí a medida que se construyen los submódulos de la Fundación.
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.artifacts import ArtifactStore
from bayesrisk.core.audit import (
    AuditEvent,
    AuditKind,
    AuditSink,
    FanOutSink,
    InMemoryAuditSink,
    NullAuditSink,
)
from bayesrisk.core.base import (
    BaseBayesRiskEstimator,
    BaseECLModel,
    BaseForecaster,
    BaseProvisionModel,
    BaseSurvivalEstimator,
    BayesRiskClassifier,
    BayesRiskTransformer,
)

# Nombres anteriores al renombre (D-REN-3): alias del mismo objeto, en `__all__` como en 1.20.
from bayesrisk.core.base import BaseNikodymEstimator as BaseNikodymEstimator
from bayesrisk.core.base import NikodymClassifier as NikodymClassifier
from bayesrisk.core.base import NikodymTransformer as NikodymTransformer
from bayesrisk.core.config import (
    INFRA_SECTIONS,
    SCHEMA_VERSION,
    BayesRiskBaseConfig,
    BayesRiskConfig,
    ReproConfig,
    RunConfig,
    config_hash,
    dump_config,
    load_config,
    loads_config,
    migrate,
    migration,
)
from bayesrisk.core.config import NikodymBaseConfig as NikodymBaseConfig
from bayesrisk.core.config import NikodymConfig as NikodymConfig
from bayesrisk.core.exceptions import (
    ArtifactExistsError,
    ArtifactNotFoundError,
    BayesRiskError,
    ConfigError,
    ConfigVersionError,
    DataValidationError,
    DuplicateRegistrationError,
    MigrationNotFoundError,
    MissingDependencyError,
    NotFittedError,
    RegistryError,
    RegulatoryError,
    ReproducibilityError,
    UnknownComponentError,
    UntrustedStudyError,
)
from bayesrisk.core.exceptions import NikodymError as NikodymError
from bayesrisk.core.lineage import LineageBundle, RunContext
from bayesrisk.core.markers import (
    DECLARED_MARKERS,
    INSTITUTIONAL_MARKER,
    MISSING_DATA_MARKER,
    declared_prefixes,
    is_declared_warning,
)
from bayesrisk.core.mixins import AuditableMixin, SerializationMixin
from bayesrisk.core.registry import REGISTRY, Registry, register, unregister
from bayesrisk.core.results import ECLResultLike, ProvisionResultLike
from bayesrisk.core.steps import ArtifactKey, Step, StepAdapter

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "SeedManager": ("bayesrisk.core.seeding", "SeedManager"),
    "Study": ("bayesrisk.core.study", "Study"),
}

__all__ = [
    "DECLARED_MARKERS",
    "INFRA_SECTIONS",
    "INSTITUTIONAL_MARKER",
    "MISSING_DATA_MARKER",
    "REGISTRY",
    "SCHEMA_VERSION",
    "ArtifactExistsError",
    "ArtifactKey",
    "ArtifactNotFoundError",
    "ArtifactStore",
    "AuditEvent",
    "AuditKind",
    "AuditSink",
    "AuditableMixin",
    "BaseBayesRiskEstimator",
    "BaseECLModel",
    "BaseForecaster",
    "BaseNikodymEstimator",
    "BaseProvisionModel",
    "BaseSurvivalEstimator",
    "BayesRiskBaseConfig",
    "BayesRiskClassifier",
    "BayesRiskConfig",
    "BayesRiskError",
    "BayesRiskTransformer",
    "ConfigError",
    "ConfigVersionError",
    "DataValidationError",
    "DuplicateRegistrationError",
    "ECLResultLike",
    "FanOutSink",
    "InMemoryAuditSink",
    "LineageBundle",
    "MigrationNotFoundError",
    "MissingDependencyError",
    "NikodymBaseConfig",
    "NikodymClassifier",
    "NikodymConfig",
    "NikodymError",
    "NikodymTransformer",
    "NotFittedError",
    "NullAuditSink",
    "ProvisionResultLike",
    "Registry",
    "RegistryError",
    "RegulatoryError",
    "ReproConfig",
    "ReproducibilityError",
    "RunConfig",
    "RunContext",
    "SeedManager",
    "SerializationMixin",
    "Step",
    "StepAdapter",
    "Study",
    "UnknownComponentError",
    "UntrustedStudyError",
    "config_hash",
    "declared_prefixes",
    "dump_config",
    "is_declared_warning",
    "load_config",
    "loads_config",
    "migrate",
    "migration",
    "register",
    "unregister",
]


def __getattr__(name: str) -> Any:
    """Carga exports stateful bajo demanda para preservar el núcleo liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.core' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
