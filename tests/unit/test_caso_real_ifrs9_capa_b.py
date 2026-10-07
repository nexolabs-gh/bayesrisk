"""El caso real de IFRS 9, capa B (enmienda CASO-REAL-IFRS9, D-CRE-2 y D-CRE-3).

- **D-CRE-2 (§3.2).** Con la fecha de otorgamiento y/o la de vencimiento, la provisión lee la curva
  de PD desde la **edad** de cada operación —fraccionaria, en períodos de la curva, con riesgo
  constante dentro de cada período— y la corta en su **vencimiento** (IFRS 9 5.5.19; Stage 1 con
  el menor entre 12 meses y la vida, B5.5.43). Una operación vencida con saldo tiene un período.
  Más allá del último período con incumplimientos observados, el riesgo de cada operación se
  extiende con la media de sus tres últimos períodos con incumplimientos (§8-6).
- **D-CRE-3 (§3.3).** Con la cuota del contrato, la exposición de cada período es el saldo al
  inicio del período en la tabla de cuota fija que paga el saldo de hoy justo al vencimiento, con la
  tasa **implícita** (no la EIR). Si la cuota no alcanza (``c·n < B``), la EAD queda constante y se
  cuenta.

Las cifras de §3.2 y §3.3 con el motor sobre Lending Club y Freddie Mac son evidencia fuera de CI
(``evidencia/s35/medir_capa_b.py``); aquí, los casos a mano que fijan cada regla.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest

from bayesrisk.provisioning.ifrs9 import IfrsProvisioningConfig, IfrsProvisioningEngine
from bayesrisk.provisioning.ifrs9.config import (
    IfrsEadConfig,
    IfrsLgdConfig,
    IfrsPdConfig,
    IfrsScenarioConfig,
    IfrsStagingConfig,
)
from bayesrisk.provisioning.ifrs9.exceptions import IfrsConfigError, IfrsInputError
from bayesrisk.provisioning.ifrs9.results import IfrsProvisionResult

_CORTE = "2026-03-01"


def _cfg(**cambios: Any) -> IfrsProvisioningConfig:
    """Curva de survival leída tal cual (TTC), EAD y LGD entregadas, fechas declaradas."""
    base: dict[str, Any] = {
        "row_id_col": None,
        "portfolio_col": "portfolio",
        "origination_date_col": "otorgamiento",
        "maturity_date_col": "vencimiento",
        "pd": IfrsPdConfig(
            term_structure_source="survival",
            base_pd_source="term_structure",
            pit_mode="ttc_only",
            horizon_12m_periods=1,
        ),
        "lgd": IfrsLgdConfig(method="provided"),
        "ead": IfrsEadConfig(method="provided"),
        "scenarios": IfrsScenarioConfig(source="single"),
        "staging": IfrsStagingConfig(),
    }
    base.update(cambios)
    return IfrsProvisioningConfig(**base)


def _curva(row_ids: list[str], hazards: list[float], *, unidad: str = "year") -> pd.DataFrame:
    """La curva de ``discrete_hazard``: el mismo riesgo por período para cada operación."""
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
        "eir": [0.10] * n,
        "days_past_due": [0] * n,
        "is_default": [False] * n,
        "as_of_date": [_CORTE] * n,
    }
    base.update(columnas)
    return pd.DataFrame(base, index=pd.Index([f"op{i}" for i in range(n)], name="loan_id"))


def _calcular(
    frame: pd.DataFrame,
    curva: pd.DataFrame,
    cfg: IfrsProvisioningConfig | None = None,
    eventos: dict[int, int] | None = None,
) -> IfrsProvisionResult:
    return IfrsProvisioningEngine.from_config(cfg or _cfg()).calculate(
        frame,
        term_structure=curva,
        as_of_date=_CORTE,
        events_by_period=eventos if eventos is not None else {1: 5, 2: 4, 3: 3},
    )


def _s(hazards: list[float], x: float, cola: float | None = None) -> float:
    """Supervivencia por tramos, escrita a mano: riesgo constante dentro de cada período."""

    def h(k: int) -> float:
        return hazards[k - 1] if k <= len(hazards) else float(cola if cola is not None else 0.0)

    entero = math.floor(x)
    s = 1.0
    for k in range(1, entero + 1):
        s *= 1.0 - h(k)
    return s * (1.0 - h(entero + 1)) ** (x - entero)


# ─────────────────────────── D-CRE-2: el caso a mano de §6-3 ───────────────────────────

_HAZARDS = [0.10, 0.20, 0.30]


def test_curva_de_tres_periodos_edad_1_5_y_vida_1_25() -> None:
    """§6-3: la PD de cada tramo [A + t - 1, A + min(t, L)] condicionada a sobrevivir hasta A."""
    frame = _cartera(
        days_past_due=[0, 45],  # una en Stage 1 y otra en Stage 2
        otorgamiento=["2024-09-01", "2024-09-01"],  # 18 meses: 1,5 años
        vencimiento=["2027-06-01", "2027-06-01"],  # 15 meses: 1,25 años
    )
    resultado = _calcular(frame, _curva(list(frame.index), _HAZARDS))

    s_a = _s(_HAZARDS, 1.5)
    pd1 = (_s(_HAZARDS, 1.5) - _s(_HAZARDS, 2.5)) / s_a
    pd2 = (_s(_HAZARDS, 2.5) - _s(_HAZARDS, 2.75)) / s_a
    tramo = resultado.ecl_term_structure.set_index("row_id").loc["op1"]
    assert tramo["period"].tolist() == [1, 2]
    assert tramo["curve_start"].tolist() == pytest.approx([1.5, 2.5])
    assert tramo["curve_end"].tolist() == pytest.approx([2.5, 2.75])
    assert tramo["pd_marginal"].tolist() == pytest.approx([pd1, pd2], rel=1e-12)

    detalle = resultado.detail.set_index("row_id")
    assert detalle.loc["op0", "age_periods"] == pytest.approx(1.5)
    assert detalle.loc["op0", "life_periods"] == pytest.approx(1.25)
    # Stage 1: el menor entre 12 meses (un período) y la vida (1,25): sólo el primer tramo.
    assert detalle.loc["op0", "ecl_reported_unrounded"] == pytest.approx(
        pd1 * 0.5 * 1_000.0 / 1.10, rel=1e-12
    )
    # Stage 2: la vida entera, cada tramo descontado al final de su período.
    assert detalle.loc["op1", "ecl_reported_unrounded"] == pytest.approx(
        (pd1 / 1.10 + pd2 / 1.10**2) * 0.5 * 1_000.0, rel=1e-12
    )
    # La PD de por vida que publica la provisión es la condicionada.
    assert detalle.loc["op1", "pd_life"] == pytest.approx(pd1 + pd2, rel=1e-12)
    card = resultado.card
    assert card.contract_dates is True
    assert card.tail_from_period == 4
    assert card.ead_beyond_observed_curve == 0.0
    assert card.n_matured_with_balance == 0


def test_con_edad_cero_y_la_vida_de_la_curva_reproduce_la_cifra_de_hoy() -> None:
    """§3.2-2: con A = 0 y L = la curva (sin vencimiento), es la provisión de siempre."""
    frame = _cartera(days_past_due=[0, 45], otorgamiento=[_CORTE, _CORTE])
    curva = _curva(list(frame.index), _HAZARDS)
    con_fecha = _calcular(frame, curva, _cfg(maturity_date_col=None))
    sin_fechas = _calcular(frame, curva, _cfg(origination_date_col=None, maturity_date_col=None))
    assert con_fecha.card.total_ecl_reported == pytest.approx(
        sin_fechas.card.total_ecl_reported, rel=1e-12
    )
    assert sin_fechas.card.contract_dates is False
    assert "age_periods" not in sin_fechas.detail.columns
    assert "curve_start" not in sin_fechas.ecl_term_structure.columns


def test_vencida_con_saldo_tiene_un_periodo_y_se_cuenta() -> None:
    """§3.2-4: el vencimiento ya pasó y queda saldo: sigue expuesta un período."""
    frame = _cartera(
        days_past_due=[45],
        otorgamiento=["2022-03-01"],
        vencimiento=["2025-09-01"],
    )
    resultado = _calcular(frame, _curva(list(frame.index), _HAZARDS))
    assert resultado.detail["life_periods"].tolist() == [1.0]
    assert resultado.ecl_term_structure["period"].tolist() == [1]
    assert resultado.card.n_matured_with_balance == 1


def test_el_tope_de_vida_corta_la_vida_contractual() -> None:
    frame = _cartera(days_past_due=[45], otorgamiento=[_CORTE], vencimiento=["2029-03-01"])
    cfg = _cfg(
        pd=IfrsPdConfig(
            term_structure_source="survival",
            base_pd_source="term_structure",
            pit_mode="ttc_only",
            horizon_12m_periods=1,
            max_lifetime_periods=2,
        )
    )
    resultado = _calcular(frame, _curva(list(frame.index), _HAZARDS), cfg)
    assert resultado.detail["life_periods"].tolist() == [2.0]


def test_sin_otorgamiento_la_curva_se_lee_desde_el_periodo_1() -> None:
    frame = _cartera(days_past_due=[45], vencimiento=["2027-09-01"])
    resultado = _calcular(
        frame, _curva(list(frame.index), _HAZARDS), _cfg(origination_date_col=None)
    )
    tramo = resultado.ecl_term_structure
    assert tramo["curve_start"].tolist() == pytest.approx([0.0, 1.0])
    assert tramo["curve_end"].tolist() == pytest.approx([1.0, 1.5])
    assert resultado.detail["age_periods"].tolist() == [0.0]


# ─────────────────────────── D-CRE-2: la cola (§8-6) ───────────────────────────


def test_mas_alla_del_ultimo_periodo_con_incumplimientos_la_cola_es_la_media_de_tres() -> None:
    """§6-4: el período 4 no tiene incumplimientos; desde ahí, la media de los tres anteriores."""
    hazards = [0.10, 0.20, 0.30, 0.05]
    frame = _cartera(
        days_past_due=[45],
        otorgamiento=["2022-09-01"],  # 42 meses: 3,5 años
        vencimiento=["2028-03-01"],  # 24 meses: 2 años
    )
    resultado = _calcular(
        frame, _curva(list(frame.index), hazards), eventos={1: 5, 2: 4, 3: 3, 4: 0}
    )
    cola = (0.10 + 0.20 + 0.30) / 3
    s_a = _s(hazards[:3], 3.5, cola)
    esperado = [
        (_s(hazards[:3], 3.5, cola) - _s(hazards[:3], 4.5, cola)) / s_a,
        (_s(hazards[:3], 4.5, cola) - _s(hazards[:3], 5.5, cola)) / s_a,
    ]
    assert resultado.ecl_term_structure["pd_marginal"].tolist() == pytest.approx(
        esperado, rel=1e-12
    )
    assert esperado == pytest.approx([cola, (1 - cola) * cola], rel=1e-12)
    card = resultado.card
    assert card.tail_from_period == 4
    assert card.ead_beyond_observed_curve == pytest.approx(1_000.0)


def test_con_menos_de_tres_periodos_con_incumplimientos_la_media_de_los_que_haya() -> None:
    # Edad 1 y vida 2: los tramos [1, 2] y [2, 3], los dos en la cola.
    frame = _cartera(days_past_due=[45], otorgamiento=["2025-03-01"], vencimiento=["2028-03-01"])
    resultado = _calcular(frame, _curva(list(frame.index), _HAZARDS), eventos={1: 5, 2: 0, 3: 0})
    # Desde el período 2 el riesgo es el del período 1 (el único con incumplimientos).
    assert resultado.ecl_term_structure["pd_marginal"].tolist() == pytest.approx(
        [0.10, 0.90 * 0.10], rel=1e-12
    )
    assert resultado.card.tail_from_period == 2


def test_sin_fechas_la_curva_no_se_extiende() -> None:
    """La cola sólo aplica con alguna de las dos hojas: sin ellas, la curva publicada tal cual."""
    frame = _cartera(days_past_due=[45])
    resultado = _calcular(
        frame,
        _curva(list(frame.index), [0.10, 0.20, 0.30, 0.05]),
        _cfg(origination_date_col=None, maturity_date_col=None),
        eventos={1: 5, 2: 4, 3: 3, 4: 0},
    )
    assert resultado.ecl_term_structure["pd_marginal"].tolist()[-1] == pytest.approx(
        0.9 * 0.8 * 0.7 * 0.05
    )
    assert resultado.card.tail_from_period is None


# ─────────────────────────── D-CRE-2: entradas (§4) ───────────────────────────


@pytest.mark.parametrize(
    ("columna", "valor", "mensaje"),
    [
        ("otorgamiento", "31/12/2024", "otorgamiento"),
        ("otorgamiento", "2026-06-01", "posterior a la fecha de corte"),
        ("vencimiento", "2023-01-01", "anterior a su otorgamiento"),
    ],
)
def test_una_fecha_invalida_se_nombra_con_su_columna_y_su_fila(
    columna: str, valor: str, mensaje: str
) -> None:
    frame = _cartera(
        days_past_due=[0, 0],
        otorgamiento=["2024-09-01", "2024-09-01"],
        vencimiento=["2027-06-01", "2027-06-01"],
    )
    frame.loc["op1", columna] = valor
    with pytest.raises(IfrsInputError, match=mensaje) as error:
        _calcular(frame, _curva(list(frame.index), _HAZARDS))
    assert "op1" in str(error.value)


def test_una_fecha_vacia_es_sin_fecha_para_esa_fila() -> None:
    frame = _cartera(
        days_past_due=[45, 45],
        otorgamiento=["2024-09-01", None],
        vencimiento=["2027-06-01", None],
    )
    resultado = _calcular(frame, _curva(list(frame.index), _HAZARDS))
    detalle = resultado.detail.set_index("row_id")
    assert detalle.loc["op1", "age_periods"] == 0.0
    assert detalle.loc["op1", "life_periods"] == 3.0


def test_una_fecha_invalida_en_una_fila_sin_exposicion_no_se_valida() -> None:
    """§4 y D-CRE-5: las fechas se validan sólo en las operaciones con exposición."""
    frame = _cartera(
        ead=[1_000.0, 0.0],
        otorgamiento=["2024-09-01", "no es fecha"],
        vencimiento=["2027-06-01", "2020-01-01"],
    )
    resultado = _calcular(frame, _curva(list(frame.index), _HAZARDS))
    assert resultado.card.n_rows == 1


@pytest.mark.parametrize(
    "cambios",
    [
        {"pd": IfrsPdConfig(term_structure_source="markov", pit_mode="ttc_only")},
        {
            "pd": IfrsPdConfig(
                term_structure_source="survival", base_pd_source="calibration", pit_mode="ttc_only"
            )
        },
    ],
)
def test_por_codigo_la_lectura_desde_la_edad_exige_la_curva_de_survival(
    cambios: dict[str, Any],
) -> None:
    """§3.2-7 sin preflight: el motor también se detiene, con la causa en palabras."""
    frame = _cartera(days_past_due=[0], otorgamiento=["2024-09-01"], vencimiento=["2027-06-01"])
    with pytest.raises(IfrsConfigError, match="edad"):
        IfrsProvisioningEngine.from_config(_cfg(**cambios)).calculate(
            frame,
            term_structure=_curva(list(frame.index), _HAZARDS),
            calibrated_pd=pd.DataFrame({"pd_calibrated": [0.01]}, index=["op0"]),
            as_of_date=_CORTE,
            events_by_period={1: 5, 2: 4, 3: 3},
        )


def test_por_codigo_sin_los_incumplimientos_por_periodo_se_detiene() -> None:
    frame = _cartera(days_past_due=[0], otorgamiento=["2024-09-01"], vencimiento=["2027-06-01"])
    with pytest.raises(IfrsConfigError, match="incumplimientos por período"):
        IfrsProvisioningEngine.from_config(_cfg()).calculate(
            frame, term_structure=_curva(list(frame.index), _HAZARDS), as_of_date=_CORTE
        )


def test_una_curva_sin_unidad_reconocida_no_admite_fechas() -> None:
    frame = _cartera(days_past_due=[0], otorgamiento=["2024-09-01"], vencimiento=["2027-06-01"])
    with pytest.raises(IfrsConfigError, match="unidad"):
        _calcular(frame, _curva(list(frame.index), _HAZARDS, unidad="period"))


# ─────────────────────────── D-CRE-3: la tabla de pagos (§3.3) ───────────────────────────

_TASA_CONTRATO = 0.01  # mensual
_SALDO = 10_000.0
_MESES = 24


def _anualidad(saldo: float, i: float, n: float) -> float:
    return saldo * i / (1.0 - (1.0 + i) ** (-n))


def _saldo(saldo: float, cuota: float, i: float, k: float) -> float:
    return saldo * (1.0 + i) ** k - cuota * ((1.0 + i) ** k - 1.0) / i


def _con_cuota(cuotas: list[float], **extra: Any) -> IfrsProvisionResult:
    n = len(cuotas)
    frame = _cartera(
        ead=[_SALDO] * n,
        eir=[0.20] * n,  # la EIR NO es la tasa del contrato (pasada 2 de Codex)
        days_past_due=[45] * n,
        vencimiento=["2028-03-01"] * n,  # 24 meses
        cuota=cuotas,
        **extra,
    )
    cfg = _cfg(
        origination_date_col=None,
        ead=IfrsEadConfig(method="provided", installment_col="cuota"),
        pd=IfrsPdConfig(
            term_structure_source="survival",
            base_pd_source="term_structure",
            pit_mode="ttc_only",
            horizon_12m_periods=4,
        ),
    )
    curva = _curva(list(frame.index), [0.02] * 8, unidad="quarter")
    return _calcular(frame, curva, cfg, eventos={p: 3 for p in range(1, 9)})


def test_la_ead_sigue_la_tabla_con_la_tasa_implicita_de_la_cuota() -> None:
    """§6-6: la tabla contra la fórmula cerrada; la tasa implícita reproduce la del contrato."""
    cuota = _anualidad(_SALDO, _TASA_CONTRATO, _MESES)
    resultado = _con_cuota([cuota])
    tabla = resultado.ecl_term_structure
    # Trimestral: el período t empieza en el mes 3(t - 1).
    esperado = [_saldo(_SALDO, cuota, _TASA_CONTRATO, 3 * (t - 1)) for t in range(1, 9)]
    assert tabla["ead"].tolist() == pytest.approx(esperado, rel=1e-9)
    card = resultado.card
    assert (card.n_amortizing, card.n_installment_not_amortizing) == (1, 0)
    assert "FALTA-DATO-IFRS-4" not in card.falta_dato


def test_una_cuota_de_solo_intereses_deja_la_ead_constante_y_se_cuenta() -> None:
    cuota = _SALDO * _TASA_CONTRATO  # c·n = 0,24·B < B: no paga el saldo en el plazo
    resultado = _con_cuota([cuota])
    assert set(resultado.ecl_term_structure["ead"]) == {_SALDO}
    card = resultado.card
    assert (card.n_amortizing, card.n_installment_not_amortizing) == (0, 1)
    assert card.ead_installment_not_amortizing == pytest.approx(_SALDO)
    assert "FALTA-DATO-IFRS-4" in card.falta_dato


def test_con_tasa_implicita_cero_la_tabla_resta_la_cuota() -> None:
    cuota = _SALDO / _MESES
    tabla = _con_cuota([cuota]).ecl_term_structure
    assert tabla["ead"].tolist() == pytest.approx(
        [_SALDO - cuota * 3 * (t - 1) for t in range(1, 9)], rel=1e-9
    )


def test_una_fila_sin_cuota_conserva_la_ead_constante() -> None:
    cuota = _anualidad(_SALDO, _TASA_CONTRATO, _MESES)
    resultado = _con_cuota([cuota, np.nan])
    tabla = resultado.ecl_term_structure.set_index("row_id")
    assert set(tabla.loc["op1", "ead"]) == {_SALDO}
    assert tabla.loc["op0", "ead"].iloc[-1] < _SALDO
    assert resultado.card.n_amortizing == 1
    assert "FALTA-DATO-IFRS-4" in resultado.card.falta_dato
    avisos = resultado.detail.set_index("row_id")["warning_codes"]
    assert "FALTA-DATO-IFRS-4" not in avisos["op0"]
    assert "FALTA-DATO-IFRS-4" in avisos["op1"]


def test_con_vencimiento_y_sin_cuota_la_ead_no_amortiza() -> None:
    """§6-5: la amortización la activa la cuota, no el vencimiento (pasada 1 de Codex)."""
    frame = _cartera(ead=[_SALDO], days_past_due=[45], vencimiento=["2028-03-01"])
    trimestral = IfrsPdConfig(
        term_structure_source="survival",
        base_pd_source="term_structure",
        pit_mode="ttc_only",
        horizon_12m_periods=4,
    )
    resultado = _calcular(
        frame,
        _curva(list(frame.index), [0.02] * 8, unidad="quarter"),
        _cfg(origination_date_col=None, pd=trimestral),
        eventos={p: 3 for p in range(1, 9)},
    )
    assert set(resultado.ecl_term_structure["ead"]) == {_SALDO}
    assert "FALTA-DATO-IFRS-4" in resultado.card.falta_dato


def test_una_cuota_negativa_se_nombra() -> None:
    with pytest.raises(IfrsInputError, match="cuota"):
        _con_cuota([-5.0])


# ─────────────────────────── requisitos por contexto (§3.2-7, §3.3) ───────────────────────────


def _requisitos(**cambios: Any) -> list[Any]:
    import bayesrisk
    from bayesrisk.core.config import BayesRiskConfig
    from bayesrisk.core.config.schema import cargar_configs_de_dominio
    from bayesrisk.ui.presets import ifrs9_preset

    cargar_configs_de_dominio()
    cfg = ifrs9_preset()["config"]
    ifrs = cfg["provisioning_ifrs9"]
    ifrs["origination_date_col"] = "fecha_originacion"
    ifrs["maturity_date_col"] = "fecha_vencimiento"
    for ruta, valor in cambios.items():
        nodo = cfg
        *camino, hoja = ruta.split(".")
        for parte in camino:
            nodo = nodo[parte]
        nodo[hoja] = valor
    columnas = ["loan_id", "as_of_date", "portfolio", "ead", "lgd", "eir", "days_past_due"]
    columnas += ["is_default", "duration", "event", "utilizacion_linea", "deuda_ingreso"]
    columnas += ["antiguedad_meses", "target", "fecha_originacion", "fecha_vencimiento", "cuota"]
    resultado = bayesrisk.check_dataset(BayesRiskConfig.model_validate(cfg), columnas)
    return [m for m in resultado.mismatches if m.kind == "unmet_requirement"]


def test_fechas_y_cuota_sobre_la_curva_de_survival_no_avisan() -> None:
    assert _requisitos(**{"provisioning_ifrs9.ead.installment_col": "cuota"}) == []


@pytest.mark.parametrize(
    ("ruta", "valor", "anclada"),
    [
        ("provisioning_ifrs9.pd.base_pd_source", "calibration", "origination_date_col"),
        ("survival.method", "cox_ph", "origination_date_col"),
    ],
)
def test_las_fechas_fuera_de_la_curva_por_periodos_se_detienen_antes_de_correr(
    ruta: str, valor: str, anclada: str
) -> None:
    avisos = [a for a in _requisitos(**{ruta: valor}) if a.path.endswith(anclada)]
    assert len(avisos) == 1, avisos
    assert "edad" in avisos[0].message


@pytest.mark.parametrize(
    "cambios",
    [
        {"provisioning_ifrs9.maturity_date_col": None},
        {"provisioning_ifrs9.ead.method": "ccf"},
    ],
)
def test_la_cuota_exige_vencimiento_y_la_ead_entregada(cambios: dict[str, Any]) -> None:
    avisos = _requisitos(**{"provisioning_ifrs9.ead.installment_col": "cuota", **cambios})
    assert [a.path for a in avisos if a.path.endswith("installment_col")] == [
        "provisioning_ifrs9.ead.installment_col"
    ]


def test_con_fechas_el_paso_requiere_la_card_de_la_curva() -> None:
    from bayesrisk.provisioning.ifrs9.step import IfrsProvisioningStep

    assert ("survival", "card") in IfrsProvisioningStep(_cfg()).requires
    sin = _cfg(origination_date_col=None, maturity_date_col=None)
    assert ("survival", "card") not in IfrsProvisioningStep(sin).requires


# ─────────────────────────── la puerta guiada (§3.8) ───────────────────────────


@pytest.fixture(scope="module")
def paquete_con_contrato(tmp_path_factory: pytest.TempPathFactory) -> pd.DataFrame:
    """La cartera del paquete con tres columnas del contrato: la puerta sólo las arma."""
    from bayesrisk.ui import datasets

    ruta = datasets.materialize("ifrs9_retail_latam", workdir=tmp_path_factory.mktemp("datos"))
    cartera = pd.read_parquet(ruta)
    cartera["otorgamiento"] = "2023-06-30"
    cartera["vencimiento"] = "2027-06-30"
    cartera["cuota"] = 100.0
    return cartera


def _ecl(datos: pd.DataFrame, run_dir: Any, **cambios: Any) -> Any:
    from bayesrisk.guided import Ecl

    argumentos: dict[str, Any] = {
        "data": datos,
        "id": "loan_id",
        "as_of": "as_of_date",
        "portfolio": "portfolio",
        "exposure": "ead",
        "lgd": "lgd",
        "rate": "eir",
        "days_past_due": "days_past_due",
        "default": "is_default",
        "duration": "duration",
        "event": "event",
        "period": "year",
        "horizon": 5,
        "run_dir": run_dir,
    }
    argumentos.update(cambios)
    return Ecl(**argumentos)


def test_la_puerta_escribe_las_tres_hojas_del_contrato(
    paquete_con_contrato: pd.DataFrame, tmp_path: Any
) -> None:
    ecl = _ecl(
        paquete_con_contrato,
        tmp_path,
        origination="otorgamiento",
        maturity="vencimiento",
        installment="cuota",
    )
    ifrs = ecl.config.provisioning_ifrs9
    assert (ifrs.origination_date_col, ifrs.maturity_date_col, ifrs.ead.installment_col) == (
        "otorgamiento",
        "vencimiento",
        "cuota",
    )
    sin = _ecl(paquete_con_contrato, tmp_path, name="sin_contrato").config.provisioning_ifrs9
    assert (sin.origination_date_col, sin.maturity_date_col, sin.ead.installment_col) == (
        None,
        None,
        None,
    )


def test_la_cuota_sin_vencimiento_se_detiene_antes_de_correr(
    paquete_con_contrato: pd.DataFrame, tmp_path: Any
) -> None:
    from bayesrisk.guided import EclInputError

    with pytest.raises(EclInputError, match="maturity="):
        _ecl(paquete_con_contrato, tmp_path, installment="cuota")


def test_una_columna_del_contrato_que_no_esta_se_nombra(
    paquete_con_contrato: pd.DataFrame, tmp_path: Any
) -> None:
    from bayesrisk.guided import EclInputError

    with pytest.raises(EclInputError, match="fecha_inexistente"):
        _ecl(paquete_con_contrato, tmp_path, origination="fecha_inexistente")


# ─────────────────────────── los resúmenes y el informe (§13) ───────────────────────────


def _estudio_con_contrato(card: dict[str, Any], **cambios: Any) -> Any:
    from test_guided_summaries_cartera import _COLUMNAS_F4, _estudio

    rutas = {
        "provisioning_ifrs9.origination_date_col": "otorgamiento",
        "provisioning_ifrs9.maturity_date_col": "vencimiento",
        **cambios,
    }
    base = {
        "contract_dates": True,
        "n_rows": 10,
        "total_ead": 1_000.0,
        "tail_from_period": 11,
        "ead_beyond_observed_curve": 400.0,
        "falta_dato": ("FALTA-DATO-IFRS-4",),
    }
    base.update(card)
    return _estudio(rutas, base, _COLUMNAS_F4)


def _resumenes(study: Any) -> tuple[Any, Any]:
    from bayesrisk.guided.summaries import SummaryContext, _resumen_provision, build_final_summary

    contexto = SummaryContext(project_dir=None, run_dir=None, source_label="x", partition_label="")
    provision = _resumen_provision(study, contexto)
    return provision, build_final_summary(study, (provision,), contexto)


def test_los_supuestos_dicen_la_lectura_por_contrato_y_la_cola() -> None:
    provision, final = _resumenes(_estudio_con_contrato({}))
    supuestos = "\n".join(final.assumptions)
    assert "antigüedad de cada operación" in supuestos
    assert "vencimiento contractual (IFRS 9 5.5.19)" in supuestos
    assert "Más allá del período 10 de la curva" in supuestos
    assert "desde el corte" in supuestos and "B5.5.43" in supuestos
    assert any(linea.startswith("Con las fechas del contrato") for linea in provision.lines)
    (cola,) = [a for a in final.review if "más allá del período 10" in a]
    assert cola.startswith("Provisión IFRS 9: 40,00 % de la exposición (400)"), cola


def test_que_revisar_cuenta_las_vencidas_y_las_cuotas_que_no_alcanzan() -> None:
    study = _estudio_con_contrato(
        {
            "n_matured_with_balance": 2,
            "ead_matured_with_balance": 150.0,
            "n_amortizing": 7,
            "n_installment_not_amortizing": 3,
            "ead_installment_not_amortizing": 250.0,
        },
        **{"provisioning_ifrs9.ead.installment_col": "cuota"},
    )
    provision, final = _resumenes(study)
    revisar = "\n".join(final.review)
    assert "2 operaciones vencidas con saldo (exposición 150)" in revisar
    assert "3 operaciones tienen una cuota que no paga el saldo al vencimiento" in revisar
    assert "(exposición 250)" in revisar
    tabla = [linea for linea in provision.lines if "tabla de pagos" in linea]
    assert tabla == [
        "En 7 de 10 operaciones, la exposición sigue la tabla de pagos de la cuota del contrato "
        "hasta el vencimiento, con la tasa implícita en la cuota; en las demás queda constante "
        "(sin cuota, o con una cuota que no paga el saldo al vencimiento)"
    ]
    assert not any("dataset no trae" in linea for linea in final.assumptions)


def test_sin_fechas_los_resumenes_hablan_como_antes() -> None:
    from test_guided_summaries_cartera import _COLUMNAS_F4, _estudio

    provision, final = _resumenes(
        _estudio({}, {"n_rows": 2, "falta_dato": ("FALTA-DATO-IFRS-4",)}, _COLUMNAS_F4)
    )
    todo = "\n".join((*provision.lines, *final.assumptions, *final.review))
    assert "contrato" not in todo and "más allá del período" not in todo
    assert "Los 12 meses del Stage 1 son el primer período de la curva" in todo


def _capitulo_ifrs9(contract_dates: bool) -> str:
    from datetime import UTC, datetime

    from bayesrisk.core.lineage import LineageBundle
    from bayesrisk.report import prose
    from bayesrisk.report.results import ReportInputBundle

    lineage = LineageBundle(
        git_sha="abc123",
        git_dirty=False,
        data_hash="d" * 16,
        config_hash="c" * 16,
        root_seed=42,
        uv_lock_hash="uv123",
        library_versions={"bayesrisk": "0.1.0"},
        determinism_caveats=[],
        created_at=datetime(2026, 10, 6, tzinfo=UTC),
        schema_version="1.0.0",
    )
    card: dict[str, Any] = {"term_structure_source": "survival", "pit_mode": "ttc_only"}
    parametros: dict[str, Any] = {"ecl": {"stage3_direct": True}}
    if contract_dates:
        card |= {"contract_dates": True, "tail_from_period": 11, "ead_beyond_observed_curve": 9.0}
        parametros |= {
            "origination_date_col": "otorgamiento",
            "maturity_date_col": "vencimiento",
            "ead": {"installment_col": "cuota"},
        }
    bundle = ReportInputBundle(
        lineage=lineage,
        cards={"provisioning_ifrs9": card, "survival": {"n_rows": 10}},
        tables={},
        figures={},
        sections=(),
        pipeline_params={"provisioning_ifrs9": parametros},
    )
    partes = (*prose._results_survival(bundle), *prose._results_provisioning_ifrs9(bundle))
    return " ".join(partes)


def test_el_informe_dice_que_la_curva_no_se_uso_tal_cual_con_las_fechas() -> None:
    """§3.2-8: la lectura condicionada no es «tal cual», y la prosa dice cómo se leyó."""
    con = _capitulo_ifrs9(True)
    assert "no usa esta curva tal cual" in con
    assert "parte de esta curva tal cual" not in con
    assert "antigüedad de cada operación" in con and "vencimiento contractual" in con
    assert "Más allá del período 10 de la curva" in con and "tabla de pagos" in con
    sin = _capitulo_ifrs9(False)
    assert "parte de esta curva tal cual" in sin
    assert "antigüedad" not in sin


def test_el_copy_de_la_lectura_por_contrato_no_filtra_identificadores() -> None:
    """§6-10: lo que lee una persona —resúmenes e informe— no nombra hojas, campos ni códigos."""
    from bayesrisk.core.markers import DECLARED_MARKERS

    study = _estudio_con_contrato(
        {
            "n_matured_with_balance": 2,
            "ead_matured_with_balance": 150.0,
            "n_amortizing": 7,
            "n_installment_not_amortizing": 3,
            "ead_installment_not_amortizing": 250.0,
        },
        **{"provisioning_ifrs9.ead.installment_col": "cuota"},
    )
    provision, final = _resumenes(study)
    texto = "\n".join(
        (
            *provision.lines,
            *provision.alerts,
            *final.assumptions,
            *final.review,
            _capitulo_ifrs9(True),
        )
    )
    assert "Más allá del período" in texto  # el gate no es vacuo: el copy nuevo está aquí
    prohibidos = (
        "contract_dates",
        "tail_from_period",
        "ead_beyond_observed_curve",
        "matured_with_balance",
        "n_amortizing",
        "installment",
        "origination_date",
        "maturity_date",
        "curve_start",
        "curve_end",
        "age_periods",
        "life_periods",
        "events_by_period",
        "D-CRE",
        *DECLARED_MARKERS,
    )
    for identificador in prohibidos:
        assert identificador not in texto, identificador


def test_un_riesgo_de_uno_no_rompe_la_lectura_por_tramos() -> None:
    """Un período con riesgo 1 deja la supervivencia en cero: sin avisos de NumPy y con la PD
    que corresponde (filterwarnings=error convertiría el aviso en una corrida caída)."""
    hazards = [0.2, 1.0, 0.5]
    frame = _cartera(
        days_past_due=[45, 45],
        otorgamiento=["2025-09-01", "2023-09-01"],  # 6 meses (0,5) y 30 meses (2,5)
        vencimiento=["2028-03-01", "2028-03-01"],  # 24 meses: 2 años
    )
    resultado = _calcular(frame, _curva(list(frame.index), hazards))
    tramos = resultado.ecl_term_structure.set_index("row_id")
    # Desde 0,5: incumple con certeza en el tramo que cruza el período 2.
    assert tramos.loc["op0", "pd_marginal"].tolist() == pytest.approx([1.0, 0.0])
    # Desde 2,5 la supervivencia ya es cero: no hay a quién condicionar, y la PD queda en cero.
    assert tramos.loc["op1", "pd_marginal"].tolist() == [0.0, 0.0]
