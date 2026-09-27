"""Excepciones propias de la capa ``governance`` (SDD-03 §8)."""

from bayesrisk.core.exceptions import BayesRiskError

__all__ = ["GovernanceError", "RegistryUnavailableError"]


class GovernanceError(BayesRiskError):
    """Error al construir evidencia de gobernanza o registrar escenarios."""


class RegistryUnavailableError(GovernanceError):
    """El inventario configurado no soporta un Registry de modelos usable."""
