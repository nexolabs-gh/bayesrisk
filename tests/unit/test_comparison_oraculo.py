"""Oráculo de la comparación con OptBinning real (SDD-34 §0.3 y §11), en un subproceso.

OR-Tools revienta el proceso de pytest (S20), así que las ocho corridas del scorecard y las tres de
IFRS 9 de §0.3 corren en un intérprete aparte con la puerta guiada, se comparan con
``bayesrisk.Comparison`` y devuelven lo medido en JSON. S47 midió §0.3 **fuera** del motor; aquí
lo reproduce el motor:

- AUC, Gini y KS en la OOT, el PSI común con su banda, el índice del BCE, su HHI y el número de
  tramos, y la validación, a los decimales que §0.3 publica;
- los dos modelos repetidos (``sin_stepwise`` y ``corr_050``, otro ``config_hash`` y la misma
  huella), las dos fronteras con empates y los niveles de ``otra_particion`` y ``otra_cartera``;
- la prueba de DeLong pareada: ``iv_005`` discrimina menos que la base (p < 0,001) y
  ``tramos_4`` y ``sin_mejor`` empatan. Los p-valores son los del riesgo con que ``performance``
  publicó el AUC (la PD calibrada; S49): S47 los midió sobre el puntaje entero, con más empates
  (0,83 y 0,71); la conclusión es la misma (SDD-34 §14);
- las tres provisiones de IFRS 9, con sus diferencias contra la referencia por etapa.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Final

import pytest

_CODIGO = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    import bayesrisk
    from bayesrisk import Ecl, Scorecard
    from bayesrisk.ui.datasets import materialize

    raiz = Path(sys.argv[1])
    raiz.mkdir(parents=True, exist_ok=True)
    consumo = materialize("consumo_comportamiento", workdir=raiz / "datos")
    drift = materialize("consumo_drift", workdir=raiz / "datos")
    BASE = dict(target="bad_flag", id="loan_id", cohort="cohorte", oot_cohorts=["2024Q2"])

    def correr(nombre, datos, **extra):
        sc = Scorecard(data=datos, name=nombre, run_dir=raiz / "runs", **{**BASE, **extra})
        sc._echo = lambda _t: None
        sc.run()
        assert sc.study.run_context.status == "done", (nombre, sc.study.run_context.error)
        return sc

    base = correr("base", consumo)
    correr("tramos_4", consumo, max_bins=4)
    correr("iv_005", consumo, min_iv=0.05)
    sel = base.study.artifacts.get("selection", "selection_table")
    mejor = str(sel[sel["included"]].sort_values("iv", ascending=False).iloc[0]["feature"])
    correr("sin_mejor", consumo, features=[str(f) for f in sel["feature"] if f != mejor])
    correr("sin_stepwise", consumo, stepwise=False)
    correr("corr_050", consumo, max_correlation=0.5)
    correr("otra_particion", consumo, oot_cohorts=["2024Q1", "2024Q2"])
    correr("otra_cartera", drift)

    def comparar(nombre, corridas):
        comp = bayesrisk.Comparison([raiz / "runs" / n for n in corridas], name=nombre,
                                    run_dir=raiz / "comparaciones")
        comp._echo = lambda _t: None
        comp.run()
        assert comp.study.run_context.status == "done", comp.study.run_context.error
        a = comp.study.artifacts
        return {
            "modelos": json.loads(a.get("comparison", "models").to_json(orient="records")),
            "pruebas": json.loads(a.get("comparison", "tests").to_json(orient="records")),
            "card": a.get("comparison", "card").model_dump(mode="json"),
            "lectura": list(a.get("comparison", "reading")),
        }

    salida = {
        "mejor": mejor,
        "seis": comparar(
            "seis", ["base", "tramos_4", "iv_005", "sin_mejor", "sin_stepwise", "corr_050"]
        ),
        "niveles": comparar("niveles", ["base", "otra_particion", "otra_cartera"]),
    }
    ifrs = materialize("ifrs9_retail_latam", workdir=raiz / "datos")
    ECL = dict(
        id="loan_id", as_of="as_of_date", portfolio="portfolio", exposure="ead", lgd="lgd",
        rate="eir", days_past_due="days_past_due", default="is_default", duration="duration",
        event="event", period="year", horizon=5,
        covariates=["days_past_due", "utilizacion_linea", "deuda_ingreso", "antiguedad_meses"],
    )
    for nombre, cambios in (("f4", {}), ("horizonte_3", {"horizon": 3}),
                            ("cov_2", {"covariates": ["days_past_due", "utilizacion_linea"]})):
        e = Ecl(data=ifrs, name=nombre, run_dir=raiz / "runs", **{**ECL, **cambios})
        e._echo = lambda _t: None
        e.run()
        assert e.study.run_context.status == "done", e.study.run_context.error
    comp = bayesrisk.Comparison([raiz / "runs" / n for n in ("f4", "horizonte_3", "cov_2")],
                                name="ifrs9", run_dir=raiz / "comparaciones")
    comp._echo = lambda _t: None
    comp.run()
    salida["ifrs9"] = {
        "provision": json.loads(
            comp.study.artifacts.get("comparison", "provision").to_json(orient="records")
        ),
        "lectura": list(comp.study.artifacts.get("comparison", "reading")),
        "card": comp.study.artifacts.get("comparison", "card").model_dump(mode="json"),
    }
    print("JSON " + json.dumps(salida, ensure_ascii=False))
    """
)


