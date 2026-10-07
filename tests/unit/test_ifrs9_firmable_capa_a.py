"""IFRS 9 firmable, capa A (enmienda IFRS9-FIRMABLE, D-FIR-1…6).

- **D-FIR-1 (§3.1).** Con escenarios, el riesgo de cada tramo posterior al corte se desplaza en
  logit, ``δ_k(t) = Σ_j b_j · (x_kj(t) - x̄_j)``; la EDAD decide el riesgo base y el CALENDARIO el
  desplazamiento: el ``x`` de un tramo es el promedio de los períodos del escenario que se solapan
  con su ventana de meses. La ECL es la ponderada de los escenarios, nunca la de la macro
  promediada.
- **D-FIR-2 (§3.2).** La sensibilidad sale de una tasa de referencia larga, por MCO sobre el logit.
- **D-FIR-3 (§3.3).** El ancla son las condiciones de la historia de la curva (con fechas) o el
  largo plazo (sin fechas), y más allá del escenario el desplazamiento revierte en 24 meses.
- **D-FIR-4 (§3.4).** Al menos dos escenarios, pesos mayores que cero, 12 meses cubiertos.
- **D-FIR-5 (§3.5).** ``forward`` en modo ``fit`` contra la edad de la curva se detiene.
- **D-FIR-6 (§3.6).** Vasicek transforma el riesgo del período, no la PD marginal.

Las cifras de §1.8 con el motor sobre Lending Club y Freddie Mac son evidencia fuera de CI
(``evidencia/s37/oraculo_motor.py``); aquí, los casos a mano que fijan cada regla.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest

from bayesrisk.forward.cycle import CycleScenarioPath, ForwardCycleModel, build_cycle_model
from bayesrisk.forward.exceptions import ForwardInputError, ForwardScenarioError
from bayesrisk.provisioning.ifrs9 import IfrsProvisioningConfig, IfrsProvisioningEngine
from bayesrisk.provisioning.ifrs9.config import (
    IfrsEadConfig,
    IfrsLgdConfig,
    IfrsPdConfig,
    IfrsScenarioConfig,
    IfrsStagingConfig,
)
from bayesrisk.provisioning.ifrs9.cycle import (
    CurveHistory,
    CycleInputs,
    calendar_position,
    check_scenario_coverage,
    cycle_anchor,
    first_future_month,
)
from bayesrisk.provisioning.ifrs9.exceptions import IfrsInputError

_CORTE = "2026-03-01"
#: Marzo de 2026: el mes que contiene el día siguiente al corte.
_MES = 2026 * 12 + 2


def _q(anio: int, trimestre: int) -> int:
    """El primer mes de un trimestre, en la cuenta de ``forward`` (``año · 12 + mes - 1``)."""
    return anio * 12 + (trimestre - 1) * 3


def _modelo(
    escenarios: dict[str, tuple[float, list[float]]],
    *,
    b: float = 0.2,
    largo_plazo: float = 6.0,
    desde: int = _q(2026, 1),
    historia: tuple[list[int], list[float]] | None = None,
) -> ForwardCycleModel:
    """Un modelo del ciclo armado a mano: escenarios trimestrales desde ``desde``."""
    meses, valores = historia or ([_q(2024, t) for t in (1, 2, 3, 4)], [5.0, 6.0, 7.0, 6.0])
    return ForwardCycleModel(
        reference_rate_col="default_rate",
        factor_cols=("u",),
        intercept=-4.0,
        coefficients={"u": b},
        std_errors={"u": 0.01},
        r_squared=0.5,
        n_periods=len(meses),
        history_frequency_months=3,
        window_start_month=meses[0],
        window_end_month=meses[-1],
        long_run_means={"u": largo_plazo},
        history_start_months=tuple(meses),
        history_values={"u": tuple(valores)},
        history_rate=tuple(0.02 for _ in meses),
        scenarios=tuple(
            CycleScenarioPath(
                name=nombre,
                weight=peso,
                frequency_months=3,
                start_months=tuple(desde + 3 * i for i in range(len(serie))),
                values={"u": tuple(serie)},
            )
            for nombre, (peso, serie) in escenarios.items()
        ),
    )


def _cfg(**cambios: Any) -> IfrsProvisioningConfig:
    base: dict[str, Any] = {
        "row_id_col": None,
        "portfolio_col": "portfolio",
        "origination_date_col": "otorgamiento",
        "maturity_date_col": "vencimiento",
        "pd": IfrsPdConfig(
            term_structure_source="survival",
            base_pd_source="term_structure",
            pit_mode="cycle",
            horizon_12m_periods=1,
        ),
        "lgd": IfrsLgdConfig(method="provided"),
        "ead": IfrsEadConfig(method="provided"),
        "scenarios": IfrsScenarioConfig(source="forward"),
        "staging": IfrsStagingConfig(),
    }
    base.update(cambios)
    return IfrsProvisioningConfig(**base)


def _curva(row_ids: list[str], hazards: list[float], *, unidad: str = "year") -> pd.DataFrame:
    filas = []
    for rid in row_ids:
        sobrevive = 1.0
        for periodo, h in enumerate(hazards, start=1):
            marginal = sobrevive * h
            sobrevive *= 1.0 - h
            filas.append(
                {
                    "row_id": rid,
                    "period": periodo,
                    "time_value": float(periodo),
                    "time_unit": unidad,
                    "hazard": h,
                    "survival": sobrevive,
                    "pd_marginal": marginal,
                    "pd_cumulative": 1.0 - sobrevive,
                    "scenario": None,
                    "warning_codes": (),
                }
            )
    return pd.DataFrame(filas)


def _cartera(**columnas: list[Any]) -> pd.DataFrame:
    n = len(next(iter(columnas.values())))
    base: dict[str, list[Any]] = {
        "portfolio": ["consumo"] * n,
        "ead": [1_000.0] * n,
        "lgd": [0.5] * n,
        "eir": [0.0] * n,
        "days_past_due": [0] * n,
        "is_default": [False] * n,
        "as_of_date": [_CORTE] * n,
    }
    base.update(columnas)
    return pd.DataFrame(base, index=pd.Index([f"op{i}" for i in range(n)], name="loan_id"))


def _sigma(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float) -> float:
    return math.log(p) - math.log1p(-p)


# ───────────────────────── D-FIR-1: el tramo de calendario (§6-1) ─────────────────────────

_HAZARDS = [0.10, 0.20, 0.30]
#: Trimestres 2026T1…2027T4: cada uno distinto, para que un tramo mal ubicado se note.
_BASE = [5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5]
_ADVERSO = [x + 2.0 for x in _BASE]


def test_d_fir_1_cada_tramo_toma_la_macro_de_su_ventana_de_calendario() -> None:
    """§6-1: curva de tres períodos anuales, edad 1,5 y vida 1,25; dos escenarios trimestrales.

    El tramo 1 cubre de marzo de 2026 a febrero de 2027: un mes de 2026T1, tres de cada trimestre
    siguiente y dos de 2027T1. El tramo 2, de marzo a mayo de 2027: un mes de 2027T1 y dos de
    2027T2. La edad decide qué períodos de la curva cruza cada tramo (la mitad del 2 y la mitad del
    3; luego un cuarto del 3); el calendario, el desplazamiento.
    """
    modelo = _modelo({"base": (0.6, _BASE), "adverso": (0.4, _ADVERSO)})
    frame = _cartera(otorgamiento=["2024-09-01"], vencimiento=["2027-06-01"])
    motor = IfrsProvisioningEngine.from_config(_cfg())
    resultado = motor.calculate(
        frame,
        term_structure=_curva(["op0"], _HAZARDS),
        as_of_date=_CORTE,
        events_by_period={1: 5, 2: 4, 3: 3},
        cycle=CycleInputs(model=modelo, history=None),
    )
    ts = resultado.ecl_term_structure.set_index(["scenario", "period"])
    for nombre, serie in (("base", _BASE), ("adverso", _ADVERSO)):
        x1 = (1 * serie[0] + 3 * serie[1] + 3 * serie[2] + 3 * serie[3] + 2 * serie[4]) / 12
        x2 = (1 * serie[4] + 2 * serie[5]) / 3
        d1, d2 = 0.2 * (x1 - 6.0), 0.2 * (x2 - 6.0)
        s1 = math.sqrt(1 - _sigma(_logit(0.2) + d1)) * math.sqrt(1 - _sigma(_logit(0.3) + d1))
        pd2 = s1 * (1 - (1 - _sigma(_logit(0.3) + d2)) ** 0.25)
        assert ts.loc[(nombre, 1), "cycle_shift"] == pytest.approx(d1, abs=1e-12)
        assert ts.loc[(nombre, 2), "cycle_shift"] == pytest.approx(d2, abs=1e-12)
        assert ts.loc[(nombre, 1), "pd_marginal"] == pytest.approx(1 - s1, abs=1e-12)
        assert ts.loc[(nombre, 2), "pd_marginal"] == pytest.approx(pd2, abs=1e-12)
    porcion = motor.cycle_by_period_
    assert porcion is not None
    fila = porcion.set_index(["scenario", "period"]).loc[("base", 1)]
    assert (fila["window_start"], fila["window_end"]) == ("2026-03-01", "2027-03-01")
    assert fila["state"] == "scenario"


def test_d_fir_1_sin_fechas_el_periodo_t_es_el_tramo_t() -> None:
    """Sin fechas del contrato, ``A = 0``: el período 1 de la curva es el tramo marzo-febrero."""
    modelo = _modelo({"base": (0.5, _BASE), "adverso": (0.5, _ADVERSO)})
    cfg = _cfg(origination_date_col=None, maturity_date_col=None)
    motor = IfrsProvisioningEngine.from_config(cfg)
    resultado = motor.calculate(
        _cartera(as_of_date=[_CORTE]),
        term_structure=_curva(["op0"], [0.10, 0.20]),
        as_of_date=_CORTE,
        cycle=CycleInputs(model=modelo, history=None),
    )
    ts = resultado.ecl_term_structure.set_index(["scenario", "period"])
    x1 = (_BASE[0] + 3 * _BASE[1] + 3 * _BASE[2] + 3 * _BASE[3] + 2 * _BASE[4]) / 12
    d1 = 0.2 * (x1 - 6.0)
    assert ts.loc[("base", 1), "pd_marginal"] == pytest.approx(_sigma(_logit(0.1) + d1), abs=1e-12)


def test_d_fir_1_sin_fechas_la_ventana_sale_del_tiempo_real_de_la_curva() -> None:
    """Pasada 1 de Codex: una curva de Cox o AFT numera ``period`` 1…N y guarda su tiempo real en
    ``time_value`` —aquí cuatro trimestres expresados en años—; cada período cubre su ventana
    real (tres meses), no una unidad entera."""
    modelo = _modelo({"base": (0.5, _BASE), "adverso": (0.5, _ADVERSO)})
    cfg = _cfg(
        origination_date_col=None,
        maturity_date_col=None,
        pd=IfrsPdConfig(
            term_structure_source="survival",
            base_pd_source="term_structure",
            pit_mode="cycle",
            horizon_12m_periods=4,
        ),
    )
    curva = _curva(["op0"], [0.02, 0.03, 0.04, 0.05])
    curva["time_value"] = [0.25, 0.5, 0.75, 1.0]
    motor = IfrsProvisioningEngine.from_config(cfg)
    resultado = motor.calculate(
        _cartera(as_of_date=[_CORTE]),
        term_structure=curva,
        as_of_date=_CORTE,
        cycle=CycleInputs(model=modelo, history=None),
    )
    ts = resultado.ecl_term_structure.set_index(["scenario", "period"])
    # Marzo a mayo de 2026: un mes de 2026T1 y dos de T2; junio a agosto: uno de T2 y dos de T3.
    x1 = (_BASE[0] + 2 * _BASE[1]) / 3
    x2 = (_BASE[1] + 2 * _BASE[2]) / 3
    assert ts.loc[("base", 1), "cycle_shift"] == pytest.approx(0.2 * (x1 - 6.0), abs=1e-12)
    assert ts.loc[("base", 2), "cycle_shift"] == pytest.approx(0.2 * (x2 - 6.0), abs=1e-12)
    porcion = motor.cycle_by_period_
    assert porcion is not None
    fila = porcion.set_index(["scenario", "period"]).loc[("base", 1)]
    assert (fila["window_start"], fila["window_end"]) == ("2026-03-01", "2026-06-01")


@pytest.mark.parametrize("con_fechas", [False, True])
def test_d_fir_1_un_riesgo_de_uno_recompone_sin_nan(con_fechas: bool) -> None:
    """Pasada 1 de Codex: con un riesgo de 1, la supervivencia cae a 0 y queda ahí; restar dos
    logaritmos infinitos daba NaN y la corrida moría al validar la PD."""
    modelo = _modelo({"base": (0.5, _BASE), "adverso": (0.5, _ADVERSO)})
    cambios: dict[str, Any] = (
        {} if con_fechas else {"origination_date_col": None, "maturity_date_col": None}
    )
    frame = (
        _cartera(otorgamiento=["2025-09-01"], vencimiento=["2029-03-01"])
        if con_fechas
        else _cartera(as_of_date=[_CORTE])
    )
    resultado = IfrsProvisioningEngine.from_config(_cfg(**cambios)).calculate(
        frame,
        term_structure=_curva(["op0"], [0.20, 1.0, 0.30]),
        as_of_date=_CORTE,
        events_by_period={1: 5, 2: 4, 3: 3},
        cycle=CycleInputs(model=modelo, history=None),
    )
    marginal = resultado.ecl_term_structure["pd_marginal"].to_numpy()
    assert np.all(np.isfinite(marginal))
    por_escenario = resultado.ecl_term_structure.groupby("scenario")["pd_marginal"].sum()
    assert np.allclose(por_escenario.to_numpy(), 1.0), por_escenario


def test_d_fir_6_vasicek_con_riesgo_de_uno_no_da_nan() -> None:
    curva = _curva(["op0"], [0.20, 1.0, 0.30])
    curva["z"] = -6.0  # tan adverso que el riesgo transformado satura en 1,0 exacto
    cfg = _cfg(
        origination_date_col=None,
        maturity_date_col=None,
        pd=IfrsPdConfig(
            term_structure_source="survival",
            base_pd_source="term_structure",
            pit_mode="apply_vasicek",
            rho=0.15,
            systemic_factor_col="z",
            horizon_12m_periods=1,
        ),
        scenarios=IfrsScenarioConfig(source="single"),
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(as_of_date=[_CORTE]), term_structure=curva, as_of_date=_CORTE
    )
    marginal = resultado.ecl_term_structure["pd_marginal"].to_numpy()
    assert np.all(np.isfinite(marginal)) and float(marginal.sum()) <= 1.0 + 1e-12


def test_d_fir_1_la_ecl_pondera_escenarios_y_no_la_macro_promediada() -> None:
    """§6-2: la pérdida no es lineal en la macro; con escenarios distintos, la ponderada difiere de
    la de un escenario «medio» con la macro promediada (guarda contra el escenario medio)."""
    lejos = [x + 6.0 for x in _BASE]
    medio = [(a + b) / 2 for a, b in zip(_BASE, lejos, strict=True)]
    frame = _cartera(otorgamiento=["2024-09-01"], vencimiento=["2028-06-01"])

    def _ecl(escenarios: dict[str, tuple[float, list[float]]]) -> float:
        resultado = IfrsProvisioningEngine.from_config(_cfg()).calculate(
            frame,
            term_structure=_curva(["op0"], _HAZARDS),
            as_of_date=_CORTE,
            events_by_period={1: 5, 2: 4, 3: 3},
            cycle=CycleInputs(model=_modelo(escenarios, b=0.6), history=None),
        )
        return float(resultado.detail["ecl_reported_unrounded"].sum())

    ponderada = _ecl({"base": (0.5, _BASE), "lejos": (0.5, lejos)})
    promediada = _ecl({"medio": (0.5, medio), "medio_2": (0.5, medio)})
    # El sentido depende de la curvatura (aquí, con riesgos altos, la pérdida es cóncava en δ);
    # lo que la guarda exige es que no sean la misma cifra.
    assert abs(ponderada - promediada) > 1e-3 * promediada, (ponderada, promediada)


def test_d_fir_1_la_ecl_por_escenario_reconcilia_sin_redondear() -> None:
    """§3.1: ``Σ_k w_k · ecl_reported_by_scenario[k]`` es la suma de la ECL sin redondear."""
    modelo = _modelo({"base": (0.7, _BASE), "adverso": (0.3, _ADVERSO)})
    frame = _cartera(
        otorgamiento=["2024-09-01", "2025-09-01"],
        vencimiento=["2028-06-01", "2027-06-01"],
        days_past_due=[0, 45],
    )
    resultado = IfrsProvisioningEngine.from_config(
        _cfg(ecl={"eir_col": "eir", "rounding": "integer_currency"})
    ).calculate(
        frame,
        term_structure=_curva(["op0", "op1"], _HAZARDS),
        as_of_date=_CORTE,
        events_by_period={1: 5, 2: 4, 3: 3},
        cycle=CycleInputs(model=modelo, history=None),
    )
    secciones = resultado.card.metric_sections
    por_escenario = secciones["ecl_reported_by_scenario"]
    total = float(resultado.detail["ecl_reported_unrounded"].sum())
    assert 0.7 * por_escenario["base"] + 0.3 * por_escenario["adverso"] == pytest.approx(
        total, rel=1e-12
    )
    assert min(por_escenario.values()) <= total <= max(por_escenario.values())
    # El puente de redondeo, aparte.
    assert float(resultado.card.total_ecl_reported) == pytest.approx(
        total + secciones["rounding"]["total_difference"], abs=1e-6
    )


# ───────────────────── D-FIR-2: la sensibilidad sobre la tasa de referencia ─────────────────────


def _historia_sintetica(b: float = 0.15, n: int = 80, semilla: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    fechas = pd.date_range("2005-01-01", periods=n, freq="QS")
    u = 7.0 + 2.0 * np.sin(np.arange(n) / 6.0) + rng.normal(0.0, 0.3, n)
    logit = -4.0 + b * (u - u.mean()) + rng.normal(0.0, 0.05, n)
    return pd.DataFrame({"date": fechas, "default_rate": 1 / (1 + np.exp(-logit)), "u": u})


def _trayectorias(desde: str = "2025-01-01", n: int = 8) -> dict[str, pd.DataFrame]:
    fechas = pd.date_range(desde, periods=n, freq="QS")
    return {
        "base": pd.DataFrame({"date": fechas, "u": np.full(n, 7.0)}),
        "adverso": pd.DataFrame({"date": fechas, "u": np.linspace(7.0, 10.0, n)}),
    }


def test_d_fir_2_el_satelite_recupera_la_sensibilidad_conocida() -> None:
    """§6-3: logit(tasa) = a + 0,15·(u - ū) + ruido; el MCO lo recupera dentro de su error."""
    historia = _historia_sintetica()
    modelo = build_cycle_model(
        historia,
        _trayectorias(),
        {"base": 0.6, "adverso": 0.4},
        time_col="date",
        reference_rate_col="default_rate",
        factor_cols=("u",),
    )
    assert abs(modelo.coefficients["u"] - 0.15) < 3 * modelo.std_errors["u"]
    assert modelo.long_run_means["u"] == pytest.approx(float(historia["u"].mean()))
    assert modelo.n_periods == 80 and modelo.history_frequency_months == 3


def test_d_fir_2_la_tasa_puede_faltar_al_principio_o_al_final_pero_no_en_medio() -> None:
    """§3.3/§4: sin la tasa en los extremos, la ventana es la de los períodos con tasa."""
    historia = _historia_sintetica()
    historia.loc[[0, 1, 79], "default_rate"] = np.nan
    modelo = build_cycle_model(
        historia,
        _trayectorias(),
        {"base": 0.6, "adverso": 0.4},
        time_col="date",
        reference_rate_col="default_rate",
        factor_cols=("u",),
    )
    assert modelo.n_periods == 77
    assert modelo.long_run_means["u"] == pytest.approx(float(historia["u"].iloc[2:79].mean()))
    assert len(modelo.history_start_months) == 80  # la macro de todas sigue para el ancla
    historia.loc[40, "default_rate"] = np.nan
    with pytest.raises(ForwardInputError, match="en medio"):
        build_cycle_model(
            historia,
            _trayectorias(),
            {"base": 0.6, "adverso": 0.4},
            time_col="date",
            reference_rate_col="default_rate",
            factor_cols=("u",),
        )


@pytest.mark.parametrize("valor", [0.0, 1.0, 2.3, -0.01])
def test_d_fir_2_la_tasa_va_como_fraccion_en_el_intervalo_abierto(valor: float) -> None:
    """§4: un 0,9 % va como 0,009; fuera de (0, 1) se detiene con la fila y la unidad."""
    historia = _historia_sintetica()
    historia.loc[10, "default_rate"] = valor
    with pytest.raises(ForwardInputError, match="0,009"):
        build_cycle_model(
            historia,
            _trayectorias(),
            {"base": 0.6, "adverso": 0.4},
            time_col="date",
            reference_rate_col="default_rate",
            factor_cols=("u",),
        )


# ─────────────────────────────── D-FIR-3: el ancla (§6-4) ───────────────────────────────


def _historia_anual() -> ForwardCycleModel:
    """Historia trimestral 2019T1…2021T4 con un valor distinto por trimestre (1, 2, …, 12)."""
    meses = [_q(a, t) for a in (2019, 2020, 2021) for t in (1, 2, 3, 4)]
    return _modelo(
        {"base": (0.5, _BASE), "adverso": (0.5, _ADVERSO)},
        historia=(meses, [float(i + 1) for i in range(12)]),
        largo_plazo=6.5,
        desde=_q(2021, 1),
    )


def test_d_fir_3_el_ancla_es_la_macro_de_los_meses_observados_de_la_curva() -> None:
    """Dos filas trimestrales: una otorgada el 1 de enero de 2020 con dos períodos (2020T1 y T2:
    valores 5 y 6) y otra el 1 de noviembre de 2020 con uno, observado sólo en noviembre y
    diciembre (2020T4: 8; enero cae después del corte del 31 de diciembre). Una tercera fila sin
    fecha no entra y se cuenta."""
    modelo = _historia_anual()
    origen = calendar_position(np.array(["2020-01-01", "2020-11-01", "NaT"], dtype="datetime64[D]"))
    historia = CurveHistory(
        origination=origen, duration_periods=np.array([2, 1, 3]), n_rows_without_date=1
    )
    primer_mes = first_future_month("2020-12-31")
    assert primer_mes == 2021 * 12  # enero de 2021
    ancla = cycle_anchor(modelo, historia, months_per_period=3.0, first_month=primer_mes)
    assert ancla.kind == "curve_history"
    assert ancla.values["u"] == pytest.approx((5.0 + 6.0 + 8.0) / 3)
    assert ancla.long_run_shift == pytest.approx(0.2 * (6.5 - (5.0 + 6.0 + 8.0) / 3))
    assert (ancla.person_periods_without_date, ancla.rows_without_date) == (3, 1)


def test_d_fir_3_sin_fechas_el_ancla_es_el_largo_plazo() -> None:
    modelo = _historia_anual()
    ancla = cycle_anchor(modelo, None, months_per_period=3.0, first_month=2021 * 12)
    assert ancla.kind == "long_run"
    assert ancla.values == ancla.long_run_values == {"u": 6.5}
    assert ancla.long_run_shift == 0.0


def test_d_fir_3_la_historia_que_no_cubre_la_curva_se_detiene_con_los_anios() -> None:
    modelo = _historia_anual()
    historia = CurveHistory(
        origination=calendar_position(np.array(["2018-04-01"], dtype="datetime64[D]")),
        duration_periods=np.array([2]),
        n_rows_without_date=0,
    )
    with pytest.raises(IfrsInputError, match="2018"):
        cycle_anchor(modelo, historia, months_per_period=3.0, first_month=2021 * 12)


def test_d_fir_3_tras_el_escenario_revierte_en_24_meses_hacia_el_largo_plazo() -> None:
    """§3.3: ``δ(m) = δ_LP + (δ_último - δ_LP)·max(0, 1 - e/24)`` mes a mes."""
    from bayesrisk.provisioning.ifrs9.cycle import CycleShifter

    modelo = _modelo({"base": (0.5, [9.0] * 4), "adverso": (0.5, [9.0] * 4)}, largo_plazo=6.0)
    ancla = cycle_anchor(modelo, None, months_per_period=1.0, first_month=_MES)
    corrimiento = CycleShifter(modelo, ancla, months_per_period=1.0, first_month=_MES)
    # El escenario cubre 2026T1…T4: hasta diciembre de 2026; marzo es el primer mes futuro.
    ultimo = 0.2 * (9.0 - 6.0)
    meses = np.arange(0.0, 40.0)
    deltas = corrimiento.deltas(meses, np.ones_like(meses))["base"]
    assert deltas[:10] == pytest.approx([ultimo] * 10)  # marzo a diciembre de 2026
    for e in (1, 12, 23, 24, 30):
        assert deltas[9 + e] == pytest.approx(ultimo * max(0.0, 1.0 - e / 24.0))


# ─────────────────────── D-FIR-4: los escenarios de la institución (§6-5) ───────────────────────


def _forward(**cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "input": {
            "macro_source": {
                "type": "path",
                "path": "h.csv",
                "time_col": "date",
                "variable_cols": ["u"],
            },
            "pd_basis_assumption": "ttc",
        },
        "satellite": {"mode": "reference_rate", "factor_cols": ["u"]},
        "macro": {"kind": "scenario_paths"},
        "scenarios": {
            "scenarios": [
                {"name": "base", "weight": 0.6, "macro_path_path": "b.csv"},
                {"name": "pesimista", "weight": 0.4, "macro_path_path": "p.csv"},
            ]
        },
    }
    base.update(cambios)
    return base


def test_d_fir_4_nombres_libres_y_al_menos_dos_escenarios() -> None:
    from bayesrisk.forward.config import ForwardConfig

    ForwardConfig.model_validate(_forward())  # sin base/adverse/severe: nombres libres
    uno = _forward(
        scenarios={"scenarios": [{"name": "base", "weight": 1.0, "macro_path_path": "b.csv"}]}
    )
    with pytest.raises(ForwardScenarioError, match="al menos dos"):
        ForwardConfig.model_validate(uno)


def test_d_fir_4_un_peso_cero_se_detiene() -> None:
    from bayesrisk.forward.config import ForwardConfig

    cero = _forward(
        scenarios={
            "scenarios": [
                {"name": "base", "weight": 1.0, "macro_path_path": "b.csv"},
                {"name": "pesimista", "weight": 0.0, "macro_path_path": "p.csv"},
            ]
        }
    )
    with pytest.raises(ForwardScenarioError, match="pesan cero"):
        ForwardConfig.model_validate(cero)


def test_d_fir_4_la_tasa_y_las_trayectorias_van_juntas() -> None:
    from bayesrisk.forward.config import ForwardConfig
    from bayesrisk.forward.exceptions import ForwardConfigError

    with pytest.raises(ForwardConfigError, match="van juntos"):
        ForwardConfig.model_validate(_forward(macro={"kind": "arima"}))


def test_d_fir_4_los_escenarios_cubren_los_12_meses_posteriores_al_corte() -> None:
    justo = _modelo({"base": (0.5, [6.0] * 5), "adverso": (0.5, [7.0] * 5)})
    check_scenario_coverage(justo, first_month=_MES)  # 2026T1…2027T1: de marzo a febrero, sí
    corto = _modelo({"base": (0.5, [6.0] * 4), "adverso": (0.5, [7.0] * 4)})
    with pytest.raises(IfrsInputError, match="12 meses"):  # hasta diciembre: no alcanza
        check_scenario_coverage(corto, first_month=_MES)
    tarde = _modelo({"base": (0.5, [6.0] * 8), "adverso": (0.5, [7.0] * 8)}, desde=_q(2026, 2))
    with pytest.raises(IfrsInputError, match="primer mes posterior al corte"):
        check_scenario_coverage(tarde, first_month=_MES)


def test_d_fir_4_tablas_con_huecos_o_frecuencia_irregular_se_detienen() -> None:
    historia = _historia_sintetica().drop(index=30)
    with pytest.raises(ForwardInputError, match="huecos"):
        build_cycle_model(
            historia,
            _trayectorias(),
            {"base": 0.6, "adverso": 0.4},
            time_col="date",
            reference_rate_col="default_rate",
            factor_cols=("u",),
        )
    distintos = _trayectorias()
    distintos["adverso"] = distintos["adverso"].iloc[:-1]
    with pytest.raises(ForwardScenarioError, match="mismos períodos"):
        build_cycle_model(
            _historia_sintetica(),
            distintos,
            {"base": 0.6, "adverso": 0.4},
            time_col="date",
            reference_rate_col="default_rate",
            factor_cols=("u",),
        )


def test_d_fir_4_frecuencias_de_historia_y_escenarios_independientes() -> None:
    """Pasada 2 de Codex: historia trimestral y escenarios mensuales (o al revés) corren."""
    fechas = pd.date_range("2025-01-01", periods=24, freq="MS")
    mensuales = {
        "base": pd.DataFrame({"date": fechas, "u": np.full(24, 7.0)}),
        "adverso": pd.DataFrame({"date": fechas, "u": np.linspace(7.0, 9.0, 24)}),
    }
    modelo = build_cycle_model(
        _historia_sintetica(),
        mensuales,
        {"base": 0.5, "adverso": 0.5},
        time_col="date",
        reference_rate_col="default_rate",
        factor_cols=("u",),
    )
    assert modelo.history_frequency_months == 3
    assert {e.frequency_months for e in modelo.scenarios} == {1}


# ─────────────────────── D-FIR-5: `fit` contra la edad se detiene (§6-6) ───────────────────────


def test_d_fir_5_el_satelite_fit_sobre_la_curva_de_survival_se_detiene() -> None:
    from bayesrisk.forward.config import ForwardConfig
    from bayesrisk.forward.exceptions import SatelliteModelError
    from bayesrisk.forward.satellite import SatelliteModel

    cfg = ForwardConfig.model_validate(
        {
            "input": {
                "macro_source": {"type": "path", "path": "m.csv", "variable_cols": ["u"]},
                "pd_basis_assumption": "ttc",
            },
            "satellite": {"mode": "fit", "factor_cols": ["u"], "min_history_periods": 3},
            "fail_on_falta_dato": False,
        }
    )
    curva = _curva(["op0", "op1"], _HAZARDS)
    curva["method"] = "discrete_hazard"
    curva["pd_source"] = "survival"
    # Una serie que casa con el `period` de la curva: sin la guarda, el ajuste correría en silencio
    # contra la edad (lo que medía §1.1 de la enmienda).
    macro = pd.DataFrame({"period": [1, 2, 3, 4, 5], "u": [4.0, 5.5, 5.0, 7.0, 6.0]})
    with pytest.raises(SatelliteModelError, match="EDAD"):
        SatelliteModel.from_config(cfg).fit(curva, macro)


# ───────────────────── D-FIR-6: Vasicek sobre el riesgo del período (§6-7) ─────────────────────


def test_d_fir_6_vasicek_transforma_el_riesgo_y_la_pd_de_vida_no_pasa_de_uno() -> None:
    from scipy.stats import norm

    hazards = [0.30, 0.50, 0.70]
    curva = _curva(["op0"], hazards)
    curva["z"] = -1.5
    cfg = _cfg(
        origination_date_col=None,
        maturity_date_col=None,
        pd=IfrsPdConfig(
            term_structure_source="survival",
            base_pd_source="term_structure",
            pit_mode="apply_vasicek",
            rho=0.15,
            systemic_factor_col="z",
            horizon_12m_periods=1,
        ),
        scenarios=IfrsScenarioConfig(source="single"),
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(as_of_date=[_CORTE]), term_structure=curva, as_of_date=_CORTE
    )
    marginal = resultado.ecl_term_structure.sort_values("period")["pd_marginal"].to_numpy()
    sobrevive, esperado = 1.0, []
    for h in hazards:
        pit = float(norm.cdf((norm.ppf(h) - math.sqrt(0.15) * -1.5) / math.sqrt(0.85)))
        esperado.append(sobrevive * pit)
        sobrevive *= 1.0 - pit
    assert marginal == pytest.approx(esperado, abs=1e-12)
    assert float(marginal.sum()) <= 1.0
    assert float(resultado.detail["pd_life"].iloc[0]) <= 1.0


# ───────────────── Sin escenarios, nada del ciclo (§6-10; la cifra, en evidencia) ─────────────────


def test_sin_escenarios_la_provision_no_publica_nada_del_ciclo() -> None:
    """Sin ``pit_mode='cycle'`` la corrida publica exactamente lo de antes: ni el desplazamiento
    en la curva consumida, ni secciones del ciclo en la card, ni la tabla por período."""
    cfg = _cfg(
        pd=IfrsPdConfig(
            term_structure_source="survival",
            base_pd_source="term_structure",
            pit_mode="ttc_only",
            horizon_12m_periods=1,
        ),
        scenarios=IfrsScenarioConfig(source="single"),
    )
    motor = IfrsProvisioningEngine.from_config(cfg)
    resultado = motor.calculate(
        _cartera(otorgamiento=["2024-09-01"], vencimiento=["2027-06-01"]),
        term_structure=_curva(["op0"], _HAZARDS),
        as_of_date=_CORTE,
        events_by_period={1: 5, 2: 4, 3: 3},
    )
    assert "cycle_shift" not in resultado.ecl_term_structure.columns
    assert "scenario_weight" not in resultado.ecl_term_structure.columns
    assert not {"cycle", "ecl_reported_by_scenario", "ecl_reported_ttc"} & set(
        resultado.card.metric_sections
    )
    assert motor.cycle_by_period_ is None
    assert list(resultado.ecl_term_structure["scenario"].unique()) == ["base"]
