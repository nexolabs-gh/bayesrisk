"""El cotejo por archivo antes y después de publicar en PyPI (RENOMBRE-BAYESRISK, D-REN-11).

La unidad es el archivo con su SHA-256, no la versión: una subida a medias deja la versión
«existente» con un archivo de menos, y los bytes distintos bajo el mismo nombre nunca se re-suben.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_RUTA = Path(__file__).resolve().parents[2] / "scripts" / "pypi_cotejar_publicacion.py"
_SPEC = importlib.util.spec_from_file_location("pypi_cotejar_publicacion", _RUTA)
assert _SPEC is not None and _SPEC.loader is not None
cotejo = importlib.util.module_from_spec(_SPEC)
sys.modules["pypi_cotejar_publicacion"] = cotejo
_SPEC.loader.exec_module(cotejo)

PROPIOS = {"bayesrisk-2.0.0-py3-none-any.whl": "a" * 64, "bayesrisk-2.0.0.tar.gz": "b" * 64}


def test_version_inexistente_sube_todo() -> None:
    assert cotejo.plan(PROPIOS, None) == (sorted(PROPIOS), [])


def test_subida_a_medias_sube_solo_lo_que_falta() -> None:
    servidos = {"bayesrisk-2.0.0-py3-none-any.whl": "a" * 64}
    assert cotejo.plan(PROPIOS, servidos) == (
        ["bayesrisk-2.0.0.tar.gz"],
        ["bayesrisk-2.0.0-py3-none-any.whl"],
    )


def test_bytes_distintos_con_el_mismo_nombre_se_detienen() -> None:
    servidos = {"bayesrisk-2.0.0.tar.gz": "c" * 64}
    with pytest.raises(SystemExit, match="OTROS bytes"):
        cotejo.plan(PROPIOS, servidos)


def test_despues_espera_hasta_ver_los_dos_archivos() -> None:
    respuestas = iter([None, {"bayesrisk-2.0.0-py3-none-any.whl": "a" * 64}, dict(PROPIOS)])
    tiempo = [0.0]
    cotejo.esperar_publicados(
        PROPIOS,
        lambda: next(respuestas),
        plazo_segundos=100,
        reloj=lambda: tiempo[0],
        dormir=lambda s: tiempo.__setitem__(0, tiempo[0] + s),
    )


def test_despues_falla_si_nunca_llega_un_archivo() -> None:
    tiempo = [0.0]
    with pytest.raises(SystemExit, match="no sirve todavía"):
        cotejo.esperar_publicados(
            PROPIOS,
            lambda: {"bayesrisk-2.0.0-py3-none-any.whl": "a" * 64},
            plazo_segundos=60,
            reloj=lambda: tiempo[0],
            dormir=lambda s: tiempo.__setitem__(0, tiempo[0] + s),
        )


def test_despues_falla_si_pypi_sirve_otros_bytes() -> None:
    with pytest.raises(SystemExit, match="bytes distintos"):
        cotejo.esperar_publicados(
            PROPIOS,
            lambda: {**PROPIOS, "bayesrisk-2.0.0.tar.gz": "d" * 64},
            plazo_segundos=60,
        )
