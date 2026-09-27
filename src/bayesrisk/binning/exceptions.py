"""Excepciones propias de la capa ``binning`` (SDD-06 §8)."""

from bayesrisk.core.exceptions import BayesRiskError

__all__ = ["BinningError", "BinningFitError", "BinningTransformError"]


class BinningError(BayesRiskError):
    """Error base del binning supervisado WoE/IV para scorecard."""


class BinningFitError(BinningError):
    """Error al ajustar bins supervisados sobre la partición de Desarrollo."""


class BinningTransformError(BinningError):
    """Error al transformar variables crudas a columnas WoE con bins fiteados."""
