"""Capa ``tracking`` de bayesrisk: frontera MLflow para runs e inventario (SDD-04).

Al importarse, registra :class:`TrackingConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.tracking`` se valida como sub-config real
sin que ``import bayesrisk.core`` arrastre ``bayesrisk.tracking`` ni ``mlflow``. MLflow se importa
siempre de forma perezosa dentro de los métodos que lo necesitan.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from bayesrisk.core.config import schema as _schema
from bayesrisk.governance.exceptions import RegistryUnavailableError
from bayesrisk.tracking.config import TrackingConfig
from bayesrisk.tracking.exceptions import ModelNotFoundError, TrackingError
from bayesrisk.tracking.inventory import MLflowInventory, ModelVersionRef, RegisteredModelInfo
from bayesrisk.tracking.recorder import RunHandle, TrackingRecorder
from bayesrisk.tracking.sink import TrackingSink

_schema._TRACKING_CONFIG_CLS = TrackingConfig

__all__ = [
    "MLflowInventory",
    "ModelNotFoundError",
    "ModelVersionRef",
    "RegisteredModelInfo",
    "RegistryUnavailableError",
    "RunHandle",
    "TrackingConfig",
    "TrackingError",
    "TrackingRecorder",
    "TrackingSink",
]
