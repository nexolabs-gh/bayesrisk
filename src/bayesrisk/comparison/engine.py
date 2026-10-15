"""El motor puro de la comparación (SDD-34 §3 y §7): sin ``Study``, sin disco, sin config.

- :func:`indice_bce` — el índice de concentración del BCE, ``1 + ln(HHI)/ln(K)`` (§3.4, D-CMP-3).
- :func:`componentes_de_delong` y :func:`delong_pareada` — el AUC con la varianza del anexo 3.1
  (:func:`~bayesrisk.monitoring.engine.auc_sobre_tramos`, con cada valor del riesgo como tramo) y
  la prueba de DeLong **pareada** entre dos modelos evaluados sobre las mismas operaciones, con la
  covarianza de sus componentes emparejados por el orden canónico (§3.5, §7-5, D-CMP-7).
- :func:`frontera` — el **núcleo** de la relación «supera» (§3.5): un modelo queda fuera sólo si
  lo supera otro que está en la frontera.
- :func:`nivel_de_comparabilidad` y :func:`misma_unidad` — los tres niveles de §3.3 y la regla de
  la unidad de los montos de §3.7 (D-CMP-5, D-CMP-8).

**Estable (SemVer 2.x).** Desde la 2.16.0 (capa B del SDD-34).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

import numpy as np

from bayesrisk.monitoring.engine import auc_sobre_tramos

__all__ = [
    "ALFA_DELONG",
    "ORDEN_DE_BANDA",
    "Componentes",
    "IndiceBce",
    "PruebaPareada",
    "componentes_de_delong",
    "delong_pareada",
    "frontera",
    "indice_bce",
    "misma_muestra_evaluada",
    "misma_unidad",
    "nivel_de_comparabilidad",
]

#: El corte de la prueba de DeLong: dos AUC empatan si la prueba no rechaza con p ≥ 0,05, el corte
#: que la librería ya usa (D-VAL-15). Constante, no perilla (§5.2).
ALFA_DELONG: Final = 0.05
#: Las bandas del PSI de la mejor a la peor: dos PSI de la misma banda empatan (§3.5).
ORDEN_DE_BANDA: Final[dict[str, int]] = {"stable": 0, "review": 1, "redevelop": 2}
#: Tolerancia relativa con que una varianza de la diferencia se lee como cero: dos modelos
#: idénticos dan una diferencia de varianzas del orden del redondeo, no exactamente cero.
_CERO_RELATIVO: Final = 1e-10

Nivel = Literal["misma_muestra", "misma_cartera", "otra_cartera"]


# ── El índice de concentración del BCE (§3.4) ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IndiceBce:
    """El índice de una corrida: ``HHI``, el índice y ``K``, o la causa por la que no se evalúa."""

    hhi: float | None
    indice: float | None
    k: int
    causa: str | None = None


def indice_bce(participacion: Sequence[float]) -> IndiceBce:
    """``HI = 1 + ln(HHI)/ln(K)`` sobre la participación por número de operaciones de cada tramo.

    Es la forma reducida de la fórmula del BCE (*Instructions for reporting the validation results
    of internal models*, 2019, §2.5.5.3): con ``CV = √(K·Σ(R_g - 1/K)²)``,
    ``HI = 1 + ln((CV² + 1)/K)/ln(K)`` y ``K·Σ(R_g - 1/K)² = K·ΣR_g² - 1``. Vale 0 si los ``K``
    tramos pesan igual y 1 si todo cae en uno; a diferencia del HHI no depende de ``K``. Sin al
    menos dos tramos, «no evaluable» con su causa.
    """
    valores = [float(v) for v in participacion]
    k = len(valores)
    if k < 2:
        return IndiceBce(None, None, k, causa="un_tramo" if k == 1 else "sin_tramos")
    total = sum(valores)
    if not math.isfinite(total) or total <= 0.0:
        return IndiceBce(None, None, k, causa="sin_operaciones")
    hhi = sum((v / total) ** 2 for v in valores)
    return IndiceBce(hhi, 1.0 + math.log(hhi) / math.log(k), k)


# ── La prueba de DeLong pareada (§3.5, §7-5) ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Componentes:
    """El AUC de un modelo sobre una muestra, su varianza y los componentes de DeLong.

    ``v10`` trae un valor por malo y ``v01`` uno por bueno, en el orden de la muestra: emparejados
    por el orden canónico, los de dos modelos sobre las mismas operaciones se corresponden.
    """

    auc: float | None
    varianza: float | None
    v10: Any
    v01: Any
    n_malos: int
    n_buenos: int
    causa: str | None = None


def componentes_de_delong(riesgo: Sequence[float], desenlace: Sequence[int]) -> Componentes:
    """El AUC y su varianza del anexo 3.1 con cada valor distinto del riesgo como un tramo.

    El riesgo va hacia el incumplimiento (mayor = más riesgo): el tramo 1 es el de menor riesgo,
    como en :func:`~bayesrisk.monitoring.engine.auc_sobre_tramos`. Con cada valor como tramo es el
    AUC del puntaje con los empates en ½ y su varianza de DeLong; los componentes por operación son
    los de su tramo.
    """
    r = np.asarray(riesgo, dtype="float64")
    y = np.asarray(desenlace, dtype="int64")
    valores, tramo = np.unique(r, return_inverse=True)
    k = int(valores.size)
    malos = np.bincount(tramo[y == 1], minlength=k)
    buenos = np.bincount(tramo[y == 0], minlength=k)
    agregado = auc_sobre_tramos(malos.tolist(), buenos.tolist())
    n_malos, n_buenos = int(malos.sum()), int(buenos.sum())
    if agregado.auc is None:
        vacio = np.zeros(0)
        return Componentes(None, None, vacio, vacio, n_malos, n_buenos, causa=agregado.cause)
    total_buenos, total_malos = float(n_buenos), float(n_malos)
    v10_tramo = (np.cumsum(buenos) - buenos + 0.5 * buenos) / total_buenos
    v01_tramo = (total_malos - np.cumsum(malos) + 0.5 * malos) / total_malos
    return Componentes(
        agregado.auc,
        agregado.variance,
        v10_tramo[tramo[y == 1]],
        v01_tramo[tramo[y == 0]],
        n_malos,
        n_buenos,
        causa=agregado.cause,
    )


@dataclass(frozen=True, slots=True)
class PruebaPareada:
    """La prueba de DeLong pareada entre dos modelos.

    ``estado``: ``"ok"`` (con estadístico y p-valor), ``"empate_sin_varianza"`` (los dos AUC
    iguales y la varianza de la diferencia nula: dos modelos idénticos) o ``"no_evaluable"`` (con
    su causa: pocos malos o buenos, o varianza nula con AUC distintos).
    """

    diferencia: float | None
    estadistico: float | None
    p_valor: float | None
    estado: Literal["ok", "empate_sin_varianza", "no_evaluable"]
    causa: str | None = None


def _covarianza(x: Any, y: Any) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    return float(np.sum((x - x.mean()) * (y - y.mean())) / (n - 1))


def delong_pareada(a: Componentes, b: Componentes) -> PruebaPareada:
    """``z = (AUC_a - AUC_b)/√(s²_a + s²_b - 2·cov)``, p-valor bilateral.

    Exige que ``a`` y ``b`` vengan de las mismas operaciones en el mismo orden con el mismo
    desenlace (lo comprueba quien llama, por las huellas). Varianza de la diferencia nula: empate
    si los AUC son iguales; si no, «no evaluable» (AUC 1 frente a 0,5, §3.5).
    """
    if a.auc is None or b.auc is None or a.varianza is None or b.varianza is None:
        causa = a.causa if a.auc is None else b.causa
        return PruebaPareada(None, None, None, "no_evaluable", causa=causa)
    if len(a.v10) != len(b.v10) or len(a.v01) != len(b.v01):
        return PruebaPareada(None, None, None, "no_evaluable", causa="muestras_distintas")
    diferencia = a.auc - b.auc
    covarianza = _covarianza(a.v10, b.v10) / a.n_malos + _covarianza(a.v01, b.v01) / a.n_buenos
    varianza = a.varianza + b.varianza - 2.0 * covarianza
    escala = a.varianza + b.varianza
    if not math.isfinite(varianza) or varianza <= _CERO_RELATIVO * max(escala, 0.0):
        if diferencia == 0.0:
            return PruebaPareada(0.0, None, None, "empate_sin_varianza")
        return PruebaPareada(diferencia, None, None, "no_evaluable", causa="zero_variance")
    z = diferencia / math.sqrt(varianza)
    return PruebaPareada(diferencia, z, math.erfc(abs(z) / math.sqrt(2.0)), "ok")


# ── La frontera como núcleo (§3.5) ───────────────────────────────────────────────────────────


def frontera(
    n: int, supera: Callable[[int, int], bool]
) -> tuple[tuple[bool, ...], tuple[tuple[int, ...], ...]]:
    """El núcleo de la relación ``supera(y, x)`` sobre ``n`` modelos, y quién saca a cada uno.

    Un modelo está en la frontera si ningún modelo **de la frontera** lo supera. La relación no
    tiene ciclos (§3.5), así que el núcleo existe y es único; se calcula en orden: primero los que
    nadie supera, después cada uno contra los ya clasificados. Devuelve, por modelo, si está en la
    frontera y los modelos de la frontera que lo superan (vacío para los de la frontera).
    """
    superadores = [tuple(y for y in range(n) if y != x and supera(y, x)) for x in range(n)]
    en_frontera: list[bool | None] = [None] * n
    pendientes = set(range(n))
    while pendientes:
        listos = sorted(
            x for x in pendientes if all(en_frontera[y] is not None for y in superadores[x])
        )
        if not listos:
            raise ValueError("la relación «supera» tiene un ciclo: no hay frontera bien definida")
        for x in listos:
            en_frontera[x] = not any(en_frontera[y] for y in superadores[x])
            pendientes.discard(x)
    estado = tuple(bool(v) for v in en_frontera)
    por = tuple(tuple(y for y in superadores[x] if estado[y]) for x in range(n))
    return estado, por


# ── Comparabilidad y unidad (§3.3, §3.7) ─────────────────────────────────────────────────────


def _iguales(a: Any, b: Any) -> bool:
    """Dos huellas conocidas e iguales: una huella ausente nunca prueba igualdad."""
    return a is not None and b is not None and a == b


def misma_muestra_evaluada(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Las mismas operaciones, en el mismo orden canónico, con el mismo desenlace (§3.3)."""
    ea, eb = a.get("evaluation_scores"), b.get("evaluation_scores")
    if not isinstance(ea, Mapping) or not isinstance(eb, Mapping):
        return False
    return (
        _iguales(a.get("portfolio_hash"), b.get("portfolio_hash"))
        and _iguales(ea.get("rows_hash"), eb.get("rows_hash"))
        and _iguales(ea.get("default_hash"), eb.get("default_hash"))
    )


