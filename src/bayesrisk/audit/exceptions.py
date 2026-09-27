"""Excepciones propias de la capa ``audit`` (SDD-03 §8)."""

from bayesrisk.core.exceptions import BayesRiskError

__all__ = ["AuditError"]


class AuditError(BayesRiskError):
    """Error de persistencia, lectura o hashing del audit-trail."""
