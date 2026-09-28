"""Cómo escribe el informe un número: es-CL, y sin que un redondeo se haga pasar por un corte.

Una sola regla para las tablas, las listas de clave y valor, los bloques del anexo de parámetros, el
linaje, los gráficos y las cifras de la página ejecutiva:

- coma decimal y punto de miles (la convención cuelga del idioma del informe, que es el español);
- cuatro decimales entre ``0,001`` y ``1.000``; dos, con miles agrupados, desde ``1.000``;
- **dos cifras significativas** bajo ``0,001``, para no escribir ``0,0000`` donde hay algo;
- notación científica con coma bajo una millonésima (``2,3e-09``): un coeficiente por peso de
  monto de una LGD sobre el frame crudo existe, y en posicional pediría diez ceros;
- p-valores con ``< 0,001`` o tres decimales;
- 🔴 **la regla del cero final**: si la cifra redondeada termina en cero y no es el valor exacto, se
  agregan decimales hasta que el último no sea cero —como máximo, hasta el valor exacto—. Una cifra
  que termina en un dígito distinto de cero con ``p`` decimales queda del mismo lado que el exacto
  de todo corte con menos de ``p`` decimales: el corte es múltiplo de ``10^-(p-1)``, la cifra no lo
  es, y la cifra es el múltiplo de ``10^-p`` más cercano al exacto. Sin la regla, un PSI de
  ``0.24996`` se escribía ``0,2500`` junto a su corte de ``0,25``.

**El exacto es decimal, nunca binario.** El de un ``float`` es ``Decimal(repr(x))`` —la
representación más corta que lo reproduce—, y el de un ``Decimal`` es el propio ``Decimal``, sin
pasar por ``float``: ``Decimal("0.24999999999999999999")`` en ``float`` es ``0.25``, y la regla lo
daría por exacto. El redondeo es al par más cercano sobre ese decimal.

Sólo presentación: los números de ``results``, de los exports y del ``data_hash`` no se tocan.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Final

__all__ = [
    "VACIO",
    "cifra",
    "conteo",
    "corte",
    "es_columna_de_conteo",
    "es_columna_de_pvalor",
    "monto",
    "porcentaje",
    "pvalor",
]

#: Marcador de celda sin valor (``None``, ``NaN``): el mismo em-dash de todo el informe.
VACIO: Final = "—"

#: Desde aquí una cifra se escribe con dos decimales y miles agrupados (montos, puntajes grandes).
_GRANDE: Final = Decimal(1000)
#: Bajo este valor absoluto la cifra lleva dos cifras significativas en vez de cuatro decimales.
_PEQUENO: Final = Decimal("0.001")
#: Bajo este valor absoluto la cifra va en notación científica.
_DIMINUTO: Final = Decimal("0.000001")
#: Nombres (sin distinguir mayúsculas) de columnas que cuentan, además de los patrones de abajo.
_CONTEOS: Final = frozenset(
    {"event", "non-event", "observaciones", "filas", "cardinality", "observed_defaults"}
)


def _exacto(valor: float | Decimal) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(repr(float(valor)))


def _redondeado(exacto: Decimal, decimales: int) -> Decimal:
    """``exacto`` redondeado al par más cercano con ``decimales``, sin tope de dígitos.

    El contexto por defecto de ``decimal`` tiene 28 dígitos: con él ``Decimal("1E+24")`` a cuatro
    decimales levantaba ``InvalidOperation`` y tumbaba el informe (pasada 1 de Codex sobre el
    código). La precisión local alcanza para el resultado entero.
    """
    with localcontext() as contexto:
        contexto.prec = max(28, exacto.adjusted() + decimales + 2)
        return exacto.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_EVEN)


def _posicional(numero: Decimal, decimales: int, *, miles: bool) -> str:
    """``numero`` ya redondeado a ``decimales``, escrito en es-CL."""
    signo = "-" if numero < 0 else ""
    # Sin precisión en el formato: `numero` ya viene con `decimales` exactos, y `format` con
    # precisión redondea con el contexto de 28 dígitos (0,24999…9 de 29 cifras salía 0,25000…).
    texto = format(numero.copy_abs(), "f")  # `abs()` redondea al contexto; `copy_abs` no
    entero, _, fraccion = texto.partition(".")
    if miles:
        entero = f"{int(entero):,}".replace(",", ".")
    return f"{signo}{entero},{fraccion}" if decimales > 0 else f"{signo}{entero}"


def _decimales_del_exacto(exacto: Decimal) -> int:
    """Cuántos decimales tiene el exacto sin sus ceros a la derecha (0 si es entero).

    Se cuentan sobre la tupla del Decimal, sin ``normalize()``: con el contexto de 28 dígitos,
    ``normalize`` redondeaba ``0.24999999999999999999999999999`` a ``0.25`` y la regla del cero
    final se detenía en ``0,2500`` (pasada 1 de Codex sobre el código).
    """
    _, digitos, exponente = exacto.as_tuple()
    if not isinstance(exponente, int):
        return 0
    ceros = len(digitos) - len("".join(map(str, digitos)).rstrip("0"))
    return max(0, -(exponente + ceros))


def _con_cero_final(exacto: Decimal, decimales: int, *, miles: bool) -> str:
    """Redondea a ``decimales`` y agrega los necesarios para no terminar en un cero inexacto."""
    # El exacto tiene una cantidad finita de decimales: al llegar a ella la cifra es el exacto y
    # el bucle termina.
    limite = max(decimales, _decimales_del_exacto(exacto))
    while True:
        redondeado = _redondeado(exacto, decimales)
        texto = _posicional(redondeado, decimales, miles=miles)
        if decimales >= limite or redondeado == exacto or not texto.endswith("0"):
            return texto
        decimales += 1


def _cientifica(exacto: Decimal) -> str:
    """Notación científica con coma y mantisa de dos cifras, con la regla del cero final.

    La mantisa exacta vive en ``[1, 10)``; si al redondearla a una cifra decimal sube a ``10,0``
    (``9,96`` → ``10,0``), la regla del cero final la extiende a ``9,96``: nunca sale ``10,0e-07``.
    """
    exponente = exacto.adjusted()
    signo_exp = "-" if exponente < 0 else "+"
    with localcontext() as contexto:  # `scaleb` redondea al contexto: que quepan todas sus cifras
        contexto.prec = max(28, len(exacto.as_tuple().digits) + 2)
        mantisa_exacta = exacto.scaleb(-exponente)
    mantisa = _con_cero_final(mantisa_exacta, 1, miles=False)
    return f"{mantisa}e{signo_exp}{abs(exponente):02d}"


def cifra(valor: float | Decimal | None, *, decimales: int = 4) -> str:
    """Un número real como lo lee una persona en el informe (reglas del docstring del módulo).

    ``decimales`` es la base entre ``0,001`` y ``1.000`` (cuatro en tablas y anexos); la prosa que
    ya escribía una métrica con dos o tres decimales los conserva, con la misma regla del cero
    final encima.
    """
    if valor is None:
        return VACIO
    if isinstance(valor, float) and not math.isfinite(valor):
        if math.isnan(valor):
            return VACIO
        return "inf" if valor > 0 else "-inf"
    if isinstance(valor, Decimal) and not valor.is_finite():
        if valor.is_nan():
            return VACIO
        return "inf" if valor > 0 else "-inf"
    exacto = _exacto(valor)
    if exacto == 0:
        return _posicional(_redondeado(Decimal(0), decimales), decimales, miles=False)
    magnitud = exacto.copy_abs()
    if _redondeado(exacto, decimales).copy_abs() >= _GRANDE:
        return _con_cero_final(exacto, 2, miles=True)
    if magnitud >= _PEQUENO:
        return _con_cero_final(exacto, decimales, miles=False)
    if magnitud >= _DIMINUTO:
        # Dos cifras significativas: la primera está en la posición ``-adjusted()``.
        return _con_cero_final(exacto, 1 - exacto.adjusted(), miles=False)
    return _cientifica(exacto)


def pvalor(valor: float | Decimal | None) -> str:
    """Un p-valor: ``< 0,001`` bajo ese corte, si no, tres decimales con la regla del cero final."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return VACIO
    exacto = _exacto(valor)
    if not exacto.is_finite():
        return VACIO if exacto.is_nan() else cifra(valor)
    if exacto < _PEQUENO:
        return "< 0,001"
    return _con_cero_final(exacto, 3, miles=False)


