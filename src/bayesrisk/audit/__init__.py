"""Capa ``audit`` de bayesrisk: JSONL, entorno, hashing y replay (SDD-03).

Al importarse, registra :class:`AuditConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.audit`` se valida como sub-config real
sin que ``import bayesrisk.core`` arrastre ``bayesrisk.audit`` ni sus dependencias perezosas.

**Estable (SemVer 2.x).**
"""

from bayesrisk.audit.config import AuditConfig
from bayesrisk.audit.environment import (
    DEFAULT_TRACKED_PACKAGES,
    EnvironmentSnapshot,
    capture_environment,
)
from bayesrisk.audit.exceptions import AuditError
from bayesrisk.audit.hashing import hash_dataframe, hash_file
from bayesrisk.audit.replay import iter_trail, read_trail
from bayesrisk.audit.sink import JsonlAuditSink
from bayesrisk.core.config import schema as _schema

_schema._AUDIT_CONFIG_CLS = AuditConfig

__all__ = [
    "DEFAULT_TRACKED_PACKAGES",
    "AuditConfig",
    "AuditError",
    "EnvironmentSnapshot",
    "JsonlAuditSink",
    "capture_environment",
    "hash_dataframe",
    "hash_file",
    "iter_trail",
    "read_trail",
]
