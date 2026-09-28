"""Una categoría que no existía en Desarrollo: una sola regla para la corrida y el bundle (D-NOV).

Medido con la muestra SBA 7(a) de la prueba de Cami: 58 operaciones OOT con un ``programa`` nuevo
recibían en la corrida el riesgo promedio (65 puntos, los de las filas vacías ``Special``/
``Missing``) y el bundle las rechazaba.

- **D-NOV-1**: reciben el WoE de su **tramo de referencia** —el regular de mayor tasa de malos, el
  criterio de D-FAL-1, fijado al transformar— y los puntos que la búsqueda del escalador da a ese
  WoE; el bundle nuevo (esquema 2) los congela y el de esquema 1 sigue rechazando la fila.
- **D-NOV-2**: ``binning.cat_unknown`` sólo admite el vacío; otro valor se rechaza al validar.
- **D-NOV-3**: la alerta de D-TTD-5 sigue, y desde el 10 % de una muestra se suma la de cambio de
  dominio, repetida en la selección si la variable entra.
- **D-NOV-4**: trail, tabla de no vistas, resumen, tabla de puntos del resumen y del informe.

Usan **OptBinning real**: la cartera sintética tiene un ``segmento`` «D» que sólo aparece después de
la frontera OOT, en OOT y fuera del ajuste.

Contrato: ``docs/design/_ENMIENDA-CATEGORIAS-NO-VISTAS.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest

import bayesrisk
from bayesrisk.binning.config import BinningConfig
from bayesrisk.binning.transformer import WoEBinner, _peor_tramo_regular
from bayesrisk.core.audit import InMemoryAuditSink
from bayesrisk.core.exceptions import ConfigError
from bayesrisk.guided.summaries import _alertas_cambio_de_dominio, _alertas_categorias_no_vistas
from bayesrisk.report.builder import _referencias_no_vistas, _rotulos_de_tramos
from bayesrisk.report.renderer import _table_view
from bayesrisk.scorecard.bundle import FittedScorecardBundle, _bundle_hash
from bayesrisk.scorecard.config import PointOverrideConfig
from bayesrisk.scorecard.exceptions import ScorecardBundleError
from bayesrisk.scorecard.scaler import PointsScaler, filas_de_referencia_no_vista

pytest.importorskip("optbinning")

_FRONTERA = "2021-07-01"


# ───────────────────────── fixtures ─────────────────────────


def _cartera(n: int = 1600, *, semilla: int = 11) -> pd.DataFrame:
    """``segmento`` «D» sólo tras la frontera OOT (≈20 % de OOT) y en filas sin desenlace."""
    rng = np.random.default_rng(semilla)
    fechas = pd.date_range("2019-01-01", "2021-12-31", periods=n)
    ingreso = rng.normal(size=n)
    segmento = rng.choice(np.array(["A", "B", "C"], dtype=object), size=n)
    tardias = np.asarray(fechas >= pd.Timestamp(_FRONTERA))
    segmento[tardias & (rng.uniform(size=n) < 0.2)] = "D"
    logit = -1.3 - 0.9 * ingreso + (segmento == "C") * 0.9 - (segmento == "A") * 0.5
    y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-logit))).astype(float)
    y[rng.uniform(size=n) < 0.1] = np.nan
    return pd.DataFrame(
        {
            "loan_id": [f"op-{i:05d}" for i in range(n)],
            "fecha": fechas,
            "ingreso": ingreso,
            "segmento": segmento,
            "bad_flag": y,
        }
    )


def _correr(tmp_path: Path, datos: pd.DataFrame) -> bayesrisk.Scorecard:
    ruta = tmp_path / "cartera.parquet"
    datos.to_parquet(ruta)
    sc = bayesrisk.Scorecard(
        ruta,
        target="bad_flag",
        id="loan_id",
        date="fecha",
        oot_from=_FRONTERA,
        name="no_vistas",
        run_dir=tmp_path / "run",
    )
    sc._echo = lambda _texto: None
    sc.run()
    return sc


@pytest.fixture(scope="module")
def _corrida(tmp_path_factory: pytest.TempPathFactory) -> tuple[bayesrisk.Scorecard, pd.DataFrame]:
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        datos = _cartera()
        sc = _correr(tmp_path_factory.mktemp("no_vistas"), datos)
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    assert "segmento" in sc.study.artifacts.get("model", "final_features")
    return sc, datos


def _nuevas(datos: pd.DataFrame, indice: pd.Index) -> pd.Index:
    return indice[datos.loc[indice, "segmento"].eq("D").to_numpy()]


def _aplicar(bundle: FittedScorecardBundle, datos: pd.DataFrame, indice: pd.Index) -> pd.DataFrame:
    aplicado = bundle.apply(datos.loc[indice].drop(columns=["bad_flag"])).application_frame
    aplicado.index = indice[aplicado["input_position"].to_numpy()]
    return aplicado


def _a_esquema_1(bundle: FittedScorecardBundle) -> FittedScorecardBundle:
    """El manifiesto que escribía una librería anterior a D-NOV, con las mismas reglas."""
    manifest = bundle.manifest
    del manifest["unseen_reference"]
    manifest["schema_version"] = 1
    manifest["treatment_policy"]["unseen"] = "not_scorable"
    manifest["bundle_hash"] = _bundle_hash(manifest)
    return FittedScorecardBundle(manifest=manifest, rules=bundle._rules)


# ───────────────────────── D-NOV-1: la regla ─────────────────────────


def test_el_tramo_de_referencia_es_el_regular_de_menor_woe_y_ante_un_empate_el_primero() -> None:
    """🔴 El criterio de D-FAL-1: ni ``Special``/``Missing``, ni totales, ni tramos vacíos."""
    tabla = pd.DataFrame(
        {
            "Bin": [
                np.array(["A"], dtype=object),
                np.array(["B"], dtype=object),
                np.array(["C"], dtype=object),
                np.array(["E"], dtype=object),
                "Special",
                "Missing",
                "",
            ],
            "Count": [10, 10, 10, 0, 5, 3, 38],
            "WoE": [0.2, -0.3, -0.3, -2.0, -0.9, -1.1, 0.0],
        },
        index=[0, 1, 2, 3, 4, 5, "Totals"],
    )
    assert _peor_tramo_regular(tabla) == (1, "['B']", -0.3)


def test_la_fila_no_vista_recibe_el_woe_exacto_y_el_rotulo_de_su_peor_tramo() -> None:
    """🔴 Nace rojo: OptBinning le daba WoE ≈ 0 y el rótulo «unknown»."""
    datos = _cartera(n=1200)
    desarrollo = datos.loc[datos["segmento"].ne("D") & datos["bad_flag"].notna()]
    binner = WoEBinner(feature_columns=("ingreso", "segmento"), categorical_columns=("segmento",))
    binner.fit(desarrollo[["ingreso", "segmento"]], desarrollo["bad_flag"].astype(int))
    tabla = binner.tables_["segmento"]
    posicion, etiqueta, woe = _peor_tramo_regular(tabla)  # type: ignore[misc]
    assert binner.unseen_reference_["segmento"].reference_bin == etiqueta
    assert binner.unseen_reference_["segmento"].woe == woe == float(tabla["WoE"].iloc[posicion])

    nuevas = datos.loc[datos["segmento"].eq("D"), ["ingreso", "segmento"]]
    vistas = datos.loc[datos["segmento"].ne("D"), ["ingreso", "segmento"]].head(50)
    assert set(binner.transform(nuevas)["segmento__woe"]) == {woe}
    assert binner.unknown_categories_ == {"segmento": len(nuevas.index)}
    assert set(binner.transform_bins(nuevas)["segmento__bin"]) == {etiqueta}
    # Las filas vistas no cambian: su tramo es el de siempre.
    rotulos = binner.transform_bins(vistas)["segmento__bin"]
    assert set(rotulos) <= {str(valor) for valor in tabla["Bin"]}


def test_corrida_y_bundle_dan_los_mismos_puntos_en_oot_y_fuera_del_ajuste(
    _corrida: tuple[bayesrisk.Scorecard, pd.DataFrame],
) -> None:
    """🔴 Nace rojo: la corrida les daba el riesgo promedio y el bundle las rechazaba."""
    sc, datos = _corrida
    st = sc.study
    referencia = st.artifacts.get("binning", "process").unseen_reference_["segmento"]
    tarjeta = st.artifacts.get("scorecard", "scorecard")
    (fila,) = filas_de_referencia_no_vista(
        tarjeta.loc[tarjeta["feature"].eq("segmento")], {"segmento": referencia}
    ).values()
    bundle = FittedScorecardBundle.from_study(st)
    assert bundle.manifest["schema_version"] == 2
    assert bundle.manifest["treatment_policy"]["unseen"] == "reference_bin"
    assert bundle.manifest["unseen_reference"]["segmento"] == {
        "bin_index": fila["bin_index"],
        "woe": referencia.woe,
        "raw_points": fila["raw_points"],
        "points": fila["points"],
    }
    for clave in ("score", "out_of_model_score"):
        puntaje = st.artifacts.get("scorecard", clave)
        nuevas = _nuevas(datos, puntaje.index)
        assert len(nuevas) > 0, clave
        assert set(puntaje.loc[nuevas, "segmento__points"]) == {fila["points"]}, clave
        aplicado = _aplicar(bundle, datos, nuevas)
        assert set(aplicado["scoring_status"]) == {"scored"}, clave
        assert all(
            "categoria_no_vista_como_referencia" in codigos for codigos in aplicado["warning_codes"]
        )
        np.testing.assert_array_equal(
            aplicado["score"].to_numpy(dtype="float64"),
            puntaje.loc[nuevas, "score"].to_numpy(dtype="float64"),
        )
    woe = st.artifacts.get("binning", "woe_frame")
    oot = _nuevas(datos, woe.index[woe["partition"].eq("oot")])
    assert set(woe.loc[oot, "segmento__woe"]) == {referencia.woe}
    bins = st.artifacts.get("binning", "bin_frame")
    assert set(bins.loc[oot, "segmento__bin"]) == {referencia.reference_bin}


@pytest.mark.parametrize("variante", ["override", "sin_redondeo"])
def test_con_override_sobre_la_referencia_o_sin_redondeo_corrida_y_bundle_coinciden(
    _corrida: tuple[bayesrisk.Scorecard, pd.DataFrame], tmp_path: Path, variante: str
) -> None:
    """🔴 El bundle congela la fila que resuelve el escalador, con su ajuste manual y su
    redondeo: los puntos de la fila no vista son los de su referencia también así."""
    sc, datos = _corrida
    referencia = sc.study.artifacts.get("binning", "process").unseen_reference_["segmento"]
    tarjeta = sc.config.scorecard
    if variante == "override":
        ajuste = PointOverrideConfig(
            feature="segmento", bin_label=referencia.reference_bin, points=7, reason="prueba"
        )
        tarjeta = tarjeta.model_copy(update={"point_overrides": (ajuste,)})
    else:
        tarjeta = tarjeta.model_copy(update={"rounding_method": "none"})
    st = bayesrisk.run(sc.config.model_copy(update={"scorecard": tarjeta}), run_dir=tmp_path)
    assert st.run_context.status == "done", st.run_context.error
    puntaje = st.artifacts.get("scorecard", "score")
    nuevas = _nuevas(datos, puntaje.index)
    esperado = st.artifacts.get("binning", "process").unseen_reference_["segmento"]
    (fila,) = filas_de_referencia_no_vista(
        st.artifacts.get("scorecard", "scorecard"), {"segmento": esperado}
    ).values()
    if variante == "override":
        assert fila["points"] == 7
    else:
        assert not float(fila["points"]).is_integer()
    assert set(puntaje.loc[nuevas, "segmento__points"]) == {fila["points"]}
    aplicado = _aplicar(FittedScorecardBundle.from_study(st), datos, nuevas)
    np.testing.assert_array_equal(
        aplicado["score"].to_numpy(dtype="float64"),
        puntaje.loc[nuevas, "score"].to_numpy(dtype="float64"),
    )


def test_con_dos_filas_del_mismo_woe_y_un_override_en_la_segunda_manda_la_primera() -> None:
    """🔴 La corrida (búsqueda del escalador) y el bundle (la misma función) dan la primera."""
    tablas = {
        "canal": pd.DataFrame({"Bin": ["web", "sucursal", "fono"], "WoE": [0.4, -0.5, -0.5]}),
    }
    coeficientes = pd.DataFrame(
        [
            {"feature": "intercept", "woe_column": "const", "beta": -0.4},
            {"feature": "canal", "woe_column": "canal__woe", "beta": -0.8},
        ]
    )
    ajuste = PointOverrideConfig(feature="canal", bin_label="fono", points=1, reason="prueba")
    scaler = PointsScaler(point_overrides=(ajuste,)).fit(
        coefficients=coeficientes,
        final_features=("canal",),
        final_woe_columns=("canal__woe",),
        binning_tables=tablas,
        woe_column_map={"canal": "canal__woe"},
        audit=InMemoryAuditSink(),
    )
    referencia = SimpleNamespace(woe=-0.5)
    fila = filas_de_referencia_no_vista(scaler.scorecard_, {"canal": referencia})["canal"]
    assert (fila["bin_label"], fila["source"]) == ("sucursal", "binning_table")
    puntos = scaler.transform(pd.DataFrame({"canal__woe": [-0.5]}))["canal__points"]
    assert puntos.tolist() == [fila["points"]]
    assert fila["points"] != 1


def test_con_el_signo_invertido_la_fila_sigue_a_su_tramo() -> None:
    """🔴 El límite declarado, el mismo de D-FAL-1: con un coeficiente de signo invertido la
    referencia sigue siendo el tramo de mayor riesgo observado, que ahora puntúa alto."""
    tablas = {"canal": pd.DataFrame({"Bin": ["web", "sucursal"], "WoE": [0.4, -0.5]})}
    coeficientes = pd.DataFrame(
        [
            {"feature": "intercept", "woe_column": "const", "beta": -0.4},
            {"feature": "canal", "woe_column": "canal__woe", "beta": 0.8},
        ]
    )
    scaler = PointsScaler().fit(
        coefficients=coeficientes,
        final_features=("canal",),
        final_woe_columns=("canal__woe",),
        binning_tables=tablas,
        woe_column_map={"canal": "canal__woe"},
    )
    fila = filas_de_referencia_no_vista(scaler.scorecard_, {"canal": SimpleNamespace(woe=-0.5)})
    assert fila["canal"]["bin_label"] == "sucursal"
    assert fila["canal"]["points"] == scaler.scorecard_["points"].max()


# ───────────────────────── D-NOV-1 §1.2: el bundle versionado ─────────────────────────


def test_un_bundle_de_esquema_1_carga_y_sigue_rechazando_la_fila(
    _corrida: tuple[bayesrisk.Scorecard, pd.DataFrame], tmp_path: Path
) -> None:
    """🔴 Un bundle guardado antes de la enmienda no cambia su resultado; su lineage dice 1."""
    sc, datos = _corrida
    antiguo = _a_esquema_1(FittedScorecardBundle.from_study(sc.study))
    cargado = FittedScorecardBundle.load(antiguo.save(tmp_path / "bundle"))
    puntaje = sc.study.artifacts.get("scorecard", "score")
    nuevas = _nuevas(datos, puntaje.index)
    resultado = cargado.apply(datos.loc[nuevas].drop(columns=["bad_flag"]))
    assert set(resultado.application_frame["scoring_status"]) == {"not_scorable"}
    assert (
        resultado.application_frame["not_scorable_reason"]
        .astype(str)
        .str.contains("categoria_no_observada_en_fit")
        .all()
    )
    assert resultado.lineage["bundle_schema_version"] == 1
    nuevo = FittedScorecardBundle.from_study(sc.study)
    assert (
        nuevo.apply(datos.loc[nuevas[:3]].drop(columns=["bad_flag"])).lineage[
            "bundle_schema_version"
        ]
        == 2
    )


@pytest.mark.parametrize("defecto", ["puntos", "variable_ausente", "no_categorica", "esquema_3"])
def test_un_bundle_de_esquema_2_con_una_referencia_que_no_casa_no_carga(
    _corrida: tuple[bayesrisk.Scorecard, pd.DataFrame], defecto: str
) -> None:
    """🔴 La referencia se valida contra la tabla de puntos congelada del mismo bundle."""
    sc, _ = _corrida
    bundle = FittedScorecardBundle.from_study(sc.study)
    manifest = bundle.manifest
    if defecto == "puntos":
        manifest["unseen_reference"]["segmento"]["points"] += 1
    elif defecto == "variable_ausente":
        del manifest["unseen_reference"]["segmento"]
    elif defecto == "no_categorica":
        manifest["unseen_reference"]["ingreso"] = dict(manifest["unseen_reference"]["segmento"])
    else:
        manifest["schema_version"] = 3
    manifest["bundle_hash"] = _bundle_hash(manifest)
    with pytest.raises(ScorecardBundleError, match=r"unseen_reference|no soportado"):
        FittedScorecardBundle(manifest=manifest, rules=bundle._rules)


# ───────────────────────── D-NOV-2: cat_unknown ─────────────────────────


@pytest.mark.parametrize("valor", [-0.5, 0.0, "empirical", "D"])
def test_cat_unknown_distinto_del_vacio_se_rechaza_al_validar(valor: object) -> None:
    """🔴 Nace rojo: el config lo aceptaba y la corrida moría en «Tramos y WoE»."""
    with pytest.raises(ConfigError, match="no se configura") as error:
        BinningConfig(cat_unknown=valor)
    assert tuple(error.value.loc) == ("binning", "cat_unknown")
    with pytest.raises(ConfigError, match="no se configura"):
        WoEBinner(cat_unknown=valor)._validate_config()
    assert BinningConfig(cat_unknown=None).cat_unknown is None


def test_cat_unknown_sale_de_la_pantalla_y_sigue_en_el_schema() -> None:
    """🔴 Una perilla menos en la pantalla (D-NOV-2); el campo sigue en el config estable de 2.x."""
    campo = BinningConfig.model_json_schema()["properties"]["cat_unknown"]
    assert campo["ui_widget"] == "hidden"


# ───────────────────────── D-NOV-3/4: lo que se dice ─────────────────────────


class _Almacen:
    def __init__(self, artefactos: dict[tuple[str, str], Any]) -> None:
        self._artefactos = artefactos

    def has(self, domain: str, key: str) -> bool:
        return (domain, key) in self._artefactos

    def get(self, domain: str, key: str) -> Any:
        return self._artefactos[(domain, key)]


def _estudio(filas_no_vistas: int, *, oot: int = 1000) -> Any:
    tabla = pd.DataFrame(
        {
            "variable": ["anio_fiscal"],
            "muestra": ["oot"],
            "filas": [filas_no_vistas],
            "tramo_asignado": ["['2007' '2008']"],
        }
    )
    frame = pd.DataFrame(
        {"partition": ["oot"] * oot + ["desarrollo"] * 50, "ttd": [True] * (oot + 50)}
    )
    tablas = {
        "anio_fiscal": pd.DataFrame(
            {
                "Bin": [np.array(["2005"], dtype=object), np.array(["2007", "2008"], dtype=object)],
                "Count": [10, 10],
                "WoE": [0.3, -0.4],
            }
        )
    }
    return SimpleNamespace(
        artifacts=_Almacen(
            {
                ("binning", "unseen_categories"): tabla,
                ("binning", "tables"): tablas,
                ("data", "frame"): frame,
                ("data", "splits"): SimpleNamespace(partition_col="partition", ttd_col="ttd"),
            }
        ),
        config=SimpleNamespace(binning=BinningConfig()),
    )


def test_la_alerta_de_d_ttd_5_sale_con_una_fila_y_dice_el_peor_tramo() -> None:
    """🔴 Sigue para toda variable con una sola fila no vista, ahora con su tramo (D-NOV-4)."""
    (alerta,) = _alertas_categorias_no_vistas(_estudio(1))
    assert alerta == (
        "«anio_fiscal»: 1 operación con una categoría que no existía en Desarrollo (1 en Fuera "
        "de tiempo (OOT)); en esa variable recibe el riesgo de su peor tramo («2007, 2008»)"
    )
    assert _alertas_cambio_de_dominio(_estudio(1)) == ()


def test_la_alerta_de_cambio_de_dominio_sale_desde_el_diez_por_ciento() -> None:
    """🔴 Desde el 10 % de la muestra, no bajo él; no excluye nada."""
    assert _alertas_cambio_de_dominio(_estudio(99)) == ()
    (alerta,) = _alertas_cambio_de_dominio(_estudio(100))
    assert alerta == (
        "«anio_fiscal»: el 10,0 % de las operaciones fuera de tiempo (OOT) trae un valor que no "
        "existía en Desarrollo. Si la variable se deriva de la fecha, no sirve para predecir "
        "fuera de tiempo: considera excluirla (`exclude`)."
    )
    assert _alertas_cambio_de_dominio(_estudio(100), ("otra",)) == ()


def test_la_corrida_lo_dice_en_trail_resumenes_y_tablas_de_puntos(
    _corrida: tuple[bayesrisk.Scorecard, pd.DataFrame],
) -> None:
    """🔴 Trail con el peor tramo; alerta de dominio en «Tramos y WoE» y en la selección (el
    ``segmento`` entra); la tabla de puntos del resumen —la del Excel— y la del informe con la
    línea de las no vistas."""
    sc, datos = _corrida
    st = sc.study
    referencia = st.artifacts.get("binning", "process").unseen_reference_["segmento"]
    trail = Path(sc.project_dir) / "run" / "audit_trail.jsonl"
    eventos = [json.loads(linea) for linea in trail.read_text(encoding="utf-8").splitlines()]
    (evento,) = (
        e["payload"]
        for e in eventos
        if e["kind"] == "decision" and e["payload"].get("regla") == "categoria_no_vista"
    )
    assert (evento["accion"], evento["umbral"]) == (
        "asignar_woe_peor_tramo",
        referencia.reference_bin,
    )
    frame = st.artifacts.get("data", "frame")
    en_oot = frame["partition"].eq("oot")
    fraccion = float((en_oot & datos["segmento"].eq("D")).sum()) / float(en_oot.sum())
    assert fraccion >= 0.10
    for etapa in ("binning", "selection"):
        assert any(
            "«segmento»: el" in alerta and "considera excluirla" in alerta
            for alerta in sc.summary(etapa).alerts
        ), etapa

    tabla = sc.summary("scorecard").table
    assert tabla is not None
    linea = tabla.loc[tabla["Tramo"].eq("Categorías no vistas → como «C»")]
    assert len(linea.index) == 1
    tarjeta = st.artifacts.get("scorecard", "scorecard")
    (fila,) = filas_de_referencia_no_vista(tarjeta, {"segmento": referencia}).values()
    assert (linea["Variable"].iloc[0], linea["Puntos"].iloc[0]) == ("segmento", fila["points"])
    posicion = tabla.index.get_loc(linea.index[0])
    assert tabla["Variable"].iloc[posicion - 1] == "segmento"
    if posicion + 1 < len(tabla.index):
        assert tabla["Variable"].iloc[posicion + 1] != "segmento"

    vista = _table_view(
        "scorecard.scorecard",
        tarjeta,
        max_rows=500,
        bin_labels=_rotulos_de_tramos(st),
        lineas_no_vistas=_referencias_no_vistas(st),
    )
    assert _referencias_no_vistas(st) == {"segmento": int(cast(int, fila["bin_index"]))}
    columnas = vista["columns"]
    (informe,) = (
        dict(zip(columnas, fila_vista, strict=True))
        for fila_vista in vista["rows"]
        if str(fila_vista[columnas.index("bin_label")]).startswith("Categorías no vistas")
    )
    assert informe["bin_label"] == "Categorías no vistas → como «C»"
    assert informe["feature"] == "segmento"
    assert vista["total_rows"] == vista["shown_rows"] == len(tarjeta.index) + 1
