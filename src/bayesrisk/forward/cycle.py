"""La vía de los escenarios de la institución (IFRS9-FIRMABLE D-FIR-2 y D-FIR-4).

Con ``forward.satellite.mode = "reference_rate"`` y ``forward.macro.kind = "scenario_paths"`` la
capa ``forward`` no proyecta la macro ni toca la curva: lee dos tablas que entrega la institución y
publica ``("forward", "cycle_model")``, que la provisión IFRS 9 consume con
``pd.pit_mode = "cycle"``:

- **La historia** de una tasa de incumplimiento de referencia larga con sus variables macro. El
  satélite se ajusta sobre ella por mínimos cuadrados, ``logit(r_c) = a + Σ_j b_j · (x_cj - x̄_j)``,
  con la macro contemporánea y en niveles; ``x̄_j`` es la media de la ventana (el largo plazo).
  La tasa va como fracción en (0, 1), sin inferir la escala por la magnitud. Puede faltar al
  principio o al final de la tabla —el período del corte todavía no la tiene—: esos períodos no
  entran al satélite y sólo dan su macro al ancla de la provisión (D-FIR-3). Un hueco en medio
  detiene la corrida.
- **Los escenarios**: una trayectoria por escenario (``macro_path_path``), con su peso en el config.
  Son la previsión de la institución (B5.5.51): se toman tal cual, sin modelo macro.

Cada tabla tiene **una frecuencia regular** —mensual, trimestral o anual—, inferida de sus fechas
y declarada, y **sin huecos**: la fecha de cada fila marca el período que la contiene. La frecuencia
de la historia y la de los escenarios son independientes (pasada 2 de Codex sobre la enmienda).

**Qué NO se configura** (§3.2): el rezago (el contemporáneo fue el mejor en las tres series
medidas), la forma (logit lineal), el estimador (MCO) y la ventana (las filas con la tasa). Son
constantes con su razón, no perillas.

``pandas``/``numpy`` se importan de forma perezosa: ``import bayesrisk.forward`` no debe
arrastrarlas.

**Experimental (fuera de la garantía SemVer 2.x).**
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal, Self, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.forward.exceptions import (
    ForwardInputError,
    ForwardScenarioError,
    SatelliteModelError,
)

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    NDArrayFloat: TypeAlias = np.ndarray[Any, np.dtype[np.float64]]
    NDArrayInt: TypeAlias = np.ndarray[Any, np.dtype[np.int64]]
    DataFrame: TypeAlias = pd.DataFrame
else:
    NDArrayFloat: TypeAlias = Any
    NDArrayInt: TypeAlias = Any
    DataFrame: TypeAlias = Any

__all__ = [
    "MESES_DE_REVERSION",
    "PERIODOS_SIN_ALERTA",
    "UMBRAL_R2",
    "UMBRAL_T",
    "CycleScenarioPath",
    "ForwardCycleModel",
    "build_cycle_model",
    "calendar_table",
    "month_label",
]

FrequencyMonths = Literal[1, 3, 12]

#: §3.3: más allá del último mes de un escenario, el desplazamiento vuelve en línea recta (en
#: logit) hacia las condiciones de largo plazo en estos meses. Lectura supervisora (ECB 2020; EBA
#: 2021 §115 y 116: tres años de pronóstico y luego reversión); medido, mueve +0,3 puntos en Freddie
#: Mac y nada en Lending Club. No es una perilla.
MESES_DE_REVERSION: Final = 24
#: §3.2: «Qué revisar» alerta si la sensibilidad es incierta —``|b / se| < 2``, la regla de dos
#: errores estándar, o R² < 0,1, menos de lo que explicó la serie más débil medida (castigos de
#: consumo, 0,13)— o si la ventana tiene menos de 20 períodos (cinco años trimestrales: menos de un
#: ciclo). Constantes de la lectura, no del cálculo.
UMBRAL_T: Final = 2.0
UMBRAL_R2: Final = 0.1
PERIODOS_SIN_ALERTA: Final = 20

#: Las frecuencias que una tabla puede tener, en meses por período, y su nombre.
_FRECUENCIAS: Final[dict[int, str]] = {1: "mensual", 3: "trimestral", 12: "anual"}
_NUMPY_MESSAGE: Final = "La vía de escenarios requiere numpy; instale las dependencias base."
_PANDAS_MESSAGE: Final = "La vía de escenarios requiere pandas; instale las dependencias base."


class CycleScenarioPath(BaseModel):
    """La trayectoria macro de un escenario, por período de su tabla (D-FIR-4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    weight: float = Field(gt=0.0, le=1.0)
    frequency_months: FrequencyMonths
    #: El primer mes de cada período, como ``año · 12 + mes - 1``.
    start_months: tuple[int, ...] = Field(min_length=1)
    values: dict[str, tuple[float, ...]]
    #: La huella del contenido de su tabla (SHA-256 lógico, la del trail): su ubicación no entra
    #: al ``config_hash`` (IFRS9-FIRMABLE capa C; Cami, 2026-10-09). La pone ``forward`` al leerla.
    content_hash: str | None = None

    @model_validator(mode="after")
    def _check_largos(self) -> Self:
        for variable, serie in self.values.items():
            if len(serie) != len(self.start_months):
                raise ValueError(f"La trayectoria de {variable!r} no tiene un valor por período.")
            if not all(math.isfinite(v) for v in serie):
                raise ValueError(f"La trayectoria de {variable!r} trae valores no finitos.")
        return self

    @property
    def last_month(self) -> int:
        """El último mes que cubre el escenario."""
        return self.start_months[-1] + self.frequency_months - 1


class ForwardCycleModel(BaseModel):
    """El satélite contra la tasa de referencia, su historia y los escenarios (D-FIR-2 y D-FIR-4).

    Lo publica ``forward`` como ``("forward", "cycle_model")`` y lo consume la provisión IFRS 9
    con ``pd.pit_mode = "cycle"``. Los meses van como ``año · 12 + mes - 1``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_rate_col: str
    factor_cols: tuple[str, ...] = Field(min_length=1)
    intercept: float
    coefficients: dict[str, float]
    std_errors: dict[str, float]
    r_squared: float | None
    #: Períodos de la ventana del satélite: los que traen la tasa.
    n_periods: int = Field(ge=1)
    history_frequency_months: FrequencyMonths
    window_start_month: int
    window_end_month: int
    #: Las condiciones de largo plazo: la media de cada variable en la ventana del satélite.
    long_run_means: dict[str, float]
    history_start_months: tuple[int, ...]
    history_values: dict[str, tuple[float, ...]]
    history_rate: tuple[float | None, ...]
    scenarios: tuple[CycleScenarioPath, ...] = Field(min_length=2)
    reversion_months: int = MESES_DE_REVERSION
    #: La huella del contenido de la tabla de historia, como ``content_hash`` de cada escenario.
    history_hash: str | None = None

    @model_validator(mode="after")
    def _check_consistencia(self) -> Self:
        variables = set(self.factor_cols)
        for nombre, mapa in (
            ("coefficients", self.coefficients),
            ("std_errors", self.std_errors),
            ("long_run_means", self.long_run_means),
            ("history_values", self.history_values),
        ):
            if set(mapa) != variables:
                raise ValueError(f"{nombre} no trae exactamente las variables {sorted(variables)}.")
        for escenario in self.scenarios:
            if set(escenario.values) != variables:
                raise ValueError(f"El escenario {escenario.name!r} no trae las mismas variables.")
        total = math.fsum(e.weight for e in self.scenarios)
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(f"Los pesos de los escenarios deben sumar 1; suman {total!r}.")
        return self

    @property
    def weights(self) -> dict[str, float]:
        """El peso de cada escenario, en el orden del config."""
        return {e.name: e.weight for e in self.scenarios}

    @property
    def history_last_month(self) -> int:
        """El último mes que cubre la tabla de historia."""
        return self.history_start_months[-1] + self.history_frequency_months - 1


@dataclass(frozen=True)
class CalendarTable:
    """Una tabla con una fila por período, regular y sin huecos (§3.4)."""

    frequency_months: int
    start_months: NDArrayInt
    frame: DataFrame


def month_label(start_month: int, frequency_months: int) -> str:
    """El período en palabras cortas: «2019-03», «2019T1» o «2019»."""
    anio, mes = divmod(int(start_month), 12)
    if frequency_months == 12:
        return f"{anio}"
    if frequency_months == 3:
        return f"{anio}T{mes // 3 + 1}"
    return f"{anio}-{mes + 1:02d}"


def calendar_table(frame: DataFrame, *, time_col: str, nombre: str) -> CalendarTable:
    """Ordena la tabla por fecha e infiere su frecuencia; se detiene ante un hueco (§3.4).

    La fecha de cada fila marca el período mensual, trimestral o anual que la contiene. La
    frecuencia es la menor de las tres con la que los períodos quedan seguidos, uno por fila: una
    tabla trimestral fechada el 15 de cada mes intermedio también es trimestral.

    Raises
    ------
    ForwardInputError
        Si falta la columna de fecha, una fecha no se puede leer, dos filas caen en el mismo
        período, la tabla trae menos de dos períodos o tiene huecos.
    """
    pandas = _import_pandas()
    numpy = _import_numpy()
    if time_col not in frame.columns:
        raise ForwardInputError(
            f"La tabla {nombre} no trae la columna de fecha {time_col!r}. Columnas: "
            f"{', '.join(str(c) for c in frame.columns)}."
        )
    fechas = _fechas(frame[time_col], nombre=nombre, pandas=pandas, numpy=numpy)
    orden = numpy.argsort(fechas, kind="mergesort")
    ordenada = frame.iloc[orden].reset_index(drop=True)
    fechas = fechas[orden]
    meses = (
        pandas.DatetimeIndex(fechas).year.to_numpy() * 12
        + pandas.DatetimeIndex(fechas).month.to_numpy()
        - 1
    ).astype(numpy.int64)
    if meses.size < 2:
        raise ForwardInputError(
            f"La tabla {nombre} trae un solo período: con uno no se puede saber su frecuencia. "
            "Entrega al menos dos."
        )
    for frecuencia in _FRECUENCIAS:
        claves = meses // frecuencia
        if bool(numpy.all(numpy.diff(claves) == 1)):
            return CalendarTable(
                frequency_months=frecuencia,
                start_months=(claves * frecuencia).astype(numpy.int64),
                frame=ordenada,
            )
    repetidas = numpy.flatnonzero(numpy.diff(meses) == 0)
    if repetidas.size:
        i = int(repetidas[0])
        raise ForwardInputError(
            f"La tabla {nombre} trae dos filas del mismo período ({_iso(fechas[i])} y "
            f"{_iso(fechas[i + 1])}): una fila por período."
        )
    saltos = numpy.diff(meses)
    paso = int(numpy.min(saltos))
    i = int(numpy.flatnonzero(saltos != paso)[0]) if bool(numpy.any(saltos != paso)) else 0
    raise ForwardInputError(
        f"La tabla {nombre} no tiene una frecuencia regular sin huecos —mensual, trimestral o "
        f"anual, un período por fila—: entre {_iso(fechas[i])} y {_iso(fechas[i + 1])} hay "
        f"{int(saltos[i])} meses."
    )


def build_cycle_model(
    history: DataFrame,
    scenario_paths: Mapping[str, DataFrame],
    weights: Mapping[str, float],
    *,
    time_col: str,
    reference_rate_col: str,
    factor_cols: Sequence[str],
) -> ForwardCycleModel:
    """Ajusta el satélite sobre la historia y lee las trayectorias de los escenarios (§3.2, §3.4).

    ``scenario_paths`` lleva una tabla por escenario (fecha y variables) y ``weights``, el peso de
    cada uno: los dos en el orden del config. La cobertura de los 12 meses posteriores al corte la
    comprueba la provisión, que conoce el corte.

    Raises
    ------
    ForwardInputError
        Si una tabla no trae sus columnas, una fecha no se lee, una tabla tiene huecos, una
        variable trae valores no numéricos o la tasa sale de (0, 1).
    ForwardScenarioError
        Si hay menos de dos escenarios, un peso no es positivo, los escenarios no traen los
        mismos períodos o la misma frecuencia.
    SatelliteModelError
        Si la ventana del satélite tiene menos períodos que variables + 2 o una variable es
        constante en ella.
    """
    numpy = _import_numpy()
    variables = tuple(str(v) for v in factor_cols)
    tabla = calendar_table(history, time_col=time_col, nombre="de historia")
    faltan = [c for c in (reference_rate_col, *variables) if c not in tabla.frame.columns]
    if faltan:
        raise ForwardInputError(
            f"La tabla de historia no trae {', '.join(repr(c) for c in faltan)}. Columnas: "
            f"{', '.join(str(c) for c in tabla.frame.columns)}."
        )
    macro = {v: _numeros(tabla, v, nombre="de historia") for v in variables}
    tasa = _tasa_de_referencia(tabla, reference_rate_col)
    con_tasa = numpy.flatnonzero(~numpy.isnan(tasa))
    if con_tasa.size == 0:
        raise ForwardInputError(
            f"La tabla de historia no trae ningún valor de la tasa {reference_rate_col!r}."
        )
    primera, ultima = int(con_tasa[0]), int(con_tasa[-1])
    hueco = numpy.flatnonzero(numpy.isnan(tasa[primera : ultima + 1]))
    if hueco.size:
        i = primera + int(hueco[0])
        raise ForwardInputError(
            f"La tasa {reference_rate_col!r} falta en {_rotulo(tabla, i)}, en medio de la "
            "historia: la ventana de la sensibilidad no puede tener huecos (la tasa sólo puede "
            "faltar al principio o al final de la tabla)."
        )
    ventana = slice(primera, ultima + 1)
    n = ultima - primera + 1
    if n < len(variables) + 2:
        raise SatelliteModelError(
            f"La ventana de la sensibilidad tiene {n} períodos con la tasa y hacen falta al "
            f"menos {len(variables) + 2} para estimar {len(variables)} "
            f"{'variable' if len(variables) == 1 else 'variables'} con su error."
        )
    medias: dict[str, float] = {}
    diseno = [numpy.ones(n, dtype=numpy.float64)]
    for v in variables:
        x = macro[v][ventana]
        if float(numpy.ptp(x)) == 0.0:
            raise SatelliteModelError(
                f"La variable {v!r} es constante en la ventana de la sensibilidad: no hay cómo "
                "estimar cuánto mueve la tasa."
            )
        medias[v] = float(x.mean())
        diseno.append(x - medias[v])
    xmat = numpy.column_stack(diseno)
    y = numpy.log(tasa[ventana]) - numpy.log1p(-tasa[ventana])
    coef, _residuo, rango, _sing = numpy.linalg.lstsq(xmat, y, rcond=None)
    if int(rango) < xmat.shape[1]:
        raise SatelliteModelError(
            "Las variables de la historia son colineales en la ventana de la sensibilidad: no "
            "se puede separar el efecto de cada una."
        )
    residuos = y - xmat @ coef
    libres = n - xmat.shape[1]
    s2 = float(residuos @ residuos) / libres if libres > 0 else math.nan
    covarianza = s2 * numpy.linalg.inv(xmat.T @ xmat)
    total = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(residuos @ residuos) / total if total > 0.0 else None

    escenarios = _escenarios(
        scenario_paths, weights, time_col=time_col, variables=variables, numpy=numpy
    )
    return ForwardCycleModel(
        reference_rate_col=reference_rate_col,
        factor_cols=variables,
        intercept=float(coef[0]),
        coefficients={v: float(coef[i + 1]) for i, v in enumerate(variables)},
        std_errors={v: float(math.sqrt(covarianza[i + 1, i + 1])) for i, v in enumerate(variables)},
        r_squared=None if r2 is None else float(r2),
        n_periods=n,
        history_frequency_months=cast("FrequencyMonths", tabla.frequency_months),
        window_start_month=int(tabla.start_months[primera]),
        window_end_month=int(tabla.start_months[ultima]),
        long_run_means=medias,
        history_start_months=tuple(int(m) for m in tabla.start_months),
        history_values={v: tuple(float(x) for x in macro[v]) for v in variables},
        history_rate=tuple(None if math.isnan(float(r)) else float(r) for r in tasa),
        scenarios=escenarios,
    )


def _escenarios(
    scenario_paths: Mapping[str, DataFrame],
    weights: Mapping[str, float],
    *,
    time_col: str,
    variables: tuple[str, ...],
    numpy: Any,
) -> tuple[CycleScenarioPath, ...]:
    if len(scenario_paths) < 2:
        raise ForwardScenarioError(
            "Hacen falta al menos dos escenarios: uno solo no es un rango (IFRS 9 5.5.17(a)) y no "
            "basta si la pérdida no es lineal en la macro."
        )
    salida: list[CycleScenarioPath] = []
    referencia: tuple[int, tuple[int, ...], str] | None = None
    for nombre, frame in scenario_paths.items():
        peso = float(weights[nombre])
        if not peso > 0.0:
            raise ForwardScenarioError(
                f"El escenario {nombre!r} tiene peso {peso!r}: los pesos tienen que ser mayores "
                "que cero (un escenario sin peso no es parte del rango)."
            )
        tabla = calendar_table(frame, time_col=time_col, nombre=f"del escenario {nombre!r}")
        faltan = [v for v in variables if v not in tabla.frame.columns]
        if faltan:
            raise ForwardInputError(
                f"La trayectoria del escenario {nombre!r} no trae "
                f"{', '.join(repr(v) for v in faltan)}: los escenarios llevan las mismas variables "
                "que la historia."
            )
        periodos = tuple(int(m) for m in tabla.start_months)
        if referencia is None:
            referencia = (tabla.frequency_months, periodos, nombre)
        elif (tabla.frequency_months, periodos) != referencia[:2]:
            raise ForwardScenarioError(
                f"Los escenarios {referencia[2]!r} y {nombre!r} no traen los mismos períodos: "
                f"{month_label(referencia[1][0], referencia[0])} a "
                f"{month_label(referencia[1][-1], referencia[0])} "
                f"({_FRECUENCIAS[referencia[0]]}) frente a "
                f"{month_label(periodos[0], tabla.frequency_months)} a "
                f"{month_label(periodos[-1], tabla.frequency_months)} "
                f"({_FRECUENCIAS[tabla.frequency_months]}). Todos los escenarios llevan un valor "
                "por período, en los mismos períodos."
            )
        salida.append(
            CycleScenarioPath(
                name=nombre,
                weight=peso,
                frequency_months=cast("FrequencyMonths", tabla.frequency_months),
                start_months=periodos,
                values={
                    v: tuple(
                        float(x) for x in _numeros(tabla, v, nombre=f"del escenario {nombre!r}")
                    )
                    for v in variables
                },
            )
        )
    del numpy
    return tuple(salida)


def _tasa_de_referencia(tabla: CalendarTable, columna: str) -> NDArrayFloat:
    """La tasa como fracción en (0, 1), con ``NaN`` donde falta (§4: sin inferir la escala)."""
    pandas = _import_pandas()
    numpy = _import_numpy()
    cruda = tabla.frame[columna]
    valores = pandas.to_numeric(cruda, errors="coerce").to_numpy(dtype=numpy.float64)
    ilegible = ~cruda.isna().to_numpy() & numpy.isnan(valores)
    fuera = ~numpy.isnan(valores) & ((valores <= 0.0) | (valores >= 1.0) | ~numpy.isfinite(valores))
    malas = numpy.flatnonzero(ilegible | fuera)
    if malas.size:
        i = int(malas[0])
        raise ForwardInputError(
            f"La tasa de referencia {columna!r} vale {cruda.iloc[i]!r} en {_rotulo(tabla, i)}: "
            "tiene que ser una fracción entre 0 y 1, sin incluirlos —un 0,9 % va como 0,009—. "
            "En 0 o en 1 su logit no está definido."
        )
    return cast("NDArrayFloat", valores)


def _numeros(tabla: CalendarTable, columna: str, *, nombre: str) -> NDArrayFloat:
    """Una variable macro numérica y finita en todas las filas de la tabla."""
    pandas = _import_pandas()
    numpy = _import_numpy()
    valores = pandas.to_numeric(tabla.frame[columna], errors="coerce").to_numpy(dtype=numpy.float64)
    malas = numpy.flatnonzero(~numpy.isfinite(valores))
    if malas.size:
        i = int(malas[0])
        raise ForwardInputError(
            f"La variable {columna!r} de la tabla {nombre} no es un número en "
            f"{_rotulo(tabla, i)} ({tabla.frame[columna].iloc[i]!r}): la macro va completa en "
            "todos los períodos."
        )
    return cast("NDArrayFloat", valores)


def _fechas(serie: Any, *, nombre: str, pandas: Any, numpy: Any) -> Any:
    if isinstance(serie.dtype, pandas.DatetimeTZDtype):
        fechas = serie.dt.tz_localize(None)
    elif pandas.api.types.is_datetime64_any_dtype(serie):
        fechas = serie
    else:
        texto = serie.astype("string").str.strip()
        fechas = pandas.to_datetime(texto, format="ISO8601", errors="coerce")
    malas = numpy.flatnonzero(fechas.isna().to_numpy())
    if malas.size:
        i = int(malas[0])
        raise ForwardInputError(
            f"La tabla {nombre} trae una fecha que no se puede leer en la fila {i + 1}: "
            f"{serie.iloc[i]!r}. Usa fechas AAAA-MM-DD o una columna de tipo fecha."
        )
    return pandas.DatetimeIndex(fechas).normalize().to_numpy().astype("datetime64[D]")


def _rotulo(tabla: CalendarTable, i: int) -> str:
    return month_label(int(tabla.start_months[i]), tabla.frequency_months)


def _iso(fecha: Any) -> str:
    return str(fecha)[:10]


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
