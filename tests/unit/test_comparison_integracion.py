"""El resumen comparable en corridas reales y la comparación por sus puertas (SDD-34 §6, §11).

Corridas guiadas del scorecard con los dobles de OptBinning (OR-Tools revienta el proceso de
pytest); las cifras de §0.3 con OptBinning real viven en ``test_comparison_oraculo.py``, en un
subproceso. Aquí:

- el resumen que deja la corrida es el mismo desde el objeto vivo, desde ``bayesrisk.run`` y desde
  ``runs.save`` de la pantalla, y no trae identificadores de operación;
- su riesgo reproduce el AUC publicado y su PSI común, el PSI publicado con la receta de fábrica;
- una corrida de puntajes externos termina ``done`` y deja su resumen con lo que no tiene en nulo;
- armarlo nunca hace fallar una corrida terminada (D-VIS);
- la puerta guiada y su YAML dan el mismo ``config_hash`` y los mismos artefactos; la elección se
  ata a la huella y queda sin efecto si la corrida elegida ya no está;
- un lineage sin comparación no gana ``comparison_hashes``.
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
from bayesrisk.comparison import comparable
from bayesrisk.core.config import BayesRiskConfig, loads_config
from bayesrisk.guided import Comparison, ComparisonInputError, Scorecard

COHORTES = ("2023Q1", "2023Q2", "2023Q3", "2023Q4", "2024Q1", "2024Q2")


def _cartera(semilla: int = 45) -> pd.DataFrame:
    """6.000 operaciones en seis añadas, con variables enteras a la medida de los dobles."""
    rng = np.random.default_rng(semilla)
    filas = []
    for i, cohorte in enumerate(COHORTES):
        n = 1_000
        x = {c: rng.binomial(3, 0.35, n) for c in ("uso", "atraso", "antiguedad")}
        risk = rng.binomial(2, 0.3, n)
        logit = (
            -2.0
            + 0.9 * (x["uso"] > 1.5)
            + 0.8 * (x["atraso"] > 1.5)
            - 0.6 * (x["antiguedad"] > 1.5)
            + 0.8 * (risk > 0.5)
            + 0.7 * (risk > 1.5)
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
    """Tres corridas guiadas de la misma cartera: la base, una sin una variable y una copia."""
    from conftest import parchar_optbinning

    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        parchar_optbinning(parche)
        raiz = tmp_path_factory.mktemp("comparacion")
        datos = _cartera()
        corridas: dict[str, Scorecard] = {}
        for nombre, extra in (
            ("base", {}),
            ("sin_uso", {"features": ["atraso", "antiguedad", "risk"]}),
            ("sin_stepwise", {"stepwise": False}),
        ):
            sc = Scorecard(
                datos,
                target="bad_flag",
                id="loan_id",
                cohort="cohorte",
                oot_cohorts=["2024Q2"],
                name=nombre,
                run_dir=raiz / "corridas",
                **extra,
            )
            sc._echo = lambda _texto: None
            sc.run()
            assert sc.study.run_context.status == "done", sc.study.run_context.error
            corridas[nombre] = sc
        comp = Comparison(
            [raiz / "corridas" / n for n in ("base", "sin_uso", "sin_stepwise")],
            run_dir=raiz / "comparaciones",
        )
        comp._echo = lambda _texto: None
        comp.run()
        assert comp.study.run_context.status == "done", comp.study.run_context.error
        yield {"raiz": raiz, "corridas": corridas, "comp": comp, "parche": parche}


def _archivo(entorno: dict[str, Any], nombre: str) -> Path:
    return entorno["raiz"] / "corridas" / nombre / "run" / comparable.COMPARABLE_FILENAME


# ── el resumen de una corrida ────────────────────────────────────────────────────────────────


def test_el_resumen_es_el_mismo_desde_las_tres_fuentes(
    entorno: dict[str, Any], tmp_path: Path
) -> None:
    """El archivo de ``bayesrisk.run``, el objeto vivo y ``runs.save``: lo mismo, byte a byte."""
    from bayesrisk.ui import runs

    sc = entorno["corridas"]["base"]
    en_disco = _archivo(entorno, "base").read_bytes()
    assert comparable.bytes_canonicos(comparable.armar(sc.study)) == en_disco
    assert comparable.bytes_canonicos(comparable.resumen_de(sc.study)) == en_disco
    run_id = runs.save(sc.study, workdir=tmp_path, governance=None)
    assert (tmp_path / "runs" / run_id / comparable.COMPARABLE_FILENAME).read_bytes() == en_disco


def test_el_resumen_no_trae_identificadores_de_operacion(entorno: dict[str, Any]) -> None:
    texto = _archivo(entorno, "base").read_text(encoding="utf-8")
    assert "op-" not in texto
    resumen = json.loads(texto)
    assert set(resumen["evaluation_scores"]) == {
        "order",
        "basis",
        "rows_hash",
        "default_hash",
        "risk",
        "default",
    }


def test_su_riesgo_reproduce_el_auc_publicado(entorno: dict[str, Any]) -> None:
    from sklearn.metrics import roc_auc_score

    resumen = json.loads(_archivo(entorno, "base").read_text(encoding="utf-8"))
    puntajes = resumen["evaluation_scores"]
    oot = next(s for s in resumen["samples"] if s["sample"] == "oot")
    assert resumen["evaluation_sample"] == "oot"
    assert len(puntajes["risk"]) == oot["n"] == 1_000
    assert roc_auc_score(puntajes["default"], puntajes["risk"]) == pytest.approx(
        oot["auc"], abs=1e-12
    )


def test_el_psi_comun_es_el_publicado_con_la_receta_de_fabrica(entorno: dict[str, Any]) -> None:
    """D-CMP-7: con la receta de fábrica el PSI común coincide con el que la corrida publicó."""
    resumen = json.loads(_archivo(entorno, "base").read_text(encoding="utf-8"))
    assert resumen["psi_recipe"] == comparable.RECETA_PSI_DE_FABRICA
    propio = next(p for p in resumen["score_psi"] if p["comparison"] == "dev_vs_oot")
    assert resumen["score_psi_common"]["psi"] == pytest.approx(propio["psi"], abs=1e-15)
    assert resumen["score_psi_common"]["band"] == propio["band"]


def test_el_mismo_modelo_tiene_la_misma_huella_con_otro_config(entorno: dict[str, Any]) -> None:
    base = json.loads(_archivo(entorno, "base").read_text(encoding="utf-8"))
    copia = json.loads(_archivo(entorno, "sin_stepwise").read_text(encoding="utf-8"))
    otra = json.loads(_archivo(entorno, "sin_uso").read_text(encoding="utf-8"))
    assert base["config_hash"] != copia["config_hash"]
    assert base["model_hash"] == copia["model_hash"]
    assert base["model_hash"] != otra["model_hash"]


def test_un_lineage_sin_comparacion_no_gana_la_clave(entorno: dict[str, Any]) -> None:
    lineage = json.loads(
        (entorno["raiz"] / "corridas" / "base" / "run" / "study" / "lineage.json").read_text(
            encoding="utf-8"
        )
    )
    assert "comparison_hashes" not in lineage
    assert "bundle_hash" not in lineage


# ── puntajes externos y D-VIS ────────────────────────────────────────────────────────────────


def _puntajes_externos() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(1)
    n = 900
    particion = np.array(["desarrollo"] * 500 + ["holdout"] * 200 + ["oot"] * 200)
    target = (rng.random(n) < 0.25).astype("int64")
    score = np.round(600 - 40 * target + rng.normal(scale=30, size=n))
    pd_cal = 1.0 / (1.0 + np.exp((score - 560) / 25))
    indice = pd.Index([f"op-{i}" for i in range(n)], name="loan_id")
    puntaje = pd.DataFrame({"partition": particion, "target": target, "score": score}, index=indice)
    calibrada = pd.DataFrame(
        {"partition": particion, "target": target, "pd_calibrated": pd_cal}, index=indice
    )
    return puntaje, calibrada


def test_una_corrida_de_puntajes_externos_deja_su_resumen(tmp_path: Path) -> None:
    """«Validar un modelo existente»: sin tarjeta ni variables, termina ``done`` con su resumen."""
    puntaje, calibrada = _puntajes_externos()
    config = BayesRiskConfig.model_validate({"performance": {}, "audit": {"enabled": True}})
    study = bayesrisk.run(
        config,
        run_dir=tmp_path / "externa",
        artifacts={
            ("scorecard", "score"): puntaje,
            ("calibration", "calibrated_pd_frame"): calibrada,
        },
    )
    assert study.run_context.status == "done", study.run_context.error
    resumen, _ = comparable.leer(tmp_path / "externa")
    assert resumen["model_hash"] is None and resumen["variables"] is None
    assert resumen["portfolio_hash"] is None
    assert {"model_hash", "variables", "grades", "portfolio_hash"} <= set(resumen["missing"])
    assert "op-" not in (tmp_path / "externa" / "comparable.json").read_text(encoding="utf-8")


def test_armar_el_resumen_nunca_tumba_una_corrida(
    entorno: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-VIS: la corrida sigue ``done``, el registro lo declara y no queda resumen a medias."""
    puntaje, calibrada = _puntajes_externos()

    def _revienta(_study: Any) -> None:
        raise RuntimeError("defecto inyectado")

    monkeypatch.setattr(comparable, "armar_al_cerrar", _revienta)
    config = BayesRiskConfig.model_validate({"performance": {}, "audit": {"enabled": True}})
    study = bayesrisk.run(
        config,
        run_dir=tmp_path / "rota",
        artifacts={
            ("scorecard", "score"): puntaje,
            ("calibration", "calibrated_pd_frame"): calibrada,
        },
    )
    assert study.run_context.status == "done"
    assert not (tmp_path / "rota" / comparable.COMPARABLE_FILENAME).exists()
    eventos = [
        json.loads(linea)
        for linea in (tmp_path / "rota" / "audit_trail.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    aviso = [e for e in eventos if e["payload"].get("regla") == comparable.REGLA_SIN_RESUMEN]
    assert len(aviso) == 1 and "defecto inyectado" in aviso[0]["payload"]["valor"]["causa"]
    assert eventos[-1]["kind"] == "run_end"


def test_un_sink_que_no_registra_el_aviso_no_le_quita_el_run_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pasada 1 de Codex: el aviso del resumen tampoco puede tumbar la corrida si el sink falla al
    registrarlo; la corrida sigue terminada, emite su ``run_end`` y la causa queda en el Study."""
    from bayesrisk.core.audit import AuditEvent, InMemoryAuditSink
    from bayesrisk.core.study import Study

    class _SinkQueFallaConElAviso(InMemoryAuditSink):
        def emit(self, event: AuditEvent) -> None:
            if event.payload.get("regla") == comparable.REGLA_SIN_RESUMEN:
                raise OSError("disco lleno")
            super().emit(event)

    def _revienta(_study: Any) -> None:
        raise RuntimeError("defecto inyectado")

    monkeypatch.setattr(comparable, "armar_al_cerrar", _revienta)
    puntaje, calibrada = _puntajes_externos()
    study = Study(BayesRiskConfig.model_validate({"performance": {}}))
    sink = _SinkQueFallaConElAviso()
    study.set_audit_sink(sink)
    study.artifacts.set("scorecard", "score", puntaje)
    study.artifacts.set("calibration", "calibrated_pd_frame", calibrada)
    study.run()
    assert study.run_context.status == "done"
    assert sink.events[-1].kind == "run_end"
    assert "defecto inyectado" in (study._causa_sin_resumen_comparable or "")


# ── la comparación por sus puertas ───────────────────────────────────────────────────────────


def test_la_comparacion_publica_sus_artefactos_y_su_lineage(entorno: dict[str, Any]) -> None:
    comp = entorno["comp"]
    claves = {c for d, c in comp.study.artifacts.keys() if d == "comparison"}  # noqa: SIM118
    assert claves == {
        "runs",
        "models",
        "tests",
        "samples",
        "variables",
        "provision",
        "reading",
        "result",
        "card",
    }
    huellas = tuple(
        comparable.huella(json.loads(_archivo(entorno, n).read_text(encoding="utf-8")))
        for n in ("base", "sin_uso", "sin_stepwise")
    )
    assert comp.study.run_context.lineage.comparison_hashes == huellas
    card = comp.study.artifacts.get("comparison", "card")
    assert card.same_as == {"sin_stepwise": "base"}
    assert card.levels == ("referencia", "misma_muestra", "misma_muestra")
    assert 3 <= len(card.reading) <= 8


def test_la_puerta_completa_da_lo_mismo(entorno: dict[str, Any], tmp_path: Path) -> None:
    """D-SIM-1: el YAML de la puerta, corrido por ``bayesrisk.run``, da los mismos artefactos."""
    comp = entorno["comp"]
    study = bayesrisk.run(loads_config(comp.to_yaml()), run_dir=tmp_path / "completa")
    assert study.run_context.status == "done", study.run_context.error
    assert study.lineage_bundle().config_hash == comp.config_hash
    assert (
        study.run_context.lineage.comparison_hashes
        == comp.study.run_context.lineage.comparison_hashes
    )
    for clave in ("runs", "models", "tests", "samples", "variables"):
        esperado = comp.study.artifacts.get("comparison", clave)
        obtenido = study.artifacts.get("comparison", clave)
        if clave == "runs":
            esperado, obtenido = (
                esperado.drop(columns=["created_at"]),
                obtenido.drop(columns=["created_at"]),
            )
        pd.testing.assert_frame_equal(obtenido, esperado)
    assert study.artifacts.get("comparison", "reading") == comp.study.artifacts.get(
        "comparison", "reading"
    )


def test_las_rutas_no_entran_al_config_hash(entorno: dict[str, Any], tmp_path: Path) -> None:
    comp = entorno["comp"]
    movidas = []
    for i, ruta in enumerate(comp.config.comparison.runs):
        destino = tmp_path / f"r{i}.json"
        destino.write_bytes(Path(ruta).read_bytes())
        movidas.append(str(destino))
    otra = comp.config.model_copy(
        update={"comparison": comp.config.comparison.model_copy(update={"runs": tuple(movidas)})}
    )
    from bayesrisk.core.config import config_hash

    assert config_hash(otra) == comp.config_hash


def test_el_resumen_de_la_comparacion_habla(entorno: dict[str, Any]) -> None:
    comp = entorno["comp"]
    etapa = comp.summary("comparison")
    assert etapa.label == "Comparación"
    assert "Las tres corridas usan las mismas operaciones" in etapa.lines[0]
    assert list(etapa.table.columns)[:3] == ["Modelo", "Muestra", "AUC"]
    final = comp.summary()
    assert final.title == "Resumen de la comparación"
    assert final.to_dict()["family"] == "comparacion"


def test_la_eleccion_queda_en_el_registro_y_cae_si_la_corrida_ya_no_esta(
    entorno: dict[str, Any], tmp_path: Path
) -> None:
    comp = Comparison(
        [entorno["raiz"] / "corridas" / n for n in ("base", "sin_uso")],
        name="eleccion",
        run_dir=tmp_path,
    )
    comp._echo = lambda _texto: None
    comp.choose("sin_uso", reason="menos variables, la misma discriminación")
    assert comp.study.artifacts.get("comparison", "card").chosen == "sin_uso"
    assert any(
        "eligió sin_uso" in linea for linea in comp.study.artifacts.get("comparison", "reading")
    )
    humanas = [
        p for _paso, p in comp.study.run_context.preamble if p["regla"] == "decision_del_usuario"
    ]
    assert humanas[-1]["accion"] == "choose" and humanas[-1]["autor"] == "usuario"

    # La misma elección sobre otra lista: la corrida elegida ya no está.
    crudo = comp.config.model_dump(mode="python")
    crudo["comparison"]["runs"] = [
        str(entorno["raiz"] / "corridas" / "base"),
        str(entorno["raiz"] / "corridas" / "sin_stepwise"),
    ]
    study = bayesrisk.run(BayesRiskConfig.model_validate(crudo), run_dir=tmp_path / "otra")
    assert study.run_context.status == "done", study.run_context.error
    assert study.artifacts.get("comparison", "card").chosen is None
    sin_efecto = [
        p for _paso, p in study.run_context.preamble if p["regla"] == "decision_sin_efecto"
    ]
    assert sin_efecto and sin_efecto[0]["accion"] == "choose"


def test_la_puerta_rechaza_lo_que_no_se_compara(entorno: dict[str, Any], tmp_path: Path) -> None:
    base = entorno["raiz"] / "corridas" / "base"
    with pytest.raises(ComparisonInputError, match="entre 2 y 10"):
        Comparison([base], run_dir=tmp_path)
    with pytest.raises(ComparisonInputError, match="la misma"):
        Comparison([base, base], run_dir=tmp_path)
    with pytest.raises(ComparisonInputError, match="no tiene resumen comparable"):
        vieja = tmp_path / "vieja"
        (vieja / "study").mkdir(parents=True)
        Comparison([base, vieja], run_dir=tmp_path)
    with pytest.raises(ComparisonInputError, match="no es una de las corridas"):
        entorno["comp"].choose("ninguna", reason="x")


def test_un_objeto_vivo_se_compara_igual_que_su_carpeta(
    entorno: dict[str, Any], tmp_path: Path
) -> None:
    vivo = Comparison(
        [entorno["corridas"]["base"], entorno["corridas"]["sin_uso"]], name="vivo", run_dir=tmp_path
    )
    carpeta = Comparison(
        [entorno["raiz"] / "corridas" / n for n in ("base", "sin_uso")],
        name="carpeta",
        run_dir=tmp_path,
    )
    assert vivo.config_hash == carpeta.config_hash
    assert [Path(r).name for r in vivo.config.comparison.runs] == [
        Path(r).name for r in carpeta.config.comparison.runs
    ]


def test_con_nombres_repetidos_se_elige_por_el_nombre_visible(tmp_path: Path) -> None:
    """Pasada 2 de Codex: dos corridas que se llaman igual se distinguen por su posición
    («consumo (1)», «consumo (2)») y ``choose`` elige la que se nombra, por su huella."""
    from test_comparison_step import _resumen

    rutas = []
    for i, ruido in enumerate((0.5, 0.9), start=1):
        resumen = _resumen("consumo", riesgo=[float(v) for v in np.linspace(0, 1, 600) * ruido])
        rutas.append(
            comparable.escribir(resumen, (tmp_path / f"r{i}").mkdir() or tmp_path / f"r{i}")
        )
    comp = Comparison(rutas, name="repetidos", run_dir=tmp_path / "comparaciones")
    comp._echo = lambda _texto: None
    assert comp.names == ("consumo (1)", "consumo (2)")
    comp.choose("consumo (2)", reason="la segunda")
    card = comp.study.artifacts.get("comparison", "card")
    assert card.chosen == "consumo (2)"
    registro = comp.config.decisions[-1]
    segunda, _ = comparable.leer(rutas[1])
    assert registro.value == {"comparison.choice": comparable.huella(segunda)}
    with pytest.raises(ComparisonInputError, match="no es una de las corridas"):
        comp.choose("consumo", reason="ambiguo")
