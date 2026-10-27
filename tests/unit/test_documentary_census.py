"""Censo D-DOC-SC desde productores, independiente del catálogo del renderer."""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from pandas.testing import assert_frame_equal
from test_report_builder import _study_completo, _validation_result

from bayesrisk.report.builder import ReportBuilder
from bayesrisk.report.config import ReportConfig

# Cada categoría tiene una razón: A=agregado íntegro, R=registros propios, N=metadatos/objetos,
# O=operaciones fuera del anexo, D=contenedor duplicado con artefactos separados.
# Cambiar un productor exige clasificar su destino; nunca se deriva esta lista del colector.
SOURCES = {
    "data": {"N": "data_hash data_card", "O": "frame splits labels special"},
    "eda": {"A": "default_rate univariate quality", "N": "stability eda_card", "D": "figures"},
    "binning": {
        "A": "tables summary event_rate_by_partition unseen_categories bin_edges",
        "N": "process binning_card",
        "O": "woe_frame bin_frame out_of_model_woe_frame",
        "D": "result",
    },
    "selection": {
        "A": "selection_table correlation_matrix vif_table stability_table iv_by_partition",
        "N": "selected_features selected_woe_columns selection_card",
        "O": "selected_woe_frame",
        "D": "result",
    },
    "model": {
        "A": "coefficients",
        "R": "stepwise_trace",
        "N": "estimator final_features final_woe_columns fit_statistics model_card",
        "O": "raw_pd_frame out_of_model_pd_frame",
        "D": "result",
    },
    "scorecard": {"A": "scorecard", "N": "card", "O": "score out_of_model_score", "D": "result"},
    "calibration": {
        "N": "parameters card",
        "O": "calibrated_pd_frame out_of_model_calibrated_pd_frame",
        "D": "result",
    },
    "performance": {"A": "performance_table discriminant_metrics", "N": "card", "D": "result"},
    "stability": {"A": "psi_table stability_metrics out_of_model_psi", "R": "result", "N": "card"},
    "validation": {
        "A": (
            "hosmer_lemeshow_groups calibration_tie_groups discrimination "
            "calibration stability backtesting"
        ),
        "R": "interpretation",
        "N": "card",
        "D": "result",
    },
    "master_scale": {
        "A": "grades grade_table cutoff_table",
        "N": "card",
        "O": "assignment",
        "D": "result",
    },
}
STEPS = dict(
    zip(
        SOURCES,
        (
            "DataStep",
            "EdaStep",
            "BinningStep",
            "SelectionStep",
            "ModelStep",
            "ScorecardStep",
            "CalibrationStep",
            "PerformanceStep",
            "StabilityStep",
            "ValidationStep",
            "MasterScaleStep",
        ),
        strict=True,
    )
)
CLASSIFIED = {
    (domain, key): category
    for domain, groups in SOURCES.items()
    for category, names in groups.items()
    for key in names.split()
}


def test_censo_fuentes_contratos_y_publicaciones_en_ambos_sentidos():
    contracts = set()
    publications = set()
    for domain, name in STEPS.items():
        module = importlib.import_module(f"bayesrisk.{domain}.step")
        public = importlib.import_module(f"bayesrisk.{domain}")
        contracts.update(getattr(public, name).provides)
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "set"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "artifacts"
            ):
                assert len(node.args) >= 2
                assert all(isinstance(arg, ast.Constant) for arg in node.args[:2]), (
                    "Publicación dinámica: clasificar explícitamente"
                )
                publications.add((node.args[0].value, node.args[1].value))
    assert len(CLASSIFIED) == 77
    assert contracts == set(CLASSIFIED) == publications


DIRECT = {
    domain + "." + key
    for (domain, key), category in CLASSIFIED.items()
    if category == "A" and domain not in {"eda", "validation"} and key != "tables"
}


