"""Motor numérico de la escala maestra (SDD-32 §3, §7): funciones puras sobre arreglos.

Sin estado y sin ``Study``: el paso (:mod:`bayesrisk.master_scale.step`) lee los artefactos, llama
a estas funciones y publica. Todo lo que aquí es un número fijo es una **constante** con su razón
(§5.2 y §13 del SDD): no se configura.

- :func:`formar_cortes` — D-ESC-1: los tramos que forman los datos, con el binning monótono óptimo
  que la librería ya usa para las variables (OptBinning, el mismo solver ``mip``/``bop``).
- :func:`asignar_tramos` / :func:`aprobar` — la **regla única** de §3.2: ``s ≥ c`` al lado de
  puntaje mayor, ``s < c`` al de menor, en las dos direcciones; la dirección sólo dice qué lado es
  el de menor riesgo. Se compara siempre con ``c`` exacto.
- :func:`pd_por_tramo` — D-ESC-2: tasa suavizada, igualación isotónica (§12-8) y el
  desplazamiento común ``δ`` que reconcilia con el ancla de la calibración.
- :func:`tabla_por_tramo` — D-ESC-3: cada tramo en cada muestra, con el contraste de Jeffreys de
  la validación.
- :func:`tabla_de_cortes` — D-ESC-4: aprobados, tasa de malos de los aprobados, PD esperada,
  malos evitados y buenos rechazados, con sus conteos y celdas vacías cuando el denominador es 0.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.master_scale.exceptions import MasterScaleFitError

__all__ = [
    "CUTOFF_TABLE_COLUMNS",
    "GRADE_TABLE_COLUMNS",
    "MAX_GRADES",
    "MAX_PVALUE",
    "MIN_GRADE_SHARE",
    "MIN_ROWS_EVALUABLE",
    "DiagnosticoDeMuestra",
    "Formacion",
    "PdDeTramos",
    "aprobar",
    "asignar_tramos",
    "corte_de_los_primeros",
    "diagnostico_por_muestra",
    "formar_cortes",
    "pava",
    "pd_por_tramo",
    "tabla_de_cortes",
    "tabla_por_tramo",
    "vecinos_que_no_se_distinguen",
    "z_entre_vecinos",
]

#: D-ESC-1, regla 2: cada tramo con al menos el 5 % de Desarrollo, la misma cota que la puerta
#: guiada usa para los tramos de cada variable (``min_bin_size=0.05``; Basilea II §409).
MIN_GRADE_SHARE: Final = 0.05
#: D-ESC-1, regla 3: tasas de malos de tramos vecinos distintas con p ≤ 0,05 (Z de OptBinning entre
#: tramos consecutivos; Basilea II §410 y 12 CFR 217.122(b)(1)(i)).
MAX_PVALUE: Final = 0.05
#: D-ESC-1, regla 4: hasta diez tramos (mantiene la escala operable; sólo obligó en la SBA).
MAX_GRADES: Final = 10
#: D-ESC-3: bajo 30 operaciones con desenlace un tramo no se contrasta («No evaluable»); es el
#: mínimo de la validación (``validation.min_rows_per_group``).
MIN_ROWS_EVALUABLE: Final = 30
#: El solver del binning de la librería (``binning.solver`` de fábrica): ``cp`` se cuelga en
#: variables continuas con ortools ≥ 9.12 (D-ABA-5). Medido en S42: sobre las dos carteras del
#: paquete forma los mismos cortes que el ``cp`` de la medición de S41.
_SOLVER: Final[dict[str, str]] = {"solver": "mip", "mip_solver": "bop"}
#: Estados del solver con una partición utilizable.
_ESTADOS_UTILES: Final = frozenset({"OPTIMAL", "FEASIBLE"})

GRADE_TABLE_COLUMNS: Final[tuple[str, ...]] = (
    "sample",
    "grade",
    "n",
    "share",
    "n_with_outcome",
    "n_bad",
    "bad_rate",
    "pd",
    "jeffreys_p_value",
    "traffic_light",
)
CUTOFF_TABLE_COLUMNS: Final[tuple[str, ...]] = (
    "sample",
    "grades_approved",
    "cutoff_score",
    "declared",
    "n_scored",
    "n_with_outcome",
    "n_approved",
    "n_approved_with_outcome",
    "n_bad",
    "n_good",
    "approved_share",
    "approved_bad_rate",
    "approved_expected_pd",
    "bads_avoided_share",
    "goods_rejected_share",
)


@dataclass(frozen=True, slots=True)
class Formacion:
    """Los cortes que formaron los datos y el estado del solver que los produjo."""

    cuts: tuple[float, ...]
    status: str
    cause: str | None = None


@dataclass(frozen=True, slots=True)
class PdDeTramos:
    """La PD de cada tramo (1 = menor riesgo), el ``δ`` del ancla y los tramos igualados."""

    pd: tuple[float, ...]
    smoothed_rate: tuple[float, ...]
    delta: float
    anchor: float
    equalized: tuple[tuple[int, ...], ...]


def _import_optimal_binning() -> type[Any]:
    """``OptimalBinning`` de OptBinning (el extra ``scoring``); los tests lo sustituyen."""
    try:
        optbinning = importlib.import_module("optbinning")
    except ImportError as exc:
        raise MissingDependencyError(
            "La escala maestra requiere OptBinning; instale bayesrisk[scoring]."
        ) from exc
    return cast("type[Any]", optbinning.OptimalBinning)


def formar_cortes(
    score: np.ndarray[Any, Any], target: np.ndarray[Any, Any], *, mayor_es_menor_riesgo: bool
) -> Formacion:
    """D-ESC-1: los cortes de los tramos que forman los datos de Desarrollo.

    Monótonos (la tasa de malos baja al subir el puntaje con la dirección de fábrica), con al
    menos :data:`MIN_GRADE_SHARE` de las operaciones por tramo, tasas de vecinos distintas con
    p ≤ :data:`MAX_PVALUE` y hasta :data:`MAX_GRADES`; la pre-segmentación y el resto, los de
    fábrica de OptBinning (CART en hasta 20 grupos de al menos 5 %). El número de tramos no se
    configura. Si el solver no entrega una partición —o falla—, la escala es **un** tramo y la
    causa viaja en ``cause``: la escala es operativa, no un gate del modelo (§8).
    """
    # Los avisos conocidos y ratificados de OptBinning (SDD-06 §9) se silencian como en el binning
    # de las variables: con los avisos como error (pytest, o quien lo configure) el aviso de
    # scikit-learn sobre `force_all_finite` dejaba la escala en un tramo (censo de S42).
    from bayesrisk.binning.transformer import _suppress_known_optbinning_warnings

    clase = _import_optimal_binning()
    tendencia = "descending" if mayor_es_menor_riesgo else "ascending"
    try:
        with _suppress_known_optbinning_warnings():
            binning = clase(
                name="score",
                dtype="numerical",
                monotonic_trend=tendencia,
                min_bin_size=MIN_GRADE_SHARE,
                max_n_bins=MAX_GRADES,
                max_pvalue=MAX_PVALUE,
                max_pvalue_policy="consecutive",
                **_SOLVER,
            )
            binning.fit(np.asarray(score, dtype="float64"), np.asarray(target, dtype="int64"))
        estado = str(binning.status)
    except Exception as exc:  # la escala degrada a un tramo; la corrida no se detiene (§8)
        return Formacion(cuts=(), status="ERROR", cause=f"{type(exc).__name__}: {exc}")
    if estado not in _ESTADOS_UTILES:
        return Formacion(cuts=(), status=estado, cause=f"el solver terminó en {estado}")
    cortes = tuple(sorted(float(c) for c in np.asarray(binning.splits, dtype="float64")))
    return Formacion(cuts=cortes, status=estado)


def asignar_tramos(
    score: np.ndarray[Any, Any], cuts: Sequence[float], *, mayor_es_menor_riesgo: bool
) -> np.ndarray[Any, Any]:
    """El tramo de cada puntaje (1 = menor riesgo) con la regla única de §3.2; 0 si no hay puntaje.

    ``searchsorted(..., side="right")`` cuenta los cortes ``c ≤ s``: un puntaje igual a un corte
    cae al lado de puntaje mayor (``s ≥ c``), en las dos direcciones.
    """
    valores = np.asarray(score, dtype="float64")
    cortes = np.asarray(sorted(float(c) for c in cuts), dtype="float64")
    k = len(cortes) + 1
    sobre = np.searchsorted(cortes, valores, side="right")
    tramo = (k - sobre) if mayor_es_menor_riesgo else (sobre + 1)
    return np.where(np.isnan(valores), 0, tramo).astype("int64")


def aprobar(
    score: np.ndarray[Any, Any], cutoff: float | None, *, mayor_es_menor_riesgo: bool
) -> np.ndarray[Any, Any]:
    """Si cada puntaje queda del lado aprobado (de menor riesgo) del corte, con la regla única.

    Sin corte (``None``) se aprueba todo; un puntaje ausente nunca se aprueba.
    """
    valores = np.asarray(score, dtype="float64")
    presentes: np.ndarray[Any, Any] = ~np.isnan(valores)
    if cutoff is None:
        return presentes
    with np.errstate(invalid="ignore"):
        lado: np.ndarray[Any, Any] = (
            valores >= float(cutoff) if mayor_es_menor_riesgo else valores < float(cutoff)
        )
    aprobado: np.ndarray[Any, Any] = lado & presentes
    return aprobado


def corte_de_los_primeros(
    k: int, cuts: Sequence[float], *, mayor_es_menor_riesgo: bool
) -> float | None:
    """El corte que aprueba exactamente los tramos ``1…k``; ``None`` si ``k`` los aprueba todos."""
    cortes = sorted(float(c) for c in cuts)
    total = len(cortes) + 1
    if k >= total:
        return None
    return cortes[total - k - 1] if mayor_es_menor_riesgo else cortes[k - 1]


def pava(
    valores: Sequence[float], pesos: Sequence[float]
) -> tuple[np.ndarray[Any, Any], list[list[int]]]:
    """Regresión isotónica no decreciente ponderada (PAVA) y los bloques que agrupó.

    Devuelve los valores ajustados y la lista de bloques (posiciones consecutivas) en orden. Dos
    vecinos con el mismo valor también se agrupan (el ajuste no cambia): no se distinguen, y así
    la PD sólo empata entre tramos que la regla de §12-8 igualó y alertó (§6.3 del SDD-32).
    """
    bloques: list[list[Any]] = []  # [valor, peso, posiciones]
    for posicion, (valor, peso) in enumerate(zip(valores, pesos, strict=True)):
        bloques.append([float(valor), float(peso), [posicion]])
        while len(bloques) > 1 and bloques[-2][0] >= bloques[-1][0]:
            v2, w2, p2 = bloques.pop()
            v1, w1, p1 = bloques.pop()
            bloques.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, p1 + p2])
    ajustados = np.empty(len(valores), dtype="float64")
    for valor, _peso, posiciones in bloques:
        ajustados[posiciones] = valor
    return ajustados, [list(b[2]) for b in bloques]


def _logit(p: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    from scipy.special import logit

    salida: np.ndarray[Any, Any] = logit(p)
    return salida


def _expit(x: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """La sigmoide sin desbordar y sin perder los subnormales.

    Con ``x < 0`` se escribe ``exp(x)/(1 + exp(x))``: ``1/(1 + exp(-x))`` se iría a 0 bajo -709
    (pasada 2 de Codex: un ancla de 1e-310).
    """
    valores = np.asarray(x, dtype="float64")
    salida: np.ndarray[Any, Any] = np.empty_like(valores)
    positivos = valores >= 0
    salida[positivos] = 1.0 / (1.0 + np.exp(-valores[positivos]))
    exponencial = np.exp(valores[~positivos])
    salida[~positivos] = exponencial / (1.0 + exponencial)
    return salida


#: Los extremos representables del intervalo abierto (0, 1): una PD de tramo nunca es 0 ni 1 (la
#: tarjeta lo exige). Junto a los bordes el `float` redondea a 0 o 1; se acota al vecino interior.
_PD_MINIMA: Final = float(np.nextafter(0.0, 1.0))
_PD_MAXIMA: Final = float(np.nextafter(1.0, 0.0))


def pd_por_tramo(n: Sequence[int], d: Sequence[int], *, ancla: float) -> PdDeTramos:
    """D-ESC-2: la PD de cada tramo desde sus conteos de Desarrollo, llevada al ancla.

    ``r_g = (d_g + ½)/(n_g + 1)`` (media de Jeffreys: nunca 0 ni 1); si el orden se invierte, los
    tramos vecinos comparten el valor de la regresión isotónica ponderada por ``n_g`` (§12-8); y
    ``PD_g = logit⁻¹(logit(r_g) + δ)`` con el ``δ`` único tal que ``Σ (n_g/N)·PD_g = ancla``. El
    desplazamiento común conserva el orden.
    """
    from scipy.optimize import brentq

    n_arr = np.asarray(n, dtype="float64")
    d_arr = np.asarray(d, dtype="float64")
    if n_arr.size == 0 or np.any(n_arr <= 0):
        raise MasterScaleFitError("Cada tramo necesita al menos una operación de Desarrollo.")
    if not 0.0 < float(ancla) < 1.0:
        raise MasterScaleFitError(
            f"El ancla de la calibración debe estar en (0, 1); se recibió {ancla!r}."
        )
    tasa = (d_arr + 0.5) / (n_arr + 1.0)
    ajustada, bloques = pava(tasa.tolist(), n_arr.tolist())
    pesos = n_arr / n_arr.sum()
    base = _logit(ajustada)

    def brecha(delta: float) -> float:
        return float(np.sum(pesos * _expit(base + delta))) - float(ancla)

    # El intervalo sale del ancla y de las tasas: con δ = logit(ancla) - max logit(r) toda PD
    # queda bajo el ancla (brecha ≤ 0) y con δ = logit(ancla) - min logit(r), sobre ella (≥ 0).
    # Un ±20 fijo no cambiaba de signo con anclas extremas (pasada 1 de Codex).
    centro = float(_logit(np.asarray([float(ancla)]))[0])
    bajo, alto = centro - float(base.max()) - 1.0, centro - float(base.min()) + 1.0
    try:
        delta = float(brentq(brecha, bajo, alto, xtol=1e-14, rtol=4 * np.finfo(float).eps))
    except (ValueError, RuntimeError) as exc:  # un fallo numérico es de la etapa, no de Python
        raise MasterScaleFitError(
            f"La PD de los tramos no se pudo reconciliar con el ancla {ancla!r}: {exc}"
        ) from exc
    pd_final = np.clip(_expit(base + delta), _PD_MINIMA, _PD_MAXIMA)
    igualados = tuple(tuple(p + 1 for p in b) for b in bloques if len(b) > 1)
    return PdDeTramos(
        pd=tuple(float(x) for x in pd_final),
        smoothed_rate=tuple(float(x) for x in tasa),
        delta=delta,
        anchor=float(ancla),
        equalized=igualados,
    )


def vecinos_que_no_se_distinguen(
    n: Sequence[int], d: Sequence[int]
) -> tuple[tuple[int, int, float | None], ...]:
    """Los pares de tramos vecinos cuyas tasas de malos no se distinguen (p > 0,05 o sin varianza).

    Sin varianza —los dos sin malos, o los dos sólo con malos— las tasas son iguales y no hay
    p-valor que publicar: el par se declara con ``None`` (pasada 2 de Codex).
    """
    return tuple(
        (g, g + 1, p) for g, p in enumerate(z_entre_vecinos(n, d), 1) if p is None or p > MAX_PVALUE
    )


def z_entre_vecinos(n: Sequence[int], d: Sequence[int]) -> list[float | None]:
    """El p-valor del Z de dos proporciones entre cada par de tramos vecinos (el de OptBinning).

    Bilateral y agrupado, como ``optbinning.binning.metrics.test_proportions``; ``None`` cuando la
    proporción común es 0 o 1 (no hay varianza que contrastar).
    """
    from scipy.stats import norm

    salida: list[float | None] = []
    for (n1, d1), (n2, d2) in pairwise(zip(n, d, strict=True)):
        p1, p2 = d1 / n1, d2 / n2
        p = (d1 + d2) / (n1 + n2)
        varianza = p * (1.0 - p) * (1.0 / n1 + 1.0 / n2)
        if varianza <= 0.0:
            salida.append(None)
            continue
        z = abs(p1 - p2) / math.sqrt(varianza)
        salida.append(float(2.0 * norm.sf(z)))
    return salida


def tabla_por_tramo(
    muestras: Mapping[str, pd.DataFrame], pd_tramo: Sequence[float]
) -> pd.DataFrame:
    """D-ESC-3: cada tramo en cada muestra, con su contraste de Jeffreys y su semáforo.

    ``muestras`` lleva, por muestra, un frame con ``grade`` (1…K) y ``target`` (0/1 o vacío). El
    contraste es el de la validación —``binomial_by_grade`` con ``test="jeffreys"``, unilateral, la
    PD del tramo contra sus malos— sobre las operaciones con desenlace; un tramo con menos de
    :data:`MIN_ROWS_EVALUABLE` queda ``not_evaluable``.
    """
    from bayesrisk.validation.calibration_tests import binomial_by_grade

    filas: list[dict[str, Any]] = []
    k = len(pd_tramo)
    for muestra, frame in muestras.items():
        total = len(frame.index)
        tramos = frame["grade"].to_numpy(dtype="int64")
        objetivo = pd.to_numeric(frame["target"], errors="coerce").to_numpy(dtype="float64")
        con_desenlace = ~np.isnan(objetivo)
        contrastes: dict[int, tuple[float, str]] = {}
        evaluables = [
            g
            for g in range(1, k + 1)
            if int(np.sum((tramos == g) & con_desenlace)) >= MIN_ROWS_EVALUABLE
        ]
        if evaluables:
            mascara = con_desenlace & np.isin(tramos, evaluables)
            sub = pd.DataFrame(
                {
                    "grade": tramos[mascara].astype(str),
                    "pd": np.asarray(pd_tramo, dtype="float64")[tramos[mascara] - 1],
                    "target": objetivo[mascara].astype("int64"),
                }
            )
            for registro in binomial_by_grade(
                sub, grade_col="grade", pd_col="pd", target_col="target", test="jeffreys"
            ):
                contrastes[int(registro.grade)] = (
                    float(registro.p_value),
                    str(registro.traffic_light),
                )
        for g in range(1, k + 1):
            en_tramo = tramos == g
            n_g = int(np.sum(en_tramo))
            n_con = int(np.sum(en_tramo & con_desenlace))
            malos = int(np.nansum(objetivo[en_tramo & con_desenlace]))
            p_valor, semaforo = contrastes.get(g, (None, "not_evaluable"))
            filas.append(
                {
                    "sample": muestra,
                    "grade": g,
                    "n": n_g,
                    "share": (n_g / total) if total else None,
                    "n_with_outcome": n_con,
                    "n_bad": malos if n_con else None,
                    "bad_rate": (malos / n_con) if n_con else None,
                    "pd": float(pd_tramo[g - 1]),
                    "jeffreys_p_value": p_valor,
                    "traffic_light": semaforo,
                }
            )
    return pd.DataFrame(filas, columns=list(GRADE_TABLE_COLUMNS))


def _fila_de_corte(
    muestra: str,
    *,
    aprobado: np.ndarray[Any, Any],
    objetivo: np.ndarray[Any, Any],
    pd_operacion: np.ndarray[Any, Any],
    tramos_aprobados: int | None,
    corte: float | None,
    declarado: bool,
) -> dict[str, Any]:
    con_desenlace = ~np.isnan(objetivo)
    n_puntuadas = int(aprobado.size)
    n_con = int(np.sum(con_desenlace))
    n_aprob = int(np.sum(aprobado))
    aprob_con = aprobado & con_desenlace
    n_aprob_con = int(np.sum(aprob_con))
    malos = int(np.nansum(objetivo[con_desenlace]))
    buenos = n_con - malos
    malos_aprob = int(np.nansum(objetivo[aprob_con]))
    buenos_aprob = n_aprob_con - malos_aprob
    return {
        "sample": muestra,
        "grades_approved": tramos_aprobados,
        "cutoff_score": corte,
        "declared": declarado,
        "n_scored": n_puntuadas,
        "n_with_outcome": n_con,
        "n_approved": n_aprob,
        "n_approved_with_outcome": n_aprob_con,
        "n_bad": malos,
        "n_good": buenos,
        "approved_share": (n_aprob / n_puntuadas) if n_puntuadas else None,
        "approved_bad_rate": (malos_aprob / n_aprob_con) if n_aprob_con else None,
        "approved_expected_pd": (
            float(np.sum(pd_operacion[aprob_con]) / n_aprob_con) if n_aprob_con else None
        ),
        "bads_avoided_share": ((malos - malos_aprob) / malos) if malos else None,
        "goods_rejected_share": ((buenos - buenos_aprob) / buenos) if buenos else None,
    }


def tabla_de_cortes(
    muestras: Mapping[str, pd.DataFrame],
    cuts: Sequence[float],
    pd_tramo: Sequence[float],
    *,
    mayor_es_menor_riesgo: bool,
    corte_declarado: float | None,
) -> pd.DataFrame:
    """D-ESC-4: por muestra, una fila por cada «aprobar los tramos 1…k» y la del corte declarado.

    «Aprobados» se mide sobre todas las operaciones puntuadas de la muestra; las demás columnas,
    sobre las que tienen desenlace (D-CPY-1). Cada fila publica sus conteos y una celda cuyo
    denominador es 0 queda vacía (``None``), nunca en 0 (§3.5). El corte de la institución se
    calcula en su puntaje exacto con el mismo predicado; no tiene que ser un límite de tramo.
    """
    filas: list[dict[str, Any]] = []
    k_total = len(cuts) + 1
    pd_arr = np.asarray(pd_tramo, dtype="float64")
    for muestra, frame in muestras.items():
        puntaje = pd.to_numeric(frame["score"]).to_numpy(dtype="float64")
        objetivo = pd.to_numeric(frame["target"], errors="coerce").to_numpy(dtype="float64")
        tramos = frame["grade"].to_numpy(dtype="int64")
        pd_operacion = pd_arr[tramos - 1]
        for k in range(1, k_total + 1):
            corte = corte_de_los_primeros(k, cuts, mayor_es_menor_riesgo=mayor_es_menor_riesgo)
            filas.append(
                _fila_de_corte(
                    muestra,
                    aprobado=tramos <= k,
                    objetivo=objetivo,
                    pd_operacion=pd_operacion,
                    tramos_aprobados=k,
                    corte=corte,
                    declarado=False,
                )
            )
        if corte_declarado is not None:
            filas.append(
                _fila_de_corte(
                    muestra,
                    aprobado=aprobar(
                        puntaje, corte_declarado, mayor_es_menor_riesgo=mayor_es_menor_riesgo
                    ),
                    objetivo=objetivo,
                    pd_operacion=pd_operacion,
                    tramos_aprobados=None,
                    corte=float(corte_declarado),
                    declarado=True,
                )
            )
    return pd.DataFrame(filas, columns=list(CUTOFF_TABLE_COLUMNS))


@dataclass(frozen=True, slots=True)
class DiagnosticoDeMuestra:
    """Monotonía, inversiones, concentración y semáforos de una muestra (D-ESC-3)."""

    monotonic: bool
    inversions: tuple[tuple[int, int], ...]
    hhi: float | None
    max_share: float | None
    max_share_grade: int | None
    red_grades: tuple[int, ...]
    amber_grades: tuple[int, ...]
    not_evaluable_grades: tuple[int, ...]


def diagnostico_por_muestra(tabla: pd.DataFrame) -> dict[str, DiagnosticoDeMuestra]:
    """Por muestra de :func:`tabla_por_tramo`: si la tasa de malos sigue el orden de los tramos.

    La monotonía se lee **sobre los tramos evaluables** (al menos :data:`MIN_ROWS_EVALUABLE`
    operaciones con desenlace; medido en S41: sin esa condición, un tramo de 6 operaciones de la
    OOT de ``consumo_drift`` daba una inversión espuria): la tasa no decrece al pasar a un tramo de
    más riesgo. La concentración —``HHI = Σ participación²`` y el tramo mayor— se publica y no se
    alerta: ninguna fuente fija un umbral (§3.4).
    """
    salida: dict[str, DiagnosticoDeMuestra] = {}
    for muestra, grupo in tabla.groupby("sample", sort=False):
        grupo = grupo.sort_values("grade")
        evaluables = grupo.loc[grupo["n_with_outcome"] >= MIN_ROWS_EVALUABLE]
        tasas = [
            (int(g), float(t))
            for g, t in zip(evaluables["grade"], evaluables["bad_rate"], strict=True)
        ]
        inversiones = tuple((a, b) for (a, ta), (b, tb) in pairwise(tasas) if tb < ta)
        partes = [float(s) for s in grupo["share"] if s is not None and not pd.isna(s)]
        hhi = float(sum(s * s for s in partes)) if partes else None
        if partes:
            posicion = int(np.argmax(grupo["share"].astype("float64").to_numpy()))
            mayor = float(grupo["share"].iloc[posicion])
            tramo_mayor: int | None = int(grupo["grade"].iloc[posicion])
        else:
            mayor, tramo_mayor = None, None
        luces = dict(
            zip(grupo["grade"].astype(int), grupo["traffic_light"].astype(str), strict=True)
        )
        salida[str(muestra)] = DiagnosticoDeMuestra(
            monotonic=not inversiones,
            inversions=inversiones,
            hhi=hhi,
            max_share=mayor,
            max_share_grade=tramo_mayor,
            red_grades=tuple(g for g, luz in luces.items() if luz == "red"),
            amber_grades=tuple(g for g, luz in luces.items() if luz == "amber"),
            not_evaluable_grades=tuple(g for g, luz in luces.items() if luz == "not_evaluable"),
        )
    return salida
