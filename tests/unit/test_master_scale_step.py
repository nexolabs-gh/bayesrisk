"""El paso ``master_scale`` dentro de una corrida (SDD-32 §2, §3.5, §6, §9).

La muestra «Fuera del ajuste» (D-TTD), las decisiones al trail, los requisitos del pipeline y los
rótulos de una tarjeta que no sólo produce enteros. Con los dobles de OptBinning.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from _ui_f1 import write_stacked_behavior_parquet

from bayesrisk.core.config import BayesRiskConfig
from bayesrisk.core.exceptions import ConfigError
from bayesrisk.core.study import Study
from bayesrisk.guided import Scorecard


@pytest.fixture(autouse=True)
def _usar_fake_binning_process(fake_binning_process: object) -> None:
    del fake_binning_process


def _frame(tmp_path: Path) -> pd.DataFrame:
    ruta = tmp_path / "cartera.parquet"
    write_stacked_behavior_parquet(ruta, repeats=50)
    return pd.read_parquet(ruta)


def _puerta(datos: Any, tmp_path: Path, **kwargs: Any) -> Scorecard:
    sc = Scorecard(
        datos,
        target="bad_flag",
        id="loan_id",
        cohort="cohort",
        oot_cohorts=["oot"],
        name="paso",
        run_dir=tmp_path / "corridas",
        min_iv=0.0,
        **kwargs,
    )
    sc._echo = lambda _texto: None
    return sc


def test_las_solicitudes_sin_desenlace_son_una_muestra_mas(tmp_path: Path) -> None:
    frame = _frame(tmp_path)
    sin_desenlace = frame.index[frame["cohort"] != "oot"][:40]
    frame["bad_flag"] = frame["bad_flag"].astype("float64")
    frame.loc[sin_desenlace, "bad_flag"] = np.nan
    sc = _puerta(frame, tmp_path).run()
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    fuera = sc.study.artifacts.get("scorecard", "out_of_model_score")
    assert len(fuera.index) == 40
    tabla = sc.study.artifacts.get("master_scale", "grade_table")
    propia = tabla.loc[tabla["sample"] == "fuera_de_modelo"]
    assert propia["n"].sum() == 40
    assert (propia["n_with_outcome"] == 0).all()
    assert propia["bad_rate"].isna().all() and propia["jeffreys_p_value"].isna().all()
    cortes = sc.study.artifacts.get("master_scale", "cutoff_table")
    filas = cortes.loc[cortes["sample"] == "fuera_de_modelo"]
    assert (filas["n_scored"] == 40).all() and (filas["n_with_outcome"] == 0).all()
    assert filas["approved_share"].notna().all()
    for columna in ("approved_bad_rate", "bads_avoided_share", "goods_rejected_share"):
        assert filas[columna].isna().all(), columna
    assert "Participación Fuera del ajuste" in sc.results["master_scale"].columns


def test_la_escala_declara_sus_decisiones_al_trail(tmp_path: Path) -> None:
    sc = _puerta(_frame(tmp_path), tmp_path).run()
    corte = float(sc.study.artifacts.get("master_scale", "card").cuts[0])
    sc.set_cutoff(corte, reason="prueba del trail")
    sc.resume()
    trail = sc.project_dir / "run" / "audit_trail.jsonl"
    eventos = [json.loads(linea) for linea in trail.read_text(encoding="utf-8").splitlines()]
    propios = {
        e["payload"]["regla"]: e["payload"]
        for e in eventos
        if e.get("kind") == "decision"
        and str(e["payload"].get("regla", "")).startswith("master_scale_")
    }
    assert {"master_scale_grades", "master_scale_pd", "master_scale_cutoff"} <= set(propios)
    assert propios["master_scale_grades"]["accion"] == "formar_tramos"
    assert propios["master_scale_grades"]["valor"]["origen"] == "formed"
    assert propios["master_scale_pd"]["valor"]["pd"] == list(
        sc.study.artifacts.get("master_scale", "card").pd
    )
    assert propios["master_scale_cutoff"]["umbral"] == corte


def test_la_escala_exige_el_puntaje_y_la_calibracion_antes_de_correr() -> None:
    from bayesrisk.ui.presets import standard_preset

    crudo = standard_preset()["config"]
    crudo["master_scale"] = {}
    crudo["calibration"] = None
    for seccion in ("performance", "stability", "validation"):
        crudo[seccion] = None
    with pytest.raises(ConfigError, match="calibration"):
        Study(BayesRiskConfig.model_validate(crudo), apply_global_seed=False).check_pipeline()


def test_una_tarjeta_sin_redondeo_rotula_los_cortes_exactos(tmp_path: Path) -> None:
    sc = _puerta(_frame(tmp_path), tmp_path)
    scorecard = sc.config.scorecard.model_copy(update={"rounding_method": "none"})
    sc._config = sc._config.model_copy(update={"scorecard": scorecard})
    sc.run()
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    ficha = sc.study.artifacts.get("master_scale", "card")
    assert ficha.integer_card is False
    rotulos = sc.study.artifacts.get("master_scale", "grades")["label"].tolist()
    assert rotulos[0].startswith("desde ") and rotulos[-1].startswith("menos de ")