def _monedas_distintas(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    ma, mb = a.get("currency"), b.get("currency")
    return ma is not None and mb is not None and ma != mb


def nivel_de_comparabilidad(ref: Mapping[str, Any], otro: Mapping[str, Any]) -> Nivel:
    """El nivel de ``otro`` contra la referencia: misma muestra, misma cartera u otra cartera.

    En IFRS 9 la misma cartera exige también la misma fecha de corte y que las monedas declaradas
    no difieran (§8); una provisión no tiene muestra evaluada.
    """
    misma_cartera = _iguales(ref.get("portfolio_hash"), otro.get("portfolio_hash"))
    if ref.get("family") == "ifrs9":
        misma_fecha = ref.get("as_of") == otro.get("as_of")
        if misma_cartera and misma_fecha and not _monedas_distintas(ref, otro):
            return "misma_cartera"
        return "otra_cartera"
    if misma_muestra_evaluada(ref, otro):
        return "misma_muestra"
    return "misma_cartera" if misma_cartera else "otra_cartera"


def misma_unidad(a: Mapping[str, Any], b: Mapping[str, Any]) -> tuple[bool, str]:
    """Si los montos de dos provisiones se pueden restar, y por qué (§3.7, D-MON).

    Por **construcción**: la misma cartera y las mismas columnas de monto, sin monedas declaradas
    distintas. Por **declaración**: las dos declaran la misma moneda. Una moneda sin declarar no
    es «la misma»: no prueba nada.
    """
    if _monedas_distintas(a, b):
        return False, "monedas_distintas"
    if a.get("currency") is not None and a.get("currency") == b.get("currency"):
        return True, "misma_moneda"
    columnas_a, columnas_b = a.get("amount_columns"), b.get("amount_columns")
    if (
        _iguales(a.get("portfolio_hash"), b.get("portfolio_hash"))
        and columnas_a is not None
        and columnas_a == columnas_b
    ):
        return True, "misma_cartera_y_columnas"
    return False, "unidad_no_probada"
