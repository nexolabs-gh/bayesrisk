"""Motor de la escala maestra (SDD-32 §3, §11): canónicos a mano, regla única y propiedades.

Sin OptBinning: los tramos los fija la institución o el caso; la formación con el solver real se
prueba en ``test_master_scale_oraculo.py`` (en un subproceso: OR-Tools revienta pytest).
"""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from bayesrisk.core.tramos import rotulo_de_corte_de_puntaje, rotulo_de_tramo_de_puntaje
from bayesrisk.master_scale.engine import (
    MIN_ROWS_EVALUABLE,
    aprobar,
    asignar_tramos,
    corte_de_los_primeros,
    diagnostico_por_muestra,
    pava,
    pd_por_tramo,
    tabla_de_cortes,
    tabla_por_tramo,
    z_entre_vecinos,
)

# ─────────────────────── canónico a mano: veinte operaciones, tres tramos ───────────────────────

#: (puntaje, malo) por tramo de la institución con cortes 500,5 y 520,5 («más puntaje, menos
#: riesgo»): tramo 1 = s ≥ 520,5; tramo 2 = 500,5 ≤ s < 520,5; tramo 3 = s < 500,5.
_TRAMO_1 = [(530, 0), (535, 0), (540, 1), (545, 0), (550, 0), (525, 0), (522, 0), (560, 0)]
_TRAMO_2 = [(505, 1), (510, 0), (515, 1), (501, 0), (519, 0), (520, 0)]
_TRAMO_3 = [(480, 1), (490, 1), (495, 0), (500, 1), (470, 1), (499, 0)]
_CORTES = (500.5, 520.5)


