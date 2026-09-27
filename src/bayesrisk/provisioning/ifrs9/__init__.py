"""Motor de provisiones IFRS 9: pérdida crediticia esperada (ECL).

Al importarse, registra :class:`IfrsProvisioningConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.provisioning_ifrs9`` se valida como
sub-config real sin que ``import bayesrisk.core`` arrastre ``bayesrisk.provisioning`` ni
dependencias numéricas pesadas (scipy/statsmodels/pandas). El motor, los resultados y el step llegan
en los bloques siguientes de SDD-16 (B16.2+); **B16.1 aporta solo config y excepciones**.
Nomenclatura IFRS 9 (regla dura D-CONV-1): ``pd``/``lgd``/``ead``.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

from bayesrisk.core.config import schema as _schema
from bayesrisk.provisioning.ifrs9.base import BaseEclModel
from bayesrisk.provisioning.ifrs9.config import (
    IfrsEadConfig,
    IfrsEclConfig,
    IfrsLgdConfig,
    IfrsPdConfig,
    IfrsProvisioningConfig,
    IfrsScenarioConfig,
    IfrsStagingConfig,
)
from bayesrisk.provisioning.ifrs9.ead import EadEngine
from bayesrisk.provisioning.ifrs9.ecl import EclEngine
from bayesrisk.provisioning.ifrs9.engine import IfrsProvisioningEngine
from bayesrisk.provisioning.ifrs9.exceptions import (
    IfrsConfigError,
    IfrsEadError,
    IfrsEclError,
    IfrsInputError,
    IfrsLgdError,
    IfrsPdError,
    IfrsProvisioningError,
    IfrsStagingError,
    IfrsTermStructureError,
)
from bayesrisk.provisioning.ifrs9.pd_pit import marginal_to_horizon, vasicek_pit
from bayesrisk.provisioning.ifrs9.results import (
    IfrsEclRecord,
    IfrsEclTermRecord,
    IfrsProvisionCard,
    IfrsProvisionResult,
    IfrsStageRecord,
)
from bayesrisk.provisioning.ifrs9.staging import StagingEngine
from bayesrisk.provisioning.ifrs9.step import (
    IFRS9_PROVISIONING_ARTIFACTS,
    IfrsProvisioningStep,
)

# D-LGD-2: el motor de LGD vive en el nivel compartido; se re-exporta aquí para no romper los
# imports que ya existían (`from bayesrisk.provisioning.ifrs9 import LgdEngine`).
from bayesrisk.provisioning.lgd import LgdEngine

# Registra la clase real del sub-config provisioning_ifrs9 en el hook de `core`.
_schema._PROVISIONING_IFRS9_CONFIG_CLS = IfrsProvisioningConfig

__all__ = [
    "IFRS9_PROVISIONING_ARTIFACTS",
    "BaseEclModel",
    "EadEngine",
    "EclEngine",
    "IfrsConfigError",
    "IfrsEadConfig",
    "IfrsEadError",
    "IfrsEclConfig",
    "IfrsEclError",
    "IfrsEclRecord",
    "IfrsEclTermRecord",
    "IfrsInputError",
    "IfrsLgdConfig",
    "IfrsLgdError",
    "IfrsPdConfig",
    "IfrsPdError",
    "IfrsProvisionCard",
    "IfrsProvisionResult",
    "IfrsProvisioningConfig",
    "IfrsProvisioningEngine",
    "IfrsProvisioningError",
    "IfrsProvisioningStep",
    "IfrsScenarioConfig",
    "IfrsStageRecord",
    "IfrsStagingConfig",
    "IfrsStagingError",
    "IfrsTermStructureError",
    "LgdEngine",
    "StagingEngine",
    "marginal_to_horizon",
    "vasicek_pit",
]
