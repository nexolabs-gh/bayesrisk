"""Genera o verifica el golden que ata el espejo TypeScript de ``bayesrisk.report.cifras``.

Enmienda CIFRAS-EN-PANTALLA (D-PAN-1): la pantalla escribe los números con la regla del informe, y
``web/src/lib/cifras.ts`` es su espejo. Este archivo es la verdad de Python sobre casos de borde y
2.000 ``float`` sembrados; ``test_cifras_golden.py`` exige que sea exactamente lo que genera el
código, y vitest exige que el espejo dé cada texto.

Cada caso es una fila ``[función, argumento, entrada, salida]``. Las entradas van **tipadas**,
porque JSON no las representa todas: ``{"float": "<repr>"}``, ``{"especial": "nan"|"inf"|"-inf"}``,
``{"entero": "<dígitos>"}`` y ``null`` (``None``).

Uso: ``python scripts/cifras_golden.py`` verifica; ``--write`` regenera y hay que revisar el diff.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "web" / "src" / "fixtures" / "cifras-golden.json"

sys.path.insert(0, str(ROOT / "src"))
from bayesrisk.report import cifras  # noqa: E402

#: Semilla fija: el golden es determinista.
_SEMILLA = 20260927
_SEMBRADOS = 2000

#: Variantes de cada función: (nombre, argumento, llamada).
_VARIANTES: list[tuple[str, int | None]] = [
    ("cifra", 4),
    ("cifra", 3),
    ("cifra", 2),
    ("cifra", 1),
    ("cifra", 0),
    ("pvalor", None),
    ("corte", 2),
    ("corte", 0),
    ("porcentaje", 2),
    ("porcentaje", 1),
    ("porcentaje", 0),
    ("monto", None),
]

_BORDES: list[float] = [
    0.0,
    -0.0,
    0.24996,
    0.25,
    0.2500,
    0.125,
    0.0125,
    0.00125,
    2.5,
    0.5,
    1.5,
    -2.5,
    0.001,
    0.000999,
    0.00099999,
    0.0009995,
    1e-6,
    9.99e-7,
    9.96e-7,
    1.23e-9,
    -2.3e-9,
    999.99995,
    999.9999,
    1000.0,
    999.5,
    1234.56,
    -1234.56,
    30316.0,
    123456789.123,
    1e15,
    1e21,
    1e-300,
    5e-324,
    1.7976931348623157e308,
    0.1 + 0.2,
    0.30000000000000004,
    1 / 3,
    2 / 3,
    0.7534,
    0.71,
    19.423268,
    0.2345,
    100.0,
    -0.00004,
    0.9999999,
    0.05,
    0.95,
    0.999,
    1.0,
    -1.0,
    0.333333,
    697376974.5,
    697376975.5,
    3514282.4,
]

_ESPECIALES = ("nan", "inf", "-inf")
_ENTEROS = [0, 1, -1, 999, 1000, -1000, 3961, 30316, 1234567, 2**31, 2**53 - 1, -(2**53 - 1)]


def _float_sembrado(rng: random.Random) -> float:
    """Un float de cualquier magnitud, a veces «redondo» para ejercitar la regla del cero final."""
    tipo = rng.randrange(4)
    signo = -1.0 if rng.random() < 0.2 else 1.0
    if tipo == 0:
        return signo * 10 ** rng.uniform(-12, 10)
    if tipo == 1:
        decimales = rng.randrange(0, 7)
        return signo * rng.randrange(0, 10**7) / 10**decimales
    if tipo == 2:
        # Empates exactos en binario: múltiplos de potencias de dos.
        return signo * rng.randrange(0, 2**12) / 2 ** rng.randrange(1, 12)
    return signo * rng.uniform(0, 1)


def _entrada(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, int) and not isinstance(valor, bool):
        return {"entero": str(valor)}
    if math.isnan(valor):
        return {"especial": "nan"}
    if math.isinf(valor):
        return {"especial": "inf" if valor > 0 else "-inf"}
    return {"float": repr(valor)}


def _llamar(funcion: str, argumento: int | None, valor: Any) -> str:
    if funcion == "cifra":
        return cifras.cifra(valor, decimales=int(argumento or 0))
    if funcion == "pvalor":
        return cifras.pvalor(valor)
    if funcion == "corte":
        return cifras.corte(valor, minimo=int(argumento or 0))
    if funcion == "porcentaje":
        return cifras.porcentaje(valor, decimales=int(argumento or 0))
    if funcion == "monto":
        return cifras.monto(valor, simbolo="$")
    if funcion == "conteo":
        return cifras.conteo(valor)
    raise ValueError(funcion)


def _admite(funcion: str, valor: Any) -> bool:
    """``corte`` no recibe no finitos ni ``None`` (un corte del config siempre es un número)."""
    if funcion == "corte":
        return isinstance(valor, float) and math.isfinite(valor)
    return True


def casos() -> list[list[Any]]:
    """Todas las filas del golden, en orden determinista."""
    filas: list[list[Any]] = []

    def agregar(funcion: str, argumento: int | None, valor: Any) -> None:
        if _admite(funcion, valor):
            filas.append([funcion, argumento, _entrada(valor), _llamar(funcion, argumento, valor)])

    for funcion, argumento in _VARIANTES:
        for valor in _BORDES:
            agregar(funcion, argumento, valor)
        for especial in _ESPECIALES:
            agregar(funcion, argumento, float(especial))
        agregar(funcion, argumento, None)
    for entero in _ENTEROS:
        agregar("conteo", None, entero)

    rng = random.Random(_SEMILLA)
    for indice in range(_SEMBRADOS):
        valor = _float_sembrado(rng)
        agregar("cifra", 4, valor)
        funcion, argumento = _VARIANTES[1 + indice % (len(_VARIANTES) - 1)]
        agregar(funcion, argumento, valor)
    return filas


def expected_bytes() -> bytes:
    """El golden serializado: una fila por línea, para que el diff se lea."""
    lineas = [json.dumps(fila, ensure_ascii=False, separators=(",", ":")) for fila in casos()]
    cuerpo = ",\n".join(lineas)
    return f'{{"version":1,"casos":[\n{cuerpo}\n]}}\n'.encode()


def main() -> int:
    """Verifica por defecto; ``--write`` regenera el golden."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    esperado = expected_bytes()
    if args.write:
        GOLDEN.write_bytes(esperado)
        return 0
    if not GOLDEN.is_file() or GOLDEN.read_bytes() != esperado:
        raise SystemExit(
            "cifras-golden.json no coincide con bayesrisk.report.cifras; ejecute "
            "scripts/cifras_golden.py --write y revise el diff."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