def _canonico() -> pd.DataFrame:
    filas = [(s, b) for s, b in (*_TRAMO_1, *_TRAMO_2, *_TRAMO_3)]
    return pd.DataFrame(filas, columns=["score", "target"]).astype({"target": "float64"})


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _expit(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _delta_por_biseccion(r: list[float], n: list[int], ancla: float) -> float:
    """Un δ independiente del motor: bisección pura sobre la reconciliación con el ancla."""
    total = sum(n)
    bajo, alto = -20.0, 20.0
    for _ in range(200):
        medio = (bajo + alto) / 2.0
        valor = sum(ng / total * _expit(_logit(q) + medio) for ng, q in zip(n, r, strict=True))
        if valor < ancla:
            bajo = medio
        else:
            alto = medio
    return (bajo + alto) / 2.0


def test_canonico_tramos_pd_y_tabla_de_cortes_calculados_a_mano() -> None:
    frame = _canonico()
    frame["grade"] = asignar_tramos(frame["score"].to_numpy(), _CORTES, mayor_es_menor_riesgo=True)
    assert frame["grade"].tolist() == [1] * 8 + [2] * 6 + [3] * 6

    n, d = [8, 6, 6], [1, 2, 4]
    ancla = 7 / 20
    r = [(1 + 0.5) / 9, (2 + 0.5) / 7, (4 + 0.5) / 7]
    delta = _delta_por_biseccion(r, n, ancla)
    esperadas = [_expit(_logit(q) + delta) for q in r]
    pds = pd_por_tramo(n, d, ancla=ancla)
    assert pds.smoothed_rate == pytest.approx(r, abs=1e-15)
    assert pds.delta == pytest.approx(delta, abs=1e-9)
    assert pds.pd == pytest.approx(esperadas, abs=1e-12)
    assert pds.equalized == ()
    assert sum(ng * p for ng, p in zip(n, pds.pd, strict=True)) / 20 == pytest.approx(ancla)

    tabla = tabla_de_cortes(
        {"desarrollo": frame}, _CORTES, pds.pd, mayor_es_menor_riesgo=True, corte_declarado=510.0
    ).set_index(["grades_approved"], drop=False)
    # (aprobados, malos aprobados) por k: los tramos 1…k.
    for k, (aprob, malos_aprob, corte) in {
        1: (8, 1, 520.5),
        2: (14, 3, 500.5),
        3: (20, 7, None),
    }.items():
        fila = tabla.loc[tabla["grades_approved"] == k].iloc[0]
        assert fila["cutoff_score"] == corte or (corte is None and pd.isna(fila["cutoff_score"]))
        assert (fila["n_scored"], fila["n_with_outcome"]) == (20, 20)
        assert (fila["n_approved"], fila["n_approved_with_outcome"]) == (aprob, aprob)
        assert (fila["n_bad"], fila["n_good"]) == (7, 13)
        assert fila["approved_share"] == pytest.approx(float(Fraction(aprob, 20)))
        assert fila["approved_bad_rate"] == pytest.approx(float(Fraction(malos_aprob, aprob)))
        assert fila["bads_avoided_share"] == pytest.approx(float(Fraction(7 - malos_aprob, 7)))
        buenos_aprob = aprob - malos_aprob
        assert fila["goods_rejected_share"] == pytest.approx(float(Fraction(13 - buenos_aprob, 13)))
        esperada = sum(ng * p for ng, p in zip(n[:k], pds.pd[:k], strict=True)) / sum(n[:k])
        assert fila["approved_expected_pd"] == pytest.approx(esperada)
    # El corte de la institución, exacto en su puntaje (no es un límite de tramo): s ≥ 510 aprueba
    # el tramo 1 entero y 510, 515, 519 y 520 del tramo 2 —12 operaciones, 2 malas—.
    declarada = tabla.loc[tabla["declared"]].iloc[0]
    assert declarada["cutoff_score"] == 510.0
    assert (declarada["n_approved"], declarada["approved_bad_rate"]) == (12, pytest.approx(2 / 12))
    assert declarada["bads_avoided_share"] == pytest.approx(5 / 7)
    assert declarada["goods_rejected_share"] == pytest.approx(3 / 13)
    assert declarada["approved_expected_pd"] == pytest.approx((8 * pds.pd[0] + 4 * pds.pd[1]) / 12)


# ─────────────────────────── la regla única de corte (§3.2) ───────────────────────────


@pytest.mark.parametrize("corte", [493.5, 541.0, 0.5, -12.0])
@pytest.mark.parametrize("mayor_es_menor_riesgo", [True, False])
def test_los_vecinos_del_borde_caen_del_lado_correcto(
    corte: float, mayor_es_menor_riesgo: bool
) -> None:
    """``s ≥ c`` al lado de puntaje mayor, en las dos direcciones; el rótulo separa lo mismo."""
    vecinos = np.array(
        [
            corte,
            math.floor(corte) - (1 if corte == math.floor(corte) else 0),
            math.ceil(corte) + (1 if corte == math.ceil(corte) else 0),
            np.nextafter(corte, -np.inf),
            np.nextafter(corte, np.inf),
        ]
    )
    lado_mayor = vecinos >= corte
    aprobado = aprobar(vecinos, corte, mayor_es_menor_riesgo=mayor_es_menor_riesgo)
    assert (aprobado == (lado_mayor if mayor_es_menor_riesgo else ~lado_mayor)).all()
    tramos = asignar_tramos(vecinos, [corte], mayor_es_menor_riesgo=mayor_es_menor_riesgo)
    assert ((tramos == 1) == aprobado).all()
    # Con una tarjeta de enteros, ⌈c⌉ separa los mismos puntajes enteros que c.
    enteros = vecinos[vecinos == np.round(vecinos)]
    rotulo = rotulo_de_corte_de_puntaje(
        corte, enteros=True, mayor_es_menor_riesgo=mayor_es_menor_riesgo
    )
    limite = int(rotulo.split()[1].replace(".", ""))
    if mayor_es_menor_riesgo:
        assert rotulo.startswith("desde ")
        assert ((enteros >= limite) == (enteros >= corte)).all()
    else:
        assert rotulo.startswith("hasta ")
        assert ((enteros <= limite) == (enteros < corte)).all()


@given(
    cortes=st.lists(
        st.floats(min_value=-1e4, max_value=1e4, allow_nan=False),
        min_size=1,
        max_size=9,
        unique=True,
    ),
    puntajes=st.lists(
        st.floats(min_value=-2e4, max_value=2e4, allow_nan=False), min_size=1, max_size=60
    ),
    mayor_es_menor_riesgo=st.booleans(),
)
def test_aprobar_los_tramos_1_a_k_es_aplicar_su_corte(
    cortes: list[float], puntajes: list[float], mayor_es_menor_riesgo: bool
) -> None:
    valores = np.asarray(puntajes)
    tramos = asignar_tramos(valores, cortes, mayor_es_menor_riesgo=mayor_es_menor_riesgo)
    assert set(tramos.tolist()) <= set(range(1, len(cortes) + 2))
    for k in range(1, len(cortes) + 2):
        corte = corte_de_los_primeros(k, cortes, mayor_es_menor_riesgo=mayor_es_menor_riesgo)
        aprobado = aprobar(valores, corte, mayor_es_menor_riesgo=mayor_es_menor_riesgo)
        assert ((tramos <= k) == aprobado).all()


def test_un_puntaje_ausente_no_tiene_tramo_ni_se_aprueba() -> None:
    valores = np.array([np.nan, 510.0])
    assert asignar_tramos(valores, [500.5], mayor_es_menor_riesgo=True).tolist() == [0, 1]
    assert aprobar(valores, 500.5, mayor_es_menor_riesgo=True).tolist() == [False, True]
    assert aprobar(valores, None, mayor_es_menor_riesgo=True).tolist() == [False, True]


def test_rotulos_de_los_tramos_de_puntaje() -> None:
    assert rotulo_de_tramo_de_puntaje(555.5, None, enteros=True) == "desde 556 puntos"
    assert rotulo_de_tramo_de_puntaje(526.5, 555.5, enteros=True) == "de 527 a 555 puntos"
    assert rotulo_de_tramo_de_puntaje(None, 493.5, enteros=True) == "hasta 493 puntos"
    assert rotulo_de_tramo_de_puntaje(541.0, 541.5, enteros=True) == "541 puntos"
    assert rotulo_de_tramo_de_puntaje(None, 1500.25, enteros=False) == "menos de 1.500,25 puntos"
    assert (
        rotulo_de_tramo_de_puntaje(475.58, 490.0, enteros=False)
        == "desde 475,58 y menos de 490 puntos"
    )
    assert rotulo_de_tramo_de_puntaje(None, None, enteros=True) == "todos los puntajes"
    assert (
        rotulo_de_corte_de_puntaje(541.0, enteros=True, mayor_es_menor_riesgo=False)
        == "hasta 540 puntos"
    )
    assert (
        rotulo_de_corte_de_puntaje(493.5, enteros=False, mayor_es_menor_riesgo=False)
        == "menos de 493,5 puntos"
    )


# ───────────────────── la PD del tramo: los contraejemplos fijos (§11) ─────────────────────


def test_contraejemplo_de_la_pasada_1_se_iguala_con_pava() -> None:
    """(30, 0) y (300, 1): tasas 0 % y 0,33 %, suavizadas 1,61 % y 0,50 % —el orden se invierte—."""
    pds = pd_por_tramo([30, 300], [0, 1], ancla=1 / 330)
    assert pds.equalized == ((1, 2),)
    assert pds.pd[0] == pds.pd[1]
    assert [round(100 * p, 4) for p in pds.pd] == [0.303, 0.303]
    assert round(pds.delta, 6) == -0.685515


def test_contraejemplo_de_la_pasada_2_deja_rojo_el_primer_tramo_en_desarrollo() -> None:
    """(1000, 500) y (1000, 100): la igualación y el ancla dejan 30 % en los dos; el 1 sale rojo."""
    pds = pd_por_tramo([1000, 1000], [500, 100], ancla=0.3)
    assert [round(100 * p, 4) for p in pds.pd] == [30.0, 30.0]
    assert round(pds.delta, 6) == -0.000951
    frame = pd.DataFrame(
        {
            "grade": [1] * 1000 + [2] * 1000,
            "target": [1.0] * 500 + [0.0] * 500 + [1.0] * 100 + [0.0] * 900,
        }
    )
    tabla = tabla_por_tramo({"desarrollo": frame}, pds.pd)
    assert tabla["traffic_light"].tolist() == ["red", "green"]


def test_pava_ponderado_agrupa_lo_que_invierte_y_conserva_lo_que_no() -> None:
    ajustados, bloques = pava([0.1, 0.3, 0.2, 0.4], [1.0, 1.0, 3.0, 1.0])
    assert ajustados.tolist() == pytest.approx([0.1, 0.225, 0.225, 0.4])
    assert bloques == [[0], [1, 2], [3]]


@given(
    conteos=st.lists(
        st.tuples(st.integers(min_value=1, max_value=5000), st.floats(min_value=0, max_value=1)),
        min_size=1,
        max_size=10,
    ),
    ancla=st.floats(min_value=0.001, max_value=0.999),
)
def test_la_pd_no_decrece_empata_solo_si_se_igualo_y_promedia_el_ancla(
    conteos: list[tuple[int, float]], ancla: float
) -> None:
    n = [ng for ng, _ in conteos]
    d = [round(ng * f) for ng, f in conteos]
    pds = pd_por_tramo(n, d, ancla=ancla)
    assert all(b >= a for a, b in zip(pds.pd[:-1], pds.pd[1:], strict=True))
    igualados = {t for bloque in pds.equalized for t in bloque}
    for g, (a, b) in enumerate(zip(pds.pd[:-1], pds.pd[1:], strict=True), 1):
        if a == b:
            assert g in igualados and g + 1 in igualados
    promedio = sum(ng * p for ng, p in zip(n, pds.pd, strict=True)) / sum(n)
    assert promedio == pytest.approx(ancla, abs=1e-9)
    assert all(0.0 < p < 1.0 for p in pds.pd)


# ─────────────────────── tabla por tramo, cortes y denominadores cero ───────────────────────


def _muestra(
    scores: list[float], targets: list[float | None], cortes: tuple[float, ...]
) -> pd.DataFrame:
    frame = pd.DataFrame({"score": scores, "target": [np.nan if t is None else t for t in targets]})
    frame["grade"] = asignar_tramos(frame["score"].to_numpy(), cortes, mayor_es_menor_riesgo=True)
    return frame


def test_las_celdas_sin_denominador_quedan_vacias_y_nunca_en_cero() -> None:
    cortes = (500.5,)
    pd_tramo = (0.1, 0.4)
    muestras = {
        "desarrollo": _muestra([510, 520, 490, 480], [0, 1, 1, 0], cortes),
        "holdout": _muestra([510, 490], [0.0, 0.0], cortes),  # sin malos
        "oot": _muestra([510, 490], [1.0, 1.0], cortes),  # sin buenos
        "fuera_de_modelo": _muestra([510, 490, 495], [None, None, None], cortes),  # sin desenlace
    }
    tabla = tabla_de_cortes(
        muestras, cortes, pd_tramo, mayor_es_menor_riesgo=True, corte_declarado=999.0
    )
    rechazo_total = tabla.loc[tabla["declared"] & (tabla["sample"] == "desarrollo")].iloc[0]
    assert rechazo_total["n_approved"] == 0
    assert rechazo_total["approved_share"] == 0.0
    assert pd.isna(rechazo_total["approved_bad_rate"])
    assert pd.isna(rechazo_total["approved_expected_pd"])
    assert rechazo_total["bads_avoided_share"] == 1.0
    sin_malos = tabla.loc[(tabla["sample"] == "holdout") & (tabla["grades_approved"] == 1)].iloc[0]
    assert pd.isna(sin_malos["bads_avoided_share"])
    assert sin_malos["goods_rejected_share"] == 0.5
    sin_buenos = tabla.loc[(tabla["sample"] == "oot") & (tabla["grades_approved"] == 1)].iloc[0]
    assert pd.isna(sin_buenos["goods_rejected_share"])
    fuera = tabla.loc[(tabla["sample"] == "fuera_de_modelo") & (tabla["grades_approved"] == 1)]
    fila = fuera.iloc[0]
    assert (fila["n_scored"], fila["n_with_outcome"], fila["n_approved"]) == (3, 0, 1)
    assert fila["approved_share"] == pytest.approx(1 / 3)
    for columna in (
        "approved_bad_rate",
        "approved_expected_pd",
        "bads_avoided_share",
        "goods_rejected_share",
    ):
        assert pd.isna(fila[columna]), columna


@given(
    datos=st.lists(
        st.tuples(st.integers(min_value=300, max_value=700), st.booleans()), min_size=5, max_size=80
    ),
    cortes=st.lists(
        st.sampled_from([400.5, 450.5, 500.5, 550.5, 600.5]), min_size=1, max_size=4, unique=True
    ),
)
def test_la_tabla_de_cortes_es_monotona_y_cuadra_los_malos(
    datos: list[tuple[int, bool]], cortes: list[float]
) -> None:
    cortes_t = tuple(sorted(cortes))
    frame = _muestra([s for s, _ in datos], [float(b) for _, b in datos], cortes_t)
    pd_tramo = tuple(np.linspace(0.05, 0.6, len(cortes_t) + 1))
    tabla = tabla_de_cortes(
        {"desarrollo": frame}, cortes_t, pd_tramo, mayor_es_menor_riesgo=True, corte_declarado=None
    ).sort_values("grades_approved")
    aprobados = tabla["approved_share"].to_numpy(dtype=float)
    assert (np.diff(aprobados) >= 0).all()
    for columna in ("bads_avoided_share", "goods_rejected_share"):
        serie = tabla[columna]
        if serie.notna().all():
            assert (np.diff(serie.to_numpy(dtype=float)) <= 1e-12).all()
    malos = int(frame["target"].sum())
    for fila in tabla.itertuples():
        if pd.isna(fila.approved_bad_rate) or malos == 0:
            continue
        aprobados_malos = fila.approved_bad_rate * fila.n_approved_with_outcome
        evitados = fila.bads_avoided_share * malos
        assert aprobados_malos + evitados == pytest.approx(malos)


@given(
    datos=st.lists(
        st.tuples(st.integers(min_value=300, max_value=700), st.booleans()), min_size=5, max_size=60
    ),
    cortes=st.lists(
        st.sampled_from([400.5, 450.5, 500.5, 550.5]), min_size=1, max_size=3, unique=True
    ),
)
def test_las_dos_direcciones_del_puntaje_dan_la_tabla_espejada(
    datos: list[tuple[int, bool]], cortes: list[float]
) -> None:
    """Invertir el puntaje (s → -s) y su dirección forma los mismos tramos y la misma tabla."""
    cortes_t = tuple(sorted(cortes))
    espejo = tuple(sorted(-c for c in cortes_t))
    directa = pd.DataFrame({"score": [s for s, _ in datos], "target": [float(b) for _, b in datos]})
    invertida = directa.assign(score=-directa["score"])
    directa["grade"] = asignar_tramos(
        directa["score"].to_numpy(), cortes_t, mayor_es_menor_riesgo=True
    )
    invertida["grade"] = asignar_tramos(
        invertida["score"].to_numpy(), espejo, mayor_es_menor_riesgo=False
    )
    # Un corte entero del espejo separa distinto: s ≥ c del lado mayor se vuelve -s ≥ -c.
    # Con cortes x,5 y puntajes enteros nunca hay empate en el borde.
    assert directa["grade"].tolist() == invertida["grade"].tolist()
    pd_tramo = tuple(np.linspace(0.05, 0.6, len(cortes_t) + 1))
    columnas = ["grades_approved", "approved_share", "approved_bad_rate", "bads_avoided_share"]
    a = tabla_de_cortes(
        {"d": directa}, cortes_t, pd_tramo, mayor_es_menor_riesgo=True, corte_declarado=None
    )
    b = tabla_de_cortes(
        {"d": invertida}, espejo, pd_tramo, mayor_es_menor_riesgo=False, corte_declarado=None
    )
    pd.testing.assert_frame_equal(a[columnas], b[columnas])


def test_el_contraste_por_tramo_y_su_minimo_de_treinta() -> None:
    """Jeffreys como la validación: ``Beta.cdf(PD; d + ½, n - d + ½)``; bajo 30, sin contraste."""
    from scipy.stats import beta

    frame = pd.DataFrame(
        {
            "grade": [1] * 40 + [2] * (MIN_ROWS_EVALUABLE - 1),
            "target": [1.0] * 10 + [0.0] * 30 + [1.0] * 5 + [0.0] * (MIN_ROWS_EVALUABLE - 6),
        }
    )
    tabla = tabla_por_tramo({"holdout": frame}, (0.2, 0.3))
    primera, segunda = tabla.iloc[0], tabla.iloc[1]
    assert primera["jeffreys_p_value"] == pytest.approx(beta.cdf(0.2, 10.5, 30.5))
    assert primera["traffic_light"] in {"green", "amber", "red"}
    assert pd.isna(segunda["jeffreys_p_value"])
    assert segunda["traffic_light"] == "not_evaluable"
    diag = diagnostico_por_muestra(tabla)["holdout"]
    assert diag.not_evaluable_grades == (2,)
    assert diag.hhi == pytest.approx((40 / 69) ** 2 + (29 / 69) ** 2)


def test_la_monotonia_se_lee_sobre_los_tramos_evaluables() -> None:
    """Un tramo chico que invierte no cuenta (S41: la inversión espuria de un tramo de 6)."""
    frame = pd.DataFrame(
        {
            "grade": [1] * 40 + [2] * 6 + [3] * 40,
            "target": [1.0] * 4 + [0.0] * 36 + [0.0] * 6 + [1.0] * 20 + [0.0] * 20,
        }
    )
    tabla = tabla_por_tramo({"oot": frame}, (0.1, 0.2, 0.5))
    # 10 %, (0 % en 6 operaciones) y 50 %: el tramo 2 no es evaluable y no rompe el orden.
    assert diagnostico_por_muestra(tabla)["oot"].monotonic
    tercera = frame.assign(target=[1.0] * 20 + [0.0] * 20 + [0.0] * 6 + [1.0] * 2 + [0.0] * 38)
    diag = diagnostico_por_muestra(tabla_por_tramo({"oot": tercera}, (0.1, 0.2, 0.5)))["oot"]
    assert not diag.monotonic and diag.inversions == ((1, 3),)


def test_el_z_entre_vecinos_es_el_de_optbinning() -> None:
    from scipy.stats import norm

    p = z_entre_vecinos([100, 100], [10, 30])[0]
    p1, p2, pc = 0.1, 0.3, 0.2
    z = abs(p1 - p2) / math.sqrt(pc * (1 - pc) * (2 / 100))
    assert p == pytest.approx(2 * norm.sf(z))
    assert z_entre_vecinos([10, 10], [0, 0]) == [None]


# ─────────────────────── D-ESC-1: lo que la formación le pide a OptBinning ───────────────────────


@pytest.mark.parametrize(
    ("mayor_es_menor_riesgo", "tendencia"), [(True, "descending"), (False, "ascending")]
)
def test_la_formacion_pide_a_optbinning_las_cuatro_reglas(
    monkeypatch: pytest.MonkeyPatch, mayor_es_menor_riesgo: bool, tendencia: str
) -> None:
    """Las cuatro reglas son constantes y viajan tal cual al solver (§3.2).

    En las carteras del paquete la pre-segmentación de OptBinning (grupos de al menos 5 %) y la
    monotonía de los datos dejan los mismos tramos aunque una regla se pierda: el oráculo con datos
    reales no lo vería, así que se fija lo que se le pide al solver. El solver es el de la librería
    (``mip``/``bop``): ``cp`` se cuelga en variables continuas (D-ABA-5).
    """
    import bayesrisk.master_scale.engine as motor

    pedidos: list[dict[str, object]] = []

    class Espia:
        def __init__(self, **kwargs: object) -> None:
            pedidos.append(kwargs)
            self.splits = [500.5]
            self.status = "OPTIMAL"

        def fit(self, x: object, y: object) -> None:
            del x, y

    monkeypatch.setattr(motor, "_import_optimal_binning", lambda: Espia)
    formacion = motor.formar_cortes(
        np.array([480.0, 520.0]), np.array([1, 0]), mayor_es_menor_riesgo=mayor_es_menor_riesgo
    )
    assert formacion.cuts == (500.5,) and formacion.status == "OPTIMAL"
    assert pedidos == [
        {
            "name": "score",
            "dtype": "numerical",
            "monotonic_trend": tendencia,
            "min_bin_size": 0.05,
            "max_n_bins": 10,
            "max_pvalue": 0.05,
            "max_pvalue_policy": "consecutive",
            "solver": "mip",
            "mip_solver": "bop",
        }
    ]


def test_un_solver_sin_particion_deja_un_tramo_y_dice_por_que(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import bayesrisk.master_scale.engine as motor

    class Infactible:
        def __init__(self, **kwargs: object) -> None:
            self.splits = [500.5]
            self.status = "INFEASIBLE"

        def fit(self, x: object, y: object) -> None:
            del x, y

    class Roto(Infactible):
        def fit(self, x: object, y: object) -> None:
            raise RuntimeError("sin memoria")

    monkeypatch.setattr(motor, "_import_optimal_binning", lambda: Infactible)
    sin_particion = motor.formar_cortes(np.array([1.0]), np.array([0]), mayor_es_menor_riesgo=True)
    assert sin_particion.cuts == () and sin_particion.cause == "el solver terminó en INFEASIBLE"
    monkeypatch.setattr(motor, "_import_optimal_binning", lambda: Roto)
    roto = motor.formar_cortes(np.array([1.0]), np.array([0]), mayor_es_menor_riesgo=True)
    assert roto.cuts == () and roto.status == "ERROR" and "sin memoria" in str(roto.cause)


@pytest.mark.parametrize("ancla", [1e-10, 1e-6, 0.5, 1 - 1e-6, 1 - 1e-10])
def test_el_delta_se_encuentra_con_anclas_extremas(ancla: float) -> None:
    """El intervalo de ``δ`` sale del ancla y de las tasas, no de ±20 fijo (pasada 1 de Codex):
    con un ancla de 1e-10 el ±20 no cambiaba de signo y la etapa abortaba."""
    pds = pd_por_tramo([100, 200, 50], [3, 30, 25], ancla=ancla)
    promedio = sum(n * p for n, p in zip([100, 200, 50], pds.pd, strict=True)) / 350
    assert promedio == pytest.approx(ancla, rel=1e-6)
    assert all(0.0 < p < 1.0 for p in pds.pd)
    assert list(pds.pd) == sorted(pds.pd)


def test_conteos_imposibles_son_un_error_de_la_etapa() -> None:
    """Un error de la escala es de dominio (la corrida lo absorbe y lo dice), no un ValueError."""
    from bayesrisk.master_scale.exceptions import MasterScaleFitError

    with pytest.raises(MasterScaleFitError, match="al menos una operación"):
        pd_por_tramo([10, 0], [1, 0], ancla=0.1)
    with pytest.raises(MasterScaleFitError, match="ancla"):
        pd_por_tramo([10], [1], ancla=1.0)


@pytest.mark.parametrize(
    ("n", "d", "ancla"),
    [([100], [1], 1e-310), ([100, 100], [0, 100], 1 - 1e-12), ([50, 50], [0, 50], 1e-300)],
)
def test_la_pd_del_tramo_queda_dentro_de_cero_y_uno_con_anclas_al_borde(
    n: list[int], d: list[int], ancla: float
) -> None:
    """Pasada 2 de Codex: con un ancla subnormal la sigmoide desbordaba y brentq fallaba fuera de
    la etapa; con un ancla junto a 1 una PD llegaba a 1,0 y la tarjeta la rechazaba."""
    from bayesrisk.scorecard.bundle import _validate_master_scale

    pds = pd_por_tramo(n, d, ancla=ancla)
    assert all(0.0 < p < 1.0 for p in pds.pd), pds.pd
    assert list(pds.pd) == sorted(pds.pd)
    _validate_master_scale(
        {
            "cuts": [500.5 + i for i in range(len(n) - 1)],
            "grade_pd": list(pds.pd),
            "approval_cutoff": None,
            "source": "formed",
        }
    )


def test_vecinos_sin_varianza_tampoco_se_distinguen() -> None:
    """Pasada 2 de Codex: dos tramos de la institución sin malos tienen la misma tasa; el Z no
    tiene varianza (p indefinido) y no se alertaba. Se declaran sin p-valor."""
    from bayesrisk.master_scale.engine import vecinos_que_no_se_distinguen

    assert vecinos_que_no_se_distinguen([200, 100, 100], [0, 0, 20]) == ((1, 2, None),)
    assert vecinos_que_no_se_distinguen([100, 100], [10, 30]) == ()
    (par,) = vecinos_que_no_se_distinguen([100, 100], [10, 12])
    assert par[:2] == (1, 2) and par[2] is not None and par[2] > 0.05
