"""Errores del entrenamiento LGD experimental con historia separada."""

from bayesrisk.core.exceptions import BayesRiskError, ConfigError


class LgdTrainingConfigError(ConfigError):
    """Roles de historia incompatibles."""


class LgdTrainingError(BayesRiskError):
    """Historia, ajuste o modelo que no satisface el contrato declarado."""
