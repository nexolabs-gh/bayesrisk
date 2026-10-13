"""El motor del monitoreo (SDD-33 §3, §11): oráculos independientes y una regla por caso.

- La prueba de AUC del BCE contra el anexo 3.1 calculado a mano (una suma par a par, sin agregar
  por tramo) y la hoja 4.0 de la plantilla oficial (``G10 = (AUC_init - AUC_curr)/√s²``,
  ``H10 = 1 - NORM.DIST(G10)``), cotejadas en S44 (``privado/evidencia/s44/cotejo_bce_auc.txt``).
- Los contraejemplos de las tres pasadas de Codex sobre el SDD: composición, intercepto y pendiente
  0,5, con las cifras de ``medir_h4_c.txt`` y ``medir_h4_d.txt``.
- La pendiente de Cox contra ``statsmodels`` (GLM binomial) en datos sin estructura.
- El PSI contra ``stability`` (sus cortes, su regla de igualdad y su suavizado sólo de ceros).
- Una fila de la tabla de §3.5 por caso, con la precisión de Cami del 2026-10-13: el ámbar que pide
  vigilar es el de los indicadores de la cartera, no el de un tramo suelto.
"""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pytest
from scipy.stats import norm

from bayesrisk.monitoring import engine
from bayesrisk.monitoring.engine import EstadoDelPeriodo, veredicto_del_periodo

# ── la prueba del BCE ───────────────────────────────────────────────────────────────────


def _anexo_par_a_par(grados: list[int], malos: list[int]) -> tuple[float, float]:
    """El anexo 3.1 literal: U con empates en ½ sobre cada par (malo, bueno), sin agregar."""
    a = [g for g, y in zip(grados, malos, strict=True) if y == 1]
    b = [g for g, y in zip(grados, malos, strict=True) if y == 0]

    def u(ga: int, gb: int) -> float:
        # Un malo en un tramo de MAYOR riesgo que el bueno es concordante (tramo 1 = menor riesgo).
        return 1.0 if ga > gb else (0.5 if ga == gb else 0.0)

    v10 = [sum(u(ga, gb) for gb in b) / len(b) for ga in a]
    v01 = [sum(u(ga, gb) for ga in a) / len(a) for gb in b]
    auc = sum(v10) / len(a)
    var10 = sum((v - auc) ** 2 for v in v10) / (len(a) - 1)
    var01 = sum((v - auc) ** 2 for v in v01) / (len(b) - 1)
    return auc, var10 / len(a) + var01 / len(b)


def test_el_auc_y_su_varianza_son_los_del_anexo_3_1_par_a_par() -> None:
    """Tres tramos: 1 malo y 4 buenos, 2 y 3, 3 y 1 (a mano: AUC = 71/96)."""
    malos, buenos = [1, 2, 3], [4, 3, 1]
    grados = [
        g for g, (d, b) in enumerate(zip(malos, buenos, strict=True), 1) for _ in range(d + b)
    ]
    marcas = [y for d, b in zip(malos, buenos, strict=True) for y in [1] * d + [0] * b]
    auc_literal, var_literal = _anexo_par_a_par(grados, marcas)
    medido = engine.auc_sobre_tramos(malos, buenos)
    assert Fraction(medido.auc).limit_denominator(1000) == Fraction(71, 96)
    assert medido.auc == pytest.approx(auc_literal, abs=1e-15)
    assert medido.variance == pytest.approx(var_literal, rel=1e-12)
    assert (medido.n_bad, medido.n_good, medido.cause) == (6, 8, None)


def test_la_prueba_es_la_hoja_4_0_de_la_plantilla() -> None:
    """G10 = (AUC_init - AUC_curr)/√s² y H10 = 1 - NORM.DIST(G10): orientación y distribución."""
    periodo = engine.auc_sobre_tramos([1, 2, 3], [4, 3, 1])
    prueba = engine.prueba_del_bce(0.80, periodo)
    g10 = (0.80 - periodo.auc) / math.sqrt(periodo.variance)
    assert prueba.statistic == pytest.approx(g10, rel=1e-12)
    assert prueba.p_value == pytest.approx(1.0 - norm.cdf(g10), rel=1e-12)
    assert prueba.light == "green"  # un AUC que bajó 0,06 con 14 operaciones no es evidencia


