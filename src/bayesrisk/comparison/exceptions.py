"""Excepciones propias de la capa ``comparison`` (SDD-34 §8)."""

from bayesrisk.core.exceptions import BayesRiskError

__all__ = ["ComparisonDataError", "ComparisonError"]


class ComparisonError(BayesRiskError):
    """Error base de la comparación de corridas."""


class ComparisonDataError(ComparisonError):
    """Las corridas no se pueden comparar tal como llegaron (sin resumen, mezcladas, repetidas)."""