def test_todos_los_agregados_directos_llegan_integros_antes_del_formato():
    study = _study_completo()
    sources = {}
    for ordinal, key in enumerate(sorted(DIRECT)):
        if key == "binning.bin_edges":
            frame = pd.DataFrame(
                {
                    "variable": ["edad"],
                    "bin_index": [0],
                    "lower": [-float("inf")],
                    "upper": [0.12345678901234567],
                }
            )
        else:
            frame = pd.DataFrame(
                {
                    "warning_codes": [ordinal + 0.12345678901234567, 0.0],
                    "green_alpha": [None, "=no_ejecutar"],
                    "valor": [True, False],
                },
                index=pd.MultiIndex.from_tuples([("a", 2), ("a", 2)], names=[None, "valor"]),
            )
        study.artifacts.set(*key.split(".", 1), frame, overwrite=True)
        sources[key] = frame.copy(deep=True)
    collected = ReportBuilder(ReportConfig())._collect_tables(study)
    assert collected.keys() >= DIRECT
    for key, source in sources.items():
        assert_frame_equal(source, collected[key], check_exact=True)
    assert "0,12345678901234566" in collected["binning.cut_dictionary"].iloc[0]["Regla exacta"]


def test_contenedores_de_eda_y_registros_temporales_conservan_hojas():
    study = _study_completo()
    frame = pd.DataFrame(
        {"n": [2, 0], "tasa": [0.12345678901234567, None]}, index=["primero", "último"]
    )
    for key, field in (("default_rate", "by_period"), ("quality", "by_column")):
        study.artifacts.set("eda", key, {field: frame}, overwrite=True)
    study.artifacts.set("eda", "univariate", {"profiles": {"a.b": frame, "a-b": frame}})
    study.artifacts.set(
        "stability",
        "result",
        SimpleNamespace(
            temporal_records=[
                {
                    "period": "2026-01",
                    "p25_score": 501.1234567890123,
                    "p75_score": 701.1234567890123,
                }
            ]
        ),
    )
    collected = ReportBuilder(ReportConfig())._collect_tables(study)
    for key in (
        "eda.default_rate.by_period",
        "eda.quality.by_column",
        "eda.univariate.profiles.a.b",
        "eda.univariate.profiles.a-b",
    ):
        assert_frame_equal(collected[key], frame, check_exact=True)
    assert collected["stability.temporal_records"].iloc[0]["p25_score"] == 501.1234567890123


def test_resultado_atomico_de_validacion_y_esquema_hl_original():
    from bayesrisk.validation.results import HOSMER_LEMESHOW_GROUP_COLUMNS

    assert tuple(HOSMER_LEMESHOW_GROUP_COLUMNS) == (
        "partition",
        "group",
        "n",
        "observed_defaults",
        "expected_defaults",
        "observed_dr",
        "mean_pd",
        "gap_pp",
        "oe_ratio",
        "contribution",
    )
    study = _study_completo()
    validation = _validation_result()
    study.artifacts.set("validation", "result", validation)
    study.artifacts.set("validation", "card", validation.card)
    for name in validation.card.families_run:
        study.artifacts.set("validation", name, getattr(validation, name))
    bundle = ReportBuilder(ReportConfig()).collect(study)
    for name in validation.card.families_run:
        assert_frame_equal(
            bundle.tables["validation." + name], getattr(validation, name), check_exact=True
        )


def test_grupos_contextuales_conservan_frame_original_ademas_de_lectura_por_muestra():
    import numpy as np
    from test_validation_step import _scorecard_study

    from bayesrisk.validation.config import ValidationConfig
    from bayesrisk.validation.step import ValidationStep

    cfg = ValidationConfig(families=("calibration",), calibration={"binomial_by_grade": False})
    study = _scorecard_study(config=cfg)
    study.run_context.lineage = _study_completo().run_context.lineage
    ValidationStep(cfg).execute(study, np.random.default_rng(0))
    source = study.artifacts.get("validation", "calibration_tie_groups")
    assert list(source.columns) == [
        "partition",
        "group",
        "pd_min",
        "pd_max",
        "n",
        "observed_defaults",
        "expected_defaults",
        "observed_dr",
        "mean_pd",
        "gap_pp",
        "oe_ratio",
        "oe_ratio_reason",
        "expected_non_defaults",
        "below_legacy_min_rows",
    ]
    bundle = ReportBuilder(ReportConfig(sections={"missing_policy": "skip"})).collect(study)
    assert "validation.calibration_tie_groups" in bundle.tables
    assert_frame_equal(source, bundle.tables["validation.calibration_tie_groups"], check_exact=True)
