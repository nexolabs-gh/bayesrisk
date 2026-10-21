"""H3: entradas incompatibles fallan antes de publicar una cifra de provisión."""

import numpy as np
import pandas as pd
import pytest

from bayesrisk import LgdModel
from bayesrisk.core.config import BayesRiskConfig
from bayesrisk.core.study import Study
from bayesrisk.provisioning.internal.config import (
    InternalLgdFitted,
    InternalProvisioningConfig,
    _InternalLgdComun,
)
from bayesrisk.provisioning.internal.engine import InternalProvisioningEngine
from bayesrisk.provisioning.internal.exceptions import InternalConfigError, InternalInputError
from bayesrisk.provisioning.internal.step import InternalProvisioningStep


def modelo():
    return LgdModel(
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


def cartera():
    return pd.DataFrame(
        {
            "as_of_date": ["2026-01-01"] * 2,
            "portfolio": ["A"] * 2,
            "exposure_amount": [100.0, 200.0],
            "lgd": [0.4, 0.4],
            "grupo": ["g", "g"],
            "x": [0.0, 1.0],
        }
    )


def test_fitted_rechaza_limites_invertidos():
    with pytest.raises(InternalConfigError, match=r"piso.*techo"):
        InternalLgdFitted(lgd_floor=0.8, lgd_cap=0.2)


def test_schema_base_no_inventa_un_metodo_lgd():
    props = _InternalLgdComun.model_json_schema()["properties"]
    assert "method" not in props
    assert set(props) == {"lgd_col", "lgd_floor", "lgd_cap"}
    assert all("ui_essential" not in field for field in props.values())


@pytest.mark.parametrize("defecto", ["modelo_ausente", "tipo_invalido", "rama_incompatible"])
def test_motor_rechaza_modelo_incompatible(defecto):
    fitted = defecto != "rama_incompatible"
    cfg = InternalProvisioningConfig(
        grouping="provided",
        group_col="grupo",
        lgd={"method": "fitted" if fitted else "provided"},
    )
    predictor = None if defecto == "modelo_ausente" else object() if fitted else modelo()
    message = "exige un modelo LGD validado" if fitted else "sólo se admite"
    with pytest.raises(InternalInputError, match=message):
        InternalProvisioningEngine(cfg).calculate(
            cartera(),
            pd_frame=pd.DataFrame({"pd_calibrated": [0.1, 0.2]}),
            as_of_date="2026-01-01",
            fitted_model=predictor,
        )


@pytest.mark.parametrize("con_tabla", [False, True])
def test_step_rechaza_modelo_ausente_o_sobrante(con_tabla):
    cfg = InternalProvisioningConfig(lgd={"method": "provided" if con_tabla else "fitted"})
    study = Study(BayesRiskConfig(provisioning_internal=cfg), apply_global_seed=False)
    if con_tabla:
        study.artifacts.set("lgd_training", "model_table", modelo().to_frame())
    # Ninguna entrada de cartera es necesaria para detectar el error de composición.
    with pytest.raises(InternalInputError, match=r"tabla.*modelo LGD exige|exige la tabla"):
        InternalProvisioningStep(cfg).execute(study, np.random.default_rng(0))
    assert not study.artifacts.has("provisioning_internal", "detail")


@pytest.mark.parametrize("source", ["calibration", "model"])
@pytest.mark.parametrize("part", ["principal", "complementaria"])
@pytest.mark.parametrize("defecto", ["indice_duplicado", "columna_ausente"])
def test_pd_invalida_no_se_suma_ni_publica(source, part, defecto):
    col = "pd_calibrated" if source == "calibration" else "pd_raw"
    main_key = "calibrated_pd_frame" if source == "calibration" else "raw_pd_frame"
    extra_key = (
        "out_of_model_calibrated_pd_frame" if source == "calibration" else "out_of_model_pd_frame"
    )
    main = pd.DataFrame({col: [0.1]}, index=[0])
    extra = pd.DataFrame({col: [0.2]}, index=[1])
    frame = main if part == "principal" else extra
    broken = (
        pd.concat([frame, frame])
        if defecto == "indice_duplicado"
        else frame.rename(columns={col: "otra"})
    )
    if part == "principal":
        main = broken
    else:
        extra = broken
    cfg = InternalProvisioningConfig(
        type="full_population",
        pd_source=source,
        pd_column=col,
        grouping="provided",
        group_col="grupo",
    )
    study = Study(BayesRiskConfig(provisioning_internal=cfg), apply_global_seed=False)
    study.artifacts.set("data", "frame", cartera())
    study.artifacts.set(source, main_key, main)
    study.artifacts.set(source, extra_key, extra)
    message = "índices únicos" if defecto == "indice_duplicado" else "no trae la columna"
    with pytest.raises(InternalInputError, match=message):
        InternalProvisioningStep(cfg).execute(study, np.random.default_rng(0))
    for key in ("pd_input", "detail", "groups", "summary", "card"):
        assert not study.artifacts.has("provisioning_internal", key)
    pd.testing.assert_frame_equal(study.artifacts.get(source, main_key), main, check_exact=True)
    pd.testing.assert_frame_equal(study.artifacts.get(source, extra_key), extra, check_exact=True)
