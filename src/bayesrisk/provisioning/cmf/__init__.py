"""Motor de provisiones CMF (Chile): ``PE = PI·PDI·Exposición`` (B-1).

Al importarse, registra :class:`CmfProvisioningConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.provisioning_cmf`` se valida como
sub-config real sin que ``import bayesrisk.core`` arrastre ``bayesrisk.provisioning`` ni
dependencias tabulares pesadas. Nomenclatura CMF (regla dura D-CONV-1): ``pi``/``pdi``/``pe``, nunca
``pd``/``lgd``/``ead``.

El paquete importa ``provisioning.cmf.step`` al final para ejecutar ``@register("standard",
domain="provisioning_cmf")`` sin cargar pandas, matrices ni el motor; los resultados y componentes
con dependencias de cálculo se reexportan de forma perezosa.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.provisioning.cmf.config import (
    CmfExposureConfig,
    CmfFinancialGuaranteePolicy,
    CmfGuaranteeConfig,
    CmfMatrixConfig,
    CmfPdMappingConfig,
    CmfPdMappingMethod,
    CmfPdSourceDomain,
    CmfProvisioningConfig,
    CmfRoundingPolicy,
)
from bayesrisk.provisioning.cmf.exceptions import (
    CmfCalculationError,
    CmfConfigError,
    CmfInputError,
    CmfMappingError,
    CmfMatrixError,
    CmfMissingRegulatoryDataError,
    CmfProvisioningError,
)

# Registra la clase real del sub-config provisioning_cmf en el hook de `core`.
_schema._PROVISIONING_CMF_CONFIG_CLS = CmfProvisioningConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "CMF_PROVISIONING_ARTIFACTS": (
        "bayesrisk.provisioning.cmf.step",
        "CMF_PROVISIONING_ARTIFACTS",
    ),
    "CMF_MATRIX_IDS": ("bayesrisk.provisioning.cmf.matrices", "CMF_MATRIX_IDS"),
    "CmfMatrixBundle": ("bayesrisk.provisioning.cmf.matrices", "CmfMatrixBundle"),
    "CmfMatrixManifest": ("bayesrisk.provisioning.cmf.matrices", "CmfMatrixManifest"),
    "CmfMatrixRow": ("bayesrisk.provisioning.cmf.matrices", "CmfMatrixRow"),
    "CmfPortfolioSummary": ("bayesrisk.provisioning.cmf.results", "CmfPortfolioSummary"),
    "CmfProvisionCard": ("bayesrisk.provisioning.cmf.results", "CmfProvisionCard"),
    "CmfProvisionRecord": ("bayesrisk.provisioning.cmf.results", "CmfProvisionRecord"),
    "CmfProvisionResult": ("bayesrisk.provisioning.cmf.results", "CmfProvisionResult"),
    "CmfProvisioningEngine": ("bayesrisk.provisioning.cmf.engine", "CmfProvisioningEngine"),
    "CmfProvisioningStep": ("bayesrisk.provisioning.cmf.step", "CmfProvisioningStep"),
    "load_cmf_matrices": ("bayesrisk.provisioning.cmf.matrices", "load_cmf_matrices"),
    "validate_cmf_matrix_bundle": (
        "bayesrisk.provisioning.cmf.matrices",
        "validate_cmf_matrix_bundle",
    ),
}

__all__ = [
    "CMF_MATRIX_IDS",
    "CMF_PROVISIONING_ARTIFACTS",
    "CmfCalculationError",
    "CmfConfigError",
    "CmfExposureConfig",
    "CmfFinancialGuaranteePolicy",
    "CmfGuaranteeConfig",
    "CmfInputError",
    "CmfMappingError",
    "CmfMatrixBundle",
    "CmfMatrixConfig",
    "CmfMatrixError",
    "CmfMatrixManifest",
    "CmfMatrixRow",
    "CmfMissingRegulatoryDataError",
    "CmfPdMappingConfig",
    "CmfPdMappingMethod",
    "CmfPdSourceDomain",
    "CmfPortfolioSummary",
    "CmfProvisionCard",
    "CmfProvisionRecord",
    "CmfProvisionResult",
    "CmfProvisioningConfig",
    "CmfProvisioningEngine",
    "CmfProvisioningError",
    "CmfProvisioningStep",
    "CmfRoundingPolicy",
    "load_cmf_matrices",
    "validate_cmf_matrix_bundle",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="provisioning_cmf") al
# importar `bayesrisk.provisioning.cmf`, sin contaminar `import bayesrisk.core` ni cargar pandas,
# matrices o el motor.
importlib.import_module("bayesrisk.provisioning.cmf.step")


def __getattr__(name: str) -> Any:
    """Carga componentes de ``provisioning.cmf`` bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.provisioning.cmf' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
