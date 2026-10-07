"""La PD de tu modelo ancla la curva; el SICR por tramo de vida (IFRS9-FIRMABLE D-FIR-7 y 8).

- **El anclaje** (D-FIR-7, §3.7). Con la PD a 12 meses de hoy de cada operación —de su scorecard o
  de su modelo de rating—, se resuelve un desplazamiento ``s_i`` tal que la PD de los 12 meses
  posteriores al corte de **su** curva, leída desde su edad y sin cortar por el vencimiento, sea esa
  PD; todos sus tramos usan ``logit h + s_i`` (con escenarios, ``δ_k(t)`` encima). La curva conserva
  su forma por edad y toma el nivel del modelo, también en la pérdida de por vida.
- **Existencia y unicidad.** Antes del logit, el riesgo de cada período se acota a
  ``[10⁻¹², 1 - 10⁻¹²]`` (el épsilon de :mod:`bayesrisk.provisioning.ifrs9.pd_pit`): la PD de la
  ventana es continua y estrictamente creciente en ``s`` y va de casi 0 a casi 1, así que para toda
  PD acotada a ``[10⁻⁹, 1 - 10⁻⁹]`` hay un único ``s``, que se resuelve por bisección en
  ``[-50, 50]``. Una operación con un riesgo de la ventana en el borde se cuenta: su forma por edad
  la decide el acotamiento.
- **El SICR por tramo** (D-FIR-8, §3.8). Lo que se esperaba al otorgar para los 12 meses siguientes
  al corte es la curva anclada a la PD de origen **en la edad 0**, leída en ``[A, A + 12 meses]``;
  lo de hoy, la curva anclada a la PD de hoy en la edad ``A`` —por construcción, la PD de hoy— y,
  con escenarios, la PD de esos 12 meses ponderada por escenario.

La ventana de 12 meses son los períodos de la curva que el motor ya usa para el Stage 1 (el
horizonte de 12 meses de la corrida). **Qué NO se configura** (§3.11): la cota de la PD, la del
riesgo, el intervalo de la bisección y el umbral de la reconciliación (25 %). Constantes con su
razón, no perillas.

``pandas``/``numpy`` se importan de forma perezosa.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, TypeAlias, cast

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.provisioning.ifrs9.exceptions import (
    IfrsConfigError,
    IfrsInputError,
    IfrsTermStructureError,
)

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    from bayesrisk.provisioning.ifrs9.config import IfrsProvisioningConfig

    NDArrayFloat: TypeAlias = np.ndarray[Any, np.dtype[np.float64]]
    NDArrayBool: TypeAlias = np.ndarray[Any, np.dtype[np.bool_]]
    DataFrame: TypeAlias = pd.DataFrame
else:
    NDArrayFloat: TypeAlias = Any
    NDArrayBool: TypeAlias = Any
    DataFrame: TypeAlias = Any

__all__ = [
    "PD_MINIMA",
    "RIESGO_MINIMO",
    "UMBRAL_RECONCILIACION",
    "AnchorReading",
    "ModelPd",
    "OriginationReading",
    "anchor_term_structure",
    "bounded_risk",
    "check_model_pd_config",
    "edge_curves",
    "read_model_pd",
    "solve_shift",
    "window_pd",
]

#: §3.7: el riesgo de cada período se acota antes del logit, con el mismo épsilon que la PD de
#: ``pd_pit.py``. Sin la cota, un período con riesgo 0 o 1 deja la PD de la ventana fuera del
#: alcance de cualquier desplazamiento (no habría solución, o no sería única).
RIESGO_MINIMO: Final = 1e-12
#: §3.7: la PD del modelo se acota a ``[10⁻⁹, 1 - 10⁻⁹]`` y se cuenta. Una PD de 0 o 1 no tiene
#: logit; con el riesgo acotado, la ventana alcanza ese rango con un desplazamiento en
#: ``[-50, 50]``.
PD_MINIMA: Final = 1e-9
#: §3.7: el intervalo de la bisección. Con el riesgo acotado, ``sigmoide(logit(10⁻¹²) + 50)`` ya
#: pasa de ``1 - 10⁻⁹`` y ``sigmoide(logit(1 - 10⁻¹²) - 50)`` queda bajo ``10⁻⁹`` en una ventana
#: de un período: la raíz de toda PD acotada queda encerrada.
_DESPLAZAMIENTO_MINIMO: Final = -50.0
_DESPLAZAMIENTO_MAXIMO: Final = 50.0
#: Cada iteración parte el intervalo en dos: 200 agotan la precisión de un ``float`` partiendo de
#: un ancho de 100 (``100 / 2^200``); sobre diez mil operaciones toma milisegundos.
_ITERACIONES: Final = 200
#: §3.7: la reconciliación avisa si la PD media de tu modelo y la de la curva, ponderadas por la
#: exposición, difieren en más de un 25 % relativo: el dato tiene que medir el mismo incumplimiento
#: a 12 meses que la curva y el motor no puede verificarlo de otro modo.
UMBRAL_RECONCILIACION: Final = 0.25

_NUMPY_MESSAGE: Final = "El anclaje a la PD del modelo requiere numpy; instale bayesrisk[scoring]."
_PANDAS_MESSAGE: Final = (
    "El anclaje a la PD del modelo requiere pandas; instale bayesrisk[scoring]."
)


@dataclass(frozen=True)
class ModelPd:
    """Una columna de PD del modelo por operación: acotada, con ``NaN`` donde la fila no la trae."""

    values: NDArrayFloat
    n_missing: int
    n_clipped: int


@dataclass(frozen=True)
class OriginationReading:
    """El SICR por tramo de vida (§3.8), por operación en el orden de la cartera.

    ``expected`` es la PD que se esperaba al otorgar para los 12 meses siguientes al corte;
    ``current``, la de hoy para esos mismos 12 meses (ponderada por escenario si los hay);
    ``ratio``, su cociente. Los tres son ``NaN`` donde falta la PD de hoy o la de origen.
    """

    expected: NDArrayFloat
    current: NDArrayFloat
    ratio: NDArrayFloat
    n_missing: int
    n_clipped: int
    n_not_reached: int = 0


@dataclass(frozen=True)
class AnchorReading:
    """Lo que dejó el anclaje, por operación en el orden de la cartera, y lo que se contó.

    ``shift`` y ``pd_model`` son ``NaN`` en las operaciones sin PD del modelo (la curva sin anclar);
    ``pd_curve`` es la PD de la misma ventana con la curva sin anclar, para la reconciliación;
    ``edge`` marca las operaciones ancladas con algún riesgo de la ventana en el borde.
    """

    shift: NDArrayFloat
    pd_model: NDArrayFloat
    pd_curve: NDArrayFloat
    edge: NDArrayBool
    n_missing: int
    n_clipped: int
    not_reached: NDArrayBool | None = None


def check_model_pd_config(config: IfrsProvisioningConfig) -> None:
    """Lo que el preflight avisa de las dos PD del modelo, comprobado también por código.

    Raises
    ------
    IfrsConfigError
        Si la PD del modelo se declara con una curva que no es la de supervivencia, con la PD a 12
        meses de la calibración o con otro ajuste que el ciclo de la institución; o si la PD al
        otorgar se declara sin la PD de hoy o sin la fecha de otorgamiento.
    """
    if config.pd.pd_12m_col is not None:
        if config.pd.term_structure_source != "survival":
            raise IfrsConfigError(
                "La PD de tu modelo ancla la curva de cada operación desde su edad, y eso sólo se "
                f"puede con la curva de supervivencia; la de {config.pd.term_structure_source} no "
                "es una curva por edad."
            )
        if config.pd.base_pd_source == "calibration":
            raise IfrsConfigError(
                "La PD a 12 meses ya la entrega tu modelo (pd.pd_12m_col): la calibración la "
                "reemplazaría sin anclar la curva. Usa pd.base_pd_source='term_structure'."
            )
        if config.pd.pit_mode not in ("ttc_only", "cycle"):
            raise IfrsConfigError(
                "La PD de tu modelo es a lo largo del ciclo y el ciclo lo ponen los escenarios de "
                f"la institución; con pd.pit_mode='{config.pd.pit_mode}' la curva anclada contaría "
                "el ciclo dos veces. Usa pd.pit_mode='cycle' o 'ttc_only'."
            )
    if config.staging.origination_pd_12m_col is not None:
        if config.pd.pd_12m_col is None:
            raise IfrsConfigError(
                "La PD a 12 meses al otorgar se compara con la de hoy en los mismos 12 meses: "
                "declara también la PD a 12 meses de tu modelo (pd.pd_12m_col)."
            )
        if config.origination_date_col is None:
            raise IfrsConfigError(
                "Lo que se esperaba al otorgar para los próximos 12 meses se lee desde la "
                "antigüedad de cada operación: declara la fecha de otorgamiento."
            )


def read_model_pd(frame: DataFrame, column: str, *, row_ids: Sequence[str], label: str) -> ModelPd:
    """Lee una columna de PD del modelo: vacía es «sin dato»; fuera de ``(0, 1)``, acotada.

    Raises
    ------
    IfrsInputError
        Si la columna no está en el archivo o trae un valor que no es un número; el error nombra la
        columna y la operación.
    """
    numpy = _import_numpy()
    pandas = _import_pandas()
    if column not in frame.columns:
        raise IfrsInputError(f"La columna de la {label} '{column}' no está en el frame.")
    serie = frame[column]
    valores = pandas.to_numeric(serie, errors="coerce").to_numpy(dtype=numpy.float64)
    vacia = serie.isna().to_numpy()
    malo = ~vacia & numpy.isnan(valores)
    if bool(malo.any()):
        i = int(numpy.flatnonzero(malo)[0])
        raise IfrsInputError(
            f"La columna de la {label} «{column}» trae un valor que no es un número en la "
            f"operación {row_ids[i]!r}: {serie.iloc[i]!r}."
        )
    con_dato = ~numpy.isnan(valores)
    acotada = numpy.clip(valores, PD_MINIMA, 1.0 - PD_MINIMA)
    fuera = con_dato & (acotada != valores)
    return ModelPd(
        values=cast("NDArrayFloat", numpy.where(con_dato, acotada, numpy.nan)),
        n_missing=int((~con_dato).sum()),
        n_clipped=int(fuera.sum()),
    )


def window_pd(
    riesgos: NDArrayFloat,
    relleno: NDArrayFloat | None,
    *,
    curva: Any,
    desde: NDArrayFloat,
    hasta: NDArrayFloat,
    shift: NDArrayFloat | None = None,
) -> NDArrayFloat:
    """La PD de incumplir en ``[desde, hasta]`` (períodos de la curva) dado vivo en ``desde``.

    ``riesgos`` es la matriz curvas × períodos y ``relleno`` el riesgo de cada curva más allá de su
    último período (``None``: ninguno, la curva termina ahí). Dentro de cada período el riesgo es
    constante, como en la lectura por contrato. Con ``shift`` (uno por ventana), el riesgo se acota
    a ``[10⁻¹², 1 - 10⁻¹²]`` y se desplaza en logit; sin él, se usa tal cual.
    """
    numpy = _import_numpy()
    n_periodos = riesgos.shape[1]
    desde = numpy.asarray(desde, dtype=numpy.float64)
    hasta = numpy.asarray(hasta, dtype=numpy.float64)
    curva = numpy.asarray(curva, dtype=numpy.int64)
    piso = numpy.floor(desde + 1e-12)
    largo = int(numpy.max(numpy.ceil(hasta - piso - 1e-12))) if desde.size else 0
    log_sobrevive = numpy.zeros(desde.shape[0], dtype=numpy.float64)
    for j in range(max(largo, 0)):
        k = piso.astype(numpy.int64) + 1 + j
        solape = numpy.clip(numpy.minimum(hasta, k) - numpy.maximum(desde, k - 1.0), 0.0, None)
        dentro = numpy.minimum(k, n_periodos) - 1
        mas_alla = (
            numpy.zeros(desde.shape[0], dtype=numpy.float64)
            if relleno is None
            else numpy.asarray(relleno, dtype=numpy.float64)[curva]
        )
        riesgo = numpy.where(k > n_periodos, mas_alla, riesgos[curva, dentro])
        if shift is not None:
            riesgo = _desplazar(_acotar(riesgo, numpy), shift, numpy)
        with numpy.errstate(divide="ignore", invalid="ignore"):
            aporte = numpy.where(solape > 0.0, solape * numpy.log1p(-riesgo), 0.0)
        log_sobrevive = log_sobrevive + aporte
    return cast("NDArrayFloat", -numpy.expm1(log_sobrevive))


def solve_shift(
    riesgos: NDArrayFloat,
    relleno: NDArrayFloat | None,
    *,
    curva: Any,
    desde: NDArrayFloat,
    hasta: NDArrayFloat,
    target: NDArrayFloat,
) -> tuple[NDArrayFloat, NDArrayBool]:
    """El desplazamiento en logit con que la PD de cada ventana es ``target`` (§3.7).

    Bisección en ``[-50, 50]`` sobre el riesgo acotado; ``NaN`` donde ``target`` es ``NaN``.
    Devuelve también si la raíz quedó encerrada: con una ventana larga y todos sus riesgos en el
    borde de arriba, la PD en ``s = -50`` puede seguir sobre ``10⁻⁹`` (doce riesgos mensuales de 1:
    2,3·10⁻⁹, pasada 1 de Codex sobre el código). Entonces la bisección termina en el extremo —la PD
    más cercana que el intervalo alcanza— y quien llama la cuenta en vez de darla por reproducida.
    """
    numpy = _import_numpy()
    objetivo = numpy.asarray(target, dtype=numpy.float64)
    bajo = numpy.full(objetivo.shape[0], _DESPLAZAMIENTO_MINIMO, dtype=numpy.float64)
    alto = numpy.full(objetivo.shape[0], _DESPLAZAMIENTO_MAXIMO, dtype=numpy.float64)
    con_dato = ~numpy.isnan(objetivo)
    for _ in range(_ITERACIONES):
        medio = (bajo + alto) / 2.0
        pd_medio = window_pd(riesgos, relleno, curva=curva, desde=desde, hasta=hasta, shift=medio)
        mayor = pd_medio > objetivo
        alto = numpy.where(mayor, medio, alto)
        bajo = numpy.where(mayor, bajo, medio)
    extremo = numpy.full(objetivo.shape[0], _DESPLAZAMIENTO_MINIMO, dtype=numpy.float64)
    en_el_minimo = window_pd(riesgos, relleno, curva=curva, desde=desde, hasta=hasta, shift=extremo)
    en_el_maximo = window_pd(
        riesgos, relleno, curva=curva, desde=desde, hasta=hasta, shift=-extremo
    )
    encerrada = con_dato & (en_el_minimo <= objetivo) & (en_el_maximo >= objetivo)
    return (
        cast("NDArrayFloat", numpy.where(con_dato, (bajo + alto) / 2.0, numpy.nan)),
        cast("NDArrayBool", encerrada),
    )


def edge_curves(
    riesgos: NDArrayFloat,
    relleno: NDArrayFloat | None,
    *,
    curva: Any,
    desde: NDArrayFloat,
    hasta: NDArrayFloat,
) -> NDArrayBool:
    """Las ventanas con algún riesgo que el acotamiento mueve (0, 1 o a menos de ``10⁻¹²``)."""
    numpy = _import_numpy()
    n_periodos = riesgos.shape[1]
    desde = numpy.asarray(desde, dtype=numpy.float64)
    hasta = numpy.asarray(hasta, dtype=numpy.float64)
    curva = numpy.asarray(curva, dtype=numpy.int64)
    piso = numpy.floor(desde + 1e-12)
    largo = int(numpy.max(numpy.ceil(hasta - piso - 1e-12))) if desde.size else 0
    borde = numpy.zeros(desde.shape[0], dtype=bool)
    for j in range(max(largo, 0)):
        k = piso.astype(numpy.int64) + 1 + j
        solape = numpy.minimum(hasta, k) - numpy.maximum(desde, k - 1.0)
        dentro = numpy.minimum(k, n_periodos) - 1
        mas_alla = (
            numpy.zeros(desde.shape[0], dtype=numpy.float64)
            if relleno is None
            else numpy.asarray(relleno, dtype=numpy.float64)[curva]
        )
        riesgo = numpy.where(k > n_periodos, mas_alla, riesgos[curva, dentro])
        borde |= (solape > 0.0) & (_acotar(riesgo, numpy) != riesgo)
    return cast("NDArrayBool", borde)


def anchor_term_structure(
    term_structure: DataFrame,
    row_ids: Sequence[str],
    pd_model: ModelPd,
    *,
    window_periods: int,
) -> tuple[DataFrame, AnchorReading]:
    """Ancla la curva sin fechas del contrato: cada operación la lee desde su período 1 (§3.7).

    Por curva ``(row_id, escenario)``, el riesgo de cada período sale de la PD marginal y de la
    supervivencia anterior; la ventana de 12 meses son los períodos ``1…H`` de la curva (los que el
    motor suma para el Stage 1), sin pasar de su último período. Las operaciones con PD del modelo
    se desplazan en logit sobre el riesgo acotado y se recomponen la supervivencia, la PD marginal y
    la acumulada; las demás quedan **exactamente** como venían. La salida conserva el orden de la
    curva recibida.

    Raises
    ------
    IfrsTermStructureError
        Si alguna operación tiene más de una curva (la PD del modelo es una por operación) o su
        curva no va del período 1 al último sin saltos.
    """
    numpy = _import_numpy()
    pandas = _import_pandas()
    orden = term_structure.sort_values(["row_id", "period"], kind="mergesort").index
    base = term_structure.loc[orden]
    rids = [str(v) for v in base["row_id"].tolist()]
    escenarios = [str(v) for v in base["scenario"].tolist()]
    if len(set(zip(rids, escenarios, strict=True))) != len(set(rids)):
        raise IfrsTermStructureError(
            "La PD de tu modelo es una por operación, y la curva trae más de un escenario por "
            "operación: ancla una curva por operación."
        )
    periodo = base["period"].to_numpy(dtype=numpy.float64)
    marginal = base["pd_marginal"].to_numpy(dtype=numpy.float64)
    grupos = pandas.Series(periodo).groupby(rids)
    if bool(numpy.any(periodo != grupos.cumcount().to_numpy() + 1)):
        raise IfrsTermStructureError(
            "Para anclar la curva a la PD de tu modelo, la curva de cada operación tiene que ir "
            "del período 1 al último, sin saltos: el riesgo de cada período sale de la "
            "supervivencia anterior."
        )
    # El riesgo de cada período, h_t = m_t / S_{t-1}, como lo recupera el ajuste por ciclo.
    previa_ttc = 1.0 - (
        pandas.Series(marginal).groupby(rids).cumsum().to_numpy(dtype=numpy.float64) - marginal
    )
    with numpy.errstate(divide="ignore", invalid="ignore"):
        riesgo = numpy.clip(numpy.where(previa_ttc > 0.0, marginal / previa_ttc, 0.0), 0.0, 1.0)

    posicion = {rid: i for i, rid in enumerate(row_ids)}
    fila_de = numpy.array([posicion[rid] for rid in rids], dtype=numpy.int64)
    n_periodos = int(periodo.max())
    matriz = numpy.zeros((len(row_ids), n_periodos), dtype=numpy.float64)
    ultimo = numpy.zeros(len(row_ids), dtype=numpy.float64)
    matriz[fila_de, periodo.astype(numpy.int64) - 1] = riesgo
    numpy.maximum.at(ultimo, fila_de, periodo)

    filas = numpy.arange(len(row_ids))
    desde = numpy.zeros(len(row_ids), dtype=numpy.float64)
    hasta = numpy.minimum(float(window_periods), ultimo)
    objetivo = pd_model.values
    desplazamiento, encerrada = solve_shift(
        matriz, None, curva=filas, desde=desde, hasta=hasta, target=objetivo
    )
    pd_curva = window_pd(matriz, None, curva=filas, desde=desde, hasta=hasta)
    anclada = ~numpy.isnan(objetivo)
    borde = anclada & edge_curves(matriz, None, curva=filas, desde=desde, hasta=hasta)

    en_fila = anclada[fila_de]
    nuevo = numpy.where(
        en_fila,
        _desplazar(_acotar(riesgo, numpy), numpy.nan_to_num(desplazamiento[fila_de]), numpy),
        riesgo,
    )
    serie = pandas.Series(1.0 - nuevo)
    sobrevive = serie.groupby(rids).cumprod().to_numpy(dtype=numpy.float64)
    previa = pandas.Series(sobrevive).groupby(rids).shift(1, fill_value=1.0)
    anclado = base.copy(deep=True)
    anclado["pd_marginal"] = numpy.where(
        en_fila, numpy.maximum(previa.to_numpy(dtype=numpy.float64) - sobrevive, 0.0), marginal
    )
    if "hazard" in anclado.columns:
        anclado["hazard"] = numpy.where(
            en_fila, nuevo, anclado["hazard"].to_numpy(dtype=numpy.float64)
        )
    if "survival" in anclado.columns:
        anclado["survival"] = numpy.where(
            en_fila, sobrevive, anclado["survival"].to_numpy(dtype=numpy.float64)
        )
    if "pd_cumulative" in anclado.columns:
        anclado["pd_cumulative"] = numpy.where(
            en_fila, 1.0 - sobrevive, anclado["pd_cumulative"].to_numpy(dtype=numpy.float64)
        )
    salida = anclado.loc[term_structure.index]
    return salida, AnchorReading(
        shift=desplazamiento,
        pd_model=objetivo,
        pd_curve=pd_curva,
        edge=borde,
        n_missing=pd_model.n_missing,
        n_clipped=pd_model.n_clipped,
        not_reached=anclada & ~encerrada,
    )


def bounded_risk(riesgo: NDArrayFloat) -> NDArrayFloat:
    """El riesgo acotado a ``[10⁻¹², 1 - 10⁻¹²]``, sobre el que se ancla (§3.7)."""
    return cast("NDArrayFloat", _acotar(riesgo, _import_numpy()))


def _acotar(riesgo: Any, numpy: Any) -> Any:
    return numpy.clip(riesgo, RIESGO_MINIMO, 1.0 - RIESGO_MINIMO)


def _desplazar(riesgo: Any, delta: Any, numpy: Any) -> Any:
    """``sigmoide(logit h + δ)`` sobre un riesgo ya acotado (sin infinitos)."""
    logit = numpy.log(riesgo) - numpy.log1p(-riesgo)
    with numpy.errstate(over="ignore"):
        return 1.0 / (1.0 + numpy.exp(-(logit + delta)))


def _import_numpy() -> Any:
    try:
        return importlib.import_module("numpy")
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_NUMPY_MESSAGE) from exc


def _import_pandas() -> Any:
    try:
        return importlib.import_module("pandas")
    except ModuleNotFoundError as exc:
        raise MissingDependencyError(_PANDAS_MESSAGE) from exc
