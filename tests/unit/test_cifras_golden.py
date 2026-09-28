"""El golden de las cifras es exactamente lo que escribe ``bayesrisk.report.cifras`` (D-PAN-1).

Es la mitad Python del golden bidireccional: si la regla cambia en Python sin regenerar
``web/src/fixtures/cifras-golden.json``, esto se pone rojo; si el espejo TypeScript deja de dar
algún texto del golden, se pone rojo ``web/src/lib/cifras.test.ts``.
"""

from __future__ import annotations

import importlib.util
import math
from decimal import Decimal
from pathlib import Path

from bayesrisk.report import cifras

_RAIZ = Path(__file__).resolve().parents[2]
_SCRIPT = _RAIZ / "scripts" / "cifras_golden.py"
_SPEC = importlib.util.spec_from_file_location("cifras_golden", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
golden = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(golden)


def test_el_golden_versionado_es_el_que_genera_el_codigo() -> None:
    assert golden.GOLDEN.read_bytes() == golden.expected_bytes(), (
        "cifras-golden.json quedó atrás: scripts/cifras_golden.py --write y revisar el diff"
    )


def test_el_golden_cubre_cada_funcion_y_los_bordes_tipados() -> None:
    filas = golden.casos()
    funciones = {fila[0] for fila in filas}
    assert funciones == {"cifra", "pvalor", "corte", "porcentaje", "monto", "conteo"}
    entradas = [fila[2] for fila in filas]
    assert {"float": "-0.0"} in entradas
    assert {"especial": "nan"} in entradas and {"especial": "-inf"} in entradas
    assert {"entero": str(2**53 - 1)} in entradas
    assert None in entradas
    assert len(filas) > 2 * golden._SEMBRADOS


def test_un_cero_no_lleva_signo_en_ninguna_funcion() -> None:
    assert cifras.cifra(-0.0) == "0,0000"
    assert cifras.corte(-0.0) == "0,00"
    assert cifras.corte(Decimal("-0")) == "0,00"
    assert cifras.pvalor(-0.0) == "< 0,001"
    assert cifras.porcentaje(-0.0, decimales=1) == "0,0 %"
    assert cifras.porcentaje(-0.00001, decimales=1) == "0,0 %"
    assert cifras.monto(-0.4, simbolo="$") == "$0"


def test_porcentaje_y_monto_escriben_lo_que_ya_escribia_el_informe() -> None:
    """Salieron de ``report/prose.py`` sin cambiar su salida (salvo el signo de un monto < 0)."""
    for proporcion in (0.238, 0.0299, 1.0, 0.123456, 0.5, 0.0):
        for decimales in (0, 1, 2):
            anterior = f"{proporcion * 100:.{decimales}f} %".replace(".", ",")
            assert cifras.porcentaje(proporcion, decimales=decimales) == anterior
    for valor in (697376974.5, 697376975.5, 3514282.4, 0.5, 1.5, 0.0):
        anterior = "$" + f"{round(valor):,}".replace(",", ".")
        assert cifras.monto(valor, simbolo="$") == anterior
    assert cifras.monto(-1200.4, simbolo="$") == "-$1.200"
    assert cifras.porcentaje(math.nan) == cifras.VACIO
    assert cifras.monto(None, simbolo="$") == cifras.VACIO
