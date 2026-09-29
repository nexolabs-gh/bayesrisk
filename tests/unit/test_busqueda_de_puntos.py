"""La búsqueda de puntos casa el WoE de una fila con su tramo aunque difiera en un redondeo (D-BPT).

Medido con la muestra SBA 7(a) de la prueba de Cami y bayesrisk 2.2.0: el WoE que OptBinning
recalcula al transformar difiere del de la tabla en el último bit (≤ 2,2e-16) en el 81,6 % de las
celdas; el escalador exigía igualdad exacta, las mandaba a la fórmula y registraba `bin_no_visto`.
Por la fórmula un ajuste manual de puntos no llegaba a la corrida: 23.565 filas de «SBA Express»
con 64 puntos en la corrida y 7 en la tabla y el bundle.

- **D-BPT-1**: un WoE casa con la fila de su variable **más cercana a 1e-12 o menos** —la exacta
  siempre gana; a igual distancia, la primera—; un ajuste manual sobre cualquier tramo de un grupo
  indistinguible por WoE se rechaza al ajustar (el bin asignado de D-FAL-1 no cuenta).
- **D-BPT-2**: `bin_no_visto` sólo para un WoE sin fila a 1e-12.

Contrato: ``docs/design/_ENMIENDA-BUSQUEDA-DE-PUNTOS.md``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import bayesrisk
import bayesrisk.scorecard.scaler as scaler_module
from bayesrisk.core.audit import InMemoryAuditSink
from bayesrisk.scorecard.bundle import FittedScorecardBundle
from bayesrisk.scorecard.config import PointOverrideConfig, RoundingMethod
from bayesrisk.scorecard.exceptions import ScorecardFitError
from bayesrisk.scorecard.scaler import PointsScaler

_FRONTERA = "2021-07-01"


def _ajustar(
    tablas: dict[str, pd.DataFrame],
    *,
    ajustes: tuple[PointOverrideConfig, ...] = (),
    redondeo: RoundingMethod = "nearest_integer",
    beta: float = -0.8,
    alpha: float = -0.4,
    asignados: dict[str, list[str]] | None = None,
    audit: InMemoryAuditSink | None = None,
) -> PointsScaler:
    """Un escalador de una variable, ``canal``, sobre la tabla dada."""
    coeficientes = pd.DataFrame(
        [
            {"feature": "intercept", "woe_column": "const", "beta": alpha},
            {"feature": "canal", "woe_column": "canal__woe", "beta": beta},
        ]
    )
    return PointsScaler(rounding_method=redondeo, point_overrides=ajustes).fit(
        coefficients=coeficientes,
        final_features=("canal",),
        final_woe_columns=("canal__woe",),
        binning_tables=tablas,
        woe_column_map={"canal": "canal__woe"},
        audit=audit if audit is not None else InMemoryAuditSink(),
        assigned_bins=asignados,
    )


def _puntos(scaler: PointsScaler, woes: list[float]) -> list[float | int]:
    return list(scaler.transform(pd.DataFrame({"canal__woe": woes}))["canal__points"])


def _de_la_tabla(scaler: PointsScaler, etiqueta: str) -> float | int:
    tarjeta = scaler.scorecard_
    return tarjeta.loc[tarjeta["bin_label"].eq(etiqueta), "points"].item()


def _reglas(audit: InMemoryAuditSink) -> list[str]:
    return [str(e.payload["regla"]) for e in audit.events if e.kind == "decision"]


def _ajuste(etiqueta: str, puntos: int = 7) -> PointOverrideConfig:
    return PointOverrideConfig(feature="canal", bin_label=etiqueta, points=puntos, reason="prueba")


# ───────────────────────── D-BPT-1: casar a 1e-12 ─────────────────────────


@pytest.mark.parametrize("redondeo", ["none", "nearest_integer"])
def test_un_woe_a_un_ulp_de_su_tramo_recibe_sus_puntos_sin_bin_no_visto(
    redondeo: RoundingMethod,
) -> None:
    """🔴 Nace rojo: iba por fórmula y registraba `bin_no_visto` en casi todas las filas; sin
    redondeo, a 1e-13 la fórmula ya daba otro float que la tabla (en el SBA, 8.126 puntajes de la
    corrida distintos a los del bundle en ~1e-13)."""
    audit = InMemoryAuditSink()
    tablas = {"canal": pd.DataFrame({"Bin": ["web", "sucursal"], "WoE": [0.3, -0.7]})}
    scaler = _ajustar(tablas, redondeo=redondeo, audit=audit)
    arriba, abajo = math.nextafter(0.3, 1.0), math.nextafter(-0.7, -1.0)
    web, sucursal = _de_la_tabla(scaler, "web"), _de_la_tabla(scaler, "sucursal")

    assert _puntos(scaler, [arriba, 0.3 + 1e-13, abajo]) == [web, web, sucursal]
    assert scaler.unseen_bins_ == {}
    assert "bin_no_visto" not in _reglas(audit)


def test_con_un_ajuste_manual_la_fila_a_un_ulp_recibe_el_ajuste() -> None:
    """🔴 Nace rojo: la fórmula no conocía el ajuste (en el SBA, 64 puntos en vez de 7)."""
    tablas = {"canal": pd.DataFrame({"Bin": ["web", "sucursal"], "WoE": [0.3, -0.7]})}
    scaler = _ajustar(tablas, ajustes=(_ajuste("web"),))

    assert _de_la_tabla(scaler, "web") == 7
    assert _puntos(scaler, [math.nextafter(0.3, 1.0), math.nextafter(0.3, 0.0)]) == [7, 7]


def test_el_bin_asignado_de_d_fal_1_hereda_el_ajuste_de_su_referencia_tambien_a_un_ulp() -> None:
    """🔴 El ajuste sobre la referencia sigue permitido (el bin asignado no forma grupo con ella)
    y lo reciben, a un ulp, las filas de la referencia y las del bin asignado."""
    tablas = {
        "canal": pd.DataFrame(
            {"Bin": ["web", "sucursal", "Special", "Missing"], "WoE": [0.4, -0.5, 0.0, -0.5]}
        )
    }
    audit = InMemoryAuditSink()
    scaler = _ajustar(
        tablas, ajustes=(_ajuste("sucursal"),), asignados={"canal": ["Missing"]}, audit=audit
    )

    assert _de_la_tabla(scaler, "sucursal") == _de_la_tabla(scaler, "Missing") == 7
    assert "point_override_heredado" in _reglas(audit)
    assert _puntos(scaler, [math.nextafter(-0.5, 0.0), math.nextafter(-0.5, -1.0)]) == [7, 7]


def test_la_exacta_gana_aunque_sea_la_segunda_y_a_igual_distancia_la_primera() -> None:
    """🔴 Dos filas a menos de 1e-12 sin ajuste: cada WoE exacto da su propia fila (no «la primera
    dentro de la tolerancia») y el punto medio, a igual distancia, la primera."""
    paso = 2.0**-41  # ≈ 4,5e-13: dentro de la tolerancia y representable exacto junto a 0,5
    tablas = {"canal": pd.DataFrame({"Bin": ["a", "b"], "WoE": [0.5, 0.5 + paso]})}
    scaler = _ajustar(tablas, redondeo="none")
    puntos_a, puntos_b = _de_la_tabla(scaler, "a"), _de_la_tabla(scaler, "b")
    assert puntos_a != puntos_b  # la condición de la prueba: sin redondeo, las dos filas difieren

    assert _puntos(scaler, [0.5 + paso, 0.5, 0.5 + paso / 2]) == [puntos_b, puntos_a, puntos_a]
    assert scaler.unseen_bins_ == {}


@pytest.mark.parametrize(
    ("distancia", "por_formula"), [(0.9e-12, False), (1.1e-12, True), (1e-9, True)]
)
def test_un_woe_a_mas_de_1e_12_de_toda_fila_va_por_formula_y_se_registra(
    distancia: float, por_formula: bool
) -> None:
    """D-BPT-2: sólo un WoE sin fila a 1e-12 va por fórmula y registra `bin_no_visto`."""
    audit = InMemoryAuditSink()
    tablas = {"canal": pd.DataFrame({"Bin": ["web", "sucursal"], "WoE": [0.3, -0.7]})}
    scaler = _ajustar(tablas, ajustes=(_ajuste("web"),), redondeo="none", audit=audit)

    (puntos,) = _puntos(scaler, [0.3 + distancia])

    if por_formula:
        assert puntos != 7
        assert scaler.unseen_bins_ == {"canal": 1}
        assert _reglas(audit).count("bin_no_visto") == 1
    else:
        assert puntos == 7
        assert scaler.unseen_bins_ == {}
        assert "bin_no_visto" not in _reglas(audit)


@pytest.mark.parametrize("redondeo", ["nearest_integer", "floor_integer", "ceil_integer"])
def test_un_puntaje_junto_a_un_borde_de_redondeo_da_el_entero_de_la_tabla(
    redondeo: RoundingMethod,
) -> None:
    """🔴 El límite declarado: un WoE a menos de 1e-12 del de su tramo que cruza el borde de
    redondeo daba, por la fórmula, otro entero que la tabla (y el bundle)."""
    beta, alpha = -1.0, 0.0
    factor = 20.0 / math.log(2.0)
    offset = 600.0 - factor * math.log(50.0)
    borde = 480.5 if redondeo == "nearest_integer" else 480.0
    en_el_borde = (borde - offset) / factor  # raw(w) = offset - factor·(beta·w + alpha), beta = -1
    tramo, fila = en_el_borde + 3e-13, en_el_borde - 3e-13
    tablas = {"canal": pd.DataFrame({"Bin": ["web", "sucursal"], "WoE": [tramo, 0.4]})}
    scaler = _ajustar(tablas, redondeo=redondeo, beta=beta, alpha=alpha)

    def _formula(woe: float) -> float | int:
        crudo = scaler_module._raw_points(
            direction="higher_is_lower_risk",
            factor=scaler.factor_,
            offset_share=scaler.offset_,
            beta=beta,
            woe=woe,
            intercept_share=scaler.intercept_share_,
        )
        return scaler_module._published_points(crudo, redondeo)

    assert _formula(fila) != _formula(tramo)  # la condición de la prueba: cruza el borde
    assert _puntos(scaler, [fila]) == [_de_la_tabla(scaler, "web")]


# ───────────────────────── D-BPT-1: el ajuste ambiguo se rechaza ─────────────────────────


@pytest.mark.parametrize("ajustado", ["a", "b"])
def test_un_ajuste_sobre_cualquier_tramo_de_un_grupo_indistinguible_se_rechaza(
    ajustado: str,
) -> None:
    """🔴 Nace rojo: corría y corrida y bundle divergían. Sobre el segundo, el ajuste no llegaba
    nunca a la corrida; sobre el primero, llegaba también a las filas del segundo. El grupo se
    arma sea cual sea la posición de sus tramos, y el mensaje los nombra en el orden de la tabla."""
    tablas = {"canal": pd.DataFrame({"Bin": ["a", "c", "b"], "WoE": [0.2, -0.3, 0.2 + 5e-13]})}

    with pytest.raises(ScorecardFitError, match=f"sobre «{ajustado}» de «canal».*«a», «b»"):
        _ajustar(tablas, ajustes=(_ajuste(ajustado),))
    assert _de_la_tabla(_ajustar(tablas, ajustes=(_ajuste("c"),)), "c") == 7


def test_un_regular_de_woe_cero_forma_grupo_con_los_tramos_auxiliares_vacios() -> None:
    """Conservador y declarado: los tramos auxiliares vacíos (WoE 0) sí cuentan para el grupo."""
    tablas = {
        "canal": pd.DataFrame(
            {"Bin": ["web", "sucursal", "Special", "Missing"], "WoE": [0.0, 0.5, 0.0, 0.0]}
        )
    }

    with pytest.raises(ScorecardFitError, match="«web», «Valores especiales», «Faltantes»"):
        _ajustar(tablas, ajustes=(_ajuste("web"),))


# ───────────────────────── de punta a punta, con OptBinning real ─────────────────────────


def _cartera(n: int = 1600, *, semilla: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    ingreso = rng.normal(size=n)
    segmento = rng.choice(np.array(["A", "B", "C"], dtype=object), size=n)
    logit = -1.3 - 0.9 * ingreso + (segmento == "C") * 0.9 - (segmento == "A") * 0.5
    y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-logit))).astype(float)
    return pd.DataFrame(
        {
            "loan_id": [f"op-{i:05d}" for i in range(n)],
            "fecha": pd.date_range("2019-01-01", "2021-12-31", periods=n),
            "ingreso": ingreso,
            "segmento": segmento,
            "bad_flag": y,
        }
    )


@pytest.fixture(scope="module")
def _corrida(tmp_path_factory: pytest.TempPathFactory) -> tuple[bayesrisk.Scorecard, pd.DataFrame]:
    pytest.importorskip("optbinning")
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        datos = _cartera()
        carpeta = tmp_path_factory.mktemp("busqueda")
        ruta = carpeta / "cartera.parquet"
        datos.to_parquet(ruta)
        sc = bayesrisk.Scorecard(
            ruta,
            target="bad_flag",
            id="loan_id",
            date="fecha",
            oot_from=_FRONTERA,
            name="busqueda",
            run_dir=carpeta / "run",
        )
        sc._echo = lambda _texto: None
        sc.run()
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    return sc, datos


def _celdas_a_un_ulp(study: object) -> dict[tuple[str, str], int]:
    """Por (variable, tramo), las filas puntuadas cuyo WoE no es exactamente el de la tabla."""
    artefactos = study.artifacts  # type: ignore[attr-defined]
    woe = artefactos.get("binning", "woe_frame")
    bins = artefactos.get("binning", "bin_frame")
    filas = artefactos.get("scorecard", "score").index
    tarjeta = artefactos.get("scorecard", "scorecard")
    conteo: dict[tuple[str, str], int] = {}
    for feature in artefactos.get("model", "final_features"):
        propia = tarjeta.loc[tarjeta["feature"].eq(feature)]
        woe_de = {str(r["bin_label"]): float(r["woe"]) for _, r in propia.iterrows()}
        etiquetas = bins.loc[filas, f"{feature}__bin"].astype(str)
        valores = woe.loc[filas, f"{feature}__woe"].astype("float64")
        for etiqueta, valor in zip(etiquetas, valores, strict=True):
            if etiqueta in woe_de and valor != woe_de[etiqueta]:
                clave = (str(feature), etiqueta)
                conteo[clave] = conteo.get(clave, 0) + 1
    return conteo


def _aplicar(bundle: FittedScorecardBundle, datos: pd.DataFrame, indice: pd.Index) -> pd.DataFrame:
    aplicado = bundle.apply(datos.loc[indice].drop(columns=["bad_flag"])).application_frame
    aplicado.index = indice[aplicado["input_position"].to_numpy()]
    return aplicado


def test_la_corrida_casa_sus_tramos_sin_registrar_bin_no_visto(
    _corrida: tuple[bayesrisk.Scorecard, pd.DataFrame],
) -> None:
    """🔴 Nace rojo: con OptBinning real, las filas cuyo WoE difiere un ulp del de su tramo iban
    por fórmula y el trail decía `bin_no_visto` de filas observadas."""
    sc, _ = _corrida
    assert sum(_celdas_a_un_ulp(sc.study).values()) > 0  # la condición de la prueba
    trail = Path(sc.project_dir) / "run" / "audit_trail.jsonl"
    eventos = [json.loads(linea) for linea in trail.read_text(encoding="utf-8").splitlines()]
    reglas = [e["payload"].get("regla") for e in eventos if e["kind"] == "decision"]
    assert "bin_no_visto" not in reglas


@pytest.mark.parametrize("variante", ["override", "sin_redondeo"])
def test_con_un_ajuste_o_sin_redondeo_corrida_tabla_y_bundle_coinciden(
    _corrida: tuple[bayesrisk.Scorecard, pd.DataFrame], tmp_path: Path, variante: str
) -> None:
    """🔴 Con el ajuste nace rojo: sobre un tramo con filas a un ulp no llegaba a la corrida (sí a
    la tabla y al bundle). Sin redondeo es una guarda: con esta cartera la fórmula a un ulp daba el
    mismo float; en el SBA no (8.126 puntajes distintos, medido con la 2.2.0)."""
    sc, datos = _corrida
    (feature, etiqueta), _ = max(_celdas_a_un_ulp(sc.study).items(), key=lambda par: par[1])
    tarjeta = sc.config.scorecard
    if variante == "override":
        ajuste = PointOverrideConfig(feature=feature, bin_label=etiqueta, points=7, reason="prueba")
        tarjeta = tarjeta.model_copy(update={"point_overrides": (ajuste,)})
    else:
        tarjeta = tarjeta.model_copy(update={"rounding_method": "none"})
    st = bayesrisk.run(sc.config.model_copy(update={"scorecard": tarjeta}), run_dir=tmp_path)
    assert st.run_context.status == "done", st.run_context.error

    puntaje = st.artifacts.get("scorecard", "score")
    bins = st.artifacts.get("binning", "bin_frame")
    if variante == "override":
        del_tramo = bins.loc[puntaje.index, f"{feature}__bin"].astype(str).eq(etiqueta)
        en_tramo = puntaje.index[del_tramo.to_numpy()]
        assert len(en_tramo) > 0
        assert set(puntaje.loc[en_tramo, f"{feature}__points"]) == {7}
        filas = en_tramo
    else:
        filas = puntaje.index
    aplicado = _aplicar(FittedScorecardBundle.from_study(st), datos, filas)
    np.testing.assert_array_equal(
        aplicado["score"].to_numpy(dtype="float64"),
        puntaje.loc[filas, "score"].to_numpy(dtype="float64"),
    )
