"""El motor puro de la comparación (SDD-34 §3.4, §3.5, §3.7 y §11).

- El índice del BCE contra la fórmula de su plantilla oficial (libro PD, hoja 4.0).
- La prueba de DeLong pareada contra una implementación directa, par a par.
- Los contraejemplos de las pasadas de Codex que viven en el motor: AUC 1 frente a 0,5 con varianza
  cero; el empate no transitivo A-B-C (la frontera es el núcleo); la unidad de los montos con las
  monedas en nulo.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from bayesrisk.comparison.engine import (
    componentes_de_delong,
    delong_pareada,
    frontera,
    indice_bce,
    misma_muestra_evaluada,
    misma_unidad,
    nivel_de_comparabilidad,
)

# ── el índice del BCE ────────────────────────────────────────────────────────────────────────


def _indice_de_la_plantilla(participacion: list[float]) -> float:
    """La celda de la plantilla: ``HI = 1 + LN((K·SUM((R_g - 1/K)²) + 1)/K)/LN(K)``."""
    k = len(participacion)
    suma = sum((r - 1.0 / k) ** 2 for r in participacion)
    return 1.0 + math.log((k * suma + 1.0) / k) / math.log(k)


@pytest.mark.parametrize(
    "participacion",
    [
        [0.123959, 0.352689, 0.241353, 0.197172, 0.084827],
        [0.5, 0.5],
        [0.1, 0.2, 0.3, 0.4],
        [0.05, 0.05, 0.1, 0.2, 0.2, 0.4],
    ],
)
def test_el_indice_es_el_de_la_plantilla_del_bce(participacion: list[float]) -> None:
    resultado = indice_bce(participacion)
    assert resultado.indice == pytest.approx(_indice_de_la_plantilla(participacion), abs=1e-12)
    assert resultado.hhi == pytest.approx(sum(r * r for r in participacion), abs=1e-12)


def test_el_indice_va_de_cero_a_uno_y_no_depende_de_k() -> None:
    assert indice_bce([0.25] * 4).indice == pytest.approx(0.0, abs=1e-12)
    assert indice_bce([0.2] * 5).indice == pytest.approx(0.0, abs=1e-12)
    assert indice_bce([1.0, 0.0, 0.0]).indice == pytest.approx(1.0, abs=1e-12)


def test_el_hhi_crudo_ordena_al_reves_lo_que_el_indice_corrige() -> None:
    """§0.4-4: más tramos bajan el HHI aunque la concentración relativa sea mayor."""
    cinco = indice_bce([0.123959, 0.352689, 0.241353, 0.197172, 0.084827])
    seis = indice_bce([0.08, 0.40, 0.20, 0.15, 0.10, 0.07])
    assert seis.hhi is not None and cinco.hhi is not None
    assert seis.hhi < cinco.hhi
    assert seis.indice is not None and cinco.indice is not None
    assert seis.indice > cinco.indice


def test_sin_dos_tramos_el_indice_no_es_evaluable() -> None:
    assert indice_bce([1.0]).causa == "un_tramo"
    assert indice_bce([]).causa == "sin_tramos"
    assert indice_bce([0.0, 0.0]).causa == "sin_operaciones"


# ── DeLong pareada ───────────────────────────────────────────────────────────────────────────


def _delong_directo(
    riesgo_a: np.ndarray, riesgo_b: np.ndarray, y: np.ndarray
) -> tuple[float, float, float, float, float]:
    """DeLong (1988) par a par, sin agregar: AUC, varianzas, covarianza y z."""
    malos, buenos = y == 1, y == 0

    def componentes(r: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
        x, w = r[malos], r[buenos]
        psi = (x[:, None] > w[None, :]).astype(float) + 0.5 * (x[:, None] == w[None, :])
        return float(psi.mean()), psi.mean(axis=1), psi.mean(axis=0)

    auc_a, v10a, v01a = componentes(riesgo_a)
    auc_b, v10b, v01b = componentes(riesgo_b)
    m, n = int(malos.sum()), int(buenos.sum())
    var_a = np.var(v10a, ddof=1) / m + np.var(v01a, ddof=1) / n
    var_b = np.var(v10b, ddof=1) / m + np.var(v01b, ddof=1) / n
    cov = np.cov(v10a, v10b, ddof=1)[0, 1] / m + np.cov(v01a, v01b, ddof=1)[0, 1] / n
    z = (auc_a - auc_b) / math.sqrt(var_a + var_b - 2 * cov)
    return auc_a, auc_b, float(var_a), float(cov), z


def test_la_pareada_es_la_de_delong_directa_con_empates() -> None:
    rng = np.random.default_rng(20261014)
    y = (rng.random(400) < 0.25).astype(int)
    latente = rng.normal(size=400) + 0.9 * y
    riesgo_a = np.round(latente + rng.normal(scale=0.4, size=400), 1)  # con empates
    riesgo_b = np.round(latente + rng.normal(scale=0.8, size=400), 1)
    auc_a, auc_b, var_a, _cov, z = _delong_directo(riesgo_a, riesgo_b, y)

    a = componentes_de_delong(riesgo_a, y)
    b = componentes_de_delong(riesgo_b, y)
    prueba = delong_pareada(a, b)

    assert a.auc == pytest.approx(auc_a, abs=1e-12)
    assert b.auc == pytest.approx(auc_b, abs=1e-12)
    assert a.varianza == pytest.approx(var_a, rel=1e-10)
    assert prueba.estado == "ok"
    assert prueba.estadistico == pytest.approx(z, rel=1e-9)
    assert prueba.p_valor == pytest.approx(math.erfc(abs(z) / math.sqrt(2)), rel=1e-9)


def test_el_auc_de_la_prueba_es_el_de_scikit_learn() -> None:
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(7)
    y = (rng.random(300) < 0.3).astype(int)
    riesgo = np.round(rng.normal(size=300) + y, 1)
    assert componentes_de_delong(riesgo, y).auc == pytest.approx(
        roc_auc_score(y, riesgo), abs=1e-12
    )


def test_emparejar_por_otro_orden_cambia_la_prueba_y_el_mismo_orden_no() -> None:
    """Pasada 1: los componentes se emparejan por el orden canónico; reordenar la cartera entera
    (los dos modelos igual) no cambia nada, permutar dentro de cada clase uno solo sí."""
    rng = np.random.default_rng(11)
    y = (rng.random(500) < 0.3).astype(int)
    latente = rng.normal(size=500) + y
    riesgo_a = latente + rng.normal(scale=0.3, size=500)
    riesgo_b = latente + rng.normal(scale=0.3, size=500)
    base = delong_pareada(componentes_de_delong(riesgo_a, y), componentes_de_delong(riesgo_b, y))

    orden = rng.permutation(500)
    reordenada = delong_pareada(
        componentes_de_delong(riesgo_a[orden], y[orden]),
        componentes_de_delong(riesgo_b[orden], y[orden]),
    )
    assert reordenada.estadistico == pytest.approx(base.estadistico, rel=1e-12)

    permutado = riesgo_b.copy()
    for clase in (0, 1):
        idx = np.flatnonzero(y == clase)
        permutado[idx] = permutado[rng.permutation(idx)]
    mal_emparejada = delong_pareada(
        componentes_de_delong(riesgo_a, y), componentes_de_delong(permutado, y)
    )
    assert componentes_de_delong(permutado, y).auc == pytest.approx(
        componentes_de_delong(riesgo_b, y).auc, abs=1e-12
    )
    assert abs(mal_emparejada.estadistico - base.estadistico) > 0.5


def test_auc_uno_frente_a_un_puntaje_constante_no_es_evaluable() -> None:
    """Pasada 1: varianza cero no implica AUC iguales (AUC 1 frente a 0,5)."""
    y = np.array([0] * 20 + [1] * 10)
    perfecto = np.array([0.0] * 20 + [1.0] * 10)
    constante = np.full(30, 0.3)
    prueba = delong_pareada(componentes_de_delong(perfecto, y), componentes_de_delong(constante, y))
    assert prueba.estado == "no_evaluable"
    assert prueba.causa == "zero_variance"
    assert prueba.diferencia == pytest.approx(0.5)


def test_dos_modelos_identicos_empatan_sin_estadistico() -> None:
    rng = np.random.default_rng(3)
    y = (rng.random(200) < 0.3).astype(int)
    riesgo = rng.normal(size=200) + y
    prueba = delong_pareada(componentes_de_delong(riesgo, y), componentes_de_delong(riesgo, y))
    assert prueba.estado == "empate_sin_varianza"
    assert prueba.estadistico is None


def test_pocos_malos_no_es_evaluable() -> None:
    y = np.array([0] * 30 + [1])
    riesgo = np.linspace(0, 1, 31)
    prueba = delong_pareada(componentes_de_delong(riesgo, y), componentes_de_delong(riesgo, y))
    assert prueba.estado == "no_evaluable"
    assert prueba.causa == "few_bads"


# ── la frontera como núcleo ──────────────────────────────────────────────────────────────────


def test_el_empate_no_transitivo_deja_a_y_c_en_la_frontera() -> None:
    """Pasada 2: A empata con B y B con C; A discrimina más que C; B concentra menos que A y C
    menos que B. «Lo supera alguno» deja sólo a C; el núcleo, a A y C."""
    # relación de discriminación: +1 mejor, 0 empate, -1 peor (fila contra columna)
    discriminacion = [[0, 0, 1], [0, 0, 0], [-1, 0, 0]]
    concentracion = [0.30, 0.20, 0.10]  # menor es mejor

    def supera(y: int, x: int) -> bool:
        d = discriminacion[y][x]
        s = (concentracion[x] > concentracion[y]) - (concentracion[x] < concentracion[y])
        return d >= 0 and s >= 0 and (d > 0 or s > 0)

    dentro, por = frontera(3, supera)
    assert dentro == (True, False, True)
    assert por == ((), (2,), ())
    lo_supera_alguno = tuple(not any(supera(y, x) for y in range(3) if y != x) for x in range(3))
    assert lo_supera_alguno == (False, False, True)


def test_un_ciclo_no_tiene_frontera() -> None:
    with pytest.raises(ValueError, match="ciclo"):
        frontera(2, lambda y, x: True)


# ── comparabilidad y unidad ──────────────────────────────────────────────────────────────────


def _scorecard(cartera: str, filas: str, desenlace: str) -> dict[str, object]:
    return {
        "family": "scorecard",
        "portfolio_hash": cartera,
        "evaluation_scores": {"rows_hash": filas, "default_hash": desenlace},
    }


def test_los_tres_niveles_de_comparabilidad() -> None:
    ref = _scorecard("c1", "f1", "d1")
    assert nivel_de_comparabilidad(ref, _scorecard("c1", "f1", "d1")) == "misma_muestra"
    assert nivel_de_comparabilidad(ref, _scorecard("c1", "f2", "d2")) == "misma_cartera"
    assert nivel_de_comparabilidad(ref, _scorecard("c1", "f1", "d2")) == "misma_cartera"
    assert nivel_de_comparabilidad(ref, _scorecard("c2", "f1", "d1")) == "otra_cartera"


def test_una_huella_ausente_nunca_prueba_la_misma_muestra() -> None:
    assert not misma_muestra_evaluada(_scorecard("c1", None, "d1"), _scorecard("c1", None, "d1"))  # type: ignore[arg-type]
    assert not misma_muestra_evaluada(_scorecard(None, "f", "d"), _scorecard(None, "f", "d"))  # type: ignore[arg-type]


def _provision(cartera: str, moneda: str | None, columnas: dict[str, str] | None = None) -> dict:
    return {
        "family": "ifrs9",
        "portfolio_hash": cartera,
        "as_of": "2025-06-30",
        "currency": moneda,
        "amount_columns": columnas or {"exposure": "ead", "balance": "drawn", "limit": "lim"},
    }


def test_monedas_nulas_en_carteras_distintas_no_restan_montos() -> None:
    """Pasada 3: «no declarada» no es «la misma»."""
    assert misma_unidad(_provision("c1", None), _provision("c2", None)) == (
        False,
        "unidad_no_probada",
    )


def test_la_misma_cartera_con_las_mismas_columnas_resta_montos() -> None:
    assert misma_unidad(_provision("c1", None), _provision("c1", None)) == (
        True,
        "misma_cartera_y_columnas",
    )
    otras = {"exposure": "saldo", "balance": "drawn", "limit": "lim"}
    assert misma_unidad(_provision("c1", None), _provision("c1", None, otras))[0] is False


def test_la_moneda_declarada_manda() -> None:
    assert misma_unidad(_provision("c1", "CLP"), _provision("c2", "CLP")) == (True, "misma_moneda")
    assert misma_unidad(_provision("c1", "CLP"), _provision("c1", "USD")) == (
        False,
        "monedas_distintas",
    )
    assert (
        nivel_de_comparabilidad(_provision("c1", "CLP"), _provision("c1", "USD")) == "otra_cartera"
    )
