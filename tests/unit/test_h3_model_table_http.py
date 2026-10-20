"""La excepción global de H3 no abre alineación ni deserialización arbitrarias."""

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from bayesrisk import LgdModel
from bayesrisk.lgd_training.exceptions import LgdTrainingError
from bayesrisk.lgd_training.model import read_model_table
from bayesrisk.ui import datasets, routes
from bayesrisk.ui.exceptions import UiArtifactError, UiDatasetError

KEY = ["lgd_training", "model_table"]


def model() -> LgdModel:
    return LgdModel(
        features=("NA", "=x"),
        intercept=-0.12345678901234568,
        coefficients=(0.12345678901234568, 0.9876543210987654),
        source_config_hash="a" * 64,
        source_data_hash="b" * 64,
        source_run_id="=run",
        fit_environment="@entorno",
        declaration_status="provided_unverified",
        declaration_text="Préstamo; proxy de pérdida; disponibilidad al corte, sin validación",
    )


@pytest.mark.parametrize("suffix", ["csv", "parquet", "xlsx"])
def test_modelo_global_no_se_empareja_y_preserva_coeficientes(tmp_path: Path, suffix: str):
    table = model().to_frame()
    if suffix == "csv":
        content = table.to_csv(index=False).encode()
    else:
        buffer = BytesIO()
        getattr(table, "to_excel" if suffix == "xlsx" else "to_parquet")(buffer, index=False)
        content = buffer.getvalue()
    uploaded = datasets.ingest_upload(
        content, f"modelo.{suffix}", workdir=tmp_path, artifact="lgd_training.model_table"
    )
    assert uploaded["dataset_id"].startswith("uploaded_lgd_model_v1_")
    external = [{"artifact": KEY, "dataset_id": uploaded["dataset_id"]}]
    # Ni siquiera necesita cargar una cartera para materializar una tabla global.
    got = routes._materializar_externos(external, "cartera_que_no_existe", workdir=tmp_path)[
        tuple(KEY)
    ]
    pd.testing.assert_frame_equal(got, table, check_exact=suffix != "xlsx", atol=1e-12, rtol=1e-10)
    assert LgdModel.from_frame(got).declaration_text == model().declaration_text


@pytest.mark.parametrize(
    "extra",
    [{"key_column": None}, {"key_column": "id"}, {"mode": "global"}, {"scope": "global_model"}],
)
def test_modelo_rechaza_parametros_de_alineacion(extra):
    with pytest.raises(UiArtifactError, match="global"):
        routes._entradas_externas([{"artifact": KEY, **extra}])


def test_pd_no_elude_conteo_y_cache_generico_no_se_recicla(tmp_path: Path):
    table = model().to_frame()
    content = table.to_csv(index=False).encode()
    generic = datasets.ingest_upload(content, "modelo.csv", workdir=tmp_path)["dataset_id"]
    with pytest.raises(UiArtifactError, match="subir"):
        routes._materializar_externos(
            [{"artifact": KEY, "dataset_id": generic}], "cartera", workdir=tmp_path
        )
    pd_id = datasets.ingest_upload(b"pd_calibrated\n0.1\n", "pd.csv", workdir=tmp_path)[
        "dataset_id"
    ]
    cartera = datasets.ingest_upload(b"saldo\n100\n200\n", "cartera.csv", workdir=tmp_path)[
        "dataset_id"
    ]
    with pytest.raises(UiArtifactError, match="filas"):
        routes._materializar_externos(
            [
                {
                    "artifact": ["calibration", "calibrated_pd_frame"],
                    "dataset_id": pd_id,
                    "scope": "global_model",
                }
            ],
            cartera,
            workdir=tmp_path,
        )
    with pytest.raises(UiArtifactError, match="no admite"):
        routes._entradas_externas([{"artifact": ["lgd_training", "fitted_model"]}])
    with pytest.raises(UiDatasetError):
        datasets.ingest_upload(
            b"\x80\x04pickle",
            "objeto.parquet",
            workdir=tmp_path,
            artifact="lgd_training.model_table",
        )


@pytest.mark.parametrize("suffix", ["csv", "xlsx"])
def test_lector_no_trunca_posiciones_ni_version(tmp_path: Path, suffix: str):
    for field in ["position", "format_version"]:
        table = model().to_frame()
        table[field] = table[field].astype(float) + 0.5
        path = tmp_path / f"invalido.{suffix}"
        getattr(table, "to_csv" if suffix == "csv" else "to_excel")(path, index=False)
        with pytest.raises(LgdTrainingError, match="enteros"):
            read_model_table(path)


@pytest.mark.parametrize("suffix", ["csv", "parquet", "xlsx"])
def test_codec_transporta_nombres_nominales_y_rechaza_pickle(tmp_path: Path, suffix: str):
    from dataclasses import replace

    import numpy as np

    names = ("NA", "001", "=x", "+x", "-x", "@x", "'x", '"x', "\r\nx")
    original = replace(
        model(), features=names, coefficients=tuple(0.01 * i for i in range(len(names)))
    )
    table = original.to_frame()
    path = tmp_path / ("modelo." + suffix)
    if suffix == "csv":
        table.to_csv(path, index=False)
    elif suffix == "xlsx":
        table.to_excel(path, index=False)
    else:
        table.to_parquet(path, index=False)
    loaded = LgdModel.from_frame(read_model_table(path))
    assert loaded.features == names
    np.testing.assert_allclose(loaded.coefficients, original.coefficients, atol=1e-12, rtol=1e-10)
    with pytest.raises(UiDatasetError):
        datasets.ingest_upload(
            b"\x80\x04pickle",
            "objeto." + suffix,
            workdir=tmp_path,
            artifact="lgd_training.model_table",
        )
