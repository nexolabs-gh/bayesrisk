"""``comparar`` sobre resúmenes sintéticos (SDD-34 §3.3, §3.5, §3.7, §7, §8 y §11).

Los contraejemplos de las tres pasadas de Codex que viven en la comparación —no en el motor puro—:
el mismo PSI con cortes 0,10 y 0,20, el PSI propio de 10 y 2 tramos, otro tamaño de Holdout con la
misma OOT, dos muestras evaluadas distintas, los puntajes externos, los modelos repetidos, la
elección atada a la huella y las monedas en nulo; y los errores de entrada de §8.
"""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pytest

from bayesrisk.comparison.comparable import RECETA_PSI_DE_FABRICA, huella
from bayesrisk.comparison.exceptions import ComparisonDataError
from bayesrisk.comparison.step import comparar, nombres_visibles

_RNG = np.random.default_rng(20261014)
_Y = (_RNG.random(600) < 0.25).astype(int)
_LATENTE = _RNG.normal(size=600) + 1.2 * _Y


def _riesgo(ruido: float, semilla: int) -> list[float]:
    rng = np.random.default_rng(semilla)
    return [float(v) for v in _LATENTE + rng.normal(scale=ruido, size=600)]


def _resumen(
    nombre: str,
    *,
    riesgo: list[float] | None = None,
    cartera: str | None = "cartera",
    filas: str | None = "filas-oot",
    data_hash: str = "datos",
    evaluacion: str = "oot",
    psi: float | None = 0.01,
    banda: str = "stable",
    receta: dict[str, Any] | None = None,
    psi_propio: tuple[float, str] | None = None,
    participacion: list[float] | None = None,
    model_hash: str | None = None,
    variables: list[str] | None = ("a", "b"),  # type: ignore[assignment]
    validacion: tuple[str, str | None] | None = ("pass", None),
) -> dict[str, Any]:
    from sklearn.metrics import roc_auc_score

    riesgo = riesgo if riesgo is not None else _riesgo(0.5, hash(nombre) % 1000)
    auc = float(roc_auc_score(_Y, riesgo))
    receta = receta if receta is not None else copy.deepcopy(RECETA_PSI_DE_FABRICA)
    propio = psi_propio if psi_propio is not None else (psi, banda)
    return {
        "schema_version": 1,
        "bayesrisk": "2.15.0",
        "family": "scorecard",
        "name": nombre,
        "created_at": f"2026-10-14T00:00:{abs(hash(nombre)) % 60:02d}+00:00",
        "config_hash": f"cfg-{nombre}",
        "data_hash": data_hash,
        "portfolio_hash": cartera,
        "currency": None,
        "missing": {},
        "model_hash": model_hash if model_hash is not None else f"modelo-{nombre}",
        "psi_recipe": receta,
        "samples": [
            {
                "sample": "desarrollo",
                "n": 2000,
                "n_bad": 500,
                "auc": 0.75,
                "gini": 0.5,
                "ks": 0.4,
                "status": "ok",
            },
            {
                "sample": evaluacion,
                "n": 600,
                "n_bad": int(_Y.sum()),
                "auc": auc,
                "gini": 2 * auc - 1,
                "ks": 0.3,
                "status": "ok",
            },
        ]
        if evaluacion != "desarrollo"
        else [
            {
                "sample": "desarrollo",
                "n": 600,
                "n_bad": int(_Y.sum()),
                "auc": auc,
                "gini": 2 * auc - 1,
                "ks": 0.3,
                "status": "ok",
            }
        ],
        "evaluation_sample": evaluacion,
        "evaluation_scores": {
            "order": "index",
            "basis": "pd_calibrated",
            "rows_hash": filas,
            "default_hash": "desenlace" if filas is not None else None,
            "risk": riesgo,
            "default": [int(v) for v in _Y],
        },
        "score_psi": [{"comparison": f"dev_vs_{evaluacion}", "psi": propio[0], "band": propio[1]}],
        "score_psi_common": None
        if psi is None
        else {"comparison": f"dev_vs_{evaluacion}", "psi": psi, "band": banda},
        "grades": None
        if participacion is None
        else {"k": len(participacion), "share_by_sample": {evaluacion: participacion}},
        "variables": None
        if variables is None
        else [
            {
                "feature": v,
                "beta": -1.0,
                "expected_sign": "negative",
                "sign_ok": True,
                "iv_development": 0.1,
                "iv_by_sample": {},
                "csi": [],
            }
            for v in variables
        ],
        "validation": None
        if validacion is None
        else {"status": validacion[0], "reason": validacion[1]},
    }


