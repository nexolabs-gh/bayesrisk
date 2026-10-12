"""Excepciones propias de la capa ``master_scale`` (SDD-32 §8)."""

from bayesrisk.core.exceptions import BayesRiskError

__all__ = ["MasterScaleError", "MasterScaleFitError"]


class MasterScaleError(BayesRiskError):
    """Error base de la escala maestra y los puntos de corte."""


class MasterScaleFitError(MasterScaleError):
    """La escala no se puede formar con las entradas o los cortes recibidos."""