def test_con_menos_de_dos_malos_la_prueba_no_es_evaluable() -> None:
    """La plantilla no calcula con menos de 2 incumplimientos (F11/G11/H11); nunca es verde."""
    uno = engine.auc_sobre_tramos([1, 0, 0], [10, 10, 10])
    assert uno.cause == "few_bads" and uno.auc is None
    assert engine.prueba_del_bce(0.7, uno).light == "not_evaluable"
    assert engine.auc_sobre_tramos([5, 5], [1, 0]).cause == "few_goods"


def test_todo_en_un_solo_tramo_deja_la_varianza_nula_y_la_prueba_no_evaluable() -> None:
    """§3.4: todas las contribuciones valen ½ y la varianza es cero (pasada 1 de Codex)."""
    medido = engine.auc_sobre_tramos([0, 7, 0], [0, 20, 0])
    assert medido.auc == pytest.approx(0.5)
    assert medido.cause == "zero_variance"
    assert engine.prueba_del_bce(0.7, medido).light == "not_evaluable"


# ── los contraejemplos de las pasadas 1, 2 y 3 ──────────────────────────────────────────


def test_composicion_cae_el_auc_con_los_tramos_calibrados_y_no_mueve_la_pendiente() -> None:
    """Pasada 1: PD 1 % y 10 % exactas; 10.000 y 10.000 → 1.000 y 19.000 (medir_h4_c y _d)."""
    antes = engine.auc_sobre_tramos([100, 1_000], [9_900, 9_000])
    despues = engine.auc_sobre_tramos([10, 1_900], [990, 17_100])
    assert round(antes.auc, 5) == 0.71645
    assert round(despues.auc, 5) == 0.52475
    prueba = engine.prueba_del_bce(antes.auc, despues)
    assert round(prueba.statistic, 1) == 162.2 and prueba.light == "red"
    pendiente = engine.pendiente_de_calibracion([1_000, 19_000], [10, 1_900], [0.01, 0.10])
    assert round(pendiente.slope, 4) == 1.0 and round(pendiente.std_error, 4) == 0.1329
    assert pendiente.light == "green"
    estado = EstadoDelPeriodo(
        population="green",
        with_outcome=True,
        portfolio="green",
        grades={1: "green", 2: "green"},
        auc_test=prueba.light,
        slope=pendiente.light,
    )
    assert veredicto_del_periodo(estado).verdict == "watch"  # nunca «redesarrollar»


def test_intercepto_cae_el_auc_pendiente_1_y_el_espejo_pide_recalibrar() -> None:
    """Pasada 2: PD 10 %/50 % con 100 y 820 malos de 8.200: la PD sobrestima; §12-10 (a)."""
    pendiente = engine.pendiente_de_calibracion([8_200, 8_200], [100, 820], [0.10, 0.50])
    assert round(pendiente.slope, 4) == 1.0 and round(pendiente.std_error, 4) == 0.0488
    assert pendiente.light == "green"
    assert round(engine.auc_sobre_tramos([100, 820], [8_100, 7_380]).auc, 4) == 0.7073
    pds = np.r_[np.full(8_200, 0.10), np.full(8_200, 0.50)]
    y = np.r_[np.ones(100), np.zeros(8_100), np.ones(820), np.zeros(7_380)]
    cartera = engine.calibracion_de_cartera(pds, y)
    assert cartera.light_under == "green" and cartera.light_over == "red"
    assert (cartera.light, cartera.direction) == ("red", "over")
    estado = EstadoDelPeriodo(
        population="green",
        with_outcome=True,
        portfolio=cartera.light,
        grades={1: "red", 2: "red"},
        auc_test="red",
        slope=pendiente.light,
    )
    assert veredicto_del_periodo(estado).verdict == "recalibrate"


