"""D-H10-3: entradas, target canónico y preservación de las tres puertas."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from _proyeccion_canonica import diferencias, proyeccion_canonica
from _ui_client import ui_client
from _ui_f1 import write_stacked_behavior_parquet
from pandas.testing import assert_frame_equal, assert_series_equal

import bayesrisk
from bayesrisk.core.config import BayesRiskConfig, config_hash, loads_config
from bayesrisk.core.exceptions import DataValidationError
from bayesrisk.data.config import Predicate, Rule, TargetConfig
from bayesrisk.data.target import TargetDefinition
from bayesrisk.model.exceptions import ModelFitError
from bayesrisk.model.step import _pd_frame_de
from bayesrisk.ui import runs
from bayesrisk.ui.settings import UiConfig


@pytest.fixture
def fuente(tmp_path: Path) -> pd.DataFrame:
    ruta = tmp_path / "entrada.parquet"
    write_stacked_behavior_parquet(ruta, repeats=50)
    return pd.read_parquet(ruta)


@pytest.mark.parametrize("personalizado", [False, True])
@pytest.mark.parametrize("incluir_pantalla", [False, True])
def test_target_y_dtypes_por_las_tres_puertas(
    fuente: pd.DataFrame,
    tmp_path: Path,
    fake_binning_process: object,
    monkeypatch: pytest.MonkeyPatch,
    personalizado: bool,
    incluir_pantalla: bool,
) -> None:
    del fake_binning_process
    if incluir_pantalla:
        pytest.importorskip("fastapi", reason="la pantalla exige el extra ui")
    frame = fuente.rename(columns={"bad_flag": "target"})
    frame["target"] = frame["target"].astype("Int32")
    frame.loc[frame.index[:35], "target"] = pd.NA
    frame["score"] = frame["score"].astype("int32" if personalizado else "float32")
    frame["operacion"] = pd.array([2**64 - 1 - i for i in range(len(frame))], dtype="uint64")
    original = frame.copy(deep=True)
    sc = bayesrisk.Scorecard(
        frame,
        target="target",
        id="operacion",
        cohort="cohort",
        oot_cohorts=["oot"],
        run_dir=tmp_path / "guiada",
        formats=[],
    )
    if personalizado:
        declarado = sc.config.model_dump(mode="json", by_alias=True)
        declarado["data"]["target"]["target_col"] = "objetivo"
        sc._config = BayesRiskConfig.model_validate(declarado)
    sc.run()
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    assert_frame_equal(frame, original)
    labels = sc.study.artifacts.get("data", "labels")
    assert_frame_equal(labels.frame.loc[:, original.columns], original)
    raw = sc.study.artifacts.get("model", "raw_pd_frame")
    assert labels.target_col in raw and "target" not in raw
    for dominio, clave in [
        ("scorecard", "score"),
        ("calibration", "calibrated_pd_frame"),
        ("scorecard", "out_of_model_score"),
        ("calibration", "out_of_model_calibrated_pd_frame"),
    ]:
        tabla = sc.study.artifacts.get(dominio, clave)
        assert not tabla.empty, (dominio, clave)
        assert_series_equal(
            tabla["target"], labels.frame.loc[tabla.index, labels.target_col], check_names=False
        )
    completa = bayesrisk.run(loads_config(sc.to_yaml()), run_dir=tmp_path / "completa")
    assert completa.run_context.status == "done", completa.run_context.error
    assert diferencias(proyeccion_canonica(sc.study), proyeccion_canonica(completa)) == []
    assert config_hash(completa.config) == sc.config_hash

    if not incluir_pantalla:
        return

    observados: list[Any] = []
    ejecutar = bayesrisk.run

    def observar(*args: Any, **kwargs: Any) -> Any:
        study = ejecutar(*args, **kwargs)
        observados.append(study)
        return study

    monkeypatch.setattr(bayesrisk, "run", observar)
    workdir = tmp_path / "pantalla"
    with ui_client(UiConfig(workdir=str(workdir))) as cliente:
        archivo = io.BytesIO()
        frame.to_parquet(archivo)
        subida = cliente.post(
            "/api/upload",
            files={"file": ("entrada.parquet", archivo.getvalue(), "application/octet-stream")},
        )
        assert subida.status_code == 200, subida.text
        respuesta = cliente.post(
            "/api/run",
            json={
                "config": sc.config.model_dump(mode="json", by_alias=True),
                "dataset_id": subida.json()["dataset_id"],
            },
        )
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["status"] == "done", respuesta.text
        resultado = cliente.get(f"/api/results/{respuesta.json()['run_id']}")
        assert resultado.status_code == 200
    assert len(observados) == 1
    assert diferencias(proyeccion_canonica(sc.study), proyeccion_canonica(observados[0])) == []
    assert config_hash(observados[0].config) == sc.config_hash
    payload = runs.load_results(respuesta.json()["run_id"], workdir=workdir)
    assert payload["scorecard"] is not None and payload["calibration"] is not None
    informe = runs.load_report(respuesta.json()["run_id"], workdir=workdir)
    assert "Tarjeta" in informe and "Calibraci" in informe


@pytest.mark.parametrize("nombre", ["pd_raw", "linear_predictor"])
def test_target_no_puede_sobrescribirse_con_predicciones(nombre: str) -> None:
    frame = pd.DataFrame(
        {"partition": ["desarrollo", "holdout"], nombre: [0, 1], "x__woe": [-1.0, 1.0]}
    )
    original = frame.copy(deep=True)
    estimator = SimpleNamespace(
        final_woe_columns_=("x__woe",),
        decision_function=lambda _: [0.0, 0.0],
        predict_pd=lambda _: [0.5, 0.5],
    )
    with pytest.raises(ModelFitError, match="colisiona"):
        _pd_frame_de(frame, target_col=nombre, partition_col="partition", estimator=estimator)
    assert_frame_equal(frame, original)


def test_target_y_estado_no_se_sobrescriben() -> None:
    frame = pd.DataFrame({"malo": [0, 1]})
    cfg = TargetConfig(
        target_col="label_status", bad_rule=Rule(all_of=[Predicate(col="malo", op="==", value=1)])
    )
    with pytest.raises(DataValidationError, match="colisiona"):
        TargetDefinition(cfg).apply(frame)
    assert list(frame.columns) == ["malo"]


def test_colision_de_target_con_input_se_rechaza_sin_mutarlo(
    fuente: pd.DataFrame, tmp_path: Path
) -> None:
    frame = fuente.rename(columns={"bad_flag": "target"}).assign(target_bayesrisk=42)
    original = frame.copy(deep=True)
    sc = bayesrisk.Scorecard(
        frame, target="target", cohort="cohort", oot_cohorts=["oot"], run_dir=tmp_path / "colision"
    )
    sc.run(until="data")
    assert sc.study.run_context.status == "failed"
    assert "sobrescribir" in sc.study.run_context.error.message
    assert_frame_equal(frame, original)
