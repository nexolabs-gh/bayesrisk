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
from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Final

__all__ = [
    "CRITERIOS_CON_PVALOR",
    "MOTIVOS_DE_SELECCION",
    "PARTES_DEL_CRITERIO",
    "PREFIJO_CONTRIBUCION_IV",
    "VACIO",
    "cifra",
    "conteo",
    "corte",
    "corte_porcentual",
    "es_columna_de_conteo",
    "es_columna_de_pvalor",
    "frente_al_corte",
    "monto",
    "motivo_legible",
    "motivo_legible_stepwise",
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


# --- El motivo de una decisión del motor, legible (enmienda CIFRAS-EN-PANTALLA, D-PAN-4) ---------
#
# El `detail` del motor es texto de auditoría con `:.6g` y no cambia: viaja en `results.json` y en
# los exports, y `model/step.py` lo vuelve a leer. El texto legible NO se obtiene parseándolo —ya
# redondeó a seis cifras y un corte redondeado es otra política—: se compone desde la observación y
# el umbral **originales**. Un motivo sin composición, o sin sus valores, devuelve `None` y quien
# presenta muestra el `detail` crudo.

#: Motivo de la selección → (columna de la observación, clave del umbral en `thresholds`, frase,
#: prefijo con que el selector escribe su `detail` numérico).
MOTIVOS_DE_SELECCION: Final[dict[str, tuple[str, str, str, str]]] = {
    "low_iv": ("iv", "min_iv", "IV {obs} < mínimo {umbral}", "iv="),
    "high_iv": ("iv", "max_iv", "IV {obs} ≥ máximo {umbral}", "iv="),
    "high_correlation": (
        "max_abs_corr",
        "correlation.threshold",
        "correlación {obs} > máximo {umbral}",
        "|rho|=",
    ),
    "high_vif": ("vif", "vif.threshold", "VIF {obs} > máximo {umbral}", "vif="),
}
#: Criterios del stepwise cuyo `detail` escribe `_criterion_detail` (p-valores de Wald y LR).
CRITERIOS_CON_PVALOR: Final = frozenset({"wald_pvalue", "lr_test", "both"})
#: Prefijo del `detail` del criterio de contribución de IV.
PREFIJO_CONTRIBUCION_IV: Final = "iv_contribution="
#: Las partes que `_criterion_detail` une con «, » y cómo se nombran al leerlas.
PARTES_DEL_CRITERIO: Final = {"wald_p=": "Wald", "lr_p=": "razón de verosimilitud"}


def _numero(valor: object) -> float | None:
    """``valor`` como ``float`` finito, o ``None`` (ausente, texto, ``NaN``, infinito)."""
    if isinstance(valor, bool) or not isinstance(valor, int | float | Decimal):
        try:
            import numpy as np  # los frames del motor traen escalares de numpy

            if not isinstance(valor, np.floating | np.integer):
                return None
        except ImportError:  # pragma: no cover - numpy es dependencia base
            return None
    numero = float(valor)
    return numero if math.isfinite(numero) else None


def _leer(texto: str) -> Decimal | None:
    """El número que dice un texto de :func:`cifra` o :func:`pvalor`; ``None`` si no dice uno."""
    limpio = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpio)
    except ArithmeticError:
        return None


def _signo(valor: Decimal) -> int:
    return (valor > 0) - (valor < 0)


def frente_al_corte(texto: str, valor: float, umbral: float) -> str:
    """La cifra ``texto`` de ``valor``, con los decimales que la dejan del lado correcto del corte.

    Una cifra redondeada puede escribirse igual al corte o cruzarlo cuando el corte tiene más
    decimales que ella: ``0.0499555`` a cinco decimales es ``0,04996``, **sobre** un corte de
    ``0,049956`` que el valor exacto no alcanza. Junto a su corte, una observación se escribe con
    los decimales que conservan el orden —como máximo, el exacto—. Revisión adversarial del diseño
    (pasada 3 de Codex): una comparación imposible en el texto es un defecto de presentación.
    """
    exacto, frontera = _exacto(valor), _exacto(umbral)
    lado = _signo(exacto - frontera)
    # «< 0,001» ya dice su lado cuando la cota no pasa del corte.
    if texto.startswith("< "):
        cota = _leer(texto[2:])
        if lado < 0 and cota is not None and cota <= frontera:
            return texto
    leido = _leer(texto)
    # En la igualdad, la cifra también tiene que decir el corte (pasada 1 de Codex sobre el código:
    # con `iv == max_iv == 0.24994`, «IV 0,2499 ≥ máximo 0,24994» era falso).
    if leido is not None and _signo(leido - frontera) == lado:
        return texto
    miles = exacto.copy_abs() >= _GRANDE
    _, _, fraccion = texto.partition(",")
    decimales = len(fraccion) if fraccion.isdigit() else 0
    limite = _decimales_del_exacto(exacto)
    while decimales < limite:
        decimales += 1
        redondeado = _redondeado(exacto, decimales)
        if _signo(redondeado - frontera) == lado:
            return _posicional(redondeado, decimales, miles=miles)
    return _posicional(_redondeado(exacto, limite), limite, miles=miles)


