"""Jerarquía de excepciones de bayesrisk (SDD-01 §4, SDD-05 §4.3).

Regla única: toda excepción de la librería desciende de :class:`BayesRiskError`, de modo que
``except BayesRiskError`` captura cualquier fallo propio sin tener que enumerar cada clase.
``core.exceptions`` aloja la **raíz** y las excepciones del **núcleo**; los módulos de dominio
definen sus propias subclases (de :class:`BayesRiskError` o de la excepción de core que
corresponda) en su propio módulo. Los mensajes van en **español** e incluyen, cuando aplica,
la regla, el umbral gatillante y el valor observado (auditabilidad, §4 principio 2).
"""

from collections.abc import Sequence

__all__ = [
    "ArtifactExistsError",
    "ArtifactNotFoundError",
    "BayesRiskError",
    "ConfigError",
    "ConfigVersionError",
    "DataValidationError",
    "DuplicateRegistrationError",
    "MigrationNotFoundError",
    "MissingDependencyError",
    "NikodymError",
    "NotFittedError",
    "RegistryError",
    "RegulatoryError",
    "ReproducibilityError",
    "UnknownComponentError",
    "UntrustedStudyError",
]


class BayesRiskError(Exception):
    """Raíz de toda excepción de la librería bayesrisk.

    Puede declarar ``loc``: la ruta del campo del config al que pertenece el fallo (D-EXI-5).

    🔴 **Por qué existe y por qué la declara el EMISOR.** Un error de dominio viaja a
    ``/api/validate`` con la misma forma que uno de Pydantic, y el front indexa por ``loc`` para
    pintarlo junto a su campo y ofrecer el salto. Hasta el 2026-08-08 salía siempre con ``loc: []``,
    con la razón correcta escrita en el traductor: **fabricarlo a partir del texto del mensaje sería
    adivinar**. La consecuencia, medida: elegir `provisioning_internal.lgd.method='beta_regression'`
    dejaba «Config inválido · 1 error» **sin campo al que saltar**, mientras el gesto simétrico
    —elegir una partición temporal sin su columna de fecha— sí marca el suyo. La salida no es
    adivinar: es que quien levanta el error diga a qué campo pertenece.

    ⚠️ La ruta es **absoluta desde la raíz del config** (``("provisioning_internal", "lgd",
    "covariate_cols")``), porque el ``except`` que la traduce vive en el endpoint y atrapa la
    validación del ``BayesRiskConfig`` entero: ahí ya no se sabe qué sección la emitió. Que eso ate
    al emisor con el nombre de su sección es el precio, y lo cubre un gate que exige que **toda ruta
    declarada resuelva contra ``BayesRiskConfig``** — así, renombrar una sección se pone rojo en vez
    de dejar el error apuntando al vacío. Mismo trato que la clave ``exige`` del abanico (D-EXI-2).

    ⚠️ Y es **atributo de clase con default vacío**, no un parámetro obligatorio: las 131 subclases
    existentes lo heredan sin tocar una línea, y la única que define su propio ``__init__``
    (``CalibrationOffsetExceededError``) sigue funcionando igual. Un error sin ``loc`` significa «no
    pertenece a un campo», que es la verdad de un invariante entre varios —el caso para el que el
    ``loc: []`` se escribió— y no un olvido.
    """

    loc: tuple[str | int, ...] = ()

    def __init__(self, *args: object, loc: Sequence[str | int] = ()) -> None:
        super().__init__(*args)
        if loc:
            self.loc = tuple(loc)


class ConfigError(BayesRiskError):
    """Config inválido: campo desconocido, tipo/rango erróneo o mutación de un config frozen."""


class ConfigVersionError(ConfigError):
    """El ``schema_version`` del config es mayor que el del paquete (config "del futuro")."""


class MigrationNotFoundError(ConfigError):
    """Falta un migrador registrado para saltar de una ``schema_version`` a otra."""


class DataValidationError(BayesRiskError):
    """Los datos no cumplen el contrato de esquema/calidad esperado."""


class NotFittedError(BayesRiskError):
    """Se invocó ``predict``/``transform``/``compute`` antes de ``fit``.

    Desciende solo de :class:`BayesRiskError` (D-CORE-5): un ``except`` sobre la
    ``NotFittedError`` de scikit-learn no la atrapa. Un estimador de dominio que necesite
    capturar ambas puede definir localmente una subclase multiherencia.
    """


class RegistryError(BayesRiskError):
    """Error genérico del registro de componentes (``Registry``)."""


class UnknownComponentError(RegistryError):
    """Se solicitó un componente ``(domain, name)`` no registrado."""


class DuplicateRegistrationError(RegistryError):
    """Se registró dos veces la misma pareja ``(domain, name)`` (detectado en import time)."""


class ArtifactNotFoundError(BayesRiskError):
    """Se solicitó un artefacto ``(domain, key)`` ausente del ``ArtifactStore``."""


class ArtifactExistsError(BayesRiskError):
    """Se intentó escribir un artefacto ``(domain, key)`` ya presente sin ``overwrite=True``."""


class ReproducibilityError(BayesRiskError):
    """El ``config_hash`` no coincide al recargar un ``Study`` (señal de manipulación)."""


class UntrustedStudyError(BayesRiskError):
    """Se cargó con ``trust=False`` un ``Study`` de origen no verificado (vector pickle)."""


class RegulatoryError(BayesRiskError):
    """Violación de una regla regulatoria dura (p. ej. la regla B-1; SDD-15/17/28)."""


class MissingDependencyError(BayesRiskError):
    """Se usó un backend opcional sin instalar su *extra* (import perezoso; SDD-25)."""


#: Nombres anteriores al renombre (nikodym ≤ 1.20): alias del MISMO objeto, sin aviso, para que
#: el código y los pickles escritos para nikodym sigan resolviendo (enmienda
#: RENOMBRE-BAYESRISK, D-REN-3). En ``__all__`` como en 1.20 (``import *``); se retiran en 3.0.
NikodymError = BayesRiskError
