"""Excepciones propias de la capa ``eda`` (SDD-27 §8)."""

from bayesrisk.core.exceptions import BayesRiskError

__all__ = ["EdaError"]


class EdaError(BayesRiskError):
    """Error en el análisis exploratorio descriptivo de riesgo de crédito."""