def corte_porcentual(valor: float | Decimal) -> str:
    """Un corte que es una proporción, como porcentaje **exacto**: ``0.255`` → ``25,5 %``.

    Se multiplica el decimal exacto, no el binario (``0.255 * 100`` es ``25.500000000000004``), y
    no se redondea: un corte redondeado describiría otra política.
    """
    return f"{corte(_exacto(valor) * 100, minimo=0)} %"


def motivo_legible(fila: Mapping[str, object], umbrales: Mapping[str, object]) -> str | None:
    """El motivo de una fila de ``selection_table`` en es-CL, desde sus valores originales.

    ``fila`` trae ``reason``, ``detail`` y la observación (``iv``, ``max_abs_corr``, ``vif``) a
    precisión completa; ``umbrales`` son los ``thresholds`` efectivos de la selección. Sólo se
    compone cuando el ``detail`` es el numérico del selector (una variable desplazada por
    ``force_include`` también es ``high_correlation``, con otro texto, y se deja tal cual).
    """
    motivo = fila.get("reason")
    detalle = fila.get("detail")
    if not isinstance(motivo, str) or motivo not in MOTIVOS_DE_SELECCION:
        return None
    columna, clave, frase, prefijo = MOTIVOS_DE_SELECCION[motivo]
    if not isinstance(detalle, str) or not detalle.startswith(prefijo):
        return None
    observado = _numero(fila.get(columna))
    umbral = _numero(umbrales.get(clave))
    if observado is None or umbral is None:
        return None
    obs = frente_al_corte(cifra(observado), observado, umbral)
    texto = frase.format(obs=obs, umbral=corte(umbral))
    con = fila.get("max_corr_with")
    if motivo == "high_correlation" and isinstance(con, str) and con:
        texto += f" con {con}"
    return texto


def _pvalores_del_detail(detalle: object, p_valor: float, umbral: float) -> str:
    """«Wald 0,012; razón de verosimilitud 0,034», del ``detail`` de ``_criterion_detail``."""
    if not isinstance(detalle, str):
        return ""
    partes: list[str] = []
    for trozo in detalle.split(", "):
        prefijo = next((p for p in PARTES_DEL_CRITERIO if trozo.startswith(p)), None)
        if prefijo is None:
            return ""  # un `detail` que no es el de `_criterion_detail`: no se adivina
        try:
            valor = float(trozo.removeprefix(prefijo))
        except ValueError:
            return ""
        if f"{valor:.6g}" == f"{p_valor:.6g}":
            valor = p_valor  # es el p-valor del criterio: su exacto está en el campo estructurado
        escrito = pvalor(valor)
        if escrito.startswith("<") and umbral < float(_PEQUENO):
            escrito = cifra(valor)
        partes.append(f"{PARTES_DEL_CRITERIO[prefijo]} {frente_al_corte(escrito, valor, umbral)}")
    return "; ".join(partes)


def motivo_legible_stepwise(fila: Mapping[str, object]) -> str | None:
    """El motivo de una decisión del stepwise en es-CL, desde sus valores originales.

    ``fila`` trae ``criterion``, ``detail``, ``p_value``, ``lr_stat`` y ``threshold`` (una fila de
    ``stepwise_trace`` o el ``valor`` de la decisión en la ficha, con su umbral). La contribución de
    IV es una observación y el motor la publica sólo en su ``detail``: se lee de ahí, con sus seis
    cifras significativas; el umbral, en cambio, viene siempre del campo estructurado.
    """
    criterio = fila.get("criterion")
    detalle = fila.get("detail")
    umbral = _numero(fila.get("threshold"))
    if criterio in CRITERIOS_CON_PVALOR:
        p_valor = _numero(fila.get("p_value"))
        if p_valor is None or umbral is None:
            return None
        escrito = pvalor(p_valor)
        if escrito.startswith("<") and umbral < float(_PEQUENO):
            escrito = cifra(p_valor)  # «< 0,001» no dice de qué lado queda un corte menor
        # Los p-valores de cada prueba sólo viajan en el `detail` (seis cifras): son evidencia —con
        # `both`, `p_value` es el mayor y no dice cuál de las dos decidió— y se conservan (pasada 3
        # de Codex sobre el código). El que coincide con `p_value` se escribe con su valor exacto.
        pruebas = _pvalores_del_detail(detalle, p_valor, umbral)
        texto = f"p-valor {frente_al_corte(escrito, p_valor, umbral)}"
        if pruebas:
            texto += f" ({pruebas})"
        texto += f"; umbral {corte(umbral)}"
        estadistico = _numero(fila.get("lr_stat"))
        if estadistico is not None:
            texto += f"; estadístico LR {cifra(estadistico)}"
        return texto
    if criterio == "iv_contribution" and isinstance(detalle, str):
        if not detalle.startswith(PREFIJO_CONTRIBUCION_IV) or umbral is None:
            return None
        try:
            contribucion = float(detalle.removeprefix(PREFIJO_CONTRIBUCION_IV))
        except ValueError:
            return None
        # El motor sólo registra la contribución que SUPERA el corte, pero su valor exacto no
        # viaja: si las seis cifras del `detail` no lo dicen, no se afirma una comparación (pasada
        # 1 de Codex sobre el código) y queda el texto del motor.
        if not contribucion > umbral:
            return None
        escrita = frente_al_corte(cifra(contribucion), contribucion, umbral)
        return f"contribución al IV {escrita} > máximo {corte(umbral)}"
    return None