@pytest.fixture(scope="module")
def medido(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    pytest.importorskip("optbinning")
    destino: Path = tmp_path_factory.mktemp("oraculo_comparacion")
    proceso = subprocess.run(
        [sys.executable, "-c", _CODIGO, str(destino)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        # El hijo escribe en UTF-8 aunque la consola de Windows sea cp1252 (sus avisos llevan
        # tildes): sin esto el hilo lector reventaba en el CI de Windows.
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"},
        check=False,
    )
    lineas = [ln for ln in proceso.stdout.splitlines() if ln.startswith("JSON ")]
    assert proceso.returncode == 0 and lineas, proceso.stderr[-3000:]
    resultado: dict[str, Any] = json.loads(lineas[-1][5:])
    return resultado


#: SDD-34 §0.3: ``(AUC, Gini, KS, PSI común, banda, K, HHI, índice, validación)`` en la OOT.
TABLA_0_3: Final[dict[str, tuple[Any, ...]]] = {
    "base": (0.656, 0.312, 0.252, 0.007, "stable", 5, 0.245, 0.127, "fail"),
    "tramos_4": (0.658, 0.316, 0.249, 0.008, "stable", 6, 0.189, 0.069, "pass"),
    "iv_005": (0.633, 0.266, 0.195, 0.013, "stable", 6, 0.217, 0.147, "fail"),
    "sin_mejor": (0.650, 0.299, 0.242, 0.017, "stable", 5, 0.307, 0.267, "pass"),
    "sin_stepwise": (0.656, 0.312, 0.252, 0.007, "stable", 5, 0.245, 0.127, "fail"),
    "corr_050": (0.656, 0.312, 0.252, 0.007, "stable", 5, 0.245, 0.127, "fail"),
    "otra_particion": (0.661, 0.322, 0.247, 0.009, "stable", 6, 0.211, 0.131, "fail"),
    "otra_cartera": (0.712, 0.424, 0.320, 0.745, "redevelop", 7, 0.213, 0.205, "fail"),
}
#: La mitad del último decimal publicado: §0.3 redondea a tres decimales.
_TOL: Final = 0.0005 + 1e-9


def _modelos(medido: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["name"]: m for clave in ("seis", "niveles") for m in medido[clave]["modelos"]}


@pytest.mark.parametrize("nombre", sorted(TABLA_0_3))
def test_las_cifras_de_cada_corrida_son_las_de_0_3(medido: dict[str, Any], nombre: str) -> None:
    auc, gini, ks, psi, banda, k, hhi, indice, validacion = TABLA_0_3[nombre]
    m = _modelos(medido)[nombre]
    assert m["evaluation_sample"] == "oot"
    assert m["auc"] == pytest.approx(auc, abs=_TOL)
    assert m["gini"] == pytest.approx(gini, abs=_TOL)
    assert m["ks"] == pytest.approx(ks, abs=_TOL)
    assert m["psi_common"] == pytest.approx(psi, abs=_TOL)
    assert m["psi_common_band"] == banda
    assert m["k"] == k
    assert m["hhi"] == pytest.approx(hhi, abs=_TOL)
    assert m["concentration_index"] == pytest.approx(indice, abs=_TOL)
    assert m["validation_status"] == validacion


def test_la_mejor_variable_de_la_base_es_ingreso_mensual(medido: dict[str, Any]) -> None:
    assert medido["mejor"] == "ingreso_mensual"


def test_los_dos_retadores_repetidos_son_el_mismo_modelo(medido: dict[str, Any]) -> None:
    assert medido["seis"]["card"]["same_as"] == {"sin_stepwise": "base", "corr_050": "base"}


def test_la_prueba_pareada_contra_la_base(medido: dict[str, Any]) -> None:
    pruebas = {(p["model_a"], p["model_b"]): p for p in medido["seis"]["pruebas"]}
    assert all(p["paired"] for p in pruebas.values())
    assert pruebas[("base", "iv_005")]["result"] == "a_better"
    assert pruebas[("base", "iv_005")]["p_value"] < 0.001
    # Los p-valores medidos en S49 (Windows): el solver de OptBinning mueve la tarjeta en el último
    # decimal según la plataforma y el p-valor lo amplifica (macOS 3.11: 0,6572 frente a 0,6563).
    # Lo que el oráculo vigila es la conclusión —un empate claro—, con una tolerancia de 0,01.
    for alternativa, p_valor in (("tramos_4", 0.656), ("sin_mejor", 0.717)):
        prueba = pruebas[("base", alternativa)]
        assert prueba["result"] == "tie"
        assert prueba["p_value"] >= 0.05
        assert prueba["p_value"] == pytest.approx(p_valor, abs=0.01)
    # El mismo modelo: varianza de la diferencia nula y AUC iguales, empate sin estadístico.
    assert pruebas[("base", "sin_stepwise")]["result"] == "tie"
    assert pruebas[("base", "sin_stepwise")]["statistic"] is None


def test_las_dos_fronteras_con_empates(medido: dict[str, Any]) -> None:
    card = medido["seis"]["card"]
    assert set(card["frontier_stability"]) == {
        "base",
        "tramos_4",
        "sin_mejor",
        "sin_stepwise",
        "corr_050",
    }
    assert card["frontier_concentration"] == ["tramos_4"]


def test_los_niveles_de_comparabilidad(medido: dict[str, Any]) -> None:
    assert medido["seis"]["card"]["levels"] == ["referencia"] + ["misma_muestra"] * 5
    assert medido["niveles"]["card"]["levels"] == ["referencia", "misma_cartera", "otra_cartera"]
    razones = {(p["model_a"], p["model_b"]): p["reason"] for p in medido["niveles"]["pruebas"]}
    assert razones[("base", "otra_particion")] == "otras_operaciones"
    assert razones[("base", "otra_cartera")] == "otra_cartera"


def test_la_lectura_de_0_3(medido: dict[str, Any]) -> None:
    lectura = medido["seis"]["lectura"]
    assert lectura[0] == (
        "Las seis corridas usan las mismas operaciones; sin_stepwise y corr_050 son el mismo "
        "modelo que base."
    )
    assert lectura[1] == (
        "En discriminación empatan base, tramos_4 y sin_mejor; iv_005 discrimina menos (Gini "
        "0,266 frente a 0,312; p < 0,001)."
    )
    assert lectura[2] == "Todas son estables."
    assert lectura[3] == "Reparte mejor sus tramos: tramos_4 (índice 0,07 frente a 0,13)."
    assert "Ninguna otra supera a tramos_4 en discriminación y concentración" in lectura[4]
    assert lectura[5].startswith("Pasan la validación técnica tramos_4 y sin_mejor; fallan base")
    assert lectura[6] == (
        "Comparten dos variables; iv_005 quita antiguedad_meses y mora_max_12m; sin_mejor quita "
        "ingreso_mensual."
    )


def test_las_tres_provisiones_de_0_3(medido: dict[str, Any]) -> None:
    filas = {(f["model"], f["stage"]): f for f in medido["ifrs9"]["provision"]}
    assert round(filas[("f4", "total")]["ecl"]) == 4_786_739
    assert round(filas[("horizonte_3", "total")]["ecl_difference"]) == -221_355
    assert round(filas[("horizonte_3", "2")]["ecl_difference"]) == -221_355
    assert round(filas[("cov_2", "1")]["ecl_difference"]) == 39_110
    assert round(filas[("cov_2", "2")]["ecl_difference"]) == -107_655
    assert round(filas[("cov_2", "total")]["ecl_difference"]) == -68_545
    assert all(f["same_unit"] for f in filas.values())
    lectura = medido["ifrs9"]["lectura"]
    assert "horizonte_3 provisiona 221.355 menos que f4 (-4,6 %), todo en Stage 2." in lectura
