"""H3 A: el nuevo consumidor exige PD de toda la cartera y no escribe sobre F1."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bayesrisk.core.config import BayesRiskConfig
from bayesrisk.core.study import Study
from bayesrisk.provisioning.internal.config import InternalProvisioningConfig
from bayesrisk.provisioning.internal.exceptions import InternalInputError
from bayesrisk.provisioning.internal.step import InternalProvisioningStep


@pytest.mark.parametrize(
    "source,main,extra,col",
    [
        ("calibration", "calibrated_pd_frame", "out_of_model_calibrated_pd_frame", "pd_calibrated"),
        ("model", "raw_pd_frame", "out_of_model_pd_frame", "pd_raw"),
    ],
)
def test_cobertura_total_no_sobrescribe_f1(source, main, extra, col) -> None:
    cfg = InternalProvisioningConfig(
        type="full_population",
        pd_source=source,
        pd_column=col,
        grouping="provided",
        group_col="grupo",
    )
    frame = pd.DataFrame(
        {
            "as_of_date": ["2026-01-01"] * 3,
            "portfolio": ["A"] * 3,
            "exposure_amount": [100.0] * 3,
            "lgd": [0.4] * 3,
            "grupo": ["g"] * 3,
        },
        index=["dev", "oot", "ttd"],
    )
    pd_main = pd.DataFrame({col: [0.1, 0.2]}, index=["dev", "oot"])
    pd_extra = pd.DataFrame({col: [0.3]}, index=["ttd"])

    def entrada(complemento):
        nuevo = Study(BayesRiskConfig(provisioning_internal=cfg), apply_global_seed=False)
        nuevo.artifacts.set("data", "frame", frame)
        nuevo.artifacts.set(source, main, pd_main)
        nuevo.artifacts.set(source, extra, complemento)
        return nuevo

    study = entrada(pd_extra)
    step = InternalProvisioningStep(cfg)
    step.execute(study, np.random.default_rng(0))
    assert (
        float(study.artifacts.get("provisioning_internal", "card").total_internal_provision) == 24.0
    )
    pd.testing.assert_frame_equal(study.artifacts.get(source, main), pd_main, check_exact=True)
    pd.testing.assert_frame_equal(study.artifacts.get(source, extra), pd_extra, check_exact=True)
    assert (source, extra) in step.optional_requires
    # La supresión deliberada de TTD produce rojo en el consumidor; restaurar devuelve verde.
    with pytest.raises(InternalInputError, match="Falta PD para 1 operaciones"):
        step.execute(entrada(pd_extra.iloc[:0]), np.random.default_rng(0))
    study = entrada(pd_extra)
    step.execute(study, np.random.default_rng(0))
    assert (
        float(study.artifacts.get("provisioning_internal", "card").total_internal_provision) == 24.0
    )
    with pytest.raises(InternalInputError, match="solapan"):
        step.execute(entrada(pd.DataFrame({col: [0.1]}, index=["dev"])), np.random.default_rng(0))


def test_variante_estandar_conserva_contrato_de_artefactos() -> None:
    step = InternalProvisioningStep(InternalProvisioningConfig())
    assert step.optional_requires == ()
    assert len(step.provides) == 5


@pytest.mark.parametrize("pd_ausente", [None, np.nan, pd.NA])
def test_cobertura_rechaza_pd_nula_aunque_se_tolere_falta_dato(pd_ausente) -> None:
    cfg = InternalProvisioningConfig(type="full_population", fail_on_falta_dato=False)
    study = Study(BayesRiskConfig(provisioning_internal=cfg), apply_global_seed=False)
    study.artifacts.set(
        "data",
        "frame",
        pd.DataFrame(
            {
                "as_of_date": ["2026-01-01"] * 2,
                "portfolio": ["A"] * 2,
                "exposure_amount": [100.0] * 2,
                "lgd": [0.2, 0.8],
            }
        ),
    )
    study.artifacts.set(
        "calibration", "calibrated_pd_frame", pd.DataFrame({"pd_calibrated": [0.1]}, index=[0])
    )
    study.artifacts.set(
        "calibration",
        "out_of_model_calibrated_pd_frame",
        pd.DataFrame({"pd_calibrated": [pd_ausente]}, index=[1]),
    )
    with pytest.raises(InternalInputError, match="Falta PD para 1 operaciones"):
        InternalProvisioningStep(cfg).execute(study, np.random.default_rng(0))
    assert study.artifacts.get("provisioning_internal", "pd_coverage").iloc[0].missing_rows == 1
    assert not study.artifacts.has("provisioning_internal", "detail")


def test_copy_tasa_regresion_monto_workout() -> None:
    from bayesrisk.provisioning.internal.config import (
        InternalLgdBetaRegression,
        InternalLgdFractionalResponse,
        InternalLgdWorkout,
    )

    for cls in (InternalLgdBetaRegression, InternalLgdFractionalResponse):
        field = cls.model_json_schema()["properties"]["recovery_col"]
        assert "TASA" in field["description"]
        assert "no monto" in field["ui_help"]
    assert (
        "MONTO"
        in InternalLgdWorkout.model_json_schema()["properties"]["recovery_col"]["description"]
    )
