"""IFRS 9 firmable, capa B (enmienda IFRS9-FIRMABLE, D-FIR-7…9).

- **D-FIR-7 (§3.7).** Con la PD a 12 meses de hoy del modelo (``pd.pd_12m_col``), la curva de cada
  operación se desplaza en logit por ``s_i`` tal que la PD de los 12 meses posteriores al corte
  —desde su edad, sin cortar por el vencimiento— sea la del modelo; todos sus tramos usan
  ``logit h + s_i`` y, con escenarios, ``δ_k(t)`` encima. Reconciliación con alerta sobre 25 %.
- **D-FIR-8 (§3.8).** Con la PD a 12 meses al otorgar (``staging.origination_pd_12m_col``), el SICR
  compara la PD de hoy de esos 12 meses —ponderada por escenario— con lo que se esperaba al otorgar
  para el mismo tramo de vida: la curva anclada a la PD de origen en la edad 0, leída en
  ``[A, A + 12 meses]``.
- **D-FIR-9 (§3.9).** «Supuestos» dice el método de la LGD también cuando no es la del archivo.

Las cifras de §3.7 y §3.8 con el motor sobre el paquete, Lending Club y Freddie Mac son evidencia
fuera de CI (``evidencia/s38/``); aquí, los casos a mano que fijan cada regla.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest
from test_ifrs9_firmable_capa_a import _ADVERSO, _BASE, _CORTE, _cartera, _cfg, _curva, _modelo

from bayesrisk.provisioning.ifrs9 import IfrsProvisioningConfig, IfrsProvisioningEngine
from bayesrisk.provisioning.ifrs9.config import IfrsPdConfig, IfrsScenarioConfig
from bayesrisk.provisioning.ifrs9.cycle import CycleInputs
from bayesrisk.provisioning.ifrs9.exceptions import (
    IfrsConfigError,
    IfrsInputError,
    IfrsTermStructureError,
)


def _sigma(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float) -> float:
    return math.log(p) - math.log1p(-p)


def _biseccion(f: Any, objetivo: float) -> float:
    """El ``s`` con que ``f(s) = objetivo`` (``f`` creciente), por bisección independiente."""
    bajo, alto = -50.0, 50.0
    for _ in range(200):
        medio = (bajo + alto) / 2.0
        if f(medio) > objetivo:
            alto = medio
        else:
            bajo = medio
    return (bajo + alto) / 2.0


def _pd_cfg(**cambios: Any) -> IfrsPdConfig:
    base: dict[str, Any] = {
        "term_structure_source": "survival",
        "base_pd_source": "term_structure",
        "pit_mode": "ttc_only",
        "horizon_12m_periods": 1,
        "pd_12m_col": "pd_modelo",
    }
    base.update(cambios)
    return IfrsPdConfig(**base)


def _cfg_b(**cambios: Any) -> IfrsProvisioningConfig:
    """La provisión de la capa A sin escenarios (``ttc_only``) y con la PD del modelo."""
    base: dict[str, Any] = {"pd": _pd_cfg(), "scenarios": IfrsScenarioConfig(source="single")}
    base.update(cambios)
    return _cfg(**base)


_HAZARDS = [0.10, 0.20, 0.30]
_EVENTOS = {1: 5, 2: 4, 3: 3}


# ─────────────────────── D-FIR-7: la PD del modelo ancla la curva (§6-8) ───────────────────────


def test_d_fir_7_la_pd_de_12_meses_anclada_es_la_del_modelo_desde_su_edad() -> None:
    """§6-8: curva anual de tres períodos, edad 1,5; la PD del modelo es 0,25.

    Los 12 meses posteriores al corte cruzan la mitad del período 2 y la mitad del 3: ``s`` es el
    que hace ``1 - √(1 - sigmoide(logit 0,2 + s)) · √(1 - sigmoide(logit 0,3 + s)) = 0,25``. El
    tramo siguiente usa el mismo ``s`` sobre la mitad del período 3 y la mitad de la cola (la media
    de los tres).
    """
    frame = _cartera(otorgamiento=["2024-09-01"], vencimiento=["2029-03-01"], pd_modelo=[0.25])
    resultado = IfrsProvisioningEngine.from_config(_cfg_b()).calculate(
        frame,
        term_structure=_curva(["op0"], _HAZARDS),
        as_of_date=_CORTE,
        events_by_period=_EVENTOS,
    )

    def _ventana(s: float) -> float:
        return 1.0 - math.sqrt(1 - _sigma(_logit(0.2) + s)) * math.sqrt(1 - _sigma(_logit(0.3) + s))

    s = _biseccion(_ventana, 0.25)
    detalle = resultado.detail.set_index("row_id")
    assert detalle.loc["op0", "pd_12m"] == pytest.approx(0.25, abs=1e-12)
    assert detalle.loc["op0", "pd_12m_model"] == 0.25
    ts = resultado.ecl_term_structure.set_index("period")
    cola = (0.1 + 0.2 + 0.3) / 3
    segundo = 0.75 * (
        1.0 - math.sqrt(1 - _sigma(_logit(0.3) + s)) * math.sqrt(1 - _sigma(_logit(cola) + s))
    )
    assert ts.loc[1, "pd_marginal"] == pytest.approx(0.25, abs=1e-12)
    assert ts.loc[2, "pd_marginal"] == pytest.approx(segundo, abs=1e-12)
    seccion = resultado.card.metric_sections["pd_model_anchor"]
    assert seccion["n_rows_anchored"] == 1
    assert seccion["pd_curve_mean"] == pytest.approx(_ventana(0.0), abs=1e-12)


def test_d_fir_7_sin_fechas_el_desplazamiento_es_el_logit_y_vale_para_toda_la_vida() -> None:
    """Sin fechas cada operación lee su curva desde el período 1: con la curva anual, ``s`` es
    ``logit(PD) - logit(h_1)`` y la PD de por vida usa el mismo ``s`` (el oráculo del paquete)."""
    cfg = _cfg_b(origination_date_col=None, maturity_date_col=None)
    frame = _cartera(pd_modelo=[0.15, 0.04])
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        frame, term_structure=_curva(["op0", "op1"], [0.10, 0.20]), as_of_date=_CORTE
    )
    detalle = resultado.detail.set_index("row_id")
    for rid, p in (("op0", 0.15), ("op1", 0.04)):
        s = _logit(p) - _logit(0.10)
        vida = 1.0 - (1.0 - p) * (1.0 - _sigma(_logit(0.20) + s))
        assert detalle.loc[rid, "pd_12m"] == pytest.approx(p, abs=1e-12)
        assert detalle.loc[rid, "pd_life"] == pytest.approx(vida, abs=1e-12)


def test_d_fir_7_con_escenarios_el_desplazamiento_va_encima_del_anclaje() -> None:
    """§3.7: ``logit h + s_i + δ_k(t)``; la TTC (desplazamiento cero) conserva el anclaje."""
    modelo = _modelo({"base": (0.6, _BASE), "adverso": (0.4, _ADVERSO)})
    cfg = _cfg(pd=_pd_cfg(pit_mode="cycle"))
    frame = _cartera(otorgamiento=["2024-09-01"], vencimiento=["2029-03-01"], pd_modelo=[0.25])
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        frame,
        term_structure=_curva(["op0"], _HAZARDS),
        as_of_date=_CORTE,
        events_by_period=_EVENTOS,
        cycle=CycleInputs(model=modelo, history=None),
    )

    def _ventana(s: float) -> float:
        return 1.0 - math.sqrt(1 - _sigma(_logit(0.2) + s)) * math.sqrt(1 - _sigma(_logit(0.3) + s))

    s = _biseccion(_ventana, 0.25)
    ts = resultado.ecl_term_structure.set_index(["scenario", "period"])
    for nombre, serie in (("base", _BASE), ("adverso", _ADVERSO)):
        x1 = (1 * serie[0] + 3 * serie[1] + 3 * serie[2] + 3 * serie[3] + 2 * serie[4]) / 12
        d1 = 0.2 * (x1 - 6.0)
        assert ts.loc[(nombre, 1), "pd_marginal"] == pytest.approx(_ventana(s + d1), abs=1e-12)
    secciones = resultado.card.metric_sections
    # La ECL de desplazamiento cero es la de la curva anclada: Stage 1, el primer tramo, 0,25.
    assert secciones["ecl_reported_ttc"] == pytest.approx(0.25 * 0.5 * 1_000.0, abs=1e-9)


def test_d_fir_7_la_reconciliacion_alerta_sobre_25_por_ciento() -> None:
    """§3.7: la media de la PD del modelo frente a la de la curva, ponderadas por la exposición."""
    from bayesrisk.guided.summaries import _lineas_de_la_pd_del_modelo

    cfg = _cfg_b(origination_date_col=None, maturity_date_col=None)
    curva = _curva(["op0", "op1"], [0.10, 0.20])
    for pds, alerta in (([0.20, 0.20], True), ([0.11, 0.12], False)):
        resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
            _cartera(pd_modelo=pds, ead=[1_000.0, 3_000.0]), term_structure=curva, as_of_date=_CORTE
        )
        seccion = resultado.card.metric_sections["pd_model_anchor"]
        media = (pds[0] * 1_000.0 + pds[1] * 3_000.0) / 4_000.0
        assert seccion["pd_model_mean"] == pytest.approx(media, abs=1e-12)
        assert seccion["pd_curve_mean"] == pytest.approx(0.10, abs=1e-12)
        lineas, alertas = _lineas_de_la_pd_del_modelo(resultado.card.model_dump())
        assert any(ln.startswith("PD a 12 meses de tu modelo en 2 de 2") for ln in lineas), lineas
        assert any("difieren" in a for a in alertas) is alerta, alertas


def test_d_fir_7_una_fila_vacia_usa_la_curva_sin_anclar_y_una_pd_de_borde_se_acota() -> None:
    """§3.7 y §5: sin PD, la curva tal cual (bit a bit); 0 o 1, acotada a [1e-9, 1 - 1e-9]."""
    cfg = _cfg_b(origination_date_col=None, maturity_date_col=None)
    curva = _curva(["op0", "op1", "op2"], [0.10, 0.20])
    con = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(pd_modelo=[np.nan, 0.0, 1.0]), term_structure=curva, as_of_date=_CORTE
    )
    sin = IfrsProvisioningEngine.from_config(
        _cfg_b(origination_date_col=None, maturity_date_col=None, pd=_pd_cfg(pd_12m_col=None))
    ).calculate(_cartera(pd_modelo=[np.nan, 0.0, 1.0]), term_structure=curva, as_of_date=_CORTE)
    a = con.ecl_term_structure.set_index(["row_id", "period"])["pd_marginal"]
    b = sin.ecl_term_structure.set_index(["row_id", "period"])["pd_marginal"]
    assert a.loc["op0"].tolist() == b.loc["op0"].tolist()
    detalle = con.detail.set_index("row_id")
    assert detalle.loc["op1", "pd_12m"] == pytest.approx(1e-9, rel=1e-6)
    assert detalle.loc["op2", "pd_12m"] == pytest.approx(1.0 - 1e-9, abs=1e-12)
    seccion = con.card.metric_sections["pd_model_anchor"]
    assert (seccion["n_rows_anchored"], seccion["n_rows_without_pd"]) == (2, 1)
    assert seccion["n_rows_clipped"] == 2
    assert seccion["ead_without_pd"] == 1_000.0


def test_d_fir_7_un_riesgo_en_el_borde_se_cuenta() -> None:
    """§3.7: un período de la ventana con riesgo 0 queda decidido por el acotamiento: se cuenta."""
    cfg = _cfg_b(origination_date_col=None, maturity_date_col=None)
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(pd_modelo=[0.10]), term_structure=_curva(["op0"], [0.0, 0.2]), as_of_date=_CORTE
    )
    assert resultado.card.metric_sections["pd_model_anchor"]["n_rows_at_risk_bound"] == 1
    assert resultado.detail["pd_12m"].iloc[0] == pytest.approx(0.10, abs=1e-12)


def test_d_fir_7_un_valor_que_no_es_numero_se_detiene_con_la_operacion() -> None:
    cfg = _cfg_b(origination_date_col=None, maturity_date_col=None)
    with pytest.raises(IfrsInputError, match=r"«pd_modelo».*'op1'"):
        IfrsProvisioningEngine.from_config(cfg).calculate(
            _cartera(pd_modelo=[0.1, "alto"]),
            term_structure=_curva(["op0", "op1"], [0.10, 0.20]),
            as_of_date=_CORTE,
        )


# ─────────── D-FIR-8: el SICR por tramo de vida, con el escenario en la razón (§6-9) ───────────

#: Una curva anual cuyo riesgo BAJA con la edad: a los cuatro años, el riesgo es la décima parte del
#: del primer año. Comparar la PD de hoy con la de origen sin el tramo escondería un deterioro.
_DECRECIENTE = [0.20, 0.10, 0.05, 0.03, 0.02, 0.02]
_EVENTOS_DEC = {p: 5 for p in range(1, 7)}


def test_d_fir_8_compara_con_lo_esperado_al_otorgar_para_el_mismo_tramo() -> None:
    """§6-9: edad 4 años; la PD de origen 0,20 es la de la curva en la edad 0 (``s = 0``), así que
    lo esperado para los 12 meses de hoy es el riesgo del quinto año, 0,02. Con la PD de hoy 0,05,
    la razón es 2,5 y pasa a Stage 2; con 0,03, 1,5 y se queda. Sin el tramo, 0,05 frente a 0,20 se
    leería como una mejora."""
    cfg = _cfg_b(
        staging=_cfg_b().staging.model_copy(update={"origination_pd_12m_col": "pd_origen"})
    )
    frame = _cartera(
        otorgamiento=["2022-03-01", "2022-03-01"],
        vencimiento=["2032-03-01", "2032-03-01"],
        pd_modelo=[0.05, 0.03],
        pd_origen=[0.20, 0.20],
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        frame,
        term_structure=_curva(["op0", "op1"], _DECRECIENTE),
        as_of_date=_CORTE,
        events_by_period=_EVENTOS_DEC,
    )
    detalle = resultado.detail.set_index("row_id")
    assert detalle.loc["op0", "pd_12m_origination_expected"] == pytest.approx(0.02, abs=1e-12)
    assert detalle.loc["op0", "sicr_pd_ratio_12m"] == pytest.approx(2.5, abs=1e-9)
    assert detalle.loc["op1", "sicr_pd_ratio_12m"] == pytest.approx(1.5, abs=1e-9)
    staging = resultado.staging.set_index("row_id")
    assert staging.loc["op0", "stage"] == 2
    assert staging.loc["op0", "sicr_triggers"] == ("sicr_pd_origination_12m",)
    assert staging.loc["op1", "stage"] == 1
    seccion = resultado.card.metric_sections["sicr_origination_12m"]
    assert (seccion["n_rows_evaluated"], seccion["n_rows_moved_to_stage2"]) == (2, 1)
    assert seccion["with_scenarios"] is False


def test_d_fir_8_con_escenarios_la_razon_usa_la_pd_ponderada() -> None:
    """§3.8 y §8-4: con escenarios, el numerador es la PD de los 12 meses ponderada por escenario
    con el desplazamiento de su tramo de calendario encima del anclaje. 0,035 frente a 0,02 es
    1,75 sin escenarios; con el adverso de peso 0,5, llega a 2 y pasa a Stage 2."""
    modelo = _modelo({"base": (0.5, _BASE), "adverso": (0.5, _ADVERSO)})
    base = _cfg_b(pd=_pd_cfg(pit_mode="cycle"), scenarios=IfrsScenarioConfig(source="forward"))
    cfg = base.model_copy(
        update={"staging": base.staging.model_copy(update={"origination_pd_12m_col": "pd_origen"})}
    )
    frame = _cartera(
        otorgamiento=["2022-03-01"],
        vencimiento=["2032-03-01"],
        pd_modelo=[0.035],
        pd_origen=[0.20],
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        frame,
        term_structure=_curva(["op0"], _DECRECIENTE),
        as_of_date=_CORTE,
        events_by_period=_EVENTOS_DEC,
        cycle=CycleInputs(model=modelo, history=None),
    )
    ponderada = 0.0
    for serie in (_BASE, _ADVERSO):
        x1 = (1 * serie[0] + 3 * serie[1] + 3 * serie[2] + 3 * serie[3] + 2 * serie[4]) / 12
        ponderada += 0.5 * _sigma(_logit(0.035) + 0.2 * (x1 - 6.0))
    detalle = resultado.detail.set_index("row_id")
    assert detalle.loc["op0", "sicr_pd_ratio_12m"] == pytest.approx(ponderada / 0.02, abs=1e-9)
    assert ponderada / 0.02 >= 2.0 > 0.035 / 0.02
    assert resultado.staging.set_index("row_id").loc["op0", "stage"] == 2
    assert resultado.card.metric_sections["sicr_origination_12m"]["with_scenarios"] is True


def test_d_fir_8_sin_pd_de_origen_no_se_compara_y_se_cuenta() -> None:
    cfg = _cfg_b(
        staging=_cfg_b().staging.model_copy(update={"origination_pd_12m_col": "pd_origen"})
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(
            otorgamiento=["2022-03-01"],
            vencimiento=["2032-03-01"],
            pd_modelo=[0.05],
            pd_origen=[np.nan],
        ),
        term_structure=_curva(["op0"], _DECRECIENTE),
        as_of_date=_CORTE,
        events_by_period=_EVENTOS_DEC,
    )
    seccion = resultado.card.metric_sections["sicr_origination_12m"]
    assert (seccion["n_rows_evaluated"], seccion["n_rows_without_origination_pd"]) == (0, 1)
    assert math.isnan(resultado.detail["sicr_pd_ratio_12m"].iloc[0])
    assert resultado.staging["stage"].iloc[0] == 1


# ─────────────────────────────── Requisitos, puerta y bit a bit ───────────────────────────────


@pytest.mark.parametrize(
    ("cambios", "ruta"),
    [
        ({"pd": _pd_cfg(term_structure_source="markov")}, "pd.pd_12m_col"),
        ({"pd": _pd_cfg(base_pd_source="calibration")}, "pd.pd_12m_col"),
        (
            {"pd": _pd_cfg(pit_mode="apply_vasicek", rho=0.1, systemic_factor_col="z")},
            "pd.pd_12m_col",
        ),
        ({"pd": _pd_cfg(pd_12m_col=None), "_origen": True}, "staging.origination_pd_12m_col"),
        ({"origination_date_col": None, "_origen": True}, "staging.origination_pd_12m_col"),
    ],
)
def test_requisitos_de_las_dos_pd_del_modelo(cambios: dict[str, Any], ruta: str) -> None:
    """§3.7 y §3.8: el preflight avisa antes de correr y el motor se detiene igual."""
    cambios = dict(cambios)
    origen = cambios.pop("_origen", False)
    cfg = _cfg_b(**cambios)
    if origen:
        cfg = cfg.model_copy(
            update={"staging": cfg.staging.model_copy(update={"origination_pd_12m_col": "o"})}
        )
    assert ruta in {r.path for r in cfg.requisitos_incumplidos(None)}
    with pytest.raises(IfrsConfigError):
        IfrsProvisioningEngine.from_config(cfg).calculate(
            _cartera(
                pd_modelo=[0.1], o=[0.1], otorgamiento=["2024-09-01"], vencimiento=["2029-03-01"]
            ),
            term_structure=_curva(["op0"], _HAZARDS),
            as_of_date=_CORTE,
            events_by_period=_EVENTOS,
        )


def test_sin_las_columnas_la_provision_no_publica_nada_del_modelo() -> None:
    """§6-10 de la capa B: sin las dos PD, ni columnas ni secciones nuevas (la de la 2.8.0)."""
    cfg = _cfg_b(pd=_pd_cfg(pd_12m_col=None))
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(otorgamiento=["2024-09-01"], vencimiento=["2029-03-01"]),
        term_structure=_curva(["op0"], _HAZARDS),
        as_of_date=_CORTE,
        events_by_period=_EVENTOS,
    )
    assert "pd_12m_model" not in resultado.detail.columns
    assert "sicr_pd_ratio_12m" not in resultado.detail.columns
    assert "pd_model_anchor" not in resultado.card.metric_sections
    assert "sicr_origination_12m" not in resultado.card.metric_sections


def test_la_puerta_escribe_las_dos_hojas_y_exige_lo_que_corresponde(tmp_path: Any) -> None:
    from bayesrisk.guided import Ecl
    from bayesrisk.guided.ecl import EclInputError
    from bayesrisk.ui.datasets import materialize

    datos = pd.read_parquet(materialize("ifrs9_retail_latam", workdir=tmp_path / "datos"))
    datos["pd_hoy"] = 0.05
    datos["pd_origen"] = 0.04
    datos["otorgamiento"] = "2023-01-01"
    argumentos: dict[str, Any] = dict(
        as_of="as_of_date",
        portfolio="portfolio",
        exposure="ead",
        lgd="lgd",
        rate="eir",
        days_past_due="days_past_due",
        duration="duration",
        event="event",
        period="year",
        horizon=5,
        run_dir=tmp_path / "corridas",
    )
    cfg = Ecl(
        datos, pd="pd_hoy", origination_pd="pd_origen", origination="otorgamiento", **argumentos
    ).config
    assert cfg.provisioning_ifrs9.pd.pd_12m_col == "pd_hoy"
    assert cfg.provisioning_ifrs9.staging.origination_pd_12m_col == "pd_origen"
    with pytest.raises(EclInputError, match="necesita pd="):
        Ecl(datos, origination_pd="pd_origen", origination="otorgamiento", name="b", **argumentos)
    with pytest.raises(EclInputError, match="necesita origination="):
        Ecl(datos, pd="pd_hoy", origination_pd="pd_origen", name="c", **argumentos)
    with pytest.raises(EclInputError, match="no trae la columna pd_falta"):
        Ecl(datos, pd="pd_falta", name="d", **argumentos)


# ─────────────────────────── D-FIR-9: la LGD en «Supuestos» (§3.9) ───────────────────────────


@pytest.mark.parametrize(
    ("metodo", "supuesto", "alerta"),
    [
        ("provided", "La LGD es la del archivo de cartera", False),
        ("fractional_response", "regresión de respuesta fraccional sobre 2 covariables", True),
        ("beta_regression", "regresión beta sobre 2 covariables", True),
    ],
)
def test_d_fir_9_supuestos_dice_el_metodo_de_la_lgd(
    metodo: str, supuesto: str, alerta: bool
) -> None:
    from bayesrisk.guided.summaries import _alertas_de_la_lgd, _supuesto_de_la_lgd
    from bayesrisk.provisioning.ifrs9.config import IfrsLgdConfig

    cfg = _cfg_b(lgd=IfrsLgdConfig(method=metodo, covariate_cols=["a", "b"]))
    assert any(supuesto in s for s in _supuesto_de_la_lgd(cfg)), _supuesto_de_la_lgd(cfg)
    alertas = _alertas_de_la_lgd(cfg)
    assert bool(alertas) is alerta
    if alerta:
        assert "cartera viva" in alertas[0]


def test_d_fir_9_supuestos_dice_la_lgd_de_recuperacion() -> None:
    from bayesrisk.guided.summaries import _supuesto_de_la_lgd
    from bayesrisk.provisioning.ifrs9.config import IfrsLgdConfig

    cfg = _cfg_b(lgd=IfrsLgdConfig(method="workout", recovery_col="recupero"))
    (linea,) = _supuesto_de_la_lgd(cfg)
    assert "recuperación" in linea and "tasa efectiva" in linea


# ──────────────────────────── Textos de ayuda que la enmienda corrige ────────────────────────────


def test_las_ayudas_de_base_pd_source_y_de_la_pd_de_vida_de_origen() -> None:
    """§0-5 y §0-7: la PD a 12 meses de la calibración no decide la etapa; la de vida de origen,
    con las fechas, compara contra la vida que le queda y no por tramo."""
    from bayesrisk.ui.jobs import abanico_de

    preguntas = [
        p
        for p in abanico_de(["provisioning_ifrs9"])
        if p.get("path") == "provisioning_ifrs9.pd.base_pd_source"
    ]
    assert preguntas, "la pregunta de base_pd_source desapareció del trabajo"
    for pregunta in preguntas:
        assert "decide en qué etapa" not in pregunta["help"]
        assert "pérdida" in pregunta["help"]
    from bayesrisk.provisioning.ifrs9.config import IfrsStagingConfig

    ayuda = IfrsStagingConfig.model_fields["origination_pd_life_col"].json_schema_extra
    assert isinstance(ayuda, dict)
    assert "no es por tramo" in str(ayuda["ui_help"])


# ─────────────────────────────── Pasada 1 de Codex sobre el código ───────────────────────────────


def _curva_mensual(row_ids: list[str], hazards: list[float]) -> pd.DataFrame:
    curva = _curva(row_ids, hazards, unidad="month")
    return curva


def test_codex_p1_sin_fechas_el_tope_de_vida_no_recorta_la_ventana_del_anclaje() -> None:
    """Pasada 1 (high): con ``max_lifetime_periods`` menor que los 12 meses, el anclaje se resolvía
    sobre la curva ya recortada y concentraba la PD anual en seis meses (ECL 60 en vez de 30,96).
    Se ancla sobre la curva entera y el tope recorta después la pérdida."""
    cfg = _cfg_b(
        origination_date_col=None,
        maturity_date_col=None,
        pd=_pd_cfg(horizon_12m_periods=12, max_lifetime_periods=6),
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(pd_modelo=[0.12]),
        term_structure=_curva_mensual(["op0"], [0.02] * 24),
        as_of_date=_CORTE,
    )
    mensual = 1.0 - 0.88 ** (1.0 / 12.0)
    esperada = (1.0 - (1.0 - mensual) ** 6) * 0.5 * 1_000.0
    assert resultado.card.total_ecl_reported == pytest.approx(esperada, abs=1e-9)


def test_codex_p1_la_razon_en_el_umbral_exacto_dispara_el_gatillo() -> None:
    """Pasada 1 (high): curva plana de riesgo 0,10, PD de origen 0,05 y de hoy 0,10: la razón es 2
    exacta y el umbral es inclusivo; reconstruida por bisección daba 1,9999999999999998."""
    cfg = _cfg_b(
        staging=_cfg_b().staging.model_copy(update={"origination_pd_12m_col": "pd_origen"})
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(
            otorgamiento=["2025-03-01"],
            vencimiento=["2029-03-01"],
            pd_modelo=[0.10],
            pd_origen=[0.05],
        ),
        term_structure=_curva(["op0"], [0.10] * 6),
        as_of_date=_CORTE,
        events_by_period={p: 5 for p in range(1, 7)},
    )
    assert resultado.detail["sicr_pd_ratio_12m"].iloc[0] == pytest.approx(2.0, abs=1e-12)
    assert resultado.staging["stage"].iloc[0] == 2


def test_codex_p1_una_pd_que_el_intervalo_no_alcanza_se_cuenta() -> None:
    """Pasada 1 (medium): con la lectura por contrato y doce riesgos mensuales de 1, la PD de la
    ventana en ``s = -50`` sigue sobre 1e-9: el intervalo de §3.7 no encierra la raíz. La operación
    queda en el extremo y se cuenta, en vez de publicarse como anclada a su PD."""
    cfg = _cfg_b(pd=_pd_cfg(horizon_12m_periods=12))
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(
            otorgamiento=["2026-02-01", "2026-02-01"],
            vencimiento=["2028-03-01", "2028-03-01"],
            pd_modelo=[1e-9, 0.10],
        ),
        term_structure=_curva_mensual(["op0", "op1"], [1.0] * 24),
        as_of_date=_CORTE,
        events_by_period={p: 5 for p in range(1, 25)},
    )
    seccion = resultado.card.metric_sections["pd_model_anchor"]
    assert seccion["n_rows_not_reached"] == 1
    assert seccion["n_rows_at_risk_bound"] == 2
    from bayesrisk.guided.summaries import _lineas_de_la_pd_del_modelo

    _lineas, alertas = _lineas_de_la_pd_del_modelo(resultado.card.model_dump())
    assert any("no alcanza" in a for a in alertas), alertas


def test_codex_p2_sin_fechas_una_curva_mas_corta_que_12_meses_no_se_ancla() -> None:
    """Pasada 2 (high): sin fechas, con una curva de seis meses, la ventana del anclaje se quedaba
    en su soporte y la PD anual del modelo cabía entera en seis meses (ECL 60). La curva no dice
    nada del riesgo más allá: la corrida se detiene y dice cómo cubrir los 12 meses."""
    cfg = _cfg_b(
        origination_date_col=None,
        maturity_date_col=None,
        pd=_pd_cfg(horizon_12m_periods=12),
    )
    with pytest.raises(IfrsTermStructureError, match="12 meses"):
        IfrsProvisioningEngine.from_config(cfg).calculate(
            _cartera(pd_modelo=[0.12]),
            term_structure=_curva_mensual(["op0"], [0.02] * 6),
            as_of_date=_CORTE,
        )
    # Sin la PD del modelo, la curva corta sigue corriendo como antes (su vida es su soporte).
    sin = IfrsProvisioningEngine.from_config(
        _cfg_b(
            origination_date_col=None,
            maturity_date_col=None,
            pd=_pd_cfg(horizon_12m_periods=12, pd_12m_col=None),
        )
    ).calculate(
        _cartera(pd_modelo=[0.12]),
        term_structure=_curva_mensual(["op0"], [0.02] * 6),
        as_of_date=_CORTE,
    )
    assert sin.card.n_rows == 1


def test_codex_p2_la_puerta_avisa_antes_de_correr_con_una_curva_corta(tmp_path: Any) -> None:
    from bayesrisk.guided import Ecl
    from bayesrisk.guided.ecl import EclInputError
    from bayesrisk.ui.datasets import materialize

    datos = pd.read_parquet(materialize("ifrs9_retail_latam", workdir=tmp_path / "datos"))
    datos["pd_hoy"] = 0.05
    with pytest.raises(EclInputError, match="12 meses"):
        Ecl(
            datos,
            as_of="as_of_date",
            portfolio="portfolio",
            exposure="ead",
            lgd="lgd",
            rate="eir",
            days_past_due="days_past_due",
            duration="duration",
            event="event",
            period="month",
            horizon=6,
            pd="pd_hoy",
            run_dir=tmp_path / "corridas",
        )


def test_codex_p3_con_escenarios_la_razon_en_el_umbral_no_pierde_precision() -> None:
    """Pasada 3 (high): con escenarios, el numerador se reconstruía restando supervivencias y, con
    PD muy chicas, una razón de 2 exacta salía 1,99999999: la operación se quedaba en Stage 1."""
    plano = [6.0] * 8
    modelo = _modelo({"base": (0.5, plano), "adverso": (0.5, plano)})
    base = _cfg_b(
        pd=_pd_cfg(pit_mode="cycle", horizon_12m_periods=12),
        scenarios=IfrsScenarioConfig(source="forward"),
    )
    cfg = base.model_copy(
        update={"staging": base.staging.model_copy(update={"origination_pd_12m_col": "pd_origen"})}
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(
            otorgamiento=["2025-03-01"],
            vencimiento=["2028-03-01"],
            pd_modelo=[1e-7],
            pd_origen=[5e-8],
        ),
        term_structure=_curva_mensual(["op0"], [1e-8] * 24 + [0.1] * 12),
        as_of_date=_CORTE,
        events_by_period={p: 5 for p in range(1, 37)},
        cycle=CycleInputs(model=modelo, history=None),
    )
    assert resultado.detail["sicr_pd_ratio_12m"].iloc[0] == pytest.approx(2.0, rel=1e-12)
    assert resultado.staging["stage"].iloc[0] == 2


def test_codex_p3_sin_fecha_de_otorgamiento_no_se_compara_por_tramo() -> None:
    """Pasada 3 (medium): una fila sin fecha se lee desde la edad 0 para la ECL, pero sin fecha no
    hay tramo de vida: comparar su PD de hoy con la de origen es lo que D-FIR-8 descarta. No se
    compara, se cuenta y el resumen lo avisa."""
    cfg = _cfg_b(
        staging=_cfg_b().staging.model_copy(update={"origination_pd_12m_col": "pd_origen"})
    )
    resultado = IfrsProvisioningEngine.from_config(cfg).calculate(
        _cartera(
            otorgamiento=[None, "2022-03-01"],
            vencimiento=["2032-03-01", "2032-03-01"],
            pd_modelo=[0.05, 0.05],
            pd_origen=[0.80, 0.20],
        ),
        term_structure=_curva(["op0", "op1"], _DECRECIENTE),
        as_of_date=_CORTE,
        events_by_period=_EVENTOS_DEC,
    )
    detalle = resultado.detail.set_index("row_id")
    assert math.isnan(detalle.loc["op0", "sicr_pd_ratio_12m"])
    assert detalle.loc["op1", "sicr_pd_ratio_12m"] == pytest.approx(2.5, abs=1e-9)
    seccion = resultado.card.metric_sections["sicr_origination_12m"]
    assert seccion["n_rows_without_origination_date"] == 1
    assert seccion["n_rows_evaluated"] == 1
    from bayesrisk.guided.summaries import _lineas_de_la_pd_del_modelo

    _lineas, alertas = _lineas_de_la_pd_del_modelo(resultado.card.model_dump())
    assert any("sin fecha de otorgamiento" in a for a in alertas), alertas