def _modelo(resultado: Any, nombre: str) -> dict[str, Any]:
    """La fila del modelo con los nulos de pandas (NaN) como ``None`` y los booleanos nativos."""
    fila = resultado.models[resultado.models["name"] == nombre].iloc[0]
    salida: dict[str, Any] = {}
    for clave, valor in fila.items():
        if isinstance(valor, float) and np.isnan(valor):
            valor = None
        elif isinstance(valor, np.bool_):
            valor = bool(valor)
        salida[str(clave)] = valor
    return salida


# ── la estabilidad: el PSI común manda en la frontera (pasadas 1 y 3) ────────────────────────


def test_el_mismo_psi_con_cortes_0_10_y_0_20_no_cambia_la_frontera() -> None:
    """Pasada 1: con los cortes propios, el mismo PSI 0,15 sería «Revisar» en A y «Estable» en B,
    y B superaría a A con la misma discriminación."""
    riesgo = _riesgo(0.5, 1)
    a = _resumen("a", riesgo=riesgo, psi=0.15, banda="review")
    b = _resumen(
        "b",
        riesgo=riesgo,
        psi=0.15,
        banda="review",
        receta={**RECETA_PSI_DE_FABRICA, "thresholds": [0.20, 0.30]},
        psi_propio=(0.15, "stable"),
        model_hash="otro",
    )
    resultado = comparar([a, b])
    assert _modelo(resultado, "a")["frontier_stability"] is True
    assert _modelo(resultado, "b")["frontier_stability"] is True
    assert _modelo(resultado, "b")["own_recipe"] is True
    assert any("otra receta" in linea for linea in resultado.reading)


def test_el_psi_propio_de_10_y_2_tramos_no_cambia_la_frontera() -> None:
    """Pasada 3: el mismo puntaje da PSI 10,50 «Redesarrollar» con 10 tramos y 0 «Estable» con 2;
    el PSI común (receta de fábrica, el mismo para los dos) los deja empatados."""
    riesgo = _riesgo(0.5, 2)
    a = _resumen("a", riesgo=riesgo, psi=10.4978, banda="redevelop")
    b = _resumen(
        "b",
        riesgo=riesgo,
        psi=10.4978,
        banda="redevelop",
        receta={**RECETA_PSI_DE_FABRICA, "bins": 2},
        psi_propio=(0.0, "stable"),
        model_hash="otro",
    )
    resultado = comparar([a, b])
    assert [_modelo(resultado, n)["frontier_stability"] for n in ("a", "b")] == [True, True]
    assert _modelo(resultado, "b")["psi_own"] == 0.0
    assert _modelo(resultado, "b")["psi_common"] == pytest.approx(10.4978)


def test_sin_psi_comun_el_modelo_queda_fuera_del_primer_grafico() -> None:
    resultado = comparar([_resumen("a"), _resumen("b", psi=None)])
    assert _modelo(resultado, "b")["frontier_stability"] is None
    assert _modelo(resultado, "a")["frontier_stability"] is True


# ── la prueba pareada sólo con la misma muestra evaluada (pasada 2) ──────────────────────────


def test_otro_holdout_con_la_misma_oot_conserva_la_prueba_pareada() -> None:
    a = _resumen("a", data_hash="datos-holdout-20", riesgo=_riesgo(0.4, 3))
    b = _resumen("b", data_hash="datos-holdout-30", riesgo=_riesgo(0.9, 4))
    resultado = comparar([a, b])
    prueba = resultado.tests.iloc[0]
    assert bool(prueba["paired"]) is True
    assert prueba["result"] in {"tie", "a_better", "b_better"}
    assert resultado.card.levels == ("referencia", "misma_muestra")


