"""Aceptación B: oráculos numéricos y tres puertas sobre 6.000 operaciones."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from test_h3_lgd_training import historia, puerta

from bayesrisk import LgdModel, Provision, run
from bayesrisk.core.config import BayesRiskConfig, config_hash, loads_config
from bayesrisk.lgd_training.exceptions import LgdTrainingError

pytest.importorskip("statsmodels")


def test_oraculo_ajuste_diagnostico_y_puerta_completa(tmp_path: Path):
    import statsmodels.api as sm

    p = puerta(tmp_path / "guiada").run(raise_on_error=True)
    cfg = loads_config(p.to_yaml())
    assert config_hash(cfg) == config_hash(p.config)
    complete = run(cfg, run_dir=tmp_path / "completa")
    assert complete.run_context.status == "done"
    for key in ("predictions", "evaluation", "population"):
        pd.testing.assert_frame_equal(
            p.study.artifacts.get("lgd_training", key),
            complete.artifacts.get("lgd_training", key),
            check_exact=True,
        )
    history = historia()
    train = history.iloc[:32]
    oracle = sm.GLM(
        train.lgd, sm.add_constant(train[["=ratio", "NA"]]), family=sm.families.Binomial()
    ).fit()
    predicted = oracle.predict(sm.add_constant(history.iloc[:48][["=ratio", "NA"]]))
    np.testing.assert_allclose(
        p.model_.predict(history.iloc[:48]).lgd, predicted, atol=1e-12, rtol=1e-10
    )
    metrics = p.study.artifacts.get("lgd_training", "evaluation")
    for row in metrics.itertuples(index=False):
        positions = slice(0, 32) if row.sample == "train" else slice(32, 48)
        y = history.iloc[positions].lgd.to_numpy()
        expected = (
            predicted.iloc[positions].to_numpy()
            if row.predictor == "fitted"
            else np.full(len(y), train.lgd.mean())
        )
        errors = expected - y
        np.testing.assert_allclose(
            [row.observed_mean, row.predicted_mean, row.bias, row.mae, row.rmse],
            [
                y.mean(),
                expected.mean(),
                errors.mean(),
                np.abs(errors).mean(),
                np.sqrt(np.mean(errors * errors)),
            ],
            atol=1e-12,
            rtol=1e-10,
        )
    assert "no aportada" in p.summary().text().lower()


def test_tres_puertas_6000_filas_y_equivalencia_monetaria(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from _ui_client import ui_client

    from bayesrisk.ui.settings import UiConfig

    p = puerta(tmp_path / "entrenar").run(until="lgd_training", raise_on_error=True)
    frame = pd.concat([historia().iloc[:48][["=ratio", "NA"]]] * 125, ignore_index=True)
    frame["fecha"], frame["cartera"], frame["exposicion"], frame["pd"] = (
        "2026-01-01",
        "A",
        100.0,
        0.1,
    )
    frame["operacion"] = [f"A{i}" for i in range(len(frame))]
    import statsmodels.api as sm

    monkeypatch.setattr(sm.GLM, "fit", lambda *a, **k: pytest.fail("Se reajustó al aplicar"))
    kwargs = dict(
        as_of="fecha",
        portfolio="cartera",
        exposure="exposicion",
        pd="pd",
        id="operacion",
        formats=(),
    )
    q = Provision(frame, lgd=p.model_, run_dir=tmp_path / "guiada", **kwargs).run(
        raise_on_error=True
    )
    pd_table = frame[["pd"]].rename(columns={"pd": "pd_calibrated"})
    external = {
        ("calibration", "calibrated_pd_frame"): pd_table,
        ("lgd_training", "model_table"): p.model_.to_frame(),
    }
    complete = run(q.config, artifacts=external, run_dir=tmp_path / "completa")
    assert complete.run_context.status == "done"
    expected = q.study.artifacts.get("provisioning_internal", "detail")
    pd.testing.assert_frame_equal(
        expected, complete.artifacts.get("provisioning_internal", "detail"), check_exact=True
    )
    assert len(expected) == 6000 and len(p.model_.to_frame()) == 3
    provided = frame.assign(lgd=p.model_.predict(frame).lgd)
    other = Provision(provided, lgd="lgd", run_dir=tmp_path / "provista", **kwargs).run(
        raise_on_error=True
    )
    pd.testing.assert_frame_equal(
        expected, other.study.artifacts.get("provisioning_internal", "detail"), check_exact=True
    )
    # El piso y techo recorren el mismo motor, también por agrupación proporcionada/segmento.
    for grouping in ("provided", "segment"):
        for fitted in (True, False):
            config = q.config.model_dump(mode="python", by_alias=True)
            config["data"]["load"]["source"] = str(tmp_path / "con_lgd.parquet")
            provided.assign(grupo="unico").to_parquet(tmp_path / "con_lgd.parquet", index=True)
            section = config["provisioning_internal"]
            section.update(grouping=grouping, group_col="grupo")
            section["lgd"] = dict(
                method="fitted" if fitted else "provided", lgd_floor=0.45, lgd_cap=0.55
            )
            injected = external if fitted else {("calibration", "calibrated_pd_frame"): pd_table}
            result = run(
                BayesRiskConfig.model_validate(config),
                artifacts=injected,
                run_dir=tmp_path / f"{grouping}-{fitted}",
            )
            assert result.run_context.status == "done"
            detail = result.artifacts.get("provisioning_internal", "detail")
            if fitted:
                fitted_detail = detail
            else:
                pd.testing.assert_frame_equal(fitted_detail, detail, check_exact=True)
    with ui_client(UiConfig(workdir=str(tmp_path / "http"))) as client:

        def upload(name, table, model=False):
            import io

            buffer = io.BytesIO()
            table.to_parquet(buffer, index=True)
            response = client.post(
                "/api/upload" + ("?artifact=lgd_training.model_table" if model else ""),
                files={"file": (name, buffer.getvalue(), "application/octet-stream")},
            )
            assert response.status_code == 200, response.text
            return response.json()["dataset_id"]

        data_id = upload("cartera.parquet", frame)
        probability_id = upload("pd.parquet", pd_table)
        model_id = upload("modelo.parquet", p.model_.to_frame(), True)
        cfg_json = q.config.model_dump(mode="json", by_alias=True)
        body = {
            "config": cfg_json,
            "dataset_id": data_id,
            "external_artifacts": [
                {"artifact": ["calibration", "calibrated_pd_frame"], "dataset_id": probability_id},
                {"artifact": ["lgd_training", "model_table"], "dataset_id": model_id},
            ],
        }
        validation = client.post("/api/validate", json=body)
        assert validation.status_code == 200 and validation.json()["valid"], validation.text
        assert validation.json()["config_hash"] == config_hash(q.config)
        response = client.post("/api/run", json=body)
        assert response.status_code == 200 and response.json()["status"] == "done", response.text
        output = client.get("/api/results/" + response.json()["run_id"]).json()
        assert "lgd_fitted_provenance" in str(output)
        # El informe servido debe mostrar las restricciones efectivamente consumidas.
        html = client.get("/api/report/" + response.json()["run_id"]).text
        assert 'id="section-methodology-lgd_training"' not in html
        assert "no acredita independencia" in html and "no aportada" in html.lower()
        assert output["project_available"] is True
        bundle = client.get("/api/report/" + response.json()["run_id"] + "/project")
        assert bundle.status_code == 200
        restored = extraer_proyecto(bundle.content, tmp_path / "descargado")
        from bayesrisk.core.study import Study

        saved = Study.load(restored / "study", trust=True)
        pd.testing.assert_frame_equal(
            expected, saved.artifacts.get("provisioning_internal", "detail"), check_exact=True
        )
        # Ejecuta exactamente la receta entregada, sin fit y sin depender del workdir del servidor.
        with monkeypatch.context() as context:
            context.chdir(restored)
            namespace = {}
            exec(
                compile(Path("reproducir.py").read_text(encoding="utf-8"), "reproducir.py", "exec"),
                namespace,
            )
        pd.testing.assert_frame_equal(
            expected,
            namespace["study"].artifacts.get("provisioning_internal", "detail"),
            check_exact=True,
        )


@pytest.mark.parametrize(
    "defect", ["base64", "utf8", "canonical", "metadata", "dimension", "feature"]
)
def test_codec_cerrado_rechaza_ambiguedad(tmp_path: Path, defect: str):
    p = puerta(tmp_path).run(until="lgd_training", raise_on_error=True)
    table = p.model_.to_frame()
    if defect == "base64":
        table.loc[1, "feature"] = "text:!!!"
    elif defect == "utf8":
        table.loc[1, "feature"] = "text:_w"
    elif defect == "canonical":
        table.loc[1, "feature"] += "="
    elif defect == "metadata":
        table.loc[1, "source_data_hash"] = "0" * 64
    elif defect == "dimension":
        table = table.iloc[:1]
    elif defect == "feature":
        table.loc[2, "feature"] = table.loc[1, "feature"]
    with pytest.raises(LgdTrainingError):
        LgdModel.from_frame(table)


def extraer_proyecto(content: bytes, target: Path) -> Path:
    import io
    import zipfile

    target.mkdir()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert {
            "modelo_lgd.parquet",
            "config-portable.yaml",
            "reproducir.py",
            "entradas.json",
        } <= set(archive.namelist())
        for name in archive.namelist():
            assert not Path(name).is_absolute() and ".." not in Path(name).parts
        archive.extractall(target)
    return target


def test_pantalla_entrena_y_descarga_predictor_reutilizable(tmp_path: Path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    import io

    from _ui_client import ui_client

    from bayesrisk.ui.settings import UiConfig

    history = historia()
    guided = puerta(tmp_path / "guiada").run(raise_on_error=True)
    buffer = io.BytesIO()
    history.to_parquet(buffer)
    with ui_client(UiConfig(workdir=str(tmp_path / "ui"))) as client:
        uploaded = client.post(
            "/api/upload",
            files={"file": ("historia.parquet", buffer.getvalue(), "application/octet-stream")},
        )
        assert uploaded.status_code == 200, uploaded.text
        response = client.post(
            "/api/run",
            json={
                "config": guided.config.model_dump(mode="json", by_alias=True),
                "dataset_id": uploaded.json()["dataset_id"],
            },
        )
        assert response.status_code == 200 and response.json()["status"] == "done", response.text
        run_id = response.json()["run_id"]
        bundle = client.get(f"/api/report/{run_id}/project")
        assert bundle.status_code == 200
        project = extraer_proyecto(bundle.content, tmp_path / "proyecto")
        model = LgdModel.from_frame(pd.read_parquet(project / "modelo_lgd.parquet"))
        pd.testing.assert_frame_equal(
            model.predict(history.iloc[:48]),
            guided.model_.predict(history.iloc[:48]),
            check_exact=True,
        )
        reuploaded = client.post(
            "/api/upload?artifact=lgd_training.model_table",
            files={
                "file": (
                    "modelo.parquet",
                    (project / "modelo_lgd.parquet").read_bytes(),
                    "application/octet-stream",
                )
            },
        )
        assert reuploaded.status_code == 200, reuploaded.text
        assert client.get("/api/report/" + "0" * 32 + "/project").status_code == 404
        assert client.get("/api/report/not-a-run/project").status_code == 404


def test_proyecto_h3_no_publica_zip_incompleto(tmp_path: Path, monkeypatch):
    from bayesrisk.ui import runs

    trained = puerta(tmp_path / "entrenamiento").run(raise_on_error=True)
    directory = tmp_path / "ui"
    run_id = runs.save(trained.study, workdir=directory, governance=trained.config.governance)
    previous = runs.project_path(run_id, workdir=directory).read_bytes()

    def fail(*args, **kwargs):
        raise OSError("fallo al empaquetar")

    monkeypatch.setattr(runs, "_save_h3_project", fail)
    with pytest.raises(OSError, match="empaquetar"):
        runs.save(trained.study, workdir=directory, governance=trained.config.governance)
    assert runs.project_path(run_id, workdir=directory).read_bytes() == previous


def test_card_lgd_no_oculta_corrupcion_numerica():
    from bayesrisk.ui.exceptions import UiSerializationError
    from bayesrisk.ui.serializers import _dump_card

    with pytest.raises(UiSerializationError):
        _dump_card("lgd_training", {"n_train": float("nan")})
