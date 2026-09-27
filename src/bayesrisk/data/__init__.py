"""Capa ``data`` de bayesrisk (SDD-02): carga, validación, target, particiones, ``data_hash``.

Al importarse, registra :class:`~bayesrisk.data.config.DataConfig` en el *hook* ``_DATA_CONFIG_CLS``
de :mod:`bayesrisk.core.config.schema`: así ``BayesRiskConfig`` valida y coacciona su sección
``data`` como :class:`DataConfig` **sin que ``core`` importe ``data``** (núcleo liviano, D-CORE-1).
La inversión de la dependencia vive en este lado (``data`` conoce a ``core``, no al revés).

.. note::
   El SDD-02 §5 preveía resolver el *forward-ref* con ``BayesRiskConfig.model_rebuild()``; se
   descartó porque Pydantic v2 **no re-narra** un campo ya resuelto (verificado, B2a). El *hook* +
   validador es el reemplazo: valida en construcción y mantiene el núcleo liviano.

**Estable (SemVer 2.x).**
"""

from bayesrisk.core.config import schema as _schema
from bayesrisk.data.card import DataCardSection
from bayesrisk.data.config import DataConfig
from bayesrisk.data.hashing import data_hash
from bayesrisk.data.loading import DataLoader
from bayesrisk.data.partition import Partitioner, PartitionResult
from bayesrisk.data.schema import SchemaValidator
from bayesrisk.data.special import MaskedFrame, SpecialValuePolicy
from bayesrisk.data.step import DataStep
from bayesrisk.data.target import LabeledFrame, TargetDefinition

# Registra la clase real del sub-config de datos en el hook de `core`.
_schema._DATA_CONFIG_CLS = DataConfig

__all__ = [
    "DataCardSection",
    "DataConfig",
    "DataLoader",
    "DataStep",
    "LabeledFrame",
    "MaskedFrame",
    "PartitionResult",
    "Partitioner",
    "SchemaValidator",
    "SpecialValuePolicy",
    "TargetDefinition",
    "data_hash",
]