def test_pendiente_0_5_redesarrolla_aunque_recalibrar_devuelva_las_pd() -> None:
    """Pasada 3 y §12-5 (a): 10.000 por tramo, malos de 1.000/5.000 a 2.500/5.000."""
    inicial = engine.auc_sobre_tramos([1_000, 5_000], [9_000, 5_000])
    periodo = engine.auc_sobre_tramos([2_500, 5_000], [7_500, 5_000])
    assert round(inicial.auc, 3) == 0.738 and round(periodo.auc, 3) == 0.633
    prueba = engine.prueba_del_bce(inicial.auc, periodo)
    pendiente = engine.pendiente_de_calibracion([10_000, 10_000], [2_500, 5_000], [0.10, 0.50])
    assert pendiente.slope == pytest.approx(0.5, abs=1e-9)
    assert (prueba.light, pendiente.light) == ("red", "red")
    estado = EstadoDelPeriodo(
        population="green",
        with_outcome=True,
        portfolio="green",
        grades={1: "red", 2: "green"},
        auc_test=prueba.light,
        slope=pendiente.light,
    )
    assert veredicto_del_periodo(estado).verdict == "redevelop"


# ── la pendiente ────────────────────────────────────────────────────────────────────────


def test_la_pendiente_es_la_de_statsmodels() -> None:
    """Newton agrupado por tramo = GLM binomial por operación (la misma verosimilitud)."""
    sm = pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(45)
    pds = np.array([0.03, 0.08, 0.15, 0.27, 0.44])
    n = rng.integers(80, 400, size=5)
    malos = rng.binomial(n, np.clip(pds * 1.3, 0, 0.95))
    medido = engine.pendiente_de_calibracion(n, malos, pds)
    x = np.repeat(np.log(pds / (1 - pds)), n)
    y = np.concatenate([np.r_[np.ones(d), np.zeros(k - d)] for k, d in zip(n, malos, strict=True)])
    ajuste = sm.GLM(y, sm.add_constant(x), family=sm.families.Binomial()).fit()
    assert medido.slope == pytest.approx(float(ajuste.params[1]), rel=1e-8)
    assert medido.intercept == pytest.approx(float(ajuste.params[0]), rel=1e-8)
    # statsmodels evalúa el error con los pesos de su última iteración IRLS (tolerancia 1e-8 sobre
    # la devianza): difiere en ~2e-6 relativo del de Newton convergido a 1e-10.
    assert medido.std_error == pytest.approx(float(ajuste.bse[1]), rel=1e-5)
    assert medido.p_value == pytest.approx(norm.cdf((medido.slope - 1) / medido.std_error))


def test_dos_tramos_con_la_misma_pd_dejan_la_pendiente_no_evaluable_y_el_auc_si() -> None:
    """Pasada 3: PAVA puede igualar tramos; 30 % con 1.000 operaciones y 300 malos cada uno."""
    pendiente = engine.pendiente_de_calibracion([1_000, 1_000], [300, 300], [0.30, 0.30])
    assert (pendiente.light, pendiente.cause) == ("not_evaluable", "one_pd")
    auc = engine.auc_sobre_tramos([300, 300], [700, 700])
    assert auc.cause is None and auc.auc == pytest.approx(0.5)


def test_la_separacion_perfecta_deja_la_pendiente_no_evaluable() -> None:
    """Sin estimador de máxima verosimilitud: malos y buenos en tramos separados."""
    medido = engine.pendiente_de_calibracion([50, 40, 30], [0, 10, 30], [0.05, 0.2, 0.5])
    assert (medido.light, medido.cause) == ("not_evaluable", "separation")
    assert engine.pendiente_de_calibracion([50, 30], [1, 30], [0.05, 0.5]).cause == "separation"


# ── el PSI ──────────────────────────────────────────────────────────────────────────────


def test_el_psi_reemplaza_solo_las_proporciones_cero() -> None:
    """§3.2 y pasada 2: referencia [100, 9.900], periodo [1, 2.999.999] da 0,103187, «revisar»."""
    valor = engine.psi([100, 9_900], [1, 2_999_999])
    assert round(valor, 6) == 0.103187
    assert engine.semaforo_psi(valor) == "amber"
    assert engine.psi([10, 0], [5, 5]) == pytest.approx(
        (0.5 - 1.0) * math.log(0.5) + (0.5 - 1e-6) * math.log(0.5 / 1e-6)
    )


