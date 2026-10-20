"""Historia separada H3: población, ajuste congelado y aplicación sin objetivo."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bayesrisk import Lgd, LgdModel, Provision
from bayesrisk.guided.lgd import LgdRunError
from bayesrisk.lgd_training.exceptions import LgdTrainingError


def historia() -> pd.DataFrame:
    rng = np.random.default_rng(31415)
    x, z = rng.normal(size=(2, 50))
    y = np.clip(1 / (1 + np.exp(-(-0.3 + 0.6 * x - 0.25 * z))) + rng.normal(0, 0.1, 50), 0, 1)
    y[0], y[1] = 0, 1
    frame = pd.DataFrame(
        {
            "operacion": [f"O{i}" for i in range(50)],
            "deudor": [f"D{i // 2}" for i in range(50)],
            "muestra": ["train"] * 32 + ["evaluation"] * 16 + ["excluded"] * 2,
            "incumplio": [1] * 50,
            "completo": [True] * 48 + [False] * 2,
            "lgd": y,
            "=ratio": x,
            "NA": z,
        }
    )
    frame.loc[48:, ["lgd", "=ratio", "NA"]] = np.nan
    return frame


def puerta(tmp_path: Path, frame: pd.DataFrame | None = None, **kwargs) -> Lgd:
    formats = kwargs.pop("formats", ())
    return Lgd(
        historia() if frame is None else frame,
        target="lgd",
        features=["=ratio", "NA"],
        entity="deudor",
        sample="muestra",
        default="incumplio",
        resolved="completo",
        id="operacion",
        run_dir=tmp_path,
        formats=formats,
        **kwargs,
    )


def test_ajusta_solo_train_y_predice_sin_objetivo(tmp_path: Path):
    a = puerta(tmp_path / "a").run(until="lgd_training", raise_on_error=True)
    bdata = historia()
    bdata.loc[32:47, "lgd"] = 1 - bdata.loc[32:47, "lgd"]
    b = puerta(tmp_path / "b", bdata).run(until="lgd_training", raise_on_error=True)
    np.testing.assert_array_equal(a.model_.to_frame().coefficient, b.model_.to_frame().coefficient)
    application = historia().iloc[:5][["NA", "=ratio"]].copy()
    application.index = ["Z", "Y", "X", "W", "V"]
    prediction = a.model_.predict(application)
    assert list(prediction.columns) == ["lgd"]
    assert prediction.index.equals(application.index)
    application["lgd"] = np.inf
    pd.testing.assert_frame_equal(prediction, a.model_.predict(application), check_exact=True)
    evaluation = a.study.artifacts.get("lgd_training", "evaluation")
    assert set(evaluation["sample"]) == {"train", "evaluation"}
    assert set(evaluation["predictor"]) == {"fitted", "train_mean"}
    assert set(["n", "observed_mean", "predicted_mean", "bias", "mae", "rmse"]) <= set(evaluation)
    population = a.study.artifacts.get("lgd_training", "population")
    assert population["n"].sum() == 50
    assert len(a.study.artifacts.get("lgd_training", "predictions")) == 48


@pytest.mark.parametrize(
    "defect",
    ["entity", "id", "flag", "sample", "target", "feature", "empty", "constant", "singular"],
)
def test_historia_invalida_no_entrega_modelo(tmp_path: Path, defect: str):
    frame = historia()
    if defect == "entity":
        frame.loc[32, "deudor"] = frame.loc[0, "deudor"]
    elif defect == "id":
        frame.loc[49, "operacion"] = frame.loc[0, "operacion"]
    elif defect == "flag":
        frame["incumplio"] = frame["incumplio"].astype(str)
        frame.loc[49, "incumplio"] = "false"
    elif defect == "sample":
        frame.loc[49, "muestra"] = "automatic"
    elif defect == "target":
        frame.loc[32, "lgd"] = np.nan
    elif defect == "feature":
        frame.loc[0, "=ratio"] = np.inf
    elif defect == "empty":
        frame.loc[32:47, "muestra"] = "excluded"
    elif defect == "constant":
        frame.loc[:31, "lgd"] = 0.5
    elif defect == "singular":
        frame["NA"] = frame["=ratio"]
    p = puerta(tmp_path, frame)
    p.run()
    assert p.study.run_context.status == "failed"
    assert not p.study.artifacts.has("lgd_training", "fitted_model")
    with pytest.raises(LgdRunError, match=r"ajuste|modelo|termin"):
        _ = p.model_


@pytest.mark.parametrize("suffix", ["csv", "parquet", "xlsx"])
def test_modelo_cerrado_transporte_y_prediccion_defensiva(tmp_path: Path, suffix: str):
    if suffix == "xlsx":
        pytest.importorskip("openpyxl")
    from bayesrisk.lgd_training.model import read_model_table

    p = puerta(tmp_path).run(until="lgd_training", raise_on_error=True)
    table = p.model_.to_frame()
    for name in ["feature", "source_run_id", "fit_environment", "declaration_text"]:
        assert table[name].str.startswith("text:").all()
    path = tmp_path / f"modelo.{suffix}"
    if suffix == "csv":
        table.to_csv(path, index=False)
    elif suffix == "parquet":
        table.to_parquet(path, index=False)
    else:
        table.to_excel(path, index=False)
    model = LgdModel.from_frame(read_model_table(path))
    np.testing.assert_allclose(
        model.predict(historia().iloc[:48]),
        p.model_.predict(historia().iloc[:48]),
        atol=1e-12 if suffix == "xlsx" else 0,
        rtol=1e-10 if suffix == "xlsx" else 0,
    )
    for change in [
        lambda f: f.assign(extra=1),
        lambda f: f.assign(format_version=2),
        lambda f: f.assign(feature="texto plano"),
        lambda f: f.assign(coefficient=np.inf),
        lambda f: f.assign(position=0),
    ]:
        with pytest.raises(LgdTrainingError):
            LgdModel.from_frame(change(table.copy(deep=True)))
    bad = historia().iloc[:5][["=ratio", "NA"]].copy()
    bad.loc[0, "NA"] = np.inf
    with pytest.raises(LgdTrainingError, match="finit"):
        p.model_.predict(bad)


def test_aplicar_no_ajusta_y_conserva_formula_grupal(tmp_path: Path, monkeypatch):
    p = puerta(tmp_path / "historia").run(until="lgd_training", raise_on_error=True)
    import statsmodels.api as sm

    monkeypatch.setattr(
        sm.GLM, "fit", lambda *a, **k: pytest.fail("La aplicación volvió a ajustar")
    )
    application = historia().iloc[:5][["=ratio", "NA"]].copy()
    application["fecha"], application["cartera"], application["exposicion"], application["pd"] = (
        "2026-01-01",
        "A",
        100.0,
        0.1,
    )
    q = Provision(
        application,
        as_of="fecha",
        portfolio="cartera",
        exposure="exposicion",
        pd="pd",
        lgd=p.model_,
        run_dir=tmp_path / "cartera",
        formats=(),
    ).run(raise_on_error=True)
    assert q.config.provisioning_internal.lgd.method == "fitted"
    assert "lgd_col" not in q.config.provisioning_internal.lgd.model_dump()
    assert q.study.artifacts.has("lgd_training", "model_table")
    assert not q.study.artifacts.has("lgd_training", "fitted_model")
    assert "no verificada" in str(q.summary()).lower()


def test_entrega_final_exporta_modelo_reutilizable_y_estudio(tmp_path: Path):
    pytest.importorskip("openpyxl")
    pytest.importorskip("docx")
    import zipfile

    from bayesrisk.core.study import Study
    from bayesrisk.lgd_training.model import read_model_table

    p = puerta(
        tmp_path,
        formats=["csv", "xlsx", "docx"],
        purpose="Prueba funcional declarada",
        assumptions=["Entidad préstamo; objetivo proxy disponible al corte"],
        limitations=["No acredita independencia por deudor ni transportabilidad"],
    ).run(raise_on_error=True)
    reports = p.project_dir / "reports"
    for suffix in ("csv", "xlsx"):
        candidates = [
            path
            for path in reports.glob(f"*.{suffix}")
            if "modelo_lgd" in path.name or "lgd_training_model_table" in path.name
        ]
        assert len(candidates) == 1
        restored = LgdModel.from_frame(read_model_table(candidates[0]))
        assert restored.declaration_text == p.model_.declaration_text
        np.testing.assert_allclose(
            restored.predict(historia().iloc[:48]),
            p.model_.predict(historia().iloc[:48]),
            atol=1e-12 if suffix == "xlsx" else 0,
            rtol=1e-10 if suffix == "xlsx" else 0,
        )
    html = next(reports.glob("*.html")).read_text(encoding="utf-8")
    for literal in ("Entrenamiento LGD", "proxy disponible al corte", "Supuestos"):
        assert literal in html
    from docx import Document

    document = Document(next(reports.glob("*.docx")))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "proxy disponible al corte" in text
    html = next(reports.glob("*.html")).read_text(encoding="utf-8")
    for output in (html, text):
        assert "no separa muestras" not in output
        assert "Las métricas clave no están disponibles" not in output
        assert "no tiene una fila por operación" in output
        assert "entrenamiento LGD usa el objetivo" in output
    books = p.export_excel()
    assert any("LGD" in book.name for book in books)
    saved = p.study.save(tmp_path / "guardado")
    with pytest.raises(Exception, match=r"trust|confianza"):
        Study.load(saved)
    loaded = Study.load(saved, trust=True)
    restored = loaded.artifacts.get("lgd_training", "fitted_model")
    pd.testing.assert_frame_equal(
        restored.predict(historia().iloc[:48]),
        p.model_.predict(historia().iloc[:48]),
        check_exact=True,
    )
    zipped = p.export(tmp_path / "entrega.zip")
    with zipfile.ZipFile(zipped) as archive:
        assert any("lgd_training_model_table.csv" in name for name in archive.namelist())
        assert any("input/" in name and name.endswith("parquet") for name in archive.namelist())


@pytest.mark.parametrize("failure", ["warning", "nonconverged", "insufficient"])
def test_ajuste_sin_soporte_no_publica_predictor(tmp_path: Path, monkeypatch, failure):
    import warnings
    from types import SimpleNamespace

    import statsmodels.api as sm

    frame = historia()
    if failure == "insufficient":
        frame.loc[3:31, "muestra"] = "excluded"
    else:

        def bad_fit(*args, **kwargs):
            if failure == "warning":
                warnings.warn("Advertencia de ajuste inyectada", UserWarning, stacklevel=2)
            return SimpleNamespace(converged=False, params=np.zeros(3))

        monkeypatch.setattr(sm.GLM, "fit", bad_fit)
    p = puerta(tmp_path, frame).run()
    assert p.study.run_context.status == "failed"
    for key in ("fitted_model", "model_table", "predictions", "evaluation"):
        assert not p.study.artifacts.has("lgd_training", key)


def test_predicciones_identifican_operacion_y_modelo_parcial_no_reaparece(tmp_path: Path):
    p = puerta(tmp_path).run(raise_on_error=True)
    predictions = p.study.artifacts.get("lgd_training", "predictions")
    assert predictions.operation_id.tolist() == historia().operacion.iloc[:48].tolist()
    p.run(until="data", raise_on_error=True)
    with pytest.raises(LgdRunError):
        _ = p.model_
