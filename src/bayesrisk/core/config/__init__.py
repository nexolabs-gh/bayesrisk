"""Subpaquete de configuración declarativa de bayesrisk (SDD-01 §4-5, SDD-05 §5).

Re-exporta la superficie pública del config: el schema (:class:`BayesRiskConfig` y sus secciones),
la identidad por :func:`config_hash`, la carga/volcado YAML (:func:`load_config` /
:func:`dump_config`) y el mecanismo de migración (:func:`migrate`, :func:`migration`).
"""

from bayesrisk.core.config.hashing import INFRA_SECTIONS, config_hash
from bayesrisk.core.config.loader import dump_config, load_config, loads_config
from bayesrisk.core.config.migration import SCHEMA_VERSION, migrate, migration
from bayesrisk.core.config.schema import (
    BayesRiskBaseConfig,
    BayesRiskConfig,
    DecisionEntry,
    ReproConfig,
    RunConfig,
    declara_esenciales,
)
from bayesrisk.core.config.schema import NikodymBaseConfig as NikodymBaseConfig  # D-REN-3
from bayesrisk.core.config.schema import NikodymConfig as NikodymConfig  # D-REN-3

__all__ = [
    "INFRA_SECTIONS",
    "SCHEMA_VERSION",
    "BayesRiskBaseConfig",
    "BayesRiskConfig",
    "DecisionEntry",
    "NikodymBaseConfig",
    "NikodymConfig",
    "ReproConfig",
    "RunConfig",
    "config_hash",
    "declara_esenciales",
    "dump_config",
    "load_config",
    "loads_config",
    "migrate",
    "migration",
]
