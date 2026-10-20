"""Regresiones de la revisión B: separar entrenamiento y aplicación por Study."""

import builtins
from pathlib import Path

import pandas as pd
import pytest
from test_h3_lgd_training import historia, puerta

from bayesrisk import LgdModel, Provision
from bayesrisk.core.config import BayesRiskConfig
from bayesrisk.core.exceptions import ConfigError, MissingDependencyError
from bayesrisk.core.study import Study
from bayesrisk.provisioning.internal.exceptions import InternalInputError


def config_mixta(tmp_path: Path):
    frame = historia().iloc[:48].copy()
    frame["fecha"], frame["cartera"], frame["exposicion"], frame["pd"] = (
        "2026-01-01",
        "A",
        100.0,
        0.1,
    )
    history = puerta(tmp_path / "historia", frame)
    application = Provision(
        frame,
        as_of="fecha",
        portfolio="cartera",
        exposure="exposicion",
        pd="pd",
        lgd="lgd",
        run_dir=tmp_path / "cartera",
        formats=(),
    )
    config = history.config.model_dump(mode="python", by_alias=True)
    config["provisioning_internal"] = application.config.provisioning_internal.model_dump()
    config["provisioning_internal"]["lgd"] = {"method": "fitted"}
    config["report"] = config["governance"] = None
    config["run"]["steps"] = ["data", "lgd_training", "provisioning_internal"]
    return config, frame[["pd"]].rename(columns={"pd": "pd_calibrated"})


@pytest.mark.parametrize("operation", ["check_pipeline", "run"])
@pytest.mark.parametrize("order", [None, ["data", "lgd_training", "provisioning_internal"]])
def test_rechaza_composicion_antes_de_ajustar(tmp_path, operation, order):
    config, pd_frame = config_mixta(tmp_path)
    config["run"]["steps"] = order
    study = Study(BayesRiskConfig.model_validate(config))
    study.artifacts.set("calibration", "calibrated_pd_frame", pd_frame)
    with pytest.raises(ConfigError, match="otro Study"):
        getattr(study, operation)()
    assert not study.artifacts.has("data", "frame")
    assert not study.artifacts.has("lgd_training", "fitted_model")


def test_run_step_no_aplica_el_predictor_del_mismo_study(tmp_path):
    config, pd_frame = config_mixta(tmp_path)
    study = Study(BayesRiskConfig.model_validate(config))
    study.artifacts.set("calibration", "calibrated_pd_frame", pd_frame)
    study.run(steps=["data", "lgd_training"])
    with pytest.raises(InternalInputError, match="otro Study"):
        study.run_step("provisioning_internal")
    assert not study.artifacts.has("provisioning_internal", "detail")


def test_predict_sin_scipy_indica_el_extra(monkeypatch):
    model = LgdModel(
        ("x",),
        0.0,
        (0.5,),
        "a" * 64,
        "b" * 64,
        "origen",
        "entorno",
        "not_provided",
        "No aportada",
    )
    original = builtins.__import__

    def without_scipy(name, *args, **kwargs):
        if name == "scipy" or name.startswith("scipy."):
            raise ModuleNotFoundError("No module named 'scipy'")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_scipy)
    with pytest.raises(MissingDependencyError, match=r"bayesrisk\[scoring\]"):
        model.predict(pd.DataFrame({"x": [0.0]}))
