"""La vida de cada operación según su contrato: antigüedad, vencimiento y tabla de pagos.

CASO-REAL-IFRS9 D-CRE-2 (§3.2) y D-CRE-3 (§3.3). Sin las fechas del contrato, la provisión lee la
curva de PD de cada operación desde su período 1 hasta el horizonte de la curva, como si cada
operación naciera hoy y viviera lo que la curva. Con la fecha de otorgamiento y/o la de
vencimiento, este módulo arma la curva **condicionada** de cada operación, con los períodos
contados desde el corte, y el resto del motor la consume como si fuera la de la fuente —el
descuento, la ponderación por escenario y el staging no cambian—:

- **Antigüedad** ``A``: los meses entre el otorgamiento y el corte, divididos por los meses de un
  período de la curva (la tabla de :mod:`bayesrisk.core.time_units`), **sin redondear**.
- **Supervivencia por tramos**: dentro de cada período de la curva el riesgo es constante,
  ``S(x) = Π_{k ≤ ⌊x⌋} (1 - h_k) · (1 - h_{⌊x⌋+1})^(x - ⌊x⌋)``, y la PD del período ``t`` posterior
  al corte es ``[S(A + t - 1) - S(A + min(t, L))] / S(A)``: la de incumplir en ese tramo de la curva
  dado que la operación sobrevivió hasta hoy.
- **Vida** ``L``: los meses del corte al vencimiento en períodos de la curva (IFRS 9 5.5.19: el
  período máximo es el contractual), también fraccionaria. Vencida con saldo, un período. Sin
  vencimiento, el horizonte de la curva. Con ``max_lifetime_periods``, el menor.
- **La cola** (§8-6, decisión de Cami): más allá del último período de la curva con
  incumplimientos observados, el riesgo de cada operación se extiende constante en la media de sus
  riesgos de los tres últimos períodos con incumplimientos (de los que haya). Una curva con
  intercepto por período sólo estima riesgo donde hubo incumplimientos: su último período sin
  ninguno sale con riesgo ≈ 0, y extenderlo decía «ningún riesgo más allá» para hipotecas con
  veinte años por delante (§0-1).
- **Tabla de pagos** (D-CRE-3): con la cuota mensual del contrato, la exposición de cada período es
  el saldo al inicio del período en la tabla de cuota fija que paga el saldo de hoy justo al
  vencimiento, con la tasa mensual **implícita** —la que hace que la cuota pague el saldo en el
  plazo—, no la EIR (pasada 2 de Codex: la EIR incluye comisiones y no es la tasa del contrato).
  Si la cuota no alcanza a pagar el saldo ni a tasa cero (``c · n < B``: un *bullet*, un pago final
  mayor, atrasos, intereses que se capitalizan), la exposición queda constante y se cuenta.

**Qué NO se configura** (§3.8): la regla de la cola, el riesgo constante dentro del período, la
vida de la operación vencida, el momento del descuento (al final de cada período, también el
parcial), la convención de meses (de calendario, abajo), la frecuencia de la cuota (mensual) y la
tasa de la tabla (la implícita). Son constantes con su razón, no perillas.

``pandas``/``numpy`` se importan de forma perezosa: ``import bayesrisk.provisioning.ifrs9`` no debe
arrastrarlas.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, TypeAlias, cast

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.core.time_units import year_fraction
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
    DataFrame: TypeAlias = pd.DataFrame
else:
    NDArrayFloat: TypeAlias = Any
    DataFrame: TypeAlias = Any

__all__ = [
    "ContractReading",
    "ContractTerms",
    "check_contract_config",
    "months_between",
    "read_contract_terms",
    "read_curve_by_contract",
]

#: §8-6: cuántos períodos con incumplimientos promedia la cola. La media de tres amortigua que el
#: último período con incumplimientos suele estar observado sólo en parte —y su riesgo sale bajo—,
#: y es la prudente (más ECL). Decidido por Cami el 2026-10-05; no es una perilla.
_PERIODOS_DE_LA_COLA: Final = 3
#: Ruido de coma flotante al pasar meses a períodos (``24 / 3`` puede no dar ``8`` exacto en otras
#: unidades): una antigüedad o una vida a menos de esto de un entero se toma como ese entero, para
#: no abrir un último tramo de largo 1e-15.
_TOLERANCIA_PERIODO: Final = 1e-9
#: La tasa implícita se busca por bisección en ``[0, max(1, c/B)]`` mensual: con ``i = c/B`` la
#: anualidad ya supera la cuota (``B·i/(1 - (1 + i)^(-n)) > B·i = c``), así que la raíz queda
#: siempre encerrada aunque pase del 100 % al mes —una cuota mayor que el saldo— (pasada 1 de Codex:
#: topada en el 100 %, la EAD caía a cero tras el primer período). Las iteraciones agotan la
#: precisión de un ``float``; sobre 10.000 operaciones toma milisegundos.
_TASA_MENSUAL_MINIMA_DEL_TOPE: Final = 1.0
_ITERACIONES_TASA: Final = 400
#: ``c · n = B`` a menos de esto (en la moneda de la exposición) es una tabla sin interés.
_TOLERANCIA_TASA_CERO: Final = 1e-9

_NUMPY_MESSAGE: Final = "La lectura por contrato requiere numpy; instale bayesrisk[scoring]."
_PANDAS_MESSAGE: Final = "La lectura por contrato requiere pandas; instale bayesrisk[scoring]."


@dataclass(frozen=True)
class ContractTerms:
    """Lo que el archivo dice del contrato de cada operación activa, en meses de calendario.

    ``NaN`` es «sin dato en esa fila»: sin otorgamiento la curva se lee desde el período 1, sin
    vencimiento la vida es el horizonte de la curva y sin cuota la exposición queda constante.
    """

    age_months: NDArrayFloat
    remaining_months: NDArrayFloat
    installment: NDArrayFloat | None


@dataclass(frozen=True)
class ContractReading:
    """La curva condicionada de cada operación y lo que se declara de ella (§3.2 y §3.3)."""

    term_structure: DataFrame
    ead: NDArrayFloat
    age_periods: dict[str, float]
    life_periods: dict[str, float]
    amortizing: frozenset[str]
    n_matured_with_balance: int
    ead_matured_with_balance: float
    tail_from_period: int | None
    ead_beyond_observed_curve: float | None
    n_installment_not_amortizing: int
    ead_installment_not_amortizing: float


def check_contract_config(
    config: IfrsProvisioningConfig, events_by_period: Mapping[int, int] | None
) -> None:
    """Lo que el preflight avisa, comprobado también por código (sin preflight) antes de leer datos.

    Raises
    ------
    IfrsConfigError
        Si las fechas o la cuota se declaran en una configuración donde no se pueden leer.
    """
    if config.ead.installment_col is not None:
        if config.maturity_date_col is None:
            raise IfrsConfigError(
                "La cuota del contrato arma la tabla de pagos hasta el vencimiento, y no se "
                "declaró la fecha de vencimiento: sin plazo no hay tabla."
            )
        if config.ead.method != "provided":
            raise IfrsConfigError(
                "La tabla de pagos de la cuota parte de la EAD entregada (ead.method='provided'), "
                f"no de una calculada por {config.ead.method}."
            )
    if not config.lee_fechas_del_contrato():
        return
    if config.pd.term_structure_source != "survival":
        raise IfrsConfigError(
            "Con las fechas del contrato la curva de PD se lee desde la edad de cada operación, y "
            "eso sólo se puede con la curva de supervivencia: la de "
            f"{config.pd.term_structure_source} ya parte del estado actual de cada operación."
        )
    if config.pd.base_pd_source == "calibration":
        raise IfrsConfigError(
            "Con las fechas del contrato la curva de PD se lee desde la edad de cada operación, y "
            "la PD a 12 meses tiene que salir de esa lectura: la calibración la fija sin mirar "
            "la edad (pd.base_pd_source='term_structure')."
        )
    if events_by_period is None:
        raise IfrsConfigError(
            "Con las fechas del contrato la curva de PD se lee desde la edad de cada operación, y "
            "la cola de la curva se extiende desde su último período con incumplimientos: hacen "
            "falta los incumplimientos por período de la curva, que publica la supervivencia por "
            "períodos discretos (survival.method='discrete_hazard')."
        )


def read_contract_terms(
    frame: DataFrame,
    config: IfrsProvisioningConfig,
    *,
    as_of_date: str,
    row_ids: list[str],
) -> ContractTerms:
    """Lee y valida las fechas y la cuota de las operaciones activas (§4).

    Sólo se llama con alguna fecha declarada y sobre las filas con exposición (D-CRE-5): un dato
    inválido en una fila de historia no aborta la provisión.

    Raises
    ------
    IfrsInputError
        Si una columna declarada no está en el archivo, una fecha no se puede leer, un otorgamiento
        es posterior al corte, un vencimiento es anterior a su otorgamiento o una cuota no es un
        número mayor o igual a cero. El error nombra la columna y la operación.
    """
    numpy = _import_numpy()
    pandas = _import_pandas()
    corte = _fecha_de_corte(as_of_date, pandas, numpy)
    n = len(row_ids)
    sin_fecha = numpy.full(n, numpy.datetime64("NaT"), dtype="datetime64[D]")
    otorgamiento = (
        sin_fecha
        if config.origination_date_col is None
        else _fechas(frame, config.origination_date_col, "otorgamiento", row_ids, pandas, numpy)
    )
    vencimiento = (
        sin_fecha
        if config.maturity_date_col is None
        else _fechas(frame, config.maturity_date_col, "vencimiento", row_ids, pandas, numpy)
    )
    cortes = numpy.full(n, corte, dtype="datetime64[D]")
    posterior = ~numpy.isnat(otorgamiento) & (otorgamiento > cortes)
    if bool(posterior.any()):
        i = int(numpy.flatnonzero(posterior)[0])
        raise IfrsInputError(
            f"La fecha de otorgamiento de la operación {row_ids[i]!r} ({otorgamiento[i]}) es "
            f"posterior a la fecha de corte ({corte}): una operación de la cartera ya se otorgó."
        )
    invertida = (
        ~numpy.isnat(otorgamiento) & ~numpy.isnat(vencimiento) & (vencimiento < otorgamiento)
    )
    if bool(invertida.any()):
        i = int(numpy.flatnonzero(invertida)[0])
        raise IfrsInputError(
            f"La fecha de vencimiento de la operación {row_ids[i]!r} ({vencimiento[i]}) es "
            f"anterior a su otorgamiento ({otorgamiento[i]})."
        )
    cuota = (
        None
        if config.ead.installment_col is None
        else _cuotas(frame, config.ead.installment_col, row_ids, pandas, numpy)
    )
    return ContractTerms(
        age_months=months_between(otorgamiento, cortes),
        remaining_months=months_between(cortes, vencimiento),
        installment=cuota,
    )


def months_between(start: Any, end: Any) -> NDArrayFloat:
    """Meses de calendario de ``start`` a ``end``, con la fracción del mes en curso.

    Los meses enteros son los de calendario —del 1 de enero al 1 de marzo, dos—, con el día
    acotado al largo del mes de llegada (del 31 de enero, un mes es el 28 o 29 de febrero); la
    fracción es la parte transcurrida del mes siguiente, en días. Así, fechas alineadas al mes dan
    meses enteros —lo que cuenta un contrato de cuota mensual— y las demás, la fracción sin
    redondear (§3.2-1). Negativo si ``end`` es anterior a ``start``; ``NaN`` si falta alguna.

    Es una convención, no una perilla: el motor no tiene otra.
    """
    numpy = _import_numpy()
    inicio = numpy.asarray(start, dtype="datetime64[D]")
    fin = numpy.asarray(end, dtype="datetime64[D]")
    salida = numpy.full(inicio.shape, numpy.nan, dtype=numpy.float64)
    validos = ~(numpy.isnat(inicio) | numpy.isnat(fin))
    if not bool(validos.any()):
        return cast("NDArrayFloat", salida)
    a, b = inicio[validos], fin[validos]
    hacia_atras = b < a
    desde = numpy.where(hacia_atras, b, a)
    hasta = numpy.where(hacia_atras, a, b)
    meses = _meses_hacia_adelante(desde, hasta, numpy)
    salida[validos] = numpy.where(hacia_atras, -meses, meses)
    return cast("NDArrayFloat", salida)


def read_curve_by_contract(
    term_structure: DataFrame,
    *,
    terms: ContractTerms,
    row_ids: list[str],
    ead_by_rid: Mapping[str, float],
    events_by_period: Mapping[int, int],
    max_lifetime: int | None,
) -> ContractReading:
    """Arma la curva condicionada de cada operación, con los períodos contados desde el corte.

    ``term_structure`` es la curva publicada y ya preparada por el motor (escenario normalizado,
    sin truncar por ``max_lifetime``), con su ``hazard`` por período: el riesgo condicionado que
    publica ``discrete_hazard``. La salida tiene las columnas que el resto del motor lee
    —``row_id``, ``scenario``, ``period``, ``time_value``, ``time_unit``, ``time_value_years``,
    ``pd_marginal``— más ``curve_start`` y ``curve_end``, el tramo de la curva de cada período.

    Raises
    ------
    IfrsConfigError
        Si la curva no declara una sola unidad reconocida: sin ella no se pueden pasar los meses
        del contrato a períodos de la curva.
    IfrsTermStructureError
        Si la curva no trae su riesgo por período o sus períodos no van del 1 al último en cada
        operación.
    """
    numpy = _import_numpy()
    pandas = _import_pandas()
    meses_por_periodo = _meses_por_periodo(term_structure)
    riesgos, claves, n_periodos = _riesgos_por_curva(term_structure, numpy)

    # La cola (§8-6): desde el último período de la curva con incumplimientos observados.
    con_eventos = [p for p in range(1, n_periodos + 1) if int(events_by_period.get(p, 0) or 0) > 0]
    ultimo = max(con_eventos) if con_eventos else None
    extendidos = riesgos.copy()
    if ultimo is None:
        # Sin ningún período con incumplimientos no hay cola que extender (la curva ya lo declara,
        # DATO-INSTITUCIONAL-SUR-2): más allá de la curva, ningún riesgo.
        relleno = numpy.zeros(riesgos.shape[0], dtype=numpy.float64)
    else:
        desde = max(ultimo - _PERIODOS_DE_LA_COLA, 0)
        relleno = riesgos[:, desde:ultimo].mean(axis=1)
        extendidos[:, ultimo:] = relleno[:, None]
    with numpy.errstate(divide="ignore"):
        log_sobrevive = numpy.log1p(-extendidos)
        log_cola = numpy.log1p(-relleno)
    acumulado = numpy.concatenate(
        [numpy.zeros((riesgos.shape[0], 1)), numpy.cumsum(log_sobrevive, axis=1)], axis=1
    )

    # Antigüedad y vida de cada operación, en períodos de la curva.
    posicion = {rid: i for i, rid in enumerate(row_ids)}
    edad = numpy.nan_to_num(terms.age_months / meses_por_periodo, nan=0.0)
    restante = terms.remaining_months
    vencida = ~numpy.isnan(restante) & (restante <= 0.0)
    vida = numpy.where(
        numpy.isnan(restante),
        float(n_periodos),
        numpy.where(vencida, 1.0, restante / meses_por_periodo),
    )
    if max_lifetime is not None:
        vida = numpy.minimum(vida, float(max_lifetime))
    edad, vida = _sin_ruido(edad, numpy), _sin_ruido(vida, numpy)

    # Una curva por (operación, escenario); los períodos posteriores al corte, en plano.
    fila = numpy.array([posicion[rid] for rid, _escenario in claves], dtype=numpy.int64)
    a, largo = edad[fila], vida[fila]
    tramos = numpy.maximum(numpy.ceil(largo), 1.0).astype(numpy.int64)
    curva = numpy.repeat(numpy.arange(len(claves)), tramos)
    inicio_de = numpy.concatenate([[0], numpy.cumsum(tramos)[:-1]])
    periodo = numpy.arange(int(tramos.sum())) - numpy.repeat(inicio_de, tramos) + 1
    desde_curva = a[curva] + periodo - 1.0
    hasta_curva = a[curva] + numpy.minimum(periodo.astype(numpy.float64), largo[curva])

    def _log_s(x: NDArrayFloat, c: Any) -> NDArrayFloat:
        # Un riesgo de 1 exacto da log(0) = -inf, y 0 · (-inf) no está definido: el producto se
        # toma sólo donde el factor no es cero (con 0 períodos de cola o sin fracción, aporta 0).
        entero = numpy.floor(x).astype(numpy.int64)
        fraccion = x - entero
        dentro = numpy.minimum(entero, n_periodos)
        en_cola = numpy.maximum(entero - n_periodos, 0)
        siguiente = numpy.where(
            entero < n_periodos,
            log_sobrevive[c, numpy.minimum(entero, n_periodos - 1)],
            log_cola[c],
        )
        with numpy.errstate(invalid="ignore"):
            cola = numpy.where(en_cola > 0, en_cola * log_cola[c], 0.0)
            parcial = numpy.where(fraccion > 0.0, fraccion * siguiente, 0.0)
        return cast("NDArrayFloat", acumulado[c, dentro] + cola + parcial)

    sobrevive_a = numpy.exp(_log_s(a, numpy.arange(len(claves))))
    s_desde = numpy.exp(_log_s(desde_curva, curva))
    s_hasta = numpy.exp(_log_s(hasta_curva, curva))
    with numpy.errstate(divide="ignore", invalid="ignore"):
        pd_tramo = numpy.where(
            sobrevive_a[curva] > 0.0,
            numpy.maximum(s_desde - s_hasta, 0.0) / sobrevive_a[curva],
            0.0,
        )

    unidad = _unidad(term_structure)
    fraccion_anio = cast("float", year_fraction(unidad))
    condicionada = pandas.DataFrame(
        {
            "row_id": [claves[int(c)][0] for c in curva],
            "scenario": [claves[int(c)][1] for c in curva],
            "period": periodo,
            "time_value": periodo.astype(numpy.float64),
            "time_unit": unidad,
            "time_value_years": periodo.astype(numpy.float64) * fraccion_anio,
            "pd_marginal": pd_tramo,
            "curve_start": desde_curva,
            "curve_end": hasta_curva,
        }
    )

    # La tabla de pagos (D-CRE-3), en el mismo orden plano.
    saldo = numpy.array([float(ead_by_rid[rid]) for rid in row_ids], dtype=numpy.float64)
    ead_tramo = saldo[fila][curva]
    amortiza = numpy.zeros(len(row_ids), dtype=bool)
    no_alcanza = numpy.zeros(len(row_ids), dtype=bool)
    if terms.installment is not None:
        cuota = terms.installment
        plazo = numpy.maximum(restante, 0.0)
        con_cuota = ~numpy.isnan(cuota) & ~numpy.isnan(restante)
        alcanza = con_cuota & (cuota * plazo >= saldo) & (plazo > 0.0)
        amortiza = alcanza
        no_alcanza = con_cuota & ~alcanza
        tasa = _tasa_implicita(saldo, cuota, plazo, alcanza, numpy)
        meses = (periodo - 1).astype(numpy.float64) * meses_por_periodo
        en_tabla = amortiza[fila][curva]
        ead_tramo = numpy.where(
            en_tabla,
            _saldo_tras(saldo[fila][curva], tasa[fila][curva], plazo[fila][curva], meses, numpy),
            ead_tramo,
        )

    mas_alla = None
    if ultimo is not None:
        lejos = edad + vida > float(ultimo) + _TOLERANCIA_PERIODO
        mas_alla = float(saldo[lejos].sum())
    return ContractReading(
        term_structure=condicionada,
        ead=cast("NDArrayFloat", ead_tramo),
        age_periods={rid: float(edad[i]) for i, rid in enumerate(row_ids)},
        life_periods={rid: float(vida[i]) for i, rid in enumerate(row_ids)},
        amortizing=frozenset(rid for i, rid in enumerate(row_ids) if bool(amortiza[i])),
        n_matured_with_balance=int(vencida.sum()),
        ead_matured_with_balance=float(saldo[vencida].sum()),
        tail_from_period=None if ultimo is None else ultimo + 1,
        ead_beyond_observed_curve=mas_alla,
        n_installment_not_amortizing=int(no_alcanza.sum()),
        ead_installment_not_amortizing=float(saldo[no_alcanza].sum()),
    )


# --- Fechas y meses -----------------------------------------------------------------------------


def _fecha_de_corte(as_of_date: str, pandas: Any, numpy: Any) -> Any:
    try:
        corte = pandas.to_datetime(str(as_of_date).strip(), format="ISO8601")
    except (ValueError, TypeError) as exc:
        raise IfrsInputError(
            f"La fecha de corte {as_of_date!r} no se puede leer como fecha (AAAA-MM-DD): con las "
            "fechas del contrato, la antigüedad y la vida se cuentan desde ella."
        ) from exc
    return numpy.datetime64(corte.normalize().date(), "D")


def _fechas(
    frame: DataFrame, column: str, etiqueta: str, row_ids: list[str], pandas: Any, numpy: Any
) -> Any:
    """Una columna de fechas como ``datetime64[D]``, con ``NaT`` donde la fila no trae fecha.

    Acepta lo que ``pandas.to_datetime`` lee sin ambigüedad (§4): una columna de tipo fecha o
    texto ISO. Un valor que no se puede leer detiene la corrida con la columna y la operación.
    """
    if column not in frame.columns:
        raise IfrsInputError(f"La columna de {etiqueta} '{column}' no está en el frame.")
    serie = frame[column]
    if isinstance(serie.dtype, pandas.DatetimeTZDtype):
        fechas = serie.dt.tz_localize(None)
    elif pandas.api.types.is_datetime64_any_dtype(serie):
        fechas = serie
    else:
        texto = serie.astype("string").str.strip()
        vacia = texto.isna() | (texto == "")
        fechas = pandas.to_datetime(texto.where(~vacia), format="ISO8601", errors="coerce")
        malas = (~vacia & fechas.isna()).to_numpy()
        if bool(malas.any()):
            i = int(numpy.flatnonzero(malas)[0])
            raise IfrsInputError(
                f"La columna de {etiqueta} «{column}» trae una fecha que no se puede leer en la "
                f"operación {row_ids[i]!r}: {serie.iloc[i]!r}. Usa fechas AAAA-MM-DD o una "
                "columna de tipo fecha."
            )
    return pandas.DatetimeIndex(fechas).normalize().to_numpy().astype("datetime64[D]")


def _cuotas(
    frame: DataFrame, column: str, row_ids: list[str], pandas: Any, numpy: Any
) -> NDArrayFloat:
    if column not in frame.columns:
        raise IfrsInputError(f"La columna de la cuota '{column}' no está en el frame.")
    serie = frame[column]
    valores = pandas.to_numeric(serie, errors="coerce").to_numpy(dtype=numpy.float64)
    vacia = serie.isna().to_numpy()
    mala = (~vacia & ~numpy.isfinite(valores)) | (numpy.isfinite(valores) & (valores < 0.0))
    if bool(mala.any()):
        i = int(numpy.flatnonzero(mala)[0])
        raise IfrsInputError(
            f"La columna de la cuota «{column}» trae un valor que no es un número mayor o igual a "
            f"cero en la operación {row_ids[i]!r}: {serie.iloc[i]!r}."
        )
    return cast("NDArrayFloat", numpy.where(vacia, numpy.nan, valores))


def _sumar_meses(fecha: Any, meses: Any, numpy: Any) -> Any:
    """``fecha`` más ``meses`` meses de calendario, con el día acotado al largo del mes."""
    mes = fecha.astype("datetime64[M]")
    dia = (fecha - mes.astype("datetime64[D]")).astype(numpy.int64)
    destino = mes + meses.astype("timedelta64[M]")
    primero = destino.astype("datetime64[D]")
    largo = ((destino + numpy.timedelta64(1, "M")).astype("datetime64[D]") - primero).astype(
        numpy.int64
    )
    return primero + numpy.minimum(dia, largo - 1).astype("timedelta64[D]")


def _meses_hacia_adelante(desde: Any, hasta: Any, numpy: Any) -> NDArrayFloat:
    enteros = (hasta.astype("datetime64[M]") - desde.astype("datetime64[M]")).astype(numpy.int64)
    enteros = enteros - (_sumar_meses(desde, enteros, numpy) > hasta).astype(numpy.int64)
    ancla = _sumar_meses(desde, enteros, numpy)
    siguiente = _sumar_meses(desde, enteros + 1, numpy)
    transcurrido = (hasta - ancla).astype(numpy.int64).astype(numpy.float64)
    del_mes = (siguiente - ancla).astype(numpy.int64).astype(numpy.float64)
    return cast("NDArrayFloat", enteros.astype(numpy.float64) + transcurrido / del_mes)


# --- La curva -----------------------------------------------------------------------------------


def _unidad(term_structure: DataFrame) -> str:
    if "time_unit" not in term_structure.columns:
        raise IfrsConfigError(
            "Con las fechas del contrato los meses se pasan a períodos de la curva, y la curva no "
            "declara la unidad de su duración: declárala (año, semestre, trimestre, mes, semana o "
            "día)."
        )
    unidades = {str(u) for u in term_structure["time_unit"].tolist()}
    fracciones = {year_fraction(u) for u in unidades}
    if len(fracciones) != 1 or None in fracciones:
        raise IfrsConfigError(
            "Con las fechas del contrato los meses se pasan a períodos de la curva, y la curva no "
            f"declara una sola unidad reconocida ({sorted(unidades)}): declara la unidad de su "
            "duración —año, semestre, trimestre, mes, semana o día—."
        )
    return sorted(unidades)[0]


def _meses_por_periodo(term_structure: DataFrame) -> float:
    return 12.0 * cast("float", year_fraction(_unidad(term_structure)))


def _riesgos_por_curva(
    term_structure: DataFrame, numpy: Any
) -> tuple[NDArrayFloat, list[tuple[str, str]], int]:
    """El riesgo de cada período por curva ``(row_id, scenario)``, como matriz curvas × períodos."""
    if "hazard" not in term_structure.columns:
        raise IfrsTermStructureError(
            "Con las fechas del contrato la curva se lee desde la edad de cada operación, y para "
            "eso necesita su riesgo por período (columna hazard), que publica la supervivencia "
            "por períodos discretos."
        )
    curvas: dict[tuple[str, str], dict[int, float]] = {}
    for rid, escenario, periodo, riesgo in zip(
        (str(v) for v in term_structure["row_id"].tolist()),
        (str(v) for v in term_structure["scenario"].tolist()),
        (int(v) for v in term_structure["period"].tolist()),
        (float(v) for v in term_structure["hazard"].tolist()),
        strict=True,
    ):
        curvas.setdefault((rid, escenario), {})[periodo] = riesgo
    periodos = {tuple(sorted(por)) for por in curvas.values()}
    if len(periodos) != 1:
        raise IfrsTermStructureError(
            "Con las fechas del contrato todas las curvas tienen que tener los mismos períodos."
        )
    (unicos,) = periodos
    n = len(unicos)
    if unicos != tuple(range(1, n + 1)):
        raise IfrsTermStructureError(
            "Con las fechas del contrato los períodos de la curva tienen que ir del 1 al último, "
            f"sin saltos; trae {list(unicos)}."
        )
    claves = list(curvas)
    riesgos = numpy.array(
        [[curvas[clave][p] for p in range(1, n + 1)] for clave in claves], dtype=numpy.float64
    )
    if not bool(numpy.all(numpy.isfinite(riesgos))) or bool(
        numpy.any((riesgos < 0.0) | (riesgos > 1.0))
    ):
        raise IfrsTermStructureError(
            "El riesgo por período (hazard) de la curva debe estar en [0, 1]."
        )
    return cast("NDArrayFloat", riesgos), claves, n


def _sin_ruido(valores: NDArrayFloat, numpy: Any) -> NDArrayFloat:
    redondos = numpy.rint(valores)
    return cast(
        "NDArrayFloat",
        numpy.where(numpy.abs(valores - redondos) < _TOLERANCIA_PERIODO, redondos, valores),
    )


# --- La tabla de pagos (D-CRE-3) ----------------------------------------------------------------


def _tasa_implicita(
    saldo: NDArrayFloat, cuota: NDArrayFloat, plazo: NDArrayFloat, alcanza: Any, numpy: Any
) -> NDArrayFloat:
    """La tasa mensual ``i ≥ 0`` con que la cuota paga el saldo justo en el plazo.

    Resuelve ``B · i / (1 - (1 + i)^(-n)) = c`` por bisección donde la cuota alcanza
    (``c · n ≥ B``); ``c · n = B`` es la tabla sin interés. Fuera de ``alcanza``, cero (no se usa).
    """
    tasa = numpy.zeros(saldo.shape[0], dtype=numpy.float64)
    resolver = alcanza & (numpy.abs(cuota * plazo - saldo) >= _TOLERANCIA_TASA_CERO)
    if not bool(resolver.any()):
        return cast("NDArrayFloat", tasa)
    b, c, n = saldo[resolver], cuota[resolver], plazo[resolver]
    bajo = numpy.zeros(b.shape[0], dtype=numpy.float64)
    alto = numpy.maximum(_TASA_MENSUAL_MINIMA_DEL_TOPE, c / b)
    for _ in range(_ITERACIONES_TASA):
        medio = (bajo + alto) / 2.0
        cuota_medio = b * medio / (1.0 - (1.0 + medio) ** (-n))
        mayor = cuota_medio > c
        alto = numpy.where(mayor, medio, alto)
        bajo = numpy.where(mayor, bajo, medio)
    tasa[resolver] = (bajo + alto) / 2.0
    return cast("NDArrayFloat", tasa)


def _saldo_tras(
    saldo: NDArrayFloat, tasa: NDArrayFloat, plazo: NDArrayFloat, meses: NDArrayFloat, numpy: Any
) -> NDArrayFloat:
    """El saldo tras ``k = meses`` cuotas de la tabla que paga ``B`` justo en ``n = plazo`` meses.

    ``B · (1 - (1 + i)^(k - n)) / (1 - (1 + i)^(-n))`` —con ``i = 0``, ``B · (1 - k/n)``—: la
    misma tabla que ``B(1 + i)^k - c((1 + i)^k - 1)/i`` cuando la cuota ``c`` es la anualidad de
    ``i``, que es como se resolvió la tasa, pero sin potencias positivas que desborden con una tasa
    alta ni restas de números grandes; ``expm1``/``log1p`` la mantienen precisa con una tasa casi
    cero. Nunca bajo cero.
    """
    with numpy.errstate(divide="ignore", invalid="ignore"):
        log_tasa = numpy.log1p(tasa)
        con_interes = (
            saldo * numpy.expm1((meses - plazo) * log_tasa) / numpy.expm1(-plazo * log_tasa)
        )
        sin_interes = saldo * (1.0 - meses / plazo)
    return cast(
        "NDArrayFloat", numpy.maximum(numpy.where(tasa > 0.0, con_interes, sin_interes), 0.0)
    )


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
