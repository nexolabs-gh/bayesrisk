"""La tarjeta de esquema 4, el paso ``monitoring`` y la puerta ``bayesrisk.Monitor`` (SDD-33 §11).

Una corrida guiada del scorecard sobre ``consumo_comportamiento`` (con los dobles de OptBinning:
OR-Tools revienta el proceso de pytest) deja la tarjeta que todo el módulo monitorea. Las cifras de
§0.3 con OptBinning real viven en ``test_monitoring_oraculo.py``, en un subproceso.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

import bayesrisk
from bayesrisk.guided import Monitor, MonitorInputError, Scorecard
from bayesrisk.monitoring import engine
from bayesrisk.monitoring.step import PERIODS_COLUMNS, VARIABLES_COLUMNS
from bayesrisk.scorecard.bundle import FittedScorecardBundle, _bundle_hash
from bayesrisk.scorecard.exceptions import ScorecardBundleError

COHORTES = ("2023Q1", "2023Q2", "2023Q3", "2023Q4", "2024Q1", "2024Q2")


def cartera(*, semilla: int = 45, deriva: float = 0.0, nivel: float = 0.0) -> pd.DataFrame:
    """6.000 operaciones en seis añadas, con variables enteras a la medida de los dobles.

    Los dobles de OptBinning cortan las numéricas en 1,5 (``risk``, en 0,5 y 1,5): con variables
    de 0 a 3 el modelo ordena y la escala forma varios tramos. ``deriva`` desplaza la población de
    las añadas siguientes (la misma logística: deriva de población, no de calibración) y ``nivel``
    sube el logit de la última añada (deriva de calibración).
    """
    rng = np.random.default_rng(semilla)
    filas = []
    for i, cohorte in enumerate(COHORTES):
        n = 1_000
        p = min(0.9, 0.35 + deriva * i)
        x = {c: rng.binomial(3, p, n) for c in ("uso", "atraso", "antiguedad")}
        risk = rng.binomial(2, min(0.9, 0.3 + deriva * i), n)
        logit = (
            -2.0
            + 0.9 * (x["uso"] > 1.5)
            + 0.8 * (x["atraso"] > 1.5)
            - 0.6 * (x["antiguedad"] > 1.5)
            + 0.8 * (risk > 0.5)
            + 0.7 * (risk > 1.5)
            + (nivel if cohorte == COHORTES[-1] else 0.0)
        )
        malo = rng.random(n) < 1.0 / (1.0 + np.exp(-logit))
        filas.append(
            pd.DataFrame(
                {
                    "loan_id": [f"op-{i}-{j:04d}" for j in range(n)],
                    **{c: v.astype("int64") for c, v in x.items()},
                    "risk": risk.astype("int64"),
                    "cohorte": cohorte,
                    "bad_flag": malo.astype("int64"),
                }
            )
        )
    return pd.concat(filas, ignore_index=True)


@pytest.fixture(scope="module")
def entorno(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """La corrida de desarrollo, su tarjeta guardada y dos carteras para monitorear."""
    from conftest import parchar_optbinning

    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        parchar_optbinning(parche)
        raiz = tmp_path_factory.mktemp("monitoreo")
        sc = Scorecard(
            cartera(),
            target="bad_flag",
            id="loan_id",
            cohort="cohorte",
            oot_cohorts=["2024Q2"],
            name="desarrollo",
            run_dir=raiz / "corridas",
        )
        sc._echo = lambda _texto: None
        sc.run()
        assert sc.study.run_context.status == "done", sc.study.run_context.error
        tarjeta = FittedScorecardBundle.from_study(sc.study)
        assert len(tarjeta.manifest["master_scale"]["grade_pd"]) >= 3
        ruta = tarjeta.save(raiz / "tarjeta")
        yield {
            "raiz": raiz,
            "sc": sc,
            "tarjeta": tarjeta,
            "ruta": ruta,
            "comportamiento": cartera(),
            "drift": cartera(semilla=46, deriva=0.08, nivel=0.9),
        }


def _monitor(entorno: dict[str, Any], datos: Any, nombre: str, **kwargs: Any) -> Monitor:
    argumentos: dict[str, Any] = {"period": "cohorte", "default": "bad_flag"}
    argumentos.update(kwargs)
    bundle = argumentos.pop("bundle", entorno["ruta"])
    mon = Monitor(bundle, datos, name=nombre, run_dir=entorno["raiz"] / "mon", **argumentos)
    mon._echo = lambda _texto: None
    return mon


def _variante(tarjeta: FittedScorecardBundle, **cambios: Any) -> FittedScorecardBundle:
    """La misma tarjeta con su manifiesto editado y su huella recalculada (un bundle válido)."""
    manifest = tarjeta.manifest
    for clave, valor in cambios.items():
        if valor is _QUITAR:
            manifest.pop(clave, None)
        else:
            manifest[clave] = valor
    manifest["files"] = {}
    manifest["bundle_hash"] = _bundle_hash(manifest)
    return FittedScorecardBundle(manifest=manifest, rules=tarjeta._rules)


_QUITAR = object()


# ── la tarjeta de esquema 4 (§3.7, D-MNT-2) ─────────────────────────────────────────────


def test_la_tarjeta_nueva_es_de_esquema_4_y_congela_la_referencia(entorno: dict[str, Any]) -> None:
    study = entorno["sc"].study
    manifest = entorno["tarjeta"].manifest
    assert manifest["schema_version"] == 4
    referencia = manifest["monitoring_reference"]
    asignacion = study.artifacts.get("master_scale", "assignment")
    objetivo = study.artifacts.get("scorecard", "score")["target"]
    desarrollo = asignacion.loc[asignacion["partition"] == "desarrollo"]
    puntajes = desarrollo["score"].to_numpy(dtype="float64")
    assert referencia["n_development"] == len(desarrollo.index)
    assert referencia["score_edges"] == list(engine.cortes_del_puntaje(puntajes))
    assert referencia["score_counts"] == list(
        engine.conteos_por_corte(puntajes, referencia["score_edges"])
    )
    grados = study.artifacts.get("master_scale", "grades")
    assert referencia["grade_counts"] == [int(n) for n in grados["n_development"]]
    holdout = asignacion.loc[asignacion["partition"] == "holdout"].join(objetivo)
    k = len(grados.index)
    malos = [
        int(((holdout["grade"] == g) & (holdout["target"] == 1)).sum()) for g in range(1, k + 1)
    ]
    buenos = [
        int(((holdout["grade"] == g) & (holdout["target"] == 0)).sum()) for g in range(1, k + 1)
    ]
    esperado = engine.auc_sobre_tramos(malos, buenos)
    assert esperado.cause is None
    assert referencia["auc_initial"] == {
        "source": "holdout",
        "auc": esperado.auc,
        "variance": esperado.variance,
        "n_bad": esperado.n_bad,
        "n_good": esperado.n_good,
        "cause": None,
    }
    releida = FittedScorecardBundle.load(entorno["ruta"])
    assert releida.bundle_hash == entorno["tarjeta"].bundle_hash
    assert releida.manifest["monitoring_reference"] == referencia


def test_la_referencia_no_cambia_lo_que_la_tarjeta_puntua(entorno: dict[str, Any]) -> None:
    """El esquema 4 sólo agrega agregados: un esquema 3 de la misma tarjeta puntúa igual."""
    tarjeta = entorno["tarjeta"]
    tres = _variante(tarjeta, schema_version=3, monitoring_reference=_QUITAR)
    datos = entorno["comportamiento"]
    nueva = tarjeta.apply(datos).application_frame.drop(columns="bundle_hash")
    vieja = tres.apply(datos).application_frame.drop(columns="bundle_hash")
    pd.testing.assert_frame_equal(nueva, vieja)


def test_una_tarjeta_de_esquema_3_se_lee_igual_y_el_monitoreo_la_rechaza(
    entorno: dict[str, Any],
) -> None:
    """§8 y D-MNT-2: se sigue leyendo y aplicando; el monitoreo dice cómo obtener una que sí."""
    tres = _variante(entorno["tarjeta"], schema_version=3, monitoring_reference=_QUITAR)
    ruta = tres.save(entorno["raiz"] / "tarjeta-esquema-3")
    releida = FittedScorecardBundle.load(ruta)
    assert releida.manifest["schema_version"] == 3
    assert not releida.apply(entorno["comportamiento"]).application_frame["grade"].isna().all()
    with pytest.raises(MonitorInputError, match=r"esquema 3.*Vuelve a correr el desarrollo"):
        _monitor(entorno, entorno["comportamiento"], "esquema-3", bundle=ruta)


def test_una_tarjeta_sin_escala_no_se_monitorea(entorno: dict[str, Any]) -> None:
    sin_escala = _variante(entorno["tarjeta"], master_scale=_QUITAR, monitoring_reference=_QUITAR)
    with pytest.raises(MonitorInputError, match="no trae escala maestra"):
        _monitor(entorno, entorno["comportamiento"], "sin-escala", bundle=sin_escala)


@pytest.mark.parametrize(
    "dano",
    [
        lambda r: r.update(score_counts=[*r["score_counts"][:-1], r["score_counts"][-1] + 1]),
        lambda r: r.update(grade_counts=r["grade_counts"][:-1]),
        lambda r: r.update(score_edges=list(reversed(r["score_edges"]))),
        lambda r: r["auc_initial"].update(source="oot"),
        lambda r: r["auc_initial"].update(variance=0.0),
    ],
)
def test_una_referencia_incoherente_no_se_lee(entorno: dict[str, Any], dano: Any) -> None:
    referencia = json.loads(json.dumps(entorno["tarjeta"].manifest["monitoring_reference"]))
    dano(referencia)
    with pytest.raises(ScorecardBundleError, match="monitoring_reference"):
        _variante(entorno["tarjeta"], monitoring_reference=referencia)


def test_la_referencia_sin_escala_no_es_un_manifiesto_valido(entorno: dict[str, Any]) -> None:
    with pytest.raises(ScorecardBundleError, match="Claves de manifest inválidas"):
        _variante(entorno["tarjeta"], master_scale=_QUITAR)


# ── la corrida (§6, §7) ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def corrida(entorno: dict[str, Any]) -> Monitor:
    mon = _monitor(entorno, entorno["drift"], "drift")
    mon.run()
    assert mon.study.run_context.status == "done", mon.study.run_context.error
    return mon


def test_publica_los_artefactos_de_6_2_y_los_conteos_cuadran(corrida: Monitor) -> None:
    artefactos = corrida.study.artifacts
    for clave in (
        "periods",
        "grades_by_period",
        "variables_by_period",
        "verdict",
        "card",
        "result",
    ):
        assert artefactos.has("monitoring", clave), clave
    periodos = artefactos.get("monitoring", "periods")
    assert tuple(periodos.columns) == PERIODS_COLUMNS
    assert periodos["period"].tolist() == [
        "2023Q1",
        "2023Q2",
        "2023Q3",
        "2023Q4",
        "2024Q1",
        "2024Q2",
    ]
    assert (periodos["n_scored"] + periodos["n_not_scored"] == periodos["n_rows"]).all()
    assert int(periodos["n_rows"].sum()) == 6_000
    ficha = artefactos.get("monitoring", "card")
    tramos = artefactos.get("monitoring", "grades_by_period")
    assert len(tramos.index) == ficha.n_grades * len(periodos.index)
    assert {"jeffreys_p_value_over", "traffic_light_over", "direction"} <= set(tramos.columns)
    variables = artefactos.get("monitoring", "variables_by_period")
    assert tuple(variables.columns) == VARIABLES_COLUMNS
    tarjeta = FittedScorecardBundle.load(corrida.config.monitoring.bundle)
    assert set(variables["feature"]) == set(tarjeta.manifest["model"]["features"])
    veredicto = artefactos.get("monitoring", "verdict")
    assert veredicto.period == "2024Q2" and veredicto.verdict == periodos["verdict"].iloc[-1]
    assert veredicto == ficha.verdict


def test_la_identidad_y_el_lineage(corrida: Monitor, entorno: dict[str, Any]) -> None:
    """§5.3: la ruta de la tarjeta fuera del ``config_hash``; su huella, en el lineage."""
    lineage = corrida.study.run_context.lineage
    assert lineage.bundle_hash == entorno["tarjeta"].bundle_hash
    assert lineage.model_dump(mode="json")["bundle_hash"] == lineage.bundle_hash
    desarrollo = entorno["sc"].study.run_context.lineage
    assert desarrollo.bundle_hash is None
    assert "bundle_hash" not in desarrollo.model_dump(mode="json")
    assert "bundle_hash" not in desarrollo.model_dump_json()
    escrito = json.loads(
        (corrida.project_dir / "run" / "study" / "run_metadata.json").read_text("utf-8")
    )
    assert escrito["lineage"]["bundle_hash"] == lineage.bundle_hash
    cfg = corrida.config
    movida = cfg.model_copy(
        update={"monitoring": cfg.monitoring.model_copy(update={"bundle": "otra/carpeta/tarjeta"})}
    )
    assert bayesrisk.core.config.config_hash(movida) == corrida.config_hash


def test_la_puerta_completa_da_lo_mismo(corrida: Monitor, tmp_path: Path) -> None:
    """D-SIM-1: el config de la puerta, corrido por ``bayesrisk.run``, da los mismos artefactos."""
    study = bayesrisk.run(corrida.config, run_dir=tmp_path / "completa")
    assert study.run_context.status == "done", study.run_context.error
    assert study.lineage_bundle().config_hash == corrida.config_hash
    for clave in ("periods", "grades_by_period", "variables_by_period"):
        pd.testing.assert_frame_equal(
            study.artifacts.get("monitoring", clave),
            corrida.study.artifacts.get("monitoring", clave),
        )
    assert study.artifacts.get("monitoring", "verdict") == corrida.study.artifacts.get(
        "monitoring", "verdict"
    )


def test_el_trail_lleva_la_referencia_cada_alerta_roja_y_el_veredicto(corrida: Monitor) -> None:
    eventos = [
        json.loads(linea)
        for linea in (corrida.project_dir / "run" / "audit_trail.jsonl")
        .read_text("utf-8")
        .splitlines()
    ]
    reglas = [e["payload"].get("regla") for e in eventos if e.get("kind") == "decision"]
    ficha = corrida.study.artifacts.get("monitoring", "card")
    assert reglas.count("monitoring_alerta") == len(ficha.alerts) > 0
    assert reglas.count("monitoring_veredicto") == 1
    assert reglas.count("monitoring_reference") == 1
    assert "puerta_de_entrada" in reglas and "inferencia_periodo" in reglas


def test_los_resumenes_hablan_del_monitoreo(corrida: Monitor) -> None:
    resumen = corrida.summary("monitoring")
    assert resumen.label == "Monitoreo"
    assert 3 <= len(resumen.lines) <= 8
    assert resumen.lines[0].startswith("Veredicto: ")
    assert list(resumen.table.columns)[:3] == ["Periodo", "Operaciones", "Con desenlace"]
    final = corrida.summary()
    assert final.title == "Resumen del monitoreo"
    assert final.headline()[1].startswith("Veredicto: ")
    assert final.to_dict()["family"] == "monitoreo"
    assert corrida.summary("data").label == "Cartera monitoreada"
    assert "Veredicto:" in final.text() and "Validación técnica" not in final.text()


def test_el_psi_por_periodo_es_el_de_stability_sobre_la_misma_cartera(
    entorno: dict[str, Any],
) -> None:
    """§3.2: sobre la cartera de desarrollo, el PSI de cada cohorte es el ``temporal_records``."""
    mon = _monitor(entorno, entorno["comportamiento"], "misma")
    mon.run()
    periodos = mon.study.artifacts.get("monitoring", "periods")
    temporales = entorno["sc"].study.artifacts.get("stability", "result").temporal_records
    if not temporales:
        pytest.skip("la corrida guiada no publicó la serie temporal de stability")
    stability = {r.period: r.psi for r in temporales}
    for fila in periodos.itertuples(index=False):
        assert fila.psi_score == pytest.approx(stability[fila.period], abs=1e-12), fila.period


# ── los casos borde (§8, §11) ───────────────────────────────────────────────────────────


def test_un_panel_se_monitorea_y_una_llave_repetida_en_un_periodo_falla(
    entorno: dict[str, Any],
) -> None:
    """§7-3: la misma operación en dos periodos es una cartera de comportamiento; en uno, no."""
    datos = entorno["comportamiento"]
    panel = pd.concat(
        [datos, datos.loc[datos["cohorte"] == "2024Q2"].assign(cohorte="2024Q3")],
        ignore_index=True,
    )
    mon = _monitor(entorno, panel, "panel")
    mon.run()
    assert mon.study.run_context.status == "done", mon.study.run_context.error
    assert mon.study.artifacts.get("monitoring", "periods")["period"].iloc[-1] == "2024Q3"
    repetida = pd.concat([datos, datos.iloc[[0]]], ignore_index=True)
    mal = _monitor(entorno, repetida, "repetida")
    mal.run()
    error = mal.study.run_context.error
    assert mal.study.run_context.status == "failed"
    assert "La tarjeta no puede puntuar el periodo 2023Q1" in error.message
    assert "duplicad" in error.message


def test_una_tarjeta_estricta_se_monitorea_con_el_periodo_y_el_desenlace(
    entorno: dict[str, Any],
) -> None:
    """Pasada 2: ``extra_columns="forbid"`` rechaza el periodo y el desenlace si llegan a apply."""
    tarjeta = entorno["tarjeta"]
    esquema = tarjeta.manifest["input_schema"]
    estricta = _variante(tarjeta, input_schema={**esquema, "extra_columns": "forbid"})
    with pytest.raises(ScorecardBundleError, match="prohibidas"):
        estricta.apply(entorno["comportamiento"])
    mon = _monitor(entorno, entorno["comportamiento"], "estricta", bundle=estricta)
    mon.run()
    assert mon.study.run_context.status == "done", mon.study.run_context.error


def test_las_filas_sin_desenlace_no_entran_al_contraste_de_cartera(
    entorno: dict[str, Any],
) -> None:
    """§3.3 (pasada 1): la máscara M_t; cambiar las filas inmaduras no mueve el contraste."""
    datos = entorno["comportamiento"].copy()
    inmaduras = datos.index[(datos["cohorte"] == "2024Q2")][:300]
    datos.loc[inmaduras, "bad_flag"] = np.nan
    otras = datos.copy()
    numericas = ["uso", "atraso", "antiguedad", "risk"]
    otras.loc[inmaduras, numericas] = otras.loc[inmaduras, numericas].to_numpy()[::-1]
    a = _monitor(entorno, datos, "mascara-a")
    b = _monitor(entorno, otras, "mascara-b")
    a.run()
    b.run()
    pa = a.study.artifacts.get("monitoring", "periods").iloc[-1]
    pb = b.study.artifacts.get("monitoring", "periods").iloc[-1]
    assert pa["n_with_outcome"] == pb["n_with_outcome"] == pa["n_scored"] - 300
    for columna in ("bad_rate", "expected_pd", "p_value_under", "auc", "slope"):
        assert pa[columna] == pb[columna], columna


def test_sin_columna_de_desenlace_solo_se_mide_la_poblacion(entorno: dict[str, Any]) -> None:
    mon = _monitor(entorno, entorno["drift"], "sin-desenlace", default=None)
    mon.run()
    periodos = mon.study.artifacts.get("monitoring", "periods")
    assert set(periodos["verdict"]) <= {"no_outcome_yet", "watch"}
    esperado = periodos["population_light"].map(
        lambda luz: "watch" if luz in {"red", "amber"} else "no_outcome_yet"
    )
    assert periodos["verdict"].tolist() == esperado.tolist()
    assert (periodos["n_with_outcome"] == 0).all()
    assert any("Sin columna de desenlace" in linea for linea in mon.summary("data").lines)


def test_un_ultimo_periodo_sin_desenlace_informa_el_ultimo_con_desenlace(
    entorno: dict[str, Any],
) -> None:
    datos = entorno["comportamiento"].copy()
    datos.loc[datos["cohorte"] == "2024Q2", "bad_flag"] = np.nan
    mon = _monitor(entorno, datos, "ultimo-sin-desenlace")
    mon.run()
    veredicto = mon.study.artifacts.get("monitoring", "verdict")
    assert veredicto.period == "2024Q2"
    assert veredicto.verdict in {"no_outcome_yet", "watch"}
    assert veredicto.last_with_outcome_period == "2024Q1"
    assert veredicto.last_with_outcome_verdict is not None
    assert veredicto.not_evaluable == ()


def test_una_fecha_se_agrupa_por_mes(entorno: dict[str, Any]) -> None:
    datos = entorno["comportamiento"].copy()
    meses = {"2023Q1": "2023-02-14", "2023Q2": "2023-05-03", "2023Q3": "2023-08-20"}
    datos["fecha"] = pd.to_datetime(datos["cohorte"].map(meses).fillna("2024-01-31"))
    mon = _monitor(entorno, datos, "fecha", period="fecha")
    mon.run()
    periodos = mon.study.artifacts.get("monitoring", "periods")
    assert periodos["period"].tolist() == ["2023-02", "2023-05", "2023-08", "2024-01"]
    assert mon.study.artifacts.get("monitoring", "card").period_kind == "date_month"


@pytest.mark.parametrize(
    ("cambio", "mensaje"),
    [
        ({"default": "cohorte"}, "la misma columna"),
        ({"period": "no_existe"}, "no_existe"),
        ({"default": "no_existe"}, "no_existe"),
    ],
)
def test_la_puerta_se_detiene_antes_de_correr(
    entorno: dict[str, Any], cambio: dict[str, Any], mensaje: str
) -> None:
    with pytest.raises(MonitorInputError, match=mensaje):
        _monitor(entorno, entorno["comportamiento"], "detenida", **cambio)


def test_un_desenlace_que_no_es_0_1_se_rechaza(entorno: dict[str, Any]) -> None:
    datos = entorno["comportamiento"].copy()
    datos.loc[datos.index[:3], "bad_flag"] = 2
    with pytest.raises(MonitorInputError, match="no son 0, 1 ni vacío"):
        _monitor(entorno, datos, "desenlace-2")


def test_faltan_las_variables_de_la_tarjeta(entorno: dict[str, Any]) -> None:
    variable = entorno["tarjeta"].manifest["model"]["features"][0]
    with pytest.raises(MonitorInputError, match=variable):
        _monitor(entorno, entorno["comportamiento"].drop(columns=variable), "sin-variable")


def test_el_objeto_y_la_carpeta_son_la_misma_corrida(entorno: dict[str, Any]) -> None:
    por_ruta = _monitor(entorno, entorno["comportamiento"], "por-ruta")
    por_objeto = _monitor(
        entorno, entorno["comportamiento"], "por-objeto", bundle=entorno["tarjeta"]
    )
    assert por_ruta.config_hash == por_objeto.config_hash
    copia = Path(por_objeto.config.monitoring.bundle)
    assert copia.parent.name == "input" and copia.name.startswith("tarjeta-")
    assert FittedScorecardBundle.load(copia).bundle_hash == entorno["tarjeta"].bundle_hash


def test_una_tarjeta_cambiada_despues_de_construir_no_corre(entorno: dict[str, Any]) -> None:
    mon = _monitor(entorno, entorno["comportamiento"], "cambiada")
    copia = Path(mon.config.monitoring.bundle)
    manifiesto = json.loads((copia / "manifest.json").read_text("utf-8"))
    manifiesto["master_scale"]["grade_pd"][0] = 0.01
    (copia / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    with pytest.raises(MonitorInputError, match="cambió desde que se construyó"):
        mon.run()


def test_un_periodo_con_un_malo_da_evidencia_parcial(entorno: dict[str, Any]) -> None:
    """§11: con un solo malo el AUC y la pendiente no se evalúan; el veredicto lo dice."""
    datos = entorno["comportamiento"].copy()
    ultima = datos["cohorte"] == "2024Q2"
    datos.loc[ultima, "bad_flag"] = 0
    datos.loc[datos.index[ultima][0], "bad_flag"] = 1
    mon = _monitor(entorno, datos, "un-malo")
    mon.run()
    fila = mon.study.artifacts.get("monitoring", "periods").iloc[-1]
    assert fila["auc_light"] == fila["slope_light"] == "not_evaluable"
    assert "auc_test:few_bads" in fila["not_evaluable"]
    assert "slope:few_bads" in fila["not_evaluable"]
    assert bool(fila["partial_evidence"])
    veredicto = mon.study.artifacts.get("monitoring", "verdict")
    assert veredicto.partial_evidence and "auc_test:few_bads" in veredicto.not_evaluable
    assert any("Evidencia parcial" in alerta for alerta in mon.summary("monitoring").alerts)


def test_el_csi_de_cada_variable_es_el_psi_de_sus_tramos_contra_desarrollo(
    corrida: Monitor, entorno: dict[str, Any]
) -> None:
    """§3.2: la participación de cada bin de la tarjeta en el periodo contra su ``support``."""
    tarjeta = entorno["tarjeta"]
    reglas = tarjeta._rules
    datos = entorno["drift"]
    sub = datos.loc[datos["cohorte"] == "2024Q2"]
    aplicado = tarjeta.apply(sub)
    puntuadas = set(
        aplicado.application_frame.loc[
            aplicado.application_frame["scoring_status"] == "scored", "input_position"
        ]
    )
    traza = aplicado.trace_frame.loc[aplicado.trace_frame["input_position"].isin(puntuadas)]
    variables = corrida.study.artifacts.get("monitoring", "variables_by_period")
    for variable, grupo in reglas.groupby("feature"):
        bins = [str(b) for b in grupo["bin_id"]]
        actual = traza.loc[traza["feature"] == variable, "bin_id"].astype(str).value_counts()
        esperado = engine.psi(
            [int(s) for s in grupo["support"]], [int(actual.get(b, 0)) for b in bins]
        )
        medido = variables.loc[
            (variables["period"] == "2024Q2") & (variables["feature"] == variable), "csi"
        ]
        assert float(medido.iloc[0]) == pytest.approx(esperado, rel=1e-12), variable


def test_una_fila_sin_periodo_queda_fuera_y_se_cuenta(entorno: dict[str, Any]) -> None:
    datos = entorno["comportamiento"].copy()
    datos["cohorte"] = datos["cohorte"].astype(object)
    datos.loc[datos.index[:7], "cohorte"] = None
    mon = _monitor(entorno, datos, "sin-periodo")
    mon.run()
    ficha = mon.study.artifacts.get("monitoring", "card")
    periodos = mon.study.artifacts.get("monitoring", "periods")
    assert ficha.n_rows_without_period == 7
    assert int(periodos["n_rows"].sum()) == len(datos.index) - 7
    assert any("sin periodo" in alerta for alerta in mon.summary("monitoring").alerts)


# ── la pasada 1 de Codex sobre el código ────────────────────────────────────────────────


def test_un_auc_inicial_con_varianza_nula_sigue_siendo_el_auc_inicial(
    entorno: dict[str, Any],
) -> None:
    """§3.4: la prueba usa la varianza del periodo; un Holdout separado deja AUC₀ = 1 y vale."""
    tarjeta = entorno["tarjeta"]
    referencia = json.loads(json.dumps(tarjeta.manifest["monitoring_reference"]))
    referencia["auc_initial"] = {
        "source": "holdout",
        "auc": 1.0,
        "variance": 0.0,
        "n_bad": 2,
        "n_good": 2,
        "cause": "zero_variance",
    }
    separada = _variante(tarjeta, monitoring_reference=referencia)
    mon = _monitor(entorno, entorno["comportamiento"], "auc-separado", bundle=separada)
    mon.run()
    periodos = mon.study.artifacts.get("monitoring", "periods")
    assert (periodos["auc_initial"] == 1.0).all()
    assert (periodos["auc_light"] == "red").all()  # ningún periodo ordena perfecto


def test_los_periodos_enteros_grandes_no_se_funden(entorno: dict[str, Any]) -> None:
    """Dos enteros mayores que 2**53 son el mismo float: el periodo se ordena exacto."""
    datos = entorno["comportamiento"].copy()
    datos["periodo"] = np.where(np.arange(len(datos.index)) < 3_000, 2**53, 2**53 + 1)
    mon = _monitor(entorno, datos, "enteros-grandes", period="periodo")
    mon.run()
    periodos = mon.study.artifacts.get("monitoring", "periods")
    assert periodos["period"].tolist() == [str(2**53), str(2**53 + 1)]
    assert periodos["n_rows"].tolist() == [3_000, 3_000]


def test_sin_accion_con_evidencia_parcial_no_lo_afirma_todo(entorno: dict[str, Any]) -> None:
    """Población verde y una sola operación con desenlace: «sin acción», con su salvedad."""
    from bayesrisk.monitoring.textos import ACCIONES

    datos = entorno["comportamiento"].copy()
    datos["bad_flag"] = datos["bad_flag"].astype("float64")
    datos.loc[datos.index[:-1], "bad_flag"] = np.nan
    mon = _monitor(entorno, datos, "parcial")
    mon.run()
    veredicto = mon.study.artifacts.get("monitoring", "verdict")
    assert (veredicto.verdict, veredicto.partial_evidence) == ("no_action", True)
    assert veredicto.action != ACCIONES["no_action"]
    final = mon.summary()
    assert "Evidencia parcial" in final.validation
    assert any("Evidencia parcial" in alerta for alerta in final.review)
    assert "Sin alertas" not in final.text()
    assert any("Evidencia parcial" in alerta for alerta in final.to_dict()["review"])


# ── la pasada 2 de Codex sobre el código ────────────────────────────────────────────────


def test_un_reintento_que_no_publica_no_cambia_la_huella(entorno: dict[str, Any]) -> None:
    """§9: un ``run_step`` repetido choca con la evidencia terminada y no cambia su lineage."""
    import shutil

    from bayesrisk.core.exceptions import ArtifactExistsError

    mon = _monitor(entorno, entorno["comportamiento"], "reintento")
    mon.run()
    original = mon.study.run_context.lineage.bundle_hash
    tarjeta = entorno["tarjeta"]
    otra = _variante(
        tarjeta, master_scale={**tarjeta.manifest["master_scale"], "approval_cutoff": 500.0}
    )
    assert otra.bundle_hash != original
    copia = Path(mon.config.monitoring.bundle)
    shutil.rmtree(copia)
    otra.save(copia)
    with pytest.raises(ArtifactExistsError):
        mon.study.run_step("monitoring")
    assert mon.study.run_context.lineage.bundle_hash == original


def test_las_fechas_como_objetos_se_agrupan_por_mes(
    entorno: dict[str, Any], tmp_path: Path
) -> None:
    """Un CSV con fechas ISO llega como ``datetime.date``: son fechas, también desde el archivo."""
    import datetime as dt

    datos = entorno["comportamiento"].copy()
    dias = {"2023Q1": dt.date(2023, 2, 14), "2023Q2": dt.date(2023, 5, 3)}
    datos["fecha"] = datos["cohorte"].map(dias).fillna(dt.date(2024, 1, 31))
    datos.loc[datos.index[::2], "fecha"] = datos.loc[datos.index[::2], "fecha"].map(
        lambda d: d.replace(day=1)
    )
    esperado = ["2023-02", "2023-05", "2024-01"]
    # La puerta completa (un YAML que no declara la columna) le entrega al paso los objetos tal
    # cual: el paso también los lee como fechas.
    from bayesrisk.monitoring.step import _periodos

    assert _periodos(datos["fecha"], pd)[1:] == ("date_month", esperado)
    mon = _monitor(entorno, datos, "fechas-objeto", period="fecha")
    mon.run()
    assert mon.study.run_context.status == "done", mon.study.run_context.error
    assert mon.study.artifacts.get("monitoring", "periods")["period"].tolist() == esperado
    csv = tmp_path / "cartera.csv"
    datos.to_csv(csv, index=False)
    desde_csv = _monitor(entorno, csv, "fechas-csv", period="fecha")
    desde_csv.run()
    assert desde_csv.study.run_context.status == "done", desde_csv.study.run_context.error
    periodos = desde_csv.study.artifacts.get("monitoring", "periods")
    assert periodos["period"].tolist() == esperado
    assert desde_csv.study.artifacts.get("monitoring", "card").period_kind == "date_month"


def test_los_enteros_grandes_con_vacios_tampoco_se_funden(entorno: dict[str, Any]) -> None:
    datos = entorno["comportamiento"].copy()
    datos["periodo"] = pd.array([2**53] * 3_000 + [2**53 + 1] * 2_990 + [pd.NA] * 10, dtype="Int64")
    mon = _monitor(entorno, datos, "enteros-con-vacios", period="periodo")
    mon.run()
    periodos = mon.study.artifacts.get("monitoring", "periods")
    assert periodos["period"].tolist() == [str(2**53), str(2**53 + 1)]
    assert periodos["n_rows"].tolist() == [3_000, 2_990]
    assert mon.study.artifacts.get("monitoring", "card").n_rows_without_period == 10


def test_un_periodo_inmaduro_no_oculta_la_evidencia_parcial_del_anterior(
    entorno: dict[str, Any],
) -> None:
    datos = entorno["comportamiento"].copy()
    datos["bad_flag"] = datos["bad_flag"].astype("float64")
    conservar = datos.index[datos["cohorte"] == "2024Q1"][0]
    datos.loc[datos.index != conservar, "bad_flag"] = np.nan
    mon = _monitor(entorno, datos, "parcial-y-sin-desenlace")
    mon.run()
    veredicto = mon.study.artifacts.get("monitoring", "verdict")
    assert (veredicto.period, veredicto.verdict) == ("2024Q2", "no_outcome_yet")
    assert veredicto.last_with_outcome_period == "2024Q1"
    assert veredicto.last_with_outcome_not_evaluable
    final = mon.summary()
    assert any("Evidencia parcial en 2024Q1" in alerta for alerta in final.review)
    assert "Evidencia parcial" in final.validation
    assert "Sin alertas" not in final.text()


# ── la pasada 3 de Codex sobre el código ────────────────────────────────────────────────


def test_un_csv_con_periodos_enteros_grandes_y_vacios_se_detiene(
    entorno: dict[str, Any], tmp_path: Path
) -> None:
    """Un CSV con vacíos lee los enteros como decimales: 2**53 y 2**53 + 1 llegan iguales."""
    datos = entorno["comportamiento"].copy()
    datos["periodo"] = pd.array([2**53] * 3_000 + [2**53 + 1] * 2_990 + [pd.NA] * 10, dtype="Int64")
    csv = tmp_path / "cartera.csv"
    datos.to_csv(csv, index=False)
    with pytest.raises(MonitorInputError, match="decimales"):
        _monitor(entorno, csv, "csv-enteros", period="periodo")


def test_un_panel_con_la_identidad_en_el_indice(
    tmp_path: Path, fake_binning_process: object
) -> None:
    """§7-3: con la identidad en el índice, la misma operación en dos periodos se monitorea."""
    del fake_binning_process
    sc = Scorecard(
        cartera().set_index("loan_id"),
        target="bad_flag",
        id="loan_id",
        cohort="cohorte",
        oot_cohorts=["2024Q2"],
        name="dev-indice",
        run_dir=tmp_path,
    )
    sc._echo = lambda _t: None
    sc.run()
    tarjeta = FittedScorecardBundle.from_study(sc.study)
    assert tarjeta.manifest["row_identity"]["index_name"] == "loan_id"
    datos = cartera(semilla=47).set_index("loan_id")
    panel = pd.concat([datos, datos.loc[datos["cohorte"] == "2024Q2"].assign(cohorte="2024Q3")])
    assert panel.index.has_duplicates
    mon = Monitor(tarjeta, panel, period="cohorte", default="bad_flag", run_dir=tmp_path / "m")
    mon._echo = lambda _t: None
    mon.run()
    assert mon.study.run_context.status == "done", mon.study.run_context.error
    periodos = mon.study.artifacts.get("monitoring", "periods")
    assert periodos["period"].iloc[-1] == "2024Q3" and int(periodos["n_scored"].sum()) == 7_000
    repetida = pd.concat([datos, datos.iloc[[0]]])
    mal = Monitor(
        tarjeta, repetida, period="cohorte", default="bad_flag", name="mal", run_dir=tmp_path / "m"
    )
    mal._echo = lambda _t: None
    mal.run()
    assert mal.study.run_context.status == "failed"
    assert "La tarjeta no puede puntuar el periodo 2023Q1" in mal.study.run_context.error.message


def test_una_publicacion_a_medias_conserva_la_huella_de_su_tarjeta(
    entorno: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.3 y §9: el almacén guarda antes de auditar; si el registro falla, la tabla que quedó
    lleva igual la huella de la tarjeta que la produjo."""
    from bayesrisk.core.artifacts import ArtifactStore
    from bayesrisk.core.study import Study

    mon = _monitor(entorno, entorno["comportamiento"], "a-medias")
    original = ArtifactStore.set

    def falla_al_auditar(self: Any, domain: str, key: str, value: Any, **kw: Any) -> None:
        original(self, domain, key, value, **kw)
        if (domain, key) == ("monitoring", "grades_by_period"):
            raise OSError("el registro de auditoría no se pudo escribir")

    study = Study(mon.config.model_copy(update={"audit": None}))
    monkeypatch.setattr(ArtifactStore, "set", falla_al_auditar)
    with pytest.raises(OSError, match="registro de auditoría"):
        study.run()
    monkeypatch.undo()
    assert study.artifacts.has("monitoring", "grades_by_period")
    assert not study.artifacts.has("monitoring", "verdict")
    assert study.run_context.lineage.bundle_hash == entorno["tarjeta"].bundle_hash
