"""La escala maestra por la puerta guiada (SDD-32 D-ESC-5, D-ESC-6, D-ESC-8 y D-DEC).

Corre por defecto y habla; ``set_grades``/``set_cutoff`` escriben su hoja y la decisión con motivo
(la misma por la puerta guiada y por la sección ``decisions`` del YAML); una decisión cuyo efecto ya
no está en el config avisa (D-DEC-3), no falla; ``apply`` puntúa solicitudes nuevas con la tarjeta
de la última corrida.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from _ui_f1 import write_stacked_behavior_parquet

import bayesrisk
from bayesrisk.core.config import config_hash, dump_config, loads_config
from bayesrisk.core.decisions import REGLA_DECISION_HUMANA, REGLA_DECISION_SIN_EFECTO
from bayesrisk.guided import Scorecard, ScorecardInputError
from bayesrisk.master_scale.config import MasterScaleConfig


@pytest.fixture(autouse=True)
def _usar_fake_binning_process(fake_binning_process: object) -> None:
    del fake_binning_process


@pytest.fixture
def fuente(tmp_path: Path) -> Path:
    ruta = tmp_path / "cartera.parquet"
    write_stacked_behavior_parquet(ruta, repeats=50)
    return ruta


def _puerta(fuente: Path, tmp_path: Path, **kwargs: Any) -> Scorecard:
    base: dict[str, Any] = {
        "target": "bad_flag",
        "id": "loan_id",
        "cohort": "cohort",
        "oot_cohorts": ["oot"],
        "name": "escala",
        "run_dir": tmp_path / "corridas",
        "min_iv": 0.0,
    }
    base.update(kwargs)
    sc = Scorecard(fuente, **base)
    sc._echo = lambda _texto: None
    return sc


def _eventos(study: Any) -> list[dict[str, Any]]:
    """Los eventos ``decision`` que la corrida declaró antes de sus pasos (preámbulo y D-DEC)."""
    return [payload for _paso, payload in study.preamble]


def test_la_escala_corre_por_defecto_y_habla(fuente: Path, tmp_path: Path) -> None:
    sc = _puerta(fuente, tmp_path)
    assert isinstance(sc.config.master_scale, MasterScaleConfig)
    assert sc.config.master_scale.grade_edges is None
    assert sc.config.master_scale.approval_cutoff is None
    assert sc.steps[-2:] == ("master_scale", "report")
    assert "\nmaster_scale:" in sc.to_yaml()
    sc.run()
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    resumen = sc.summary("master_scale")
    assert resumen.label == "Escala maestra"
    assert 3 <= len(resumen.lines) <= 8
    assert "Sin corte declarado" in resumen.text()
    tabla = sc.results["master_scale"]
    assert list(tabla.columns[:3]) == ["Tramo", "Puntaje", "PD del tramo"]
    assert tabla["Tramo"].tolist() == list(range(1, len(tabla.index) + 1))
    assert [titulo for titulo, _t, _f in resumen.extra_tables] == ["Tabla de puntos de corte"]
    for clave in ("grades", "grade_table", "cutoff_table", "assignment", "result", "card"):
        assert sc.study.artifacts.has("master_scale", clave), clave


def test_set_grades_y_set_cutoff_escriben_su_hoja_y_su_decision(
    fuente: Path, tmp_path: Path
) -> None:
    sc = _puerta(fuente, tmp_path).run()
    formados = list(sc.study.artifacts.get("master_scale", "card").cuts)
    assert len(formados) >= 2
    cortes = sorted(formados[:2], reverse=True)  # en cualquier orden: se guardan ordenados
    sc.set_grades(cortes, reason="los cortes de la política vigente")
    assert sc.config.master_scale.grade_edges == tuple(sorted(cortes))
    sc.set_cutoff(cortes[0], reason="apetito: tasa de malos de los aprobados acotada")
    assert sc.config.master_scale.approval_cutoff == float(cortes[0])
    registros = sc.config.decisions[-2:]
    assert [r.action for r in registros] == ["set_grades", "set_cutoff"]
    assert all(r.columns == ("score",) for r in registros)
    assert registros[0].value == {"master_scale.grade_edges": sorted(cortes)}
    assert registros[1].value == {"master_scale.approval_cutoff": float(cortes[0])}
    with pytest.raises(ScorecardInputError, match="exige reason="):
        sc.set_cutoff(500, reason=" ")
    with pytest.raises(ScorecardInputError, match="al menos un corte"):
        sc.set_grades([], reason="ninguno")
    with pytest.raises(ScorecardInputError, match="repite un corte"):
        sc.set_grades([500.5, 500.5], reason="repetido")
    # Un error no deja el config a medias: el registro y la hoja siguen como estaban.
    assert sc.config.master_scale.grade_edges == tuple(sorted(cortes))
    assert [r.action for r in sc.config.decisions[-2:]] == ["set_grades", "set_cutoff"]

    sc.resume()
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    ficha = sc.study.artifacts.get("master_scale", "card")
    assert ficha.source == "institution"
    assert list(ficha.cuts) == sorted(cortes)
    corte_tabla = sc.study.artifacts.get("master_scale", "cutoff_table")
    assert corte_tabla.loc[corte_tabla["declared"], "cutoff_score"].eq(float(cortes[0])).all()
    humanas = [p for p in _eventos(sc.study) if p.get("regla") == REGLA_DECISION_HUMANA]
    assert [p["accion"] for p in humanas][-2:] == ["set_grades", "set_cutoff"]
    final = sc.summary().text()
    assert "set_grades score (cortes " in final
    assert "set_cutoff score (corte " in final
    assert "Corte de la institución: aprobar desde " in sc.summary("master_scale").text()


def test_la_puerta_completa_da_el_mismo_config_y_las_mismas_decisiones(
    fuente: Path, tmp_path: Path
) -> None:
    sc = _puerta(fuente, tmp_path).run()
    corte = float(sc.study.artifacts.get("master_scale", "card").cuts[0])
    sc.set_cutoff(corte, reason="la del comité")
    yaml = sc.to_yaml()
    cfg = loads_config(yaml)
    assert config_hash(cfg) == sc.config_hash
    assert dump_config(cfg) == yaml
    sc.resume()
    por_yaml = bayesrisk.run(cfg, run_dir=tmp_path / "por_yaml")
    assert por_yaml.run_context.status == "done", por_yaml.run_context.error
    humanas = lambda s: [  # noqa: E731
        {k: p[k] for k in ("accion", "motivo", "valor", "variables")}
        for p in _eventos(s)
        if p.get("regla") == REGLA_DECISION_HUMANA
    ]
    assert humanas(por_yaml) == humanas(sc.study)
    tabla = por_yaml.artifacts.get("master_scale", "cutoff_table")
    pd.testing.assert_frame_equal(tabla, sc.study.artifacts.get("master_scale", "cutoff_table"))


def test_una_decision_cuyo_efecto_ya_no_esta_avisa_y_no_falla(fuente: Path, tmp_path: Path) -> None:
    """D-DEC-3 tal cual: ``approval_cutoff`` retirado a mano del YAML."""
    sc = _puerta(fuente, tmp_path).run()
    corte = float(sc.study.artifacts.get("master_scale", "card").cuts[0])
    sc.set_cutoff(corte, reason="la del comité")
    crudo = json.loads(json.dumps(loads_config(sc.to_yaml()).model_dump(mode="json")))
    crudo["master_scale"]["approval_cutoff"] = None
    cfg = loads_config(dump_config(loads_config(json.dumps(crudo))))
    study = bayesrisk.run(cfg, run_dir=tmp_path / "editado")
    assert study.run_context.status == "done", study.run_context.error
    sin_efecto = [p for p in _eventos(study) if p.get("regla") == REGLA_DECISION_SIN_EFECTO]
    assert len(sin_efecto) == 1
    assert sin_efecto[0]["accion"] == "set_cutoff"
    assert sin_efecto[0]["umbral"] == "master_scale.approval_cutoff"
    assert not any(
        p.get("regla") == REGLA_DECISION_HUMANA and p.get("accion") == "set_cutoff"
        for p in _eventos(study)
    )
    tabla = study.artifacts.get("master_scale", "cutoff_table")
    assert not tabla["declared"].any()
    from bayesrisk.guided.summaries import SummaryContext, build_final_summary

    final = build_final_summary(
        study,
        (),
        SummaryContext(project_dir=None, run_dir=None, source_label="", partition_label=""),
    )
    assert any("set_cutoff score" in a and "puntaje de aprobación" in a for a in final.review)


def test_apply_puntua_solicitudes_nuevas_con_la_tarjeta_de_la_corrida(
    fuente: Path, tmp_path: Path
) -> None:
    sc = _puerta(fuente, tmp_path)
    with pytest.raises(ScorecardInputError, match="llama a run"):
        sc.apply(pd.read_parquet(fuente))
    sc.run()
    corte = float(sc.study.artifacts.get("master_scale", "card").cuts[0])
    sc.set_cutoff(corte, reason="la del comité")
    with pytest.raises(ScorecardInputError, match="resume"):
        sc.apply(pd.read_parquet(fuente))
    sc.resume()
    solicitudes = pd.read_parquet(fuente).drop(columns=["bad_flag", "cohort"])
    nuevas = sc.apply(solicitudes)
    assert {"score", "grade", "grade_pd", "decision"} <= set(nuevas.columns)
    asignacion = sc.study.artifacts.get("master_scale", "assignment")
    comun = nuevas.set_index("input_id").join(asignacion, rsuffix="_corrida", how="inner")
    assert len(comun.index) == len(asignacion.index)
    assert (comun["grade"] == comun["grade_corrida"]).all()
    assert (comun["score"] == comun["score_corrida"]).all()
    esperada = comun["score"].astype(float).ge(corte).map({True: "approve", False: "reject"})
    assert comun["decision"].tolist() == esperada.tolist()


def test_cortes_que_dejan_un_tramo_vacio_detienen_la_etapa_y_conservan_lo_anterior(
    fuente: Path, tmp_path: Path
) -> None:
    sc = _puerta(fuente, tmp_path).run()
    sc.set_grades([10_000.5], reason="un corte fuera del rango")
    sc.resume()
    assert sc.study.run_context.status == "failed"
    error = sc.study.run_context.error
    assert error is not None and "tramo 1 sin operaciones de Desarrollo" in error.message
    assert "validation" in {d for d, _k in sc.study.artifacts.keys()}  # noqa: SIM118


def test_apply_tras_una_corrida_parcial_exige_completar_la_escala(
    fuente: Path, tmp_path: Path
) -> None:
    """Pasada 1 de Codex: ``run(until=…)`` limpiaba la marca de decisiones pendientes y ``apply``
    puntuaba sin el corte declarado, que la corrida parcial nunca aplicó."""
    sc = _puerta(fuente, tmp_path).run()
    corte = float(sc.study.artifacts.get("master_scale", "card").cuts[0])
    sc.set_cutoff(corte, reason="la del comité")
    sc.run(until="calibration")
    assert sc.study.run_context.status == "done"
    with pytest.raises(ScorecardInputError, match="completa"):
        sc.apply(pd.read_parquet(fuente))


def test_una_huella_que_no_es_un_numero_queda_sin_efecto_y_la_corrida_sigue() -> None:
    """D-DEC-3 tal cual (pasada 1 de Codex): una huella editada a mano con texto o vacía no
    aborta la corrida; se declara sin efecto."""
    from bayesrisk.core.config import BayesRiskConfig
    from bayesrisk.core.config.schema import DecisionEntry
    from bayesrisk.core.decisions import eventos_de_decisiones

    registros = (
        DecisionEntry(
            action="set_grades",
            columns=("score",),
            reason="editada a mano",
            value={"master_scale.grade_edges": ["anterior"]},
        ),
        DecisionEntry(
            action="set_cutoff",
            columns=("score",),
            reason="editada a mano",
            value={"master_scale.approval_cutoff": "alto"},
        ),
        DecisionEntry(
            action="set_cutoff",
            columns=("puntaje",),
            reason="vacía",
            value={"master_scale.approval_cutoff": None},
        ),
    )
    cfg = BayesRiskConfig.model_validate(
        {
            "master_scale": {"grade_edges": [500.0], "approval_cutoff": 520.0},
            "decisions": [r.model_dump() for r in registros],
        }
    )
    eventos = eventos_de_decisiones(cfg)
    assert [e["regla"] for e in eventos] == [REGLA_DECISION_SIN_EFECTO] * 3


@pytest.mark.parametrize(
    ("accion", "huella", "vigente"),
    [
        ("set_grades", [500, 520], {"grade_edges": [505.0, 520.0]}),
        ("set_grades", [[500]], {"grade_edges": [505.0, 520.0]}),
        ("set_cutoff", 10**400, {"approval_cutoff": 520.0}),
    ],
)
def test_las_huellas_de_la_escala_viajan_enteras_y_el_cotejo_es_total(
    accion: str, huella: object, vigente: dict[str, object]
) -> None:
    """Pasada 2 de Codex: la huella de una hoja de la escala no es una lista de variables —se
    restringía a [] o reventaba con [[500]]— y un entero gigante desbordaba el cotejo."""
    from bayesrisk.core.config import BayesRiskConfig
    from bayesrisk.core.config.schema import DecisionEntry
    from bayesrisk.core.decisions import eventos_de_decisiones

    hoja = "master_scale.grade_edges" if accion == "set_grades" else "master_scale.approval_cutoff"
    registro = DecisionEntry(
        action=accion,  # type: ignore[arg-type]
        columns=("score",),
        reason="editada a mano",
        value={hoja: huella},
    )
    cfg = BayesRiskConfig.model_validate(
        {"master_scale": vigente, "decisions": [registro.model_dump()]}
    )
    (evento,) = eventos_de_decisiones(cfg)
    assert evento["regla"] == REGLA_DECISION_SIN_EFECTO
    assert evento["valor"] == {hoja: huella}


def test_una_huella_historica_ilegible_no_tumba_los_resumenes() -> None:
    """Pasada 3 de Codex: la historia conserva la huella entera, y la línea de la decisión hacía
    float('anterior'): el informe perdía su resumen final y Resultados sus etapas."""
    from bayesrisk.core.config import BayesRiskConfig
    from bayesrisk.core.config.schema import DecisionEntry
    from bayesrisk.core.decisions import eventos_de_decisiones
    from bayesrisk.guided.summaries import decision_line, decision_lines_from_preamble

    registros = (
        DecisionEntry(
            action="set_grades",
            columns=("score",),
            reason="primera",
            value={"master_scale.grade_edges": ["anterior"]},
        ),
        DecisionEntry(
            action="set_grades",
            columns=("score",),
            reason="vigente",
            value={"master_scale.grade_edges": [500]},
        ),
    )
    cfg = BayesRiskConfig.model_validate(
        {"master_scale": {"grade_edges": [500.0]}, "decisions": [r.model_dump() for r in registros]}
    )
    lineas = decision_lines_from_preamble([("decisions", e) for e in eventos_de_decisiones(cfg)])
    assert lineas == (
        "set_grades score (cortes anterior) — «primera»",
        "set_grades score (cortes 500) — «vigente»",
    )
    gigante = {
        "regla": "decision_del_usuario",
        "accion": "set_cutoff",
        "motivo": "m",
        "variables": ["score"],
        "valor": {"master_scale.approval_cutoff": 10**400},
    }
    assert decision_line(gigante).startswith("set_cutoff score (corte 1")
