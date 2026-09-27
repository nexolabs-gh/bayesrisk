"""Inspecciona el candidato de la distribución de compatibilidad ``nikodym`` (D-REN-7, D-REN-11).

El paquete ``nikodym`` 1.21 promete no traer código de la librería: un único módulo que instala el
alias ``nikodym.<ruta>`` → ``bayesrisk.<ruta>``. Este gate lo verifica sobre los BYTES construidos
—no sobre el árbol fuente—, igual que ``check_distribution_contents.py`` hace con bayesrisk:

- exactamente un wheel y un sdist, con el nombre y la versión de ``compat/nikodym/pyproject.toml``;
- el wheel sólo contiene ``nikodym/__init__.py`` y su ``.dist-info`` (con la LICENSE);
- la METADATA depende de ``bayesrisk>=2.0,<3``, declara ``Development Status :: 7 - Inactive``,
  la licencia ``Apache-2.0`` y cada extra de bayesrisk con el mismo nombre;
- el script ``nikodym-ui`` apunta a ``bayesrisk.ui.__main__:main``;
- el sdist sólo trae el módulo, el README, la LICENSE, el ``pyproject.toml`` y lo que hatchling
  añade siempre (``PKG-INFO``, ``.gitignore``).

Uso:  python scripts/check_compat_distribution.py <directorio-con-wheel-y-sdist>
"""

from __future__ import annotations

import email.parser
import re
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
COMPAT = RAIZ / "compat" / "nikodym"


class CompatDistributionError(Exception):
    """El candidato de compatibilidad no es lo que el paquete promete."""


def _proyecto(ruta: Path) -> dict[str, object]:
    return tomllib.loads(ruta.read_text(encoding="utf-8"))["project"]  # type: ignore[no-any-return]


def verificar(directorio: Path) -> str:
    """Levanta :class:`CompatDistributionError` ante la primera promesa rota; resume lo visto."""
    compat = _proyecto(COMPAT / "pyproject.toml")
    principal = _proyecto(RAIZ / "pyproject.toml")
    version = str(compat["version"])
    wheels = sorted(directorio.glob("*.whl"))
    sdists = sorted(directorio.glob("*.tar.gz"))
    esperado_whl = f"nikodym-{version}-py3-none-any.whl"
    esperado_sdist = f"nikodym-{version}.tar.gz"
    if [p.name for p in wheels] != [esperado_whl] or [p.name for p in sdists] != [esperado_sdist]:
        raise CompatDistributionError(
            f"se esperaba exactamente {esperado_whl} y {esperado_sdist}; hay "
            f"{[p.name for p in wheels + sdists]}"
        )

    info = f"nikodym-{version}.dist-info/"
    with zipfile.ZipFile(wheels[0]) as wheel:
        nombres = set(wheel.namelist())
        codigo = {n for n in nombres if not n.startswith(info)}
        if codigo != {"nikodym/__init__.py"}:
            raise CompatDistributionError(
                f"el wheel trae código además del alias: {sorted(codigo)}"
            )
        if f"{info}licenses/LICENSE" not in nombres:
            raise CompatDistributionError("el wheel no trae la LICENSE")
        if wheel.read(f"{info}licenses/LICENSE") != (RAIZ / "LICENSE").read_bytes():
            raise CompatDistributionError("la LICENSE del wheel no es la del repositorio")
        metadata = email.parser.Parser().parsestr(wheel.read(f"{info}METADATA").decode("utf-8"))
        entry_points = wheel.read(f"{info}entry_points.txt").decode("utf-8")

    if metadata.get("Name") != "nikodym" or metadata.get("Version") != version:
        raise CompatDistributionError(
            f"METADATA declara {metadata.get('Name')} {metadata.get('Version')}"
        )
    if metadata.get("License-Expression") != "Apache-2.0":
        raise CompatDistributionError("License-Expression distinta de Apache-2.0")
    if "Development Status :: 7 - Inactive" not in (metadata.get_all("Classifier") or []):
        raise CompatDistributionError("falta el clasificador Development Status :: 7 - Inactive")
    requisitos = metadata.get_all("Requires-Dist") or []
    if "bayesrisk<3,>=2.0" not in requisitos:
        raise CompatDistributionError(f"no depende de bayesrisk>=2.0,<3: {requisitos}")
    extras = set(metadata.get_all("Provides-Extra") or [])
    extras_principal = set(principal["optional-dependencies"])  # type: ignore[arg-type]
    if extras != extras_principal:
        raise CompatDistributionError(
            f"extras distintos de bayesrisk: faltan={sorted(extras_principal - extras)}, "
            f"sobran={sorted(extras - extras_principal)}"
        )
    # El backend escribe el marcador con comillas simples o dobles según la versión: se compara la
    # forma, no el estilo de comillas.
    por_extra = {
        m.group(2): m.group(1)
        for r in requisitos
        if (m := re.fullmatch(r"bayesrisk\[(\w+)\]<3,>=2\.0; extra == ['\"](\w+)['\"]", r))
    }
    for extra in sorted(extras):
        if por_extra.get(extra) != extra:
            raise CompatDistributionError(f"el extra {extra!r} no instala bayesrisk[{extra}]")
    if "nikodym-ui = bayesrisk.ui.__main__:main" not in entry_points:
        raise CompatDistributionError("nikodym-ui no apunta a bayesrisk.ui.__main__:main")

    base = f"nikodym-{version}/"
    with tarfile.open(sdists[0], "r:gz") as sdist:
        archivos = {m.name[len(base) :] for m in sdist.getmembers() if m.isfile()}
    # `.gitignore`: hatchling lo incluye en todo sdist (también en el de bayesrisk).
    permitidos = {
        "src/nikodym/__init__.py",
        "README.md",
        "LICENSE",
        "pyproject.toml",
        "PKG-INFO",
        ".gitignore",
    }
    if archivos != permitidos:
        raise CompatDistributionError(
            f"el sdist no trae exactamente {sorted(permitidos)}: {sorted(archivos)}"
        )
    return f"nikodym {version}: alias puro, {len(extras)} extras de bayesrisk, sdist mínimo"


def main() -> int:
    """Punto de entrada: 0 si el candidato cumple, 1 con el motivo si no."""
    try:
        print(verificar(Path(sys.argv[1])))
    except CompatDistributionError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
