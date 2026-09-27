"""Coteja, archivo por archivo, lo que se va a publicar contra lo que PyPI ya sirve (D-REN-11).

La consulta por versión no basta (pasada 2 de Codex sobre la enmienda RENOMBRE-BAYESRISK): una
subida que falla a medias deja la versión «existente» con un archivo de menos, y un reintento que
mira sólo la versión la da por publicada. Aquí la unidad es el archivo y su SHA-256:

``--antes``
    Por cada archivo local: si PyPI ya lo sirve con los mismos bytes, se omitirá; si lo sirve con
    OTROS bytes, se detiene en rojo (nunca re-subir un número con contenido distinto); si falta,
    se subirá. Imprime el plan y sale en 0 salvo divergencia.
``--despues``
    Exige que PyPI sirva TODOS los archivos locales con sus SHA-256; reintenta mientras el JSON de
    PyPI se actualiza (plazo acotado) y sale en rojo si no llegan.

Uso:  python scripts/pypi_cotejar_publicacion.py (--antes|--despues) <proyecto> <version> <dist-dir>
      [--indice https://pypi.org] [--plazo-segundos 600]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

Consulta = Callable[[str], dict[str, str] | None]


def servidos_por_pypi(indice: str, proyecto: str, version: str) -> dict[str, str] | None:
    """``{nombre: sha256}`` que PyPI sirve para esa versión; ``None`` si la versión no existe."""
    url = f"{indice.rstrip('/')}/pypi/{proyecto}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as respuesta:  # URL fija del índice declarado
            datos = json.load(respuesta)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return {u["filename"]: u["digests"]["sha256"] for u in datos.get("urls", [])}


def locales(directorio: Path) -> dict[str, str]:
    """``{nombre: sha256}`` de las distribuciones de ``directorio``."""
    archivos = sorted(p for p in directorio.iterdir() if p.suffix in {".whl", ".gz"})
    if not archivos:
        raise SystemExit(f"::error::{directorio} no contiene distribuciones")
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archivos}


def plan(propios: dict[str, str], servidos: dict[str, str] | None) -> tuple[list[str], list[str]]:
    """Devuelve (a_subir, ya_publicados); levanta ``SystemExit`` ante bytes divergentes."""
    servidos = servidos or {}
    divergentes = [n for n, sha in propios.items() if n in servidos and servidos[n] != sha]
    if divergentes:
        raise SystemExit(
            "::error::PyPI ya sirve estos archivos con OTROS bytes (no se re-sube un número con "
            f"contenido distinto): {divergentes}"
        )
    ya = sorted(n for n in propios if n in servidos)
    return sorted(n for n in propios if n not in servidos), ya


def esperar_publicados(
    propios: dict[str, str],
    consulta: Callable[[], dict[str, str] | None],
    *,
    plazo_segundos: float,
    pausa: float = 20.0,
    reloj: Callable[[], float] = time.monotonic,
    dormir: Callable[[float], None] = time.sleep,
) -> None:
    """Espera, con plazo, a que PyPI sirva todos los archivos con sus SHA-256."""
    limite = reloj() + plazo_segundos
    while True:
        servidos = consulta() or {}
        faltan = sorted(n for n in propios if n not in servidos)
        distintos = sorted(n for n in propios if n in servidos and servidos[n] != propios[n])
        if distintos:
            raise SystemExit(f"::error::PyPI sirve bytes distintos de los promovidos: {distintos}")
        if not faltan:
            return
        if reloj() >= limite:
            raise SystemExit(f"::error::PyPI no sirve todavía {faltan} tras {plazo_segundos:.0f} s")
        dormir(pausa)


def main() -> int:
    """Punto de entrada de la línea de comandos."""
    parser = argparse.ArgumentParser()
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--antes", action="store_true")
    modo.add_argument("--despues", action="store_true")
    parser.add_argument("proyecto")
    parser.add_argument("version")
    parser.add_argument("dist", type=Path)
    parser.add_argument("--indice", default="https://pypi.org")
    parser.add_argument("--plazo-segundos", type=float, default=600.0)
    args = parser.parse_args()
    propios = locales(args.dist)

    def consultar() -> dict[str, str] | None:
        return servidos_por_pypi(args.indice, args.proyecto, args.version)

    if args.antes:
        a_subir, ya = plan(propios, consultar())
        print(f"{args.proyecto} {args.version}: subir={a_subir} ya_publicados={ya}")
        return 0
    esperar_publicados(propios, consultar, plazo_segundos=args.plazo_segundos)
    print(f"{args.proyecto} {args.version}: PyPI sirve los {len(propios)} archivos promovidos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