def test_dos_muestras_evaluadas_distintas_no_reciben_prueba() -> None:
    a = _resumen("a", riesgo=_riesgo(0.4, 5))
    b = _resumen("b", filas="otras-filas", riesgo=_riesgo(0.9, 6))
    resultado = comparar([a, b])
    prueba = resultado.tests.iloc[0]
    assert bool(prueba["paired"]) is False
    assert prueba["result"] == "no_test"
    assert prueba["reason"] == "otras_operaciones"
    assert resultado.card.levels[1] == "misma_cartera"
    assert any("otras operaciones de la misma cartera" in linea for linea in resultado.reading)


def test_otra_cartera_se_compara_con_su_alerta_y_sin_prueba() -> None:
    a = _resumen("a")
    b = _resumen("b", cartera="otra")
    resultado = comparar([a, b])
    assert resultado.card.levels[1] == "otra_cartera"
    assert resultado.tests.iloc[0]["reason"] == "otra_cartera"
    assert any("comparación es orientativa" in linea for linea in resultado.reading)


def test_una_diferencia_real_y_un_empate() -> None:
    """Dos modelos distintos cuya diferencia de AUC es ruido empatan por la prueba (p ≥ 0,05), no
    por ser idénticos; uno mucho más ruidoso discrimina menos de verdad (control negativo de S49:
    con dos riesgos del mismo orden el empate salía por la varianza nula y no probaba el corte)."""
    resultado = comparar(
        [
            _resumen("ref", riesgo=_riesgo(0.5, 7)),
            _resumen("igual", riesgo=_riesgo(0.55, 21)),
            _resumen("debil", riesgo=_riesgo(3.0, 8)),
        ]
    )
    pruebas = {(f["model_a"], f["model_b"]): f for _, f in resultado.tests.iterrows()}
    empate = pruebas[("ref", "igual")]
    assert empate["result"] == "tie"
    assert empate["difference"] != 0.0 and empate["p_value"] >= 0.05
    assert pruebas[("ref", "debil")]["result"] == "a_better"
    assert pruebas[("ref", "debil")]["p_value"] < 0.05
    assert any("debil discrimina menos" in linea for linea in resultado.reading)


# ── el mismo modelo, puntajes externos y Desarrollo sola ─────────────────────────────────────


def test_los_modelos_repetidos_se_agrupan_y_el_distinto_no() -> None:
    riesgo = _riesgo(0.5, 9)
    resultado = comparar(
        [
            _resumen("base", riesgo=riesgo, model_hash="m1"),
            _resumen("tramos_4", model_hash="m2"),
            _resumen("sin_stepwise", riesgo=riesgo, model_hash="m1"),
            _resumen("corr_050", riesgo=riesgo, model_hash="m1"),
        ]
    )
    assert resultado.card.same_as == {"sin_stepwise": "base", "corr_050": "base"}
    assert "sin_stepwise y corr_050 son el mismo modelo que base" in resultado.reading[0]


def test_una_corrida_de_puntajes_externos_se_compara_por_muestra() -> None:
    """Sin tarjeta, variables, escala ni estabilidad: «No aplica» y fuera de los gráficos."""
    externa = _resumen("externa", psi=None, variables=None, validacion=None, model_hash=None)
    externa["model_hash"] = None
    resultado = comparar([_resumen("ref", participacion=[0.3, 0.3, 0.4]), externa])
    fila = _modelo(resultado, "externa")
    assert fila["same_as"] is None
    assert fila["frontier_stability"] is None and fila["frontier_concentration"] is None
    assert fila["n_variables"] is None
    assert bool(resultado.tests.iloc[0]["paired"]) is True


def test_sin_oot_ni_holdout_las_cifras_son_optimistas_y_quedan_fuera() -> None:
    resultado = comparar([_resumen("ref"), _resumen("dev", evaluacion="desarrollo")])
    fila = _modelo(resultado, "dev")
    assert bool(fila["optimistic"]) is True
    assert fila["frontier_stability"] is None


def test_sin_escala_maestra_el_indice_no_es_evaluable() -> None:
    resultado = comparar([_resumen("ref", participacion=[0.2, 0.3, 0.5]), _resumen("sin")])
    assert _modelo(resultado, "sin")["concentration_index"] is None
    assert _modelo(resultado, "sin")["frontier_concentration"] is None
    assert any("sin escala maestra" in linea for linea in resultado.reading)


