"""El ajuste por ciclo de la curva de PD con los escenarios de la institución (IFRS9-FIRMABLE).

``pd.pit_mode = "cycle"`` consume el modelo que publica ``forward`` en su vía de escenarios
(``("forward", "cycle_model")``: la sensibilidad ``b_j`` estimada sobre una tasa de referencia, la
tabla de historia y las trayectorias con sus pesos) y desplaza en logit el riesgo de cada tramo de
la curva posterior al corte:

``logit h_k(i, t) = logit h_TTC(i, edad del tramo) + δ_k(t)``, con
``δ_k(t) = Σ_j b_j · (x_kj(t) - x̄_j)``

- **El tramo de calendario** (D-FIR-1, §3.1). La edad decide el riesgo base —la forma de la curva,
  la cola, el vencimiento—; el calendario decide el desplazamiento. El tramo ``t`` cubre los meses
  ``[M + (t - 1)·u, M + (t - 1)·u + largo)``, con ``M`` el primer mes posterior al corte y ``u`` los
  meses de un período de la curva; su ``x`` es el promedio de los períodos del escenario que se
  solapan con esa ventana, ponderado por los meses de solape. Dentro del tramo, el riesgo
  desplazado vale para los dos períodos de la curva que el tramo cruza.
- **El ancla** (D-FIR-3, §3.3). La curva es el promedio de las condiciones de su historia: con la
  fecha de otorgamiento, ``x̄_W`` es la macro media de los períodos-operación con que se ajustó —el
  universo del ajuste, del período 1 a la duración de cada fila, con sólo los meses observados hasta
  el corte y su valor por solape mensual con la tabla de historia—; las filas sin fecha no entran y
  se cuentan. Sin ninguna fecha, la curva se toma como de largo plazo: ``x̄_W = x̄_LP``.
- **La reversión.** Más allá del último mes de un escenario, mes a mes,
  ``δ(m) = δ_LP + (δ_último - δ_LP) · max(0, 1 - e/24)``, con ``e`` los meses transcurridos y
  ``δ_LP = Σ_j b_j · (x̄_LP_j - x̄_W_j)`` las condiciones de largo plazo de la tabla de historia.

**El calendario va por meses**, y es una convención, no una perilla: el primer mes posterior al
corte es el que contiene el **día siguiente** al corte —con el corte el 1 de marzo, marzo; con el
corte el 30 de junio, julio—, de modo que un corte a fin de mes no deja un día suelto del mes que
cierra. Los meses observados de la historia son los anteriores a ése. Un valor de una tabla vale
para todo su período (la fila del 1 de enero de una tabla trimestral, para enero, febrero y marzo).

**Qué NO se configura** (§3.11): el ancla, el largo y la forma de la reversión, la regla del tramo
de calendario y la cobertura mínima de los escenarios (los 12 meses del Stage 1). Constantes con su
razón, no perillas.

``pandas``/``numpy`` se importan de forma perezosa.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal, TypeAlias, cast

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.provisioning.ifrs9.exceptions import IfrsConfigError, IfrsInputError

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    from bayesrisk.forward.cycle import ForwardCycleModel

    NDArrayFloat: TypeAlias = np.ndarray[Any, np.dtype[np.float64]]
    DataFrame: TypeAlias = pd.DataFrame
else:
    ForwardCycleModel: TypeAlias = Any
    NDArrayFloat: TypeAlias = Any
    DataFrame: TypeAlias = Any

__all__ = [
    "MESES_CUBIERTOS",
    "CurveHistory",
    "CycleAnchor",
    "CycleInputs",
    "CycleShifter",
    "calendar_position",
    "cycle_anchor",
    "first_future_month",
    "shift_term_structure",
]

#: §3.4: los escenarios cubren al menos los 12 meses posteriores al corte, la ventana del Stage 1.
#: Menos que eso dejaría la ECL a 12 meses fuera de la previsión de la institución.
MESES_CUBIERTOS: Final = 12
#: Los meses desde el año 0: la misma cuenta que usa ``forward`` (``año · 12 + mes - 1``).
_MES_DE_LA_EPOCA: Final = 1970 * 12
_EPOCA: Final = "1970-01-01"
_ESTADO_ESCENARIO: Final = "scenario"
_ESTADO_REVERSION: Final = "reversion"
_ESTADO_LARGO_PLAZO: Final = "long_run"

_NUMPY_MESSAGE: Final = "El ajuste por ciclo requiere numpy; instale bayesrisk[scoring]."
_PANDAS_MESSAGE: Final = "El ajuste por ciclo requiere pandas; instale bayesrisk[scoring]."
_MESES: Final = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass(frozen=True)
class CurveHistory:
    """El universo con que se ajustó la curva: otorgamiento y duración de cada fila (§3.3).

    ``origination`` va en meses continuos del calendario (``NaN`` si la fila no trae fecha) y
    ``duration_periods`` en períodos enteros de la curva, como los expandió el ajuste.
    """

    origination: NDArrayFloat
    duration_periods: Any
    n_rows_without_date: int


@dataclass(frozen=True)
class CycleInputs:
    """Lo que la provisión necesita para el ajuste por ciclo: el modelo y la historia de la curva.

    ``history`` es ``None`` cuando la provisión no declara la fecha de otorgamiento: entonces la
    curva se toma como de largo plazo.
    """

    model: ForwardCycleModel
    history: CurveHistory | None


@dataclass(frozen=True)
class CycleAnchor:
    """Las condiciones contra las que se mide el desplazamiento (§3.3), con lo que se contó."""

    kind: Literal["curve_history", "long_run"]
    values: dict[str, float]
    long_run_values: dict[str, float]
    long_run_shift: float
    person_periods: int
    person_periods_without_date: int
    person_periods_without_observed_month: int
    rows_without_date: int
    first_month: int | None
    last_month: int | None

    def as_section(self) -> dict[str, Any]:
        """La sección ``cycle`` de la card de la provisión (sin la tabla por período)."""
        return {
            "anchor": self.kind,
            "anchor_values": dict(self.values),
            "long_run_values": dict(self.long_run_values),
            "long_run_shift": self.long_run_shift,
            "person_periods": self.person_periods,
            "person_periods_without_date": self.person_periods_without_date,
            "person_periods_without_observed_month": self.person_periods_without_observed_month,
            "rows_without_date": self.rows_without_date,
            "anchor_first_month": self.first_month,
            "anchor_last_month": self.last_month,
        }


def first_future_month(as_of_date: str) -> int:
    """El primer mes posterior al corte, el que contiene el día siguiente (``año·12 + mes - 1``)."""
    pandas = _import_pandas()
    try:
        corte = pandas.to_datetime(str(as_of_date).strip(), format="ISO8601")
    except (ValueError, TypeError) as exc:
        raise IfrsInputError(
            f"La fecha de corte {as_of_date!r} no se puede leer como fecha (AAAA-MM-DD): con "
            "escenarios, el calendario de cada tramo se cuenta desde ella."
        ) from exc
    siguiente = corte.normalize() + pandas.Timedelta(days=1)
    return int(siguiente.year) * 12 + int(siguiente.month) - 1


def calendar_position(dates: Any) -> NDArrayFloat:
    """Fechas en meses continuos del calendario (``NaN`` sin fecha), con la fracción del mes."""
    from bayesrisk.provisioning.ifrs9.contract import months_between

    numpy = _import_numpy()
    fechas = numpy.asarray(dates, dtype="datetime64[D]")
    epoca = numpy.full(fechas.shape, numpy.datetime64(_EPOCA), dtype="datetime64[D]")
    meses: NDArrayFloat = _MES_DE_LA_EPOCA + months_between(epoca, fechas)
    return meses


def check_scenario_coverage(model: ForwardCycleModel, *, first_month: int) -> None:
    """Los escenarios empiezan a más tardar en el primer mes futuro y cubren 12 meses (§3.4).

    Raises
    ------
    IfrsInputError
        Si algún escenario empieza después del primer mes posterior al corte o termina antes de
        cubrir los 12 meses siguientes.
    """
    hasta = first_month + MESES_CUBIERTOS - 1
    for escenario in model.scenarios:
        if escenario.start_months[0] > first_month:
            raise IfrsInputError(
                f"El escenario {escenario.name!r} empieza en "
                f"{_mes_en_palabras(escenario.start_months[0])} y el primer mes posterior al corte "
                f"es {_mes_en_palabras(first_month)}: el primer período de cada escenario tiene "
                "que contenerlo (o ser anterior)."
            )
        if escenario.last_month < hasta:
            raise IfrsInputError(
                f"El escenario {escenario.name!r} llega hasta "
                f"{_mes_en_palabras(escenario.last_month)}: los escenarios cubren al menos los "
                f"{MESES_CUBIERTOS} meses posteriores al corte "
                f"(hasta {_mes_en_palabras(hasta)}), la ventana del Stage 1."
            )


def cycle_anchor(
    model: ForwardCycleModel,
    history: CurveHistory | None,
    *,
    months_per_period: float,
    first_month: int,
) -> CycleAnchor:
    """El ancla del desplazamiento (§3.3): la historia de la curva, o el largo plazo sin fechas.

    Raises
    ------
    IfrsInputError
        Si la tabla de historia no cubre algún mes observado de la historia de la curva (un ancla
        material no se rellena con un neutro): el mensaje dice los años que faltan.
    """
    numpy = _import_numpy()
    largo = {v: float(model.long_run_means[v]) for v in model.factor_cols}
    con_fecha = (
        numpy.zeros(0, dtype=bool)
        if history is None
        else ~numpy.isnan(numpy.asarray(history.origination, dtype=numpy.float64))
    )
    if history is None or not bool(con_fecha.any()):
        duraciones = (
            numpy.zeros(0, dtype=numpy.int64)
            if history is None
            else numpy.asarray(history.duration_periods, dtype=numpy.int64)
        )
        return CycleAnchor(
            kind="long_run",
            values=dict(largo),
            long_run_values=largo,
            long_run_shift=0.0,
            person_periods=int(duraciones.sum()),
            person_periods_without_date=int(duraciones.sum()),
            person_periods_without_observed_month=0,
            rows_without_date=0 if history is None else int(history.n_rows_without_date),
            first_month=None,
            last_month=None,
        )
    origen = numpy.asarray(history.origination, dtype=numpy.float64)
    duracion = numpy.asarray(history.duration_periods, dtype=numpy.int64)
    sin_fecha_pp = int(duracion[~con_fecha].sum())
    origen, duracion = origen[con_fecha], duracion[con_fecha]
    fila = numpy.repeat(numpy.arange(origen.size), duracion)
    inicio_de = numpy.concatenate([[0], numpy.cumsum(duracion)[:-1]])
    edad = numpy.arange(int(duracion.sum())) - numpy.repeat(inicio_de, duracion) + 1
    desde = origen[fila] + (edad - 1) * months_per_period
    hasta = numpy.minimum(origen[fila] + edad * months_per_period, float(first_month))
    observado = hasta > desde
    desde, hasta = desde[observado], hasta[observado]

    primer, ultimo = model.history_start_months[0], model.history_last_month
    meses_antes = numpy.floor(desde) < primer
    meses_despues = numpy.ceil(hasta) - 1 > ultimo
    if bool(meses_antes.any()) or bool(meses_despues.any()):
        anios: set[int] = set()
        if bool(meses_antes.any()):
            anios.update(range(int(numpy.floor(desde.min())) // 12, primer // 12 + 1))
        if bool(meses_despues.any()):
            anios.update(range(ultimo // 12, int(numpy.ceil(hasta.max()) - 1) // 12 + 1))
        raise IfrsInputError(
            "La tabla de historia no cubre la ventana con que se ajustó la curva: cubre "
            f"{_mes_en_palabras(primer)} a {_mes_en_palabras(ultimo)} y la historia de la curva "
            f"necesita también los años {', '.join(str(a) for a in sorted(anios))}. El ancla del "
            "desplazamiento es la macro de esos meses: completa la tabla (la tasa puede faltar al "
            "principio o al final; la macro, no)."
        )
    valores: dict[str, float] = {}
    for variable in model.factor_cols:
        mensual = _mensual(
            model.history_start_months,
            model.history_values[variable],
            model.history_frequency_months,
            numpy,
        )
        promedio = _promedio_en_ventanas(mensual, primer, desde, hasta, numpy)
        valores[variable] = float(promedio.mean())
    delta_lp = math.fsum(
        float(model.coefficients[v]) * (largo[v] - valores[v]) for v in model.factor_cols
    )
    return CycleAnchor(
        kind="curve_history",
        values=valores,
        long_run_values=largo,
        long_run_shift=delta_lp,
        person_periods=int(observado.size) + sin_fecha_pp,
        person_periods_without_date=sin_fecha_pp,
        person_periods_without_observed_month=int((~observado).sum()),
        rows_without_date=int(history.n_rows_without_date),
        first_month=int(numpy.floor(desde.min())),
        last_month=int(numpy.ceil(hasta.max()) - 1),
    )


class CycleShifter:
    """El desplazamiento ``δ_k`` de cada escenario sobre una ventana de meses (§3.1 y §3.3)."""

    def __init__(
        self,
        model: ForwardCycleModel,
        anchor: CycleAnchor,
        *,
        months_per_period: float,
        first_month: int,
    ) -> None:
        """Arma el desplazamiento mes a mes de cada escenario, con su reversión."""
        self.model = model
        self.anchor = anchor
        self.months_per_period = float(months_per_period)
        self.first_month = int(first_month)
        self.names = tuple(e.name for e in model.scenarios)
        self.weights = model.weights

    def deltas(self, starts: NDArrayFloat, lengths: NDArrayFloat) -> dict[str, NDArrayFloat]:
        """``δ_k`` de cada ventana ``[M + start, M + start + length)`` en meses, por escenario."""
        numpy = _import_numpy()
        inicio = self.first_month + numpy.asarray(starts, dtype=numpy.float64)
        fin = inicio + numpy.asarray(lengths, dtype=numpy.float64)
        hasta = int(numpy.ceil(fin.max())) if fin.size else self.first_month + 1
        salida: dict[str, NDArrayFloat] = {}
        for escenario in self.model.scenarios:
            mensual = self._delta_mensual(escenario, hasta, numpy)
            salida[escenario.name] = _promedio_en_ventanas(
                mensual, self.first_month, inicio, fin, numpy
            )
        return salida

    def by_period(self, n_periods: int) -> DataFrame:
        """``("provisioning_ifrs9", "cycle_by_period")``: escenario × tramo completo (§3.1)."""
        pandas = _import_pandas()
        numpy = _import_numpy()
        u = self.months_per_period
        t = numpy.arange(1, n_periods + 1, dtype=numpy.float64)
        inicio = self.first_month + (t - 1.0) * u
        fin = inicio + u
        hasta = int(numpy.ceil(fin.max()))
        filas: list[DataFrame] = []
        for escenario in self.model.scenarios:
            delta = _promedio_en_ventanas(
                self._delta_mensual(escenario, hasta, numpy), self.first_month, inicio, fin, numpy
            )
            dentro = numpy.minimum(fin, escenario.last_month + 1.0) - inicio
            dentro = numpy.clip(dentro, 0.0, u)
            columnas: dict[str, Any] = {
                "scenario": escenario.name,
                "period": t.astype(numpy.int64),
                "window_start": [_fecha_iso(m) for m in inicio],
                "window_end": [_fecha_iso(m) for m in fin],
                "months_in_scenario": dentro,
            }
            for variable in self.model.factor_cols:
                mensual = _mensual(
                    escenario.start_months,
                    escenario.values[variable],
                    escenario.frequency_months,
                    numpy,
                )
                cubierto_fin = numpy.minimum(fin, escenario.last_month + 1.0)
                valor = numpy.full(t.size, numpy.nan)
                con = cubierto_fin > inicio
                if bool(con.any()):
                    valor[con] = _promedio_en_ventanas(
                        mensual, escenario.start_months[0], inicio[con], cubierto_fin[con], numpy
                    )
                columnas[variable] = valor
            columnas["cycle_shift"] = delta
            meses_tras = inicio - (escenario.last_month + 1.0)
            columnas["state"] = numpy.where(
                dentro >= u - 1e-12,
                _ESTADO_ESCENARIO,
                numpy.where(
                    meses_tras >= self.model.reversion_months - 1e-12,
                    _ESTADO_LARGO_PLAZO,
                    _ESTADO_REVERSION,
                ),
            )
            filas.append(pandas.DataFrame(columnas))
        return cast("DataFrame", pandas.concat(filas, ignore_index=True))

    def first_year_shift(self) -> dict[str, float]:
        """El desplazamiento medio de los 12 meses posteriores al corte, por escenario."""
        numpy = _import_numpy()
        deltas = self.deltas(numpy.array([0.0]), numpy.array([float(MESES_CUBIERTOS)]))
        return {nombre: float(valor[0]) for nombre, valor in deltas.items()}

    def _delta_mensual(self, escenario: Any, hasta: int, numpy: Any) -> NDArrayFloat:
        """``δ_k(m)`` para los meses ``[M, hasta)``: el escenario y, tras él, la reversión."""
        meses = numpy.arange(self.first_month, max(hasta, self.first_month + 1), dtype=numpy.int64)
        delta = numpy.zeros(meses.size, dtype=numpy.float64)
        for variable in self.model.factor_cols:
            mensual = _mensual(
                escenario.start_months,
                escenario.values[variable],
                escenario.frequency_months,
                numpy,
            )
            posicion = numpy.clip(meses - escenario.start_months[0], 0, mensual.size - 1)
            delta += float(self.model.coefficients[variable]) * (
                mensual[posicion] - float(self.anchor.values[variable])
            )
        ultimo = escenario.last_month
        ultimo_delta = math.fsum(
            float(self.model.coefficients[v])
            * (float(escenario.values[v][-1]) - float(self.anchor.values[v]))
            for v in self.model.factor_cols
        )
        transcurridos = meses - ultimo
        lp = float(self.anchor.long_run_shift)
        reversion = lp + (ultimo_delta - lp) * numpy.clip(
            1.0 - transcurridos / float(self.model.reversion_months), 0.0, 1.0
        )
        return cast("NDArrayFloat", numpy.where(meses <= ultimo, delta, reversion))


def shift_term_structure(
    term_structure: DataFrame, shifter: CycleShifter, *, months_per_period: float
) -> DataFrame:
    """La curva sin fechas del contrato, una por escenario: el período ``t`` es el tramo ``t``.

    Sin fechas, cada operación lee la curva desde su período 1 (``A = 0``, §3.1): el período ``t``
    cubre los meses ``[M + (t - 1)·u, M + t·u)``. Por curva ``(row_id, escenario)``, el riesgo de
    cada período sale de la PD marginal y de la supervivencia anterior, se desplaza en logit y se
    recompone la supervivencia; la salida lleva una curva por escenario del modelo, con su peso
    (``scenario_weight``) y su desplazamiento (``cycle_shift``).
    """
    numpy = _import_numpy()
    pandas = _import_pandas()
    base = term_structure.sort_values(["row_id", "period"], kind="mergesort").reset_index(drop=True)
    curvas = base["row_id"].astype(str).to_numpy()
    periodo = base["period"].to_numpy(dtype=numpy.float64)
    marginal = base["pd_marginal"].to_numpy(dtype=numpy.float64)
    riesgo = _riesgo_por_periodo(curvas, periodo, marginal, numpy)
    deltas = shifter.deltas(
        (periodo - 1.0) * months_per_period, numpy.full(periodo.size, months_per_period)
    )
    salida: list[DataFrame] = []
    for nombre, delta in deltas.items():
        nuevo = _desplazar(riesgo, delta, numpy)
        log_s = numpy.log1p(-nuevo)
        acumulado = pandas.Series(log_s).groupby(curvas).cumsum().to_numpy()
        supervivencia = numpy.exp(acumulado)
        previa = numpy.exp(acumulado - log_s)
        marco = base.copy(deep=True)
        marco["scenario"] = nombre
        marco["scenario_weight"] = float(shifter.weights[nombre])
        marco["hazard"] = nuevo
        marco["pd_marginal"] = numpy.maximum(previa - supervivencia, 0.0)
        if "survival" in marco.columns:
            marco["survival"] = supervivencia
        if "pd_cumulative" in marco.columns:
            marco["pd_cumulative"] = 1.0 - supervivencia
        marco["cycle_shift"] = delta
        salida.append(marco)
    return cast("DataFrame", pandas.concat(salida, ignore_index=True))


def shifted_tranche_pd(
    riesgos: NDArrayFloat,
    relleno: NDArrayFloat,
    *,
    curva: Any,
    desde: NDArrayFloat,
    hasta: NDArrayFloat,
    delta: NDArrayFloat,
) -> NDArrayFloat:
    """La PD de cada tramo con el riesgo desplazado ``δ`` en ese tramo (lectura por contrato).

    ``riesgos`` es la curva extendida (curvas × períodos, ya con la cola) y ``relleno`` el riesgo
    de la cola de cada curva. El tramo ``[desde, hasta]`` de la curva cruza a lo sumo dos períodos:
    el riesgo desplazado vale para los dos, constante dentro de cada período, y la PD es la de
    incumplir en el tramo dado que la operación sobrevivió hasta el corte.
    """
    numpy = _import_numpy()
    pandas = _import_pandas()
    n_periodos = riesgos.shape[1]
    piso = numpy.floor(desde + 1e-12)
    k1 = piso.astype(numpy.int64) + 1
    limite = numpy.minimum(hasta, piso + 1.0)
    l1 = numpy.maximum(limite - desde, 0.0)
    l2 = numpy.maximum(hasta - limite, 0.0)

    def _riesgo(k: Any) -> NDArrayFloat:
        dentro = numpy.minimum(k, n_periodos)
        return cast(
            "NDArrayFloat",
            numpy.where(k > n_periodos, relleno[curva], riesgos[curva, dentro - 1]),
        )

    h1 = _desplazar(_riesgo(k1), delta, numpy)
    h2 = _desplazar(_riesgo(k1 + 1), delta, numpy)
    with numpy.errstate(divide="ignore", invalid="ignore"):
        log_s = numpy.where(l1 > 0.0, l1 * numpy.log1p(-h1), 0.0) + numpy.where(
            l2 > 0.0, l2 * numpy.log1p(-h2), 0.0
        )
    acumulado = pandas.Series(log_s).groupby(numpy.asarray(curva)).cumsum().to_numpy()
    fin = numpy.exp(acumulado)
    inicio = numpy.exp(acumulado - log_s)
    return cast("NDArrayFloat", numpy.maximum(inicio - fin, 0.0))


def _desplazar(riesgo: NDArrayFloat, delta: NDArrayFloat, numpy: Any) -> NDArrayFloat:
    """``sigmoide(logit h + δ)``: un riesgo de 0 o de 1 queda donde está."""
    with numpy.errstate(divide="ignore", over="ignore"):
        logit = numpy.log(riesgo) - numpy.log1p(-riesgo)
        return cast("NDArrayFloat", 1.0 / (1.0 + numpy.exp(-(logit + delta))))


def _riesgo_por_periodo(
    curvas: Any, periodo: NDArrayFloat, marginal: NDArrayFloat, numpy: Any
) -> NDArrayFloat:
    """El riesgo de cada período desde la PD marginal: ``h_t = m_t / S_{t-1}``, por curva.

    Exige que cada curva vaya del período 1 al último sin saltos (la supervivencia anterior sale de
    los períodos previos).
    """
    pandas = _import_pandas()
    grupos = pandas.Series(periodo).groupby(curvas)
    esperado = grupos.cumcount().to_numpy() + 1
    if bool(numpy.any(periodo != esperado)):
        raise IfrsInputError(
            "Con escenarios, la curva de cada operación tiene que ir del período 1 al último, "
            "sin saltos: el riesgo de cada período sale de la supervivencia anterior."
        )
    acumulada = pandas.Series(marginal).groupby(curvas).cumsum().to_numpy()
    previa = 1.0 - (acumulada - marginal)
    with numpy.errstate(divide="ignore", invalid="ignore"):
        riesgo = numpy.where(previa > 0.0, marginal / previa, 0.0)
    return cast("NDArrayFloat", numpy.clip(riesgo, 0.0, 1.0))


def _mensual(
    start_months: Sequence[int], values: Sequence[float], frequency: int, numpy: Any
) -> Any:
    """La serie de una tabla, mes a mes desde su primer mes: cada valor vale para su período."""
    return numpy.repeat(numpy.asarray(values, dtype=numpy.float64), int(frequency))


def _promedio_en_ventanas(
    mensual: Any, primer_mes: int, desde: Any, hasta: Any, numpy: Any
) -> NDArrayFloat:
    """El promedio de una serie mensual sobre ``[desde, hasta)``, ponderado por el solape.

    ``mensual[i]`` vale para el mes ``primer_mes + i`` (constante dentro del mes); las ventanas van
    en meses continuos y se suponen cubiertas por la serie.
    """
    acumulado = numpy.concatenate([[0.0], numpy.cumsum(mensual)])

    def _integral(x: Any) -> Any:
        posicion = numpy.asarray(x, dtype=numpy.float64) - primer_mes
        entero = numpy.clip(numpy.floor(posicion).astype(numpy.int64), 0, mensual.size)
        fraccion = posicion - entero
        siguiente = numpy.where(
            fraccion > 0.0, mensual[numpy.minimum(entero, mensual.size - 1)], 0.0
        )
        return acumulado[entero] + fraccion * siguiente

    largo = numpy.asarray(hasta, dtype=numpy.float64) - numpy.asarray(desde, dtype=numpy.float64)
    with numpy.errstate(divide="ignore", invalid="ignore"):
        return cast("NDArrayFloat", (_integral(hasta) - _integral(desde)) / largo)


def _mes_en_palabras(mes: int) -> str:
    anio, indice = divmod(int(mes), 12)
    return f"{_MESES[indice]} de {anio}"


def _fecha_iso(mes: float) -> str:
    """Un instante en meses continuos del calendario como fecha AAAA-MM-DD (al día)."""
    import calendar

    entero = math.floor(mes)
    anio, indice = divmod(int(entero), 12)
    dias = calendar.monthrange(anio, indice + 1)[1]
    dia = 1 + math.floor((mes - entero) * dias + 1e-9)
    return f"{anio:04d}-{indice + 1:02d}-{dia:02d}"


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


def require_cycle(cycle: CycleInputs | None) -> CycleInputs:
    """La corrida con ``pit_mode='cycle'`` trae el modelo del ciclo, o no corre."""
    if cycle is None:
        raise IfrsConfigError(
            "pd.pit_mode='cycle' ajusta la PD al ciclo con los escenarios de la institución, y no "
            "llegó el modelo del ciclo: activa la sección forward con satellite.mode="
            "'reference_rate' y macro.kind='scenario_paths'."
        )
    return cycle
