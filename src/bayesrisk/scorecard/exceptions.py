"""Excepciones propias de la capa ``scorecard`` (SDD-09 §8)."""

from bayesrisk.core.exceptions import BayesRiskError

__all__ = [
    "ScorecardBundleError",
    "ScorecardError",
    "ScorecardFitError",
    "ScorecardTransformError",
]


class ScorecardError(BayesRiskError):
    """Error base del escalamiento log-odds a puntos de scorecard."""


class ScorecardFitError(ScorecardError):
    """Error al derivar la tabla de puntos desde modelo y binning."""


class ScorecardTransformError(ScorecardError):
    """Error al transformar variables WoE a puntos y score total."""


class ScorecardBundleError(ScorecardError):
    """Error al construir, verificar o aplicar un bundle público seguro."""
