"""Oráculos de D-HLC: la lectura contextual no modifica el HL convencional."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bayesrisk.validation.config import CalibrationValidationConfig, ValidationConfig
from bayesrisk.validation.evaluator import ValidationEvaluator
from bayesrisk.validation.exceptions import ValidationDataError


def _frame(pd_values: list[float] | None = None) -> pd.DataFrame:
    values = pd_values or [0.1] * 3 + [0.2] + [0.3] * 4 + [0.4] * 2
    return pd.DataFrame(
        {
            "partition": ["desarrollo"] * len(values),
            "pd_calibrated": values,
            "target": [int(i % 3 == 0) for i in range(len(values))],
        }
    )


def _config(**kwargs: object) -> ValidationConfig:
    return ValidationConfig.model_validate(
        {
            "families": ["calibration"],
            "calibration": {"binomial_by_grade": False, "hl_n_groups": 5, **kwargs},
        }
    )


def _interpret(frame: pd.DataFrame, **kwargs: object):
    from bayesrisk.validation import interpret_validation

    cfg = _config()
    result = ValidationEvaluator(cfg).validate(calibrated_pd=frame)
    return interpret_validation(
        result, calibrated_pd=frame, calibration_config=cfg.calibration, **kwargs
    )


def test_golden_empates_y_conservacion_sin_inferencia() -> None:
    value = _interpret(_frame())
    groups = value.calibration_tie_groups
    assert [g.n for g in groups] == [3, 1, 4, 2]
    assert [g.pd_max for g in groups] == [0.1, 0.2, 0.3, 0.4]
    assert sum(g.n for g in groups) == 10
    assert sum(g.observed_defaults for g in groups) == 4
    assert math.fsum(g.expected_defaults for g in groups) == pytest.approx(2.5)
    assert value.hl[0].legacy_boundary_splits_tie
    assert value.hl[0].k_groups == 4
    assert value.hl[0].formal_inference == "not_established"
    assert value.overall_status == "not_evaluable"
    assert value.coverage_gap
    assert value.n_tests == 0
    assert not {"statistic", "p_value", "degrees_of_freedom", "decision"} & set(
        groups[0].model_dump()
    )


def test_permutaciones_finitas_no_mueven_un_bit() -> None:
    frame = _frame()
    baseline = _interpret(frame).model_dump_json()
    for order in [list(reversed(range(10))), [8, 3, 0, 6, 2, 9, 5, 1, 7, 4]]:
        assert _interpret(frame.iloc[order]).model_dump_json() == baseline


@pytest.mark.parametrize("n", [1, 4, 31])
def test_pd_constante_y_una_clase_conservan_diagnostico(n: int) -> None:
    frame = _frame([0.25] * n).assign(target=0)
    value = _interpret(frame)
    assert value.hl[0].k_groups == 1
    assert value.calibration_tie_groups[0].n == n
    assert value.calibration_tie_groups[0].observed_defaults == 0


def test_oe_no_representable_es_null_con_causa_y_json_estricto() -> None:
    value = _interpret(_frame([float(np.nextafter(0.0, 1.0))]).assign(target=1))
    row = value.calibration_tie_groups[0]
    assert row.expected_defaults > 0
    assert row.oe_ratio is None
    assert row.oe_ratio_reason == "non_representable_ratio"
    assert row.observed_defaults == 1
    assert row.gap_pp == 100
    json.dumps(value.model_dump(mode="json"), allow_nan=False)


def test_contexto_no_se_infiere_del_nombre_de_muestra() -> None:
    value = _interpret(_frame())
    hl = value.hl[0]
    assert hl.context == "unknown"
    assert hl.context_source == "none"
    assert hl.context_scope == "calibration_only"
    assert not hl.full_pipeline_independence_verified


def test_sin_hl_no_fabrica_filas_ni_deuda_contextual() -> None:
    from bayesrisk.validation import interpret_validation

    cfg = _config(hosmer_lemeshow=False)
    result = ValidationEvaluator(cfg).validate(calibrated_pd=_frame())
    value = interpret_validation(result, calibrated_pd=None, calibration_config=cfg.calibration)
    assert value.hl == value.calibration_tie_groups == ()
    assert not value.coverage_gap
    assert value.warning_codes == ()


@pytest.mark.parametrize("defect", ["missing", "empty", "zero", "one", "rows", "groups", "minimum"])
def test_integridad_rechaza_inputs_contradictorios(defect: str) -> None:
    from bayesrisk.validation import interpret_validation

    frame = _frame()
    cfg = _config()
    result = ValidationEvaluator(cfg).validate(calibrated_pd=frame)
    effective = cfg.calibration
    if defect == "missing":
        frame = None
    elif defect == "empty":
        frame = frame.iloc[:0]
    elif defect in ("zero", "one"):
        frame.loc[0, "pd_calibrated"] = 0.0 if defect == "zero" else 1.0
    elif defect == "rows":
        frame = frame.iloc[:-1]
    elif defect == "groups":
        effective = CalibrationValidationConfig(hl_n_groups=10, binomial_by_grade=False)
    elif defect == "minimum":
        effective = effective.model_copy(update={"min_rows_per_group": 29})
    with pytest.raises(ValidationDataError):
        interpret_validation(result, calibrated_pd=frame, calibration_config=effective)


def test_no_recalcula_kernel_y_conserva_proyeccion_historica(monkeypatch) -> None:
    import bayesrisk.validation.calibration_tests as kernels
    import bayesrisk.validation.evaluator as evaluator
    from bayesrisk.validation import interpret_validation

    frame = _frame([0.1 + i / 500 for i in range(300)])
    cfg = _config()
    result = ValidationEvaluator(cfg).validate(calibrated_pd=frame)
    original = result.model_copy(deep=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("La interpretación no ejecuta HL")

    monkeypatch.setattr(kernels, "hosmer_lemeshow", forbidden)
    monkeypatch.setattr(evaluator, "hosmer_lemeshow", forbidden)
    value = interpret_validation(result, calibrated_pd=frame, calibration_config=cfg.calibration)
    assert result.card == original.card
    assert result.calibration_records == original.calibration_records
    pd.testing.assert_frame_equal(result.calibration, original.calibration)
    assert value.legacy_status == result.card.overall_status
    assert value.legacy_n_tests == result.card.n_tests
    assert value.legacy_n_failed == result.card.n_failed
    assert value.overall_status == "not_evaluable"


def test_deuda_es_estructural_y_dto_cerrado() -> None:
    from pydantic import ValidationError

    from bayesrisk.core.markers import governable_warnings, is_declared_warning
    from bayesrisk.validation.interpretation import HL_STRUCTURAL_WARNINGS

    value = _interpret(_frame())
    assert all(is_declared_warning(code) for code in value.warning_codes)
    assert governable_warnings(value.warning_codes, structural=HL_STRUCTURAL_WARNINGS) == ()
    with pytest.raises(ValidationError):
        type(value).model_validate({**value.model_dump(), "policy_id": "future"})
    with pytest.raises(ValidationError):
        type(value).model_validate({**value.model_dump(), "invented": True})


@pytest.mark.parametrize(
    ("psi", "hl", "expected"),
    [
        (0.01, True, "warn"),
        (0.15, True, "warn"),
        (0.30, True, "fail"),
        (0.01, False, "pass"),
        (0.15, False, "warn"),
        (0.30, False, "fail"),
    ],
)
def test_prioridades_preservan_estabilidad(psi: float, hl: bool, expected: str) -> None:
    from bayesrisk.validation import interpret_validation

    cfg = _config(hosmer_lemeshow=hl).model_copy(update={"families": ("calibration", "stability")})
    stability = pd.DataFrame(
        {
            "metric": ["score_psi"],
            "comparison": ["dev_vs_oot"],
            "feature": ["score"],
            "value": [psi],
        }
    )
    frame = _frame()
    result = ValidationEvaluator(cfg).validate(calibrated_pd=frame, stability_metrics=stability)
    value = interpret_validation(result, calibrated_pd=frame, calibration_config=cfg.calibration)
    assert value.overall_status == expected
    assert value.n_tests == 0


def test_cambiar_solo_veredicto_hl_no_mueve_estado_contextual(monkeypatch) -> None:
    from bayesrisk.validation import interpret_validation
    from bayesrisk.validation.results import CalibrationTestRecord

    frame = _frame([0.2] * 300)
    cfg = _config()
    outputs = []
    for decision, h, p in [("pass", 0.0, 1.0), ("fail", 100.0, 1e-8)]:
        record = CalibrationTestRecord(
            partition="desarrollo",
            test="hosmer_lemeshow",
            n_groups=5,
            degrees_of_freedom=3,
            statistic=h,
            p_value=p,
            alpha=0.05,
            decision=decision,
        )
        monkeypatch.setattr(
            ValidationEvaluator, "_hosmer_lemeshow_record", lambda *a, value=record: value
        )
        result = ValidationEvaluator(cfg).validate(calibrated_pd=frame)
        outputs.append(
            interpret_validation(result, calibrated_pd=frame, calibration_config=cfg.calibration)
        )
    assert [v.legacy_status for v in outputs] == ["pass", "fail"]
    assert [v.overall_status for v in outputs] == ["not_evaluable", "not_evaluable"]
    assert outputs[0].calibration_tie_groups == outputs[1].calibration_tie_groups
    assert outputs[0].n_tests == outputs[1].n_tests == 0


def _metadata(n: int):
    from bayesrisk.calibration.results import CalibrationCardSection, CalibrationParameters

    common = dict(
        method="intercept_offset",
        target_pd=0.2,
        anchor_kind="point_in_time",
        anchor_source="development_observed",
        fit_partition="desarrollo",
        n_fit=n,
        raw_mean_pd_dev=0.2,
        observed_default_rate_dev=0.2,
        offset=0.0,
        slope=None,
        intercept=None,
    )
    parameters = CalibrationParameters(
        **common, post_offset=None, target_tolerance=1e-8, achieved_mean_pd_dev=0.2
    )
    card = CalibrationCardSection(
        **common,
        calibrated_mean_pd_dev=0.2,
        ranking_preserved=True,
        ties_created=0,
        pd_raw_column="pd_raw",
        pd_calibrated_column="pd_calibrated",
        dependency_versions={},
    )
    return parameters, card


def test_metadatos_coherentes_son_declaracion_parcial_nunca_independencia() -> None:
    frame = pd.concat([_frame(), _frame().assign(partition="oot")], ignore_index=True)
    parameters, card = _metadata(10)
    value = _interpret(frame, calibration_parameters=parameters, calibration_card=card)
    assert [h.context for h in value.hl] == ["same_calibration_sample", "other_calibration_sample"]
    assert all(h.context_source == "artifact_metadata" for h in value.hl)
    assert all(not h.full_pipeline_independence_verified for h in value.hl)
    for bad in [
        None,
        card.model_copy(update={"n_fit": 9}),
        card.model_copy(update={"method": "isotonic"}),
    ]:
        value = _interpret(frame, calibration_parameters=parameters, calibration_card=bad)
        assert all(h.context == "unknown" and h.context_reason for h in value.hl)
    value = _interpret(
        frame, calibration_parameters=_metadata(11)[0], calibration_card=_metadata(11)[1]
    )
    assert all(h.context == "unknown" for h in value.hl)


def test_metadatos_model_copy_invalido_no_acreditan_procedencia() -> None:
    parameters, card = _metadata(10)
    value = _interpret(
        _frame(),
        calibration_parameters=parameters.model_copy(update={"method": "inventado"}),
        calibration_card=card.model_copy(update={"method": "inventado"}),
    )
    assert value.hl[0].context == "unknown"


def test_step_publica_mismo_diagnostico_y_eventos_aditivos_sin_abort() -> None:
    from test_validation_step import _scorecard_study

    from bayesrisk.core.audit import InMemoryAuditSink
    from bayesrisk.validation.step import ValidationStep

    cfg = _config().model_copy(update={"fail_on_falta_dato": True})
    study = _scorecard_study(config=cfg)
    step = ValidationStep(cfg)
    sink = InMemoryAuditSink()
    step._audit = sink
    result = step.execute(study, np.random.default_rng(4))
    value = study.artifacts.get("validation", "interpretation")
    pd.testing.assert_frame_equal(
        value.groups_frame(), study.artifacts.get("validation", "calibration_tie_groups")
    )
    assert study.artifacts.get("validation", "result").card == result.card
    assert result.card.falta_dato == ()
    assert ("calibration", "parameters") in step.optional_requires
    assert ("calibration", "card") in step.optional_requires
    events = [e for e in sink.events if e.payload.get("regla") == "calibration_hl_context"]
    assert len(events) == len(value.hl)
    assert all(e.payload["valor"]["formal_inference"] == "not_established" for e in events)


def test_nuevos_artefactos_no_cambian_comparable_historico() -> None:
    from test_validation_step import _scorecard_study

    from bayesrisk.comparison.comparable import _validacion
    from bayesrisk.validation.step import ValidationStep

    study = _scorecard_study(config=_config())
    ValidationStep(_config()).execute(study, np.random.default_rng(4))
    before = _validacion(study)
    # Cambiar sólo la política visible no debe entrar al productor del formato 1.
    study.artifacts.set(
        "validation",
        "interpretation",
        {"policy_id": "future", "overall_status": "pass"},
        overwrite=True,
    )
    assert _validacion(study) == before


def test_consumidor_rechaza_tabla_adulterada_y_politica_futura_no_se_aplica() -> None:
    from test_validation_step import _scorecard_study

    from bayesrisk.validation.interpretation import study_interpretation
    from bayesrisk.validation.step import ValidationStep

    study = _scorecard_study(config=_config())
    ValidationStep(_config()).execute(study, np.random.default_rng(4))
    frame = study.artifacts.get("validation", "calibration_tie_groups").copy()
    frame.loc[0, "n"] += 1
    study.artifacts.set("validation", "calibration_tie_groups", frame, overwrite=True)
    with pytest.raises(ValidationDataError, match="grupos"):
        study_interpretation(study)
    study.artifacts.set(
        "validation",
        "interpretation",
        {"policy_id": "future", "overall_status": "pass"},
        overwrite=True,
    )
    assert study_interpretation(study)[1] is None


@pytest.mark.parametrize("as_mapping", [False, True])
def test_politica_futura_persistida_degrada_a_historico(tmp_path: Path, as_mapping: bool) -> None:
    from test_report_builder import _lineage
    from test_validation_step import _scorecard_study

    from bayesrisk.core.study import Study
    from bayesrisk.guided.summaries import SummaryContext, build_stage_summary
    from bayesrisk.report.builder import ReportBuilder
    from bayesrisk.report.config import ReportConfig
    from bayesrisk.validation.interpretation import UNSUPPORTED_POLICY_TEXT, study_interpretation
    from bayesrisk.validation.step import ValidationStep

    study = _scorecard_study(config=_config())
    ValidationStep(_config()).execute(study, np.random.default_rng(4))
    value = study.artifacts.get("validation", "interpretation")
    future = value.model_copy(update={"policy_id": "hl_context_v2"})
    raw = future.model_dump() if as_mapping else future
    study.artifacts.set("validation", "interpretation", raw, overwrite=True)
    study.save(tmp_path / "study")
    loaded = Study.load(tmp_path / "study", trust=True)
    assert study_interpretation(loaded)[1] is None
    context = SummaryContext(tmp_path, tmp_path / "run", "Datos de prueba", "Muestras declaradas")
    summary = build_stage_summary("validation", loaded, context)
    assert UNSUPPORTED_POLICY_TEXT in " ".join(summary.lines)
    assert not any("Evaluación contextual" in line for line in summary.lines)
    loaded.run_context.lineage = _lineage()
    bundle = ReportBuilder(ReportConfig(sections={"missing_policy": "skip"})).collect(loaded)
    assert not any(key.startswith("validation.calibration_tie_groups.") for key in bundle.tables)
    assert bundle.validation_interpretation["policy_id"] == "hl_context_v2"


@pytest.mark.parametrize(
    ("defaults", "light", "status"),
    [
        (0, "green", "warn"),
        (50, "amber", "warn"),
        (200, "red", "fail"),
    ],
)
def test_hl_no_anula_el_contraste_por_grado(defaults: int, light: str, status: str) -> None:
    from bayesrisk.validation import interpret_validation

    frame = _frame([0.2] * 200).assign(target=[1] * defaults + [0] * (200 - defaults), grade="A")
    cfg = ValidationConfig(
        families=("calibration",),
        calibration={
            "binomial_by_grade": True,
            "grade_col": "grade",
            "pd_test": "binomial",
        },
    )
    result = ValidationEvaluator(cfg).validate(calibrated_pd=frame)
    value = interpret_validation(result, calibrated_pd=frame, calibration_config=cfg.calibration)
    assert result.grade_records[0].traffic_light == light
    assert value.overall_status == status
    assert value.n_tests == 1
    assert value.n_failed == int(light == "red")


def test_sin_empates_respeta_cortes_nominales_y_rechaza_alfa_distinto() -> None:
    from bayesrisk.validation import interpret_validation

    frame = _frame([0.01 + i / 500 for i in range(301)])
    cfg = _config()
    result = ValidationEvaluator(cfg).validate(calibrated_pd=frame)
    value = interpret_validation(result, calibrated_pd=frame, calibration_config=cfg.calibration)
    assert [g.n for g in value.calibration_tie_groups] == [61, 60, 60, 60, 60]
    assert not value.hl[0].legacy_boundary_splits_tie
    with pytest.raises(ValidationDataError, match="Alfa"):
        interpret_validation(
            result,
            calibrated_pd=frame,
            calibration_config=cfg.calibration.model_copy(update={"alpha": 0.1}),
        )
