"""Capa ``governance`` de bayesrisk: model card, inventario y escenarios (SDD-03).

Al importarse, registra :class:`GovernanceConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.governance`` se valida como sub-config
real sin que ``import bayesrisk.core`` arrastre ``bayesrisk.governance``.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from bayesrisk.core.config import schema as _schema
from bayesrisk.governance.config import GovernanceConfig
from bayesrisk.governance.exceptions import GovernanceError, RegistryUnavailableError
from bayesrisk.governance.inventory import (
    InventoryEntry,
    InventoryRecord,
    ModelInventory,
    NullInventory,
    publish_inventory,
)
from bayesrisk.governance.labels import (
    ESTADO_VALIDACION_LABELS,
    FASE_LABELS,
    MOTOR_LABELS,
    governance_label,
)
from bayesrisk.governance.model_card import DecisionRecord, ModelCard, ModelCardBuilder
from bayesrisk.governance.scenarios import OverlayRecord, ScenarioLog, ScenarioRecord

_schema._GOVERNANCE_CONFIG_CLS = GovernanceConfig

__all__ = [
    "ESTADO_VALIDACION_LABELS",
    "FASE_LABELS",
    "MOTOR_LABELS",
    "DecisionRecord",
    "GovernanceConfig",
    "GovernanceError",
    "InventoryEntry",
    "InventoryRecord",
    "ModelCard",
    "ModelCardBuilder",
    "ModelInventory",
    "NullInventory",
    "OverlayRecord",
    "RegistryUnavailableError",
    "ScenarioLog",
    "ScenarioRecord",
    "governance_label",
    "publish_inventory",
]
