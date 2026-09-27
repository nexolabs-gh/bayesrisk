"""Tests de la jerarquía de excepciones (SDD-01 §4): toda excepción cuelga de BayesRiskError."""

import pytest

from bayesrisk.core import exceptions as exc

# Pares (subclase, padre directo esperado) que fijan la forma del árbol.
HIERARCHY: list[tuple[type[exc.BayesRiskError], type[exc.BayesRiskError]]] = [
    (exc.ConfigError, exc.BayesRiskError),
    (exc.ConfigVersionError, exc.ConfigError),
    (exc.MigrationNotFoundError, exc.ConfigError),
    (exc.DataValidationError, exc.BayesRiskError),
    (exc.NotFittedError, exc.BayesRiskError),
    (exc.RegistryError, exc.BayesRiskError),
    (exc.UnknownComponentError, exc.RegistryError),
    (exc.DuplicateRegistrationError, exc.RegistryError),
    (exc.ArtifactNotFoundError, exc.BayesRiskError),
    (exc.ArtifactExistsError, exc.BayesRiskError),
    (exc.ReproducibilityError, exc.BayesRiskError),
    (exc.UntrustedStudyError, exc.BayesRiskError),
    (exc.RegulatoryError, exc.BayesRiskError),
    (exc.MissingDependencyError, exc.BayesRiskError),
]


@pytest.mark.parametrize(("child", "parent"), HIERARCHY)
def test_direct_parent(child: type[exc.BayesRiskError], parent: type[exc.BayesRiskError]) -> None:
    """Cada subclase tiene el padre directo esperado."""
    assert issubclass(child, parent)


@pytest.mark.parametrize("klass", [child for child, _ in HIERARCHY])
def test_all_descend_from_root(klass: type[exc.BayesRiskError]) -> None:
    """Toda excepción del núcleo desciende de BayesRiskError (regla única)."""
    assert issubclass(klass, exc.BayesRiskError)


def test_root_is_exception() -> None:
    """BayesRiskError es una Exception estándar (capturable con except BayesRiskError)."""
    assert issubclass(exc.BayesRiskError, Exception)


def test_except_root_catches_subclass() -> None:
    """``except BayesRiskError`` captura cualquier subclase concreta."""
    with pytest.raises(exc.BayesRiskError):
        raise exc.MissingDependencyError("falta el extra")


def test_all_exported_names_exist() -> None:
    """Cada nombre de ``__all__`` existe y es subclase de BayesRiskError."""
    for name in exc.__all__:
        obj = getattr(exc, name)
        assert issubclass(obj, exc.BayesRiskError)
