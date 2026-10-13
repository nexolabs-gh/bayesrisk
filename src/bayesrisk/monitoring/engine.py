"""Motor numérico del monitoreo (SDD-33 §3): funciones puras sobre conteos y arreglos.

Sin estado y sin ``Study``: el paso (:mod:`bayesrisk.monitoring.step`) aplica la tarjeta por
periodo, cuenta y llama a estas funciones. Todo lo que aquí es un número fijo es una **constante**
con su fuente (§5.2 y §13 del SDD; D-MNT-6): no se configura.

Lo que se **reutiliza** (SDD-31 §12.1-3: conectar, no reimplementar):

- el PSI de ``stability`` —sus cortes por cuantiles de Desarrollo, su conteo con la misma regla de
  igualdad y su fórmula con el suavizado de proporciones **cero**—;
- el contraste de Jeffreys de ``validation`` (``binomial_by_grade``), que la escala maestra ya usa
  por tramo y que aquí da también el de cartera: la PD esperada es la media de la PD del tramo
  sobre las mismas filas con desenlace (§3.3);
- el semáforo de ``validation`` (``traffic_light``) con los cortes 0,05/0,01 (D-VAL-15).

Lo único nuevo de cálculo son las dos pruebas de discriminación de §3.4: el AUC sobre los tramos
con la varianza del anexo 3.1 del BCE (y su prueba contra el AUC inicial) y la pendiente de
calibración de Cox (1958), ajustada por Newton sobre los conteos por tramo —statsmodels vive en un
extra y la regresión tiene dos parámetros—. Y la tabla de decisión de §3.5.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import numpy as np
import pandas as pd

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.master_scale.engine import MIN_ROWS_EVALUABLE

__all__ = [
    "ALFA_ROJO",
    "ALFA_VERDE",
    "DECILES",
    "MIN_MALOS_AUC",
    "MIN_ROWS_EVALUABLE",
    "PSI_ROJO",
    "PSI_VERDE",
    "SUAVIZADO",
    "VEREDICTOS",
    "AucSobreTramos",
    "Calibracion",
    "EstadoDelPeriodo",
    "Pendiente",
    "PruebaDelBce",
    "Veredicto",
    "auc_sobre_tramos",
    "calibracion_de_cartera",
    "conteos_por_corte",
    "cortes_del_puntaje",
    "pendiente_de_calibracion",
    "peor",
    "prueba_del_bce",
    "psi",
    "semaforo",
    "semaforo_psi",
    "veredicto_del_periodo",
]

Semaforo = Literal["green", "amber", "red", "not_evaluable"]

#: §3.2: las bandas del PSI de ``stability`` (``psi_stable_threshold``/``psi_review_threshold`` de
#: fábrica; convención de la industria, que ni el BCE ni Basilea fijan): < 0,10 estable, < 0,25
#: revisar, desde 0,25 rojo.
PSI_VERDE: Final = 0.10
PSI_ROJO: Final = 0.25
#: §3.2: los cortes del puntaje son los deciles de Desarrollo (``psi_bins`` de fábrica) y una
#: proporción cero se reemplaza por 10⁻⁶ (``smoothing`` de fábrica). Un test los ata a
#: ``stability``.
DECILES: Final = 10
SUAVIZADO: Final = 1e-6
#: §3.3 y §3.4: el semáforo de los p-valores, con los cortes de la validación y la escala
#: (política institucional publicada, D-VAL-15; el BCE no los fija).
ALFA_VERDE: Final = 0.05
ALFA_ROJO: Final = 0.01
#: §3.4: la plantilla del BCE (hoja 4.0) no calcula el AUC con menos de 2 incumplimientos; el mismo
#: mínimo para los buenos, sin los cuales la U de Mann-Whitney no tiene varianza.
MIN_MALOS_AUC: Final = 2
#: §3.4: Newton sobre dos parámetros converge en pocas iteraciones; el tope sólo corta un ajuste
#: que no converge (una separación que el control previo no vio), que queda «no evaluable».
_ITERACIONES_MAXIMAS: Final = 100
_TOLERANCIA: Final = 1e-10

#: §3.5: los cinco veredictos, del que menos al que más pide (identificadores del motor; el
#: resumen los dice en español).
VEREDICTOS: Final[tuple[str, ...]] = (
    "no_outcome_yet",
    "no_action",
    "watch",
    "recalibrate",
    "redevelop",
)
_GRAVEDAD: Final[dict[str, int]] = {"not_evaluable": -1, "green": 0, "amber": 1, "red": 2}

_SCIPY_MESSAGE: Final = "El monitoreo requiere scipy; instale bayesrisk[scoring]."


def _stats() -> Any:
    try:
        return importlib.import_module("scipy.stats")
    except ModuleNotFoundError as exc:  # pragma: no cover - el extra scoring trae scipy
        raise MissingDependencyError(_SCIPY_MESSAGE) from exc


# ── semáforos ───────────────────────────────────────────────────────────────────────────


def semaforo(p_valor: float | None) -> Semaforo:
    """El semáforo de un p-valor con los cortes 0,05/0,01; sin p-valor, «no evaluable»."""
    if p_valor is None or not math.isfinite(p_valor):
        return "not_evaluable"
    from bayesrisk.validation.calibration_tests import traffic_light

    return traffic_light(min(1.0, max(0.0, p_valor)), green_alpha=ALFA_VERDE, red_alpha=ALFA_ROJO)


def semaforo_psi(valor: float | None) -> Semaforo:
    """La banda del PSI de ``stability`` como semáforo; sin valor, «no evaluable»."""
    if valor is None or not math.isfinite(valor):
        return "not_evaluable"
    if valor < PSI_VERDE:
        return "green"
    if valor < PSI_ROJO:
        return "amber"
    return "red"


def peor(*semaforos: Semaforo) -> Semaforo:
    """El más grave de los evaluables; «no evaluable» sólo si ninguno lo es."""
    evaluables = [s for s in semaforos if s != "not_evaluable"]
    if not evaluables:
        return "not_evaluable"
    return max(evaluables, key=lambda s: _GRAVEDAD[s])


# ── población (§3.2) ────────────────────────────────────────────────────────────────────


def cortes_del_puntaje(puntajes_de_desarrollo: Sequence[float] | np.ndarray) -> tuple[float, ...]:
    """Los cortes efectivos del PSI del puntaje, con la regla de ``stability`` (§3.7).

    Cuantiles de Desarrollo en los deciles interiores, únicos (un puntaje discreto da menos de diez
    bins) y con las colas abiertas.
    """
    from bayesrisk.stability.evaluator import _quantile_interior_edges

    valores = np.asarray(puntajes_de_desarrollo, dtype="float64")
    valores = valores[np.isfinite(valores)]
    if valores.size == 0:
        return ()
    return tuple(float(c) for c in _quantile_interior_edges(valores, DECILES, np))


def conteos_por_corte(
    valores: Sequence[float] | np.ndarray, cortes: Sequence[float]
) -> tuple[int, ...]:
    """Cuántos valores caen en cada bin, con la regla de igualdad de ``stability``.

    Un valor igual a un corte cae en el bin superior (``searchsorted(side="right")``).
    """
    datos = np.asarray(valores, dtype="float64")
    datos = datos[np.isfinite(datos)]
    bordes = np.asarray(cortes, dtype="float64")
    indices = np.searchsorted(bordes, datos, side="right")
    return tuple(int(c) for c in np.bincount(indices, minlength=bordes.size + 1))


def psi(referencia: Sequence[int], actual: Sequence[int]) -> float | None:
    """El PSI de ``stability`` entre dos conteos por bin; ``None`` si una de las dos está vacía.

    ``Σ (a - e)·ln(a / e)`` con las proporciones de cada lado y **sólo** las proporciones cero
    reemplazadas por 10⁻⁶ (una positiva, aunque menor, se usa tal cual).
    """
    from bayesrisk.stability.evaluator import _psi_from_counts

    if len(referencia) != len(actual):
        raise ValueError("El PSI compara dos conteos con los mismos bins.")
    n_ref, n_act = int(sum(referencia)), int(sum(actual))
    if n_ref <= 0 or n_act <= 0:
        return None
    conteos = [
        (f"bin_{i:02d}", int(r), int(a))
        for i, (r, a) in enumerate(zip(referencia, actual, strict=True))
    ]
    return float(_psi_from_counts(conteos, n_ref, n_act, SUAVIZADO).total)


# ── calibración (§3.3) ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Calibracion:
    """El contraste de Jeffreys y su espejo sobre un conjunto de filas con desenlace.

    ``p_under`` es el del BCE (la PD esperada es demasiado baja: el riesgo se subestima);
    ``p_over``, su espejo (la PD es demasiado alta). ``light`` es el peor de los dos y
    ``direction``, la cola que no está en verde (las dos no pueden estarlo: suman 1).
    """

    n: int
    n_bad: int
    bad_rate: float | None
    expected_pd: float | None
    p_under: float | None
    p_over: float | None
    light_under: Semaforo
    light_over: Semaforo
    light: Semaforo
    direction: Literal["under", "over"] | None
    cause: str | None = None


def dos_colas(p_under: float | None) -> tuple[float | None, Semaforo, Semaforo, Semaforo, Any]:
    """El espejo de un p-valor del BCE, los dos semáforos, el consolidado y la dirección.

    Un p-valor ausente —``None`` o el ``NaN`` con que una tabla guarda la celda de un tramo no
    evaluable— deja las dos colas «no evaluables»: su espejo no es 0 (sería un rojo inventado).
    """
    if p_under is None or not math.isfinite(p_under):
        return None, "not_evaluable", "not_evaluable", "not_evaluable", None
    p_over = min(1.0, max(0.0, 1.0 - p_under))
    bajo, alto = semaforo(p_under), semaforo(p_over)
    direccion = "under" if bajo != "green" else ("over" if alto != "green" else None)
    return p_over, bajo, alto, peor(bajo, alto), direccion


def calibracion_de_cartera(pd_del_tramo: np.ndarray, malo: np.ndarray) -> Calibracion:
    """El contraste de cartera sobre las filas con desenlace (§3.3, «el número de grados más uno»).

    ``pd_del_tramo`` y ``malo`` son las filas de ``M_t``: la PD esperada es la media de la PD del
    tramo **sobre esas mismas filas**, como la del BCE por grado. Con menos de
    :data:`MIN_ROWS_EVALUABLE` filas con desenlace, «no evaluable» (el mínimo del tramo).
    """
    from bayesrisk.validation.calibration_tests import binomial_by_grade

    pds = np.asarray(pd_del_tramo, dtype="float64")
    y = np.asarray(malo, dtype="float64")
    n = int(y.size)
    malos = int(np.sum(y))
    tasa = malos / n if n else None
    esperada = float(np.mean(pds)) if n else None
    if n < MIN_ROWS_EVALUABLE:
        return Calibracion(
            n=n,
            n_bad=malos,
            bad_rate=tasa,
            expected_pd=esperada,
            p_under=None,
            p_over=None,
            light_under="not_evaluable",
            light_over="not_evaluable",
            light="not_evaluable",
            direction=None,
            cause="few_outcomes",
        )
    frame = pd.DataFrame({"grade": "cartera", "pd": pds, "target": y.astype("int64")})
    (registro,) = binomial_by_grade(
        frame, grade_col="grade", pd_col="pd", target_col="target", test="jeffreys"
    )
    p_under = float(registro.p_value)
    p_over, bajo, alto, luz, direccion = dos_colas(p_under)
    return Calibracion(
        n=n,
        n_bad=malos,
        bad_rate=tasa,
        expected_pd=esperada,
        p_under=p_under,
        p_over=p_over,
        light_under=bajo,
        light_over=alto,
        light=luz,
        direction=direccion,
    )


# ── discriminación (§3.4) ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AucSobreTramos:
    """El AUC del periodo sobre los tramos y su varianza (BCE §2.5.4 y anexo 3.1).

    ``cause`` dice por qué la prueba no es evaluable (pocos malos o buenos, varianza nula); el AUC
    se publica igual cuando se puede calcular.
    """

    auc: float | None
    variance: float | None
    n_bad: int
    n_good: int
    cause: str | None = None


def auc_sobre_tramos(
    malos_por_tramo: Sequence[int], buenos_por_tramo: Sequence[int]
) -> AucSobreTramos:
    """La U de Mann-Whitney sobre los tramos, con empates en ½, y la varianza del anexo 3.1.

    Los conteos van por tramo, del 1 (menor riesgo) al K. Un malo en el tramo ``g`` es concordante
    con cada bueno de un tramo de menor riesgo y empata con los de su tramo:
    ``V₁₀(g) = (buenos en tramos < g + ½·buenos en g) / |B|``; un bueno en ``h``,
    ``V₀₁(h) = (malos en tramos > h + ½·malos en h) / |A|``. ``AUC`` es la media de ``V₁₀``
    sobre los malos y ``s² = var̂(V₁₀)/|A| + var̂(V₀₁)/|B|``, con las varianzas insesgadas. Es
    exactamente la suma par a par del anexo, agregada por tramo.
    """
    d = np.asarray(malos_por_tramo, dtype="float64")
    b = np.asarray(buenos_por_tramo, dtype="float64")
    total_malos, total_buenos = float(d.sum()), float(b.sum())
    n_malos, n_buenos = int(total_malos), int(total_buenos)
    if n_malos < MIN_MALOS_AUC:
        return AucSobreTramos(None, None, n_malos, n_buenos, cause="few_bads")
    if n_buenos < MIN_MALOS_AUC:
        return AucSobreTramos(None, None, n_malos, n_buenos, cause="few_goods")
    buenos_de_menor_riesgo = np.cumsum(b) - b
    v10 = (buenos_de_menor_riesgo + 0.5 * b) / total_buenos
    malos_de_mayor_riesgo = total_malos - np.cumsum(d)
    v01 = (malos_de_mayor_riesgo + 0.5 * d) / total_malos
    auc = float(np.sum(d * v10) / total_malos)
    var10 = float(np.sum(d * (v10 - auc) ** 2) / (total_malos - 1.0))
    var01 = float(np.sum(b * (v01 - auc) ** 2) / (total_buenos - 1.0))
    varianza = var10 / total_malos + var01 / total_buenos
    if not math.isfinite(varianza) or varianza <= 0.0:
        return AucSobreTramos(auc, varianza, n_malos, n_buenos, cause="zero_variance")
    return AucSobreTramos(auc, varianza, n_malos, n_buenos)


@dataclass(frozen=True, slots=True)
class PruebaDelBce:
    """La prueba del BCE contra el AUC inicial (§2.5.4.1): ``S`` y ``1 - Φ(S)``."""

    statistic: float | None
    p_value: float | None
    light: Semaforo
    cause: str | None = None


def prueba_del_bce(auc_inicial: float, periodo: AucSobreTramos) -> PruebaDelBce:
    """``S = (AUC₀ - AUC_t)/s_t``, p-valor ``1 - Φ(S)``; «no evaluable» con la causa del AUC."""
    if periodo.cause is not None or periodo.auc is None or periodo.variance is None:
        return PruebaDelBce(None, None, "not_evaluable", cause=periodo.cause)
    s = (float(auc_inicial) - periodo.auc) / math.sqrt(periodo.variance)
    p = float(_stats().norm.sf(s))
    return PruebaDelBce(float(s), p, semaforo(p))


@dataclass(frozen=True, slots=True)
class Pendiente:
    """La pendiente de calibración de Cox: ``logit P(y=1) = a + b·logit(p_g)`` sobre ``M_t``.

    Contraste unilateral ``z = (b - 1)/se(b)``, p-valor ``Φ(z)``: un p-valor chico rechaza que la
    pendiente no sea menor que 1 (los tramos separan menos de lo que el modelo promete).
    """

    slope: float | None
    std_error: float | None
    intercept: float | None
    statistic: float | None
    p_value: float | None
    light: Semaforo
    cause: str | None = None


def _no_evaluable(causa: str) -> Pendiente:
    return Pendiente(None, None, None, None, None, "not_evaluable", cause=causa)


def pendiente_de_calibracion(
    n_por_tramo: Sequence[int], malos_por_tramo: Sequence[int], pd_por_tramo: Sequence[float]
) -> Pendiente:
    """Ajusta la regresión logística agrupada por tramo con Newton y contrasta ``b < 1``.

    Los tramos sin filas con desenlace no entran. «No evaluable», con su causa: menos de 2 malos
    o de 2 buenos; menos de dos PD distintas entre los tramos con desenlace (la igualación de PAVA
    puede dar la misma PD a dos tramos: el logit es constante y la pendiente no se identifica);
    separación perfecta (no existe el estimador de máxima verosimilitud); matriz de información no
    invertible; error estándar no finito; o el ajuste no converge.
    """
    n = np.asarray(n_por_tramo, dtype="float64")
    d = np.asarray(malos_por_tramo, dtype="float64")
    p = np.asarray(pd_por_tramo, dtype="float64")
    con = n > 0
    n, d, p = n[con], d[con], p[con]
    if float(d.sum()) < MIN_MALOS_AUC:
        return _no_evaluable("few_bads")
    if float((n - d).sum()) < MIN_MALOS_AUC:
        return _no_evaluable("few_goods")
    if np.any((p <= 0.0) | (p >= 1.0)) or not np.all(np.isfinite(p)):
        return _no_evaluable("pd_out_of_range")
    x = np.log(p) - np.log1p(-p)
    if np.unique(x).size < 2:
        return _no_evaluable("one_pd")
    x_malos, x_buenos = x[d > 0], x[(n - d) > 0]
    if x_buenos.max() <= x_malos.min() or x_malos.max() <= x_buenos.min():
        return _no_evaluable("separation")

    def log_verosimilitud(a: float, b: float) -> float:
        eta = a + b * x
        return float(np.sum(d * eta - n * np.logaddexp(0.0, eta)))

    tasa = float(d.sum() / n.sum())
    a, b = math.log(tasa) - math.log1p(-tasa), 0.0
    actual = log_verosimilitud(a, b)
    convergio = False
    for _ in range(_ITERACIONES_MAXIMAS):
        mu = 1.0 / (1.0 + np.exp(-(a + b * x)))
        w = n * mu * (1.0 - mu)
        gradiente = np.array([np.sum(d - n * mu), np.sum(x * (d - n * mu))])
        informacion = np.array(
            [[np.sum(w), np.sum(w * x)], [np.sum(w * x), np.sum(w * x * x)]], dtype="float64"
        )
        det = float(np.linalg.det(informacion))
        if not math.isfinite(det) or det <= 0.0:
            return _no_evaluable("singular_information")
        paso = np.linalg.solve(informacion, gradiente)
        escala = 1.0
        for _ in range(60):
            nuevo = log_verosimilitud(a + escala * paso[0], b + escala * paso[1])
            if nuevo >= actual - 1e-12 * max(1.0, abs(actual)):
                break
            escala /= 2.0
        a, b = a + escala * float(paso[0]), b + escala * float(paso[1])
        actual = log_verosimilitud(a, b)
        if float(np.max(np.abs(escala * paso))) < _TOLERANCIA:
            convergio = True
            break
    if not convergio or not (math.isfinite(a) and math.isfinite(b)):
        return _no_evaluable("not_converged")
    mu = 1.0 / (1.0 + np.exp(-(a + b * x)))
    w = n * mu * (1.0 - mu)
    informacion = np.array(
        [[np.sum(w), np.sum(w * x)], [np.sum(w * x), np.sum(w * x * x)]], dtype="float64"
    )
    det = float(np.linalg.det(informacion))
    if not math.isfinite(det) or det <= 0.0:
        return _no_evaluable("singular_information")
    varianza_b = float(informacion[0, 0] / det)
    if not math.isfinite(varianza_b) or varianza_b <= 0.0:
        return _no_evaluable("singular_information")
    error = math.sqrt(varianza_b)
    z = (b - 1.0) / error
    p_valor = float(_stats().norm.cdf(z))
    return Pendiente(b, error, a, z, p_valor, semaforo(p_valor))


# ── veredicto (§3.5) ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EstadoDelPeriodo:
    """Lo que la tabla de §3.5 lee de un periodo, ya en semáforos.

    ``grades`` es el semáforo consolidado (las dos colas) de cada tramo; ``previous_red_grades``,
    los tramos rojos del periodo anterior **presente** en el orden de la columna.
    """

    population: Semaforo
    with_outcome: bool
    portfolio: Semaforo = "not_evaluable"
    grades: Mapping[int, Semaforo] = field(default_factory=dict)
    previous_red_grades: frozenset[int] = frozenset()
    auc_test: Semaforo = "not_evaluable"
    slope: Semaforo = "not_evaluable"


@dataclass(frozen=True, slots=True)
class Veredicto:
    """El veredicto de un periodo, la regla que lo decidió y lo que la dispara."""

    verdict: str
    rule: str
    red_grades: tuple[int, ...] = ()
    repeated_red_grades: tuple[int, ...] = ()


def _ambar_que_pide_vigilar(e: EstadoDelPeriodo) -> bool:
    """«Cualquier ámbar» de la fila 3: el de los indicadores de la cartera.

    El PSI (del puntaje o de los tramos), la calibración de cartera y cada prueba de
    discriminación. El ámbar de un tramo solo no: un tramo rojo aislado ya sólo pide vigilar
    (§0.4-4), y con K tramos a alfa = 0,05 uno sale ámbar por azar en uno de cada cuatro o cinco
    periodos.
    """
    return "amber" in (e.population, e.portfolio, e.auc_test, e.slope)


def veredicto_del_periodo(e: EstadoDelPeriodo) -> Veredicto:
    """La tabla de §3.5, leída en orden; gana la primera fila que se cumple (D-MNT-5).

    Antes de las filas, un periodo sin desenlace: con la población roja o ámbar, vigilar; si no,
    «sin desenlace aún» (nunca «sin acción»). Lo no evaluable no cuenta como verde ni como rojo.
    """
    rojos = tuple(sorted(g for g, luz in e.grades.items() if luz == "red"))
    repetidos = tuple(g for g in rojos if g in e.previous_red_grades)
    if not e.with_outcome:
        if e.population in ("red", "amber"):
            return Veredicto("watch", "no_outcome_population_moved")
        return Veredicto("no_outcome_yet", "no_outcome")
    if e.auc_test == "red" and e.slope == "red":
        return Veredicto("redevelop", "discrimination_red", rojos, repetidos)
    if e.portfolio == "red":
        return Veredicto("recalibrate", "portfolio_red", rojos, repetidos)
    if len(rojos) >= 2:
        return Veredicto("recalibrate", "two_red_grades", rojos, repetidos)
    if repetidos:
        return Veredicto("recalibrate", "repeated_red_grade", rojos, repetidos)
    if e.population == "red":
        return Veredicto("watch", "population_red", rojos, repetidos)
    if "red" in (e.auc_test, e.slope):
        return Veredicto("watch", "one_discrimination_test_red", rojos, repetidos)
    if rojos:
        return Veredicto("watch", "isolated_red_grade", rojos, repetidos)
    if _ambar_que_pide_vigilar(e):
        return Veredicto("watch", "amber", rojos, repetidos)
    return Veredicto("no_action", "all_green", rojos, repetidos)