def test_los_cortes_y_el_conteo_son_los_de_stability() -> None:
    """Cuantiles de Desarrollo únicos, colas abiertas y un valor igual al corte va arriba."""
    from bayesrisk.stability.evaluator import (
        _bin_counts_continuous,
        _psi_from_counts,
        _quantile_interior_edges,
    )

    rng = np.random.default_rng(7)
    dev = np.round(rng.normal(500, 40, 3_000))
    actual = np.round(rng.normal(510, 45, 1_000))
    cortes = engine.cortes_del_puntaje(dev)
    assert np.array_equal(np.asarray(cortes), _quantile_interior_edges(dev, 10, np))
    esperado = _bin_counts_continuous(dev, actual, np.asarray(cortes), np)
    assert engine.conteos_por_corte(dev, cortes) == tuple(e for _l, e, _a in esperado)
    assert engine.conteos_por_corte(actual, cortes) == tuple(a for _l, _e, a in esperado)
    stability = _psi_from_counts(esperado, dev.size, actual.size, 1e-6).total
    medido = engine.psi(
        engine.conteos_por_corte(dev, cortes), engine.conteos_por_corte(actual, cortes)
    )
    assert medido == stability
    assert engine.conteos_por_corte([cortes[0]], cortes)[1] == 1


def test_un_puntaje_discreto_da_menos_de_diez_bins_y_el_mismo_psi_que_stability() -> None:
    """§3.7 (pasada 1): con dos valores de puntaje hay un corte interior, no nueve."""
    from bayesrisk.stability.evaluator import _bin_counts_continuous, _psi_from_counts

    dev = np.r_[np.full(700, 480.0), np.full(300, 520.0)]
    actual = np.r_[np.full(400, 480.0), np.full(600, 520.0)]
    cortes = engine.cortes_del_puntaje(dev)
    assert len(cortes) + 1 < 10
    conteos = _bin_counts_continuous(dev, actual, np.asarray(cortes), np)
    assert (
        engine.psi(engine.conteos_por_corte(dev, cortes), engine.conteos_por_corte(actual, cortes))
        == _psi_from_counts(conteos, dev.size, actual.size, 1e-6).total
    )


def test_las_constantes_son_las_de_stability_y_validation() -> None:
    """D-MNT-6: no hay umbrales propios; un cambio de fábrica de los dominios se ve aquí."""
    from bayesrisk.master_scale.engine import MIN_ROWS_EVALUABLE
    from bayesrisk.stability.config import StabilityConfig

    fabrica = StabilityConfig()
    assert fabrica.psi_stable_threshold == engine.PSI_VERDE
    assert fabrica.psi_review_threshold == engine.PSI_ROJO
    assert fabrica.psi_bins == engine.DECILES
    assert fabrica.smoothing == engine.SUAVIZADO
    assert (engine.ALFA_VERDE, engine.ALFA_ROJO) == (0.05, 0.01)
    assert engine.MIN_ROWS_EVALUABLE == MIN_ROWS_EVALUABLE == 30


# ── la calibración y sus dos colas ──────────────────────────────────────────────────────


def test_la_cartera_es_el_contraste_del_bce_con_su_espejo() -> None:
    """§3.3: la PD esperada es la media de la PD del tramo sobre las MISMAS filas con desenlace."""
    from scipy.stats import beta

    pds = np.r_[np.full(300, 0.05), np.full(200, 0.30)]
    y = np.r_[np.ones(30), np.zeros(270), np.ones(90), np.zeros(110)]
    medido = engine.calibracion_de_cartera(pds, y)
    esperada = float(pds.mean())
    p = float(beta.cdf(esperada, 120 + 0.5, 500 - 120 + 0.5))
    assert medido.expected_pd == pytest.approx(esperada)
    assert medido.p_under == pytest.approx(p) and medido.p_over == pytest.approx(1 - p)
    assert (medido.light, medido.direction) == ("red", "under")


