"""Gate de la marca de estabilidad: la etiqueta SemVer tiene que ser derivable, no decorativa.

`AGENTS.md` promete que el pipeline scorecard F1 es API estable bajo SemVer 2.x. Hasta 1.11.0 la
promesa se contradecía **en las dos direcciones a la vez** y ningún test lo notaba:

- ``model`` —la regresión logística PD del propio F1— se autodeclaraba *experimental*;
- ``audit`` —que no es F1— se autodeclaraba *estable*;
- ``docs_site/api.md`` publicaba una tercera lista, sin ``model``, y decía traer las firmas de
  ``1.4.0`` en un paquete ``1.11.0``.

Tres fuentes, tres respuestas distintas: para quien instala con ``pip``, la etiqueta no significaba
nada. Este gate ata las tres a :mod:`bayesrisk.testing.stability`, que es la única que decide.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from bayesrisk import __version__
from bayesrisk.testing.stability import (
    EXPERIMENTAL_DOMAINS,
    EXPERIMENTAL_SYMBOLS,
    STABLE_DOMAINS,
    UNMARKED_PACKAGES,
    declared_stability,
    domain_packages,
)

_RAIZ: Final = Path(__file__).resolve().parents[2]
_API_MD: Final = _RAIZ / "docs_site" / "api.md"

#: `docs_site/` no viaja en el sdist (`pyproject.toml` incluye sólo `/src` y `/tests`), así que los
#: dos tests que cotejan la referencia pública no tienen qué leer cuando la suite corre desde un
#: paquete distribuido. Se saltan **sólo ahí**: en un checkout —que es donde el gate tiene que
#: morder— el archivo existe y `test_la_referencia_publica_existe_en_el_checkout` lo exige.
_ES_CHECKOUT: Final = (_RAIZ / "pyproject.toml").is_file() and (_RAIZ / ".git").exists()
_sin_docs = pytest.mark.skipif(
    not _ES_CHECKOUT, reason="docs_site/ no viaja en el sdist; el gate es de checkout y CI"
)


def test_la_referencia_publica_existe_en_el_checkout() -> None:
    """Impide que el `skipif` de abajo se coma el gate dentro del propio repositorio."""
    if not _ES_CHECKOUT:
        pytest.skip("fuera de un checkout")
    assert _API_MD.is_file()


def test_el_censo_de_paquetes_no_esta_vacio() -> None:
    """Sin esto, una raíz mal apuntada dejaría todo el gate verde recorriendo cero paquetes."""
    assert len(domain_packages()) >= 20


def test_cada_paquete_del_arbol_esta_clasificado() -> None:
    """Un paquete nuevo que nadie clasificó es exactamente como se rompe un censo en silencio."""
    clasificados = {*STABLE_DOMAINS, *EXPERIMENTAL_DOMAINS, *UNMARKED_PACKAGES}
    sin_clasificar = [p for p in domain_packages() if p not in clasificados]
    assert sin_clasificar == []


def test_ninguna_lista_nombra_un_paquete_que_ya_no_existe() -> None:
    """El sentido inverso: una lista que envejece deja de gatear lo que dice gatear."""
    arbol = set(domain_packages())
    fantasmas = [
        p for p in (*STABLE_DOMAINS, *EXPERIMENTAL_DOMAINS, *UNMARKED_PACKAGES) if p not in arbol
    ]
    assert fantasmas == []


def test_ningun_paquete_esta_en_dos_listas() -> None:
    todos = [*STABLE_DOMAINS, *EXPERIMENTAL_DOMAINS, *UNMARKED_PACKAGES]
    duplicados = sorted({p for p in todos if todos.count(p) > 1})
    assert duplicados == []


@pytest.mark.parametrize("dominio", STABLE_DOMAINS)
def test_un_dominio_estable_lo_declara_en_su_cabecera(dominio: str) -> None:
    """La promesa de AGENTS.md tiene que estar escrita donde el usuario la lee: el docstring."""
    assert declared_stability(dominio) == "estable"


@pytest.mark.parametrize("dominio", EXPERIMENTAL_DOMAINS)
def test_un_dominio_experimental_lo_declara_en_su_cabecera(dominio: str) -> None:
    """El otro sentido: una superficie que aún crece no puede colarse en la garantía."""
    assert declared_stability(dominio) == "experimental"


@pytest.mark.parametrize("paquete", UNMARKED_PACKAGES)
def test_un_paquete_de_infraestructura_no_lleva_marca_por_dominio(paquete: str) -> None:
    """Si mañana se le pone marca, la decisión pasa por esta lista y no por un docstring suelto."""
    assert declared_stability(paquete) is None


def test_model_esta_bajo_garantia_porque_es_el_corazon_de_f1() -> None:
    """Regresión del defecto concreto: la logística PD quedaba fuera de la garantía que la cubre."""
    assert "model" in STABLE_DOMAINS
    assert declared_stability("model") == "estable"


@_sin_docs
def test_la_referencia_publica_declara_la_version_del_paquete() -> None:
    """`api.md` decía publicar firmas de `1.4.0` mientras el paquete iba por `1.11.0`."""
    versiones = re.findall(r"`(\d+\.\d+\.\d+)`", _API_MD.read_text(encoding="utf-8"))
    assert __version__ in versiones, f"api.md no nombra la versión {__version__}: {versiones}"


@_sin_docs
@pytest.mark.parametrize("dominio", STABLE_DOMAINS)
def test_la_referencia_publica_enumera_cada_dominio_estable(dominio: str) -> None:
    """Tercera fuente atada: lo que el visitante lee tiene que ser la misma lista que el código."""
    nota = _API_MD.read_text(encoding="utf-8").split("## ", 1)[0]
    assert f"`{dominio}`" in nota, f"api.md no enumera '{dominio}' entre los dominios estables"


#: El literal exacto de la marca experimental, el mismo que lee :func:`declared_stability`.
_MARCA_EXPERIMENTAL: Final = "**Experimental (fuera de la garantía SemVer 2.x).**"


def test_ecl_es_estable_desde_la_capa_b_de_su_enmienda() -> None:
    """D-ECL-9: la excepción por símbolo de `Ecl` se retiró al cerrar la capa B (S31).

    Su firma vive en `guided`, estable, y ya no lleva la marca experimental literal ni en la clase
    ni en su módulo; la marca de sus cifras es la de `survival` y `provisioning`.
    """
    import bayesrisk.guided.ecl as modulo

    assert "bayesrisk.guided.ecl.Ecl" not in EXPERIMENTAL_SYMBOLS
    assert _MARCA_EXPERIMENTAL not in (modulo.Ecl.__doc__ or "")
    assert _MARCA_EXPERIMENTAL not in (modulo.__doc__ or "")
    assert {"survival", "provisioning"} <= set(EXPERIMENTAL_DOMAINS)


@pytest.mark.parametrize("simbolo", sorted(EXPERIMENTAL_SYMBOLS))
def test_un_simbolo_experimental_vive_en_un_dominio_estable_y_lo_declara(simbolo: str) -> None:
    """La excepción por símbolo (D-ECL-9): sólo tiene sentido dentro de un dominio estable, y el
    símbolo y su módulo llevan la marca experimental literal en su docstring."""
    import importlib

    modulo, _, nombre = simbolo.rpartition(".")
    paquete = modulo.split(".")[1]
    assert paquete in STABLE_DOMAINS, f"{simbolo}: la excepción sobra fuera de un dominio estable"
    objeto = getattr(importlib.import_module(modulo), nombre)
    assert _MARCA_EXPERIMENTAL in (objeto.__doc__ or ""), simbolo
    assert _MARCA_EXPERIMENTAL in (importlib.import_module(modulo).__doc__ or ""), modulo


@_sin_docs
@pytest.mark.parametrize("simbolo", sorted(EXPERIMENTAL_SYMBOLS))
def test_la_referencia_publica_declara_experimental_cada_simbolo_exceptuado(simbolo: str) -> None:
    nombre = simbolo.rpartition(".")[2]
    texto = _API_MD.read_text(encoding="utf-8")
    assert f"bayesrisk.{nombre}" in texto and "experimental" in texto.casefold(), simbolo
    assert f"::: {simbolo}" in texto, f"api.md no publica la referencia de {simbolo}"
