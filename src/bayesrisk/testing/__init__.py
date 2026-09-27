"""Utilidades públicas de testing para extensores de bayesrisk (SDD-24).

El paquete se distribuye en el wheel para que terceros validen sus estimadores con el mismo
harness. Importarlo no carga ``hypothesis``; las estrategias lo importan de forma perezosa cuando
se solicitan.
"""

from bayesrisk.testing.estimator_checks import all_bayesrisk_checks, check_bayesrisk_estimator
from bayesrisk.testing.fixtures import dummy_step_config, golden_seed_sequence, minimal_study
from bayesrisk.testing.regulatory import (
    REGULATORY_COVERAGE_INCLUDE,
    REGULATORY_COVERAGE_PATHS,
    missing_regulatory_coverage_paths,
    regulatory_coverage_include_arg,
    regulatory_coverage_paths,
)
from bayesrisk.testing.reproducibility import assert_bitwise_reproducible
from bayesrisk.testing.strategies import bayesrisk_config_strategy, discriminated_union_tags

__all__ = [
    "REGULATORY_COVERAGE_INCLUDE",
    "REGULATORY_COVERAGE_PATHS",
    "all_bayesrisk_checks",
    "assert_bitwise_reproducible",
    "bayesrisk_config_strategy",
    "check_bayesrisk_estimator",
    "discriminated_union_tags",
    "dummy_step_config",
    "golden_seed_sequence",
    "minimal_study",
    "missing_regulatory_coverage_paths",
    "regulatory_coverage_include_arg",
    "regulatory_coverage_paths",
]