def test_un_p_valor_ausente_no_enciende_el_espejo() -> None:
    """Un tramo no evaluable llega como NaN desde su tabla: su espejo no es un rojo (S45)."""
    assert engine.dos_colas(float("nan"))[1:4] == ("not_evaluable",) * 3
    assert engine.dos_colas(None)[1:4] == ("not_evaluable",) * 3


def test_menos_de_30_con_desenlace_deja_la_cartera_no_evaluable() -> None:
    medido = engine.calibracion_de_cartera(np.full(29, 0.2), np.r_[np.ones(10), np.zeros(19)])
    assert (medido.light, medido.cause) == ("not_evaluable", "few_outcomes")


# ── la tabla de §3.5, una regla por caso ────────────────────────────────────────────────


def _estado(**cambios: object) -> EstadoDelPeriodo:
    base: dict[str, object] = {
        "population": "green",
        "with_outcome": True,
        "portfolio": "green",
        "grades": dict.fromkeys(range(1, 6), "green"),
        "auc_test": "green",
        "slope": "green",
    }
    base.update(cambios)
    return EstadoDelPeriodo(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("cambios", "veredicto", "regla"),
    [
        (
            {"auc_test": "red", "slope": "red", "portfolio": "red"},
            "redevelop",
            "discrimination_red",
        ),
        ({"portfolio": "red"}, "recalibrate", "portfolio_red"),
        ({"grades": {1: "red", 3: "red", 2: "green"}}, "recalibrate", "two_red_grades"),
        (
            {"grades": {4: "red", 1: "green"}, "previous_red_grades": frozenset({4})},
            "recalibrate",
            "repeated_red_grade",
        ),
        ({"population": "red"}, "watch", "population_red"),
        ({"slope": "red"}, "watch", "one_discrimination_test_red"),
        ({"auc_test": "red"}, "watch", "one_discrimination_test_red"),
        ({"grades": {2: "red", 1: "green"}}, "watch", "isolated_red_grade"),
        ({"population": "amber"}, "watch", "amber"),
        ({"portfolio": "amber"}, "watch", "amber"),
        ({"slope": "amber"}, "watch", "amber"),
        ({}, "no_action", "all_green"),
        # Cami, 2026-10-13: el ámbar de un tramo suelto no pide vigilar (§0.3, cartera estable
        # 2024Q1 con el tramo 1 en ámbar: «sin acción»).
        ({"grades": {1: "amber", 2: "green"}}, "no_action", "all_green"),
        # Lo no evaluable no cuenta como verde ni como rojo.
        ({"auc_test": "not_evaluable", "slope": "red"}, "watch", "one_discrimination_test_red"),
        ({"auc_test": "not_evaluable", "slope": "not_evaluable"}, "no_action", "all_green"),
    ],
)
def test_cada_fila_de_la_tabla(cambios: dict[str, object], veredicto: str, regla: str) -> None:
    medido = veredicto_del_periodo(_estado(**cambios))
    assert (medido.verdict, medido.rule) == (veredicto, regla)


@pytest.mark.parametrize(
    ("poblacion", "veredicto"),
    [
        ("green", "no_outcome_yet"),
        ("amber", "watch"),
        ("red", "watch"),
        ("not_evaluable", "no_outcome_yet"),
    ],
)
def test_sin_desenlace_nunca_es_sin_accion(poblacion: str, veredicto: str) -> None:
    """§3.5: un periodo sin desenlace se resuelve antes de las filas."""
    medido = veredicto_del_periodo(
        _estado(population=poblacion, with_outcome=False, auc_test="red", slope="red")
    )
    assert medido.verdict == veredicto


def test_un_rojo_del_periodo_anterior_que_no_se_repite_no_recalibra() -> None:
    medido = veredicto_del_periodo(
        _estado(grades={2: "red", 4: "green"}, previous_red_grades=frozenset({4}))
    )
    assert (medido.verdict, medido.repeated_red_grades) == ("watch", ())