def corte(valor: float | Decimal, *, minimo: int = 2) -> str:
    """Un corte del config escrito **exacto**, con al menos ``minimo`` decimales: ``0,125``.

    Un corte redondeado describiría otra política: ``0.125`` escrito ``0,12`` diría que ``0,1225``
    queda del otro lado. Sin notación científica: los cortes de una política de riesgo se escriben
    en posicional.
    """
    exacto = _exacto(valor)
    texto = format(exacto, "f")
    # Un cero no lleva signo: `-0.0` es un corte en cero (enmienda CIFRAS-EN-PANTALLA, D-PAN-1 a).
    signo = "-" if texto.startswith("-") and exacto != 0 else ""
    entero, _, fraccion = texto.lstrip("-").partition(".")
    fraccion = fraccion.rstrip("0").ljust(minimo, "0")
    return f"{signo}{entero},{fraccion}" if fraccion else f"{signo}{entero}"


def conteo(valor: int) -> str:
    """Un conteo con punto de miles: ``30.316``."""
    return f"{valor:,}".replace(",", ".")


def porcentaje(valor: float | None, *, decimales: int = 2) -> str:
    """Una proporción como porcentaje, con coma y espacio: ``0.238`` → ``23,80 %``.

    Decimales fijos, sin la regla del cero final: un porcentaje no se lee junto a un corte. Redondea
    el producto binario ``valor * 100`` al par más cercano, como el formato ``f`` de Python —que es
    lo que el informe ya escribía—. Un cero redondeado no lleva signo.
    """
    if valor is None or not math.isfinite(valor):
        return VACIO
    texto = f"{valor * 100:.{decimales}f}"
    if texto.startswith("-") and not texto.strip("-0."):
        texto = texto[1:]
    return f"{texto} %".replace(".", ",")