# ── la elección, atada a la huella (pasada 1) ────────────────────────────────────────────────


def test_la_eleccion_sigue_a_la_huella_al_reordenar_y_cae_al_reemplazar() -> None:
    a, b, c = _resumen("a"), _resumen("b"), _resumen("c")
    eleccion = {"huella": huella(b), "name": "b", "reason": "reparte mejor"}
    assert comparar([a, b, c], eleccion=eleccion).card.chosen == "b"
    assert comparar([c, a, b], eleccion=eleccion).card.chosen == "b"
    otra_b = _resumen("b", riesgo=_riesgo(0.7, 99))
    assert comparar([a, otra_b, c], eleccion=eleccion).card.chosen is None


def test_dos_corridas_con_el_mismo_nombre_se_distinguen_por_su_posicion() -> None:
    assert nombres_visibles(["consumo", "otra", "consumo"]) == (
        "consumo (1)",
        "otra",
        "consumo (3)",
    )


# ── errores de entrada (§7-2, §8) ────────────────────────────────────────────────────────────


def test_entradas_que_no_se_comparan() -> None:
    a = _resumen("a")
    with pytest.raises(ComparisonDataError, match="entre 2 y 10"):
        comparar([a])
    with pytest.raises(ComparisonDataError, match="entre 2 y 10"):
        comparar([_resumen(f"m{i}") for i in range(11)])
    with pytest.raises(ComparisonDataError, match="la misma"):
        comparar([a, copy.deepcopy(a)])
    provision = {**a, "family": "ifrs9"}
    with pytest.raises(ComparisonDataError, match="familias distintas"):
        comparar([a, provision])


# ── IFRS 9: los montos sólo se restan en la misma unidad (pasada 3) ──────────────────────────


def _provision(nombre: str, cartera: str, ecl: list[float], moneda: str | None = None) -> dict:
    etapas = [
        {"stage": e + 1, "n": 100, "exposure": 1000.0, "ecl": v, "coverage": v / 1000.0}
        for e, v in enumerate(ecl)
    ]
    return {
        "schema_version": 1,
        "bayesrisk": "2.15.0",
        "family": "ifrs9",
        "name": nombre,
        "created_at": "2026-10-14T00:00:00+00:00",
        "config_hash": f"cfg-{nombre}",
        "data_hash": cartera,
        "portfolio_hash": cartera,
        "currency": moneda,
        "missing": {},
        "as_of": "2025-06-30",
        "scenarios": [{"name": "base", "weight": 1.0}],
        "amount_columns": {"exposure": "ead", "balance": "drawn", "limit": "credit_limit"},
        "by_stage": etapas,
        "total": {"n": 300, "exposure": 3000.0, "ecl": sum(ecl), "coverage": sum(ecl) / 3000.0},
    }


def test_dos_provisiones_sin_moneda_de_carteras_distintas_no_se_restan() -> None:
    resultado = comparar(
        [_provision("f4", "c1", [10.0, 20.0, 30.0]), _provision("otra", "c2", [10.0, 15.0, 30.0])]
    )
    total = resultado.provision[
        (resultado.provision["model"] == "otra") & (resultado.provision["stage"] == "total")
    ].iloc[0]
    assert bool(total["same_unit"]) is False
    assert total["ecl_difference"] is None or np.isnan(total["ecl_difference"])
    assert any("no se restan" in linea for linea in resultado.reading)


def test_la_misma_cartera_con_las_mismas_columnas_se_resta_y_dice_donde() -> None:
    resultado = comparar(
        [
            _provision("f4", "c1", [1571504.0, 980623.0, 2234612.0]),
            _provision("horizonte_3", "c1", [1571504.0, 759268.0, 2234612.0]),
        ]
    )
    assert any(
        "horizonte_3 provisiona 221.355 menos que f4 (-4,6 %), todo en Stage 2" in linea
        for linea in resultado.reading
    )


def test_la_misma_provision_se_declara() -> None:
    resultado = comparar(
        [_provision("a", "c1", [1.0, 2.0, 3.0]), _provision("b", "c1", [1.0, 2.0, 3.0])]
    )
    assert resultado.card.same_as == {"b": "a"}
