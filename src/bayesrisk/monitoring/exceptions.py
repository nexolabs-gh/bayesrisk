"""Excepciones propias de la capa ``monitoring`` (SDD-33 §8)."""

from bayesrisk.core.exceptions import BayesRiskError

__all__ = ["MonitoringError", "MonitoringInputError"]


class MonitoringError(BayesRiskError):
    """Error base del monitoreo de un modelo en uso."""


class MonitoringInputError(MonitoringError):
    """La tarjeta o la cartera no se pueden monitorear tal como llegaron."""