def monto(valor: float | Decimal | None, *, simbolo: str) -> str:
    """Un monto redondeado a la unidad con punto de miles y su símbolo: ``$697.376.974``.

    El redondeo es al par más cercano (``round`` de Python); el signo va antes del símbolo
    (``-$1.200``). ``simbolo`` es obligatorio y sin default a propósito (D-MON-4).
    """
    if valor is None:
        return VACIO
    numero = float(valor)
    if not math.isfinite(numero):
        return VACIO
    entero = round(numero)
    signo = "-" if entero < 0 else ""
    return f"{signo}{simbolo}{abs(entero):,}".replace(",", ".")


def es_columna_de_conteo(nombre: str) -> bool:
    """Si la columna cuenta cosas (sus enteros se agrupan en miles).

    La lista va en la dirección segura **a propósito**: un conteo que no esté en ella sale sin
    agrupar (``12345``, legible y correcto), mientras que agrupar un identificador escribiría un año
    ``2.005`` o una semilla ``20.260.920``.
    """
    clave = nombre.strip().lower()
    return (
        clave == "n"
        or clave.startswith(("n_", "cum_"))
        or clave.endswith(("count", "_rows"))
        or clave in _CONTEOS
    )


def es_columna_de_pvalor(nombre: str) -> bool:
    """Si la columna es un p-valor **observado** (D-CPY-4: ``< 0,001`` o tres decimales).

    Un corte de p-valor del config (``entry_p_value``, ``exit_p_value``, ``max_pvalue``,
    ``p_value_threshold``) no es un resultado: se escribe exacto, no como ``< 0,001``.
    """
    clave = nombre.strip().lower()
    if not ("p_value" in clave or "pvalue" in clave):
        return False
    return not (
        clave.startswith(("entry_", "exit_", "max_", "min_"))
        or any(marca in clave for marca in ("threshold", "alpha", "cut", "corte"))
    )
