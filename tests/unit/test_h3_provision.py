"""H3 A: la puerta consume el motor, conserva evidencia y habla por etapa."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest


def cartera() -> pd.DataFrame:
    """Dos operaciones cuyo oráculo grupal distingue 50 de 74."""
    return pd.DataFrame(
        {
            "fecha": ["2026-01-01"] * 2,
            "cartera": ["A"] * 2,
            "exposicion": [100.0, 100.0],
            "pd": [0.1, 0.9],
            "lgd": [0.2, 0.8],
            "operacion": ["a", "b"],
            "grupo": ["unico"] * 2,
        },
        index=pd.Index(["fila-a", "fila-b"], name="fila"),
    )


def puerta(tmp_path: Path):
    from bayesrisk import Provision

    return Provision(
        cartera(),
        as_of="fecha",
        portfolio="cartera",
        exposure="exposicion",
        pd="pd",
        lgd="lgd",
        id="operacion",
        run_dir=tmp_path,
        formats=(),
    )


def test_puerta_completa_y_guiada_mismo_calculo_y_procedencia(tmp_path: Path) -> None:
    import bayesrisk

    p = puerta(tmp_path)
    assert p.config.data.target is None and p.config.data.partition is None
    p.run(raise_on_error=True)
    other = bayesrisk.run(
        p.config,
        artifacts={
            ("calibration", "calibrated_pd_frame"): cartera()[["pd"]].rename(
                columns={"pd": "pd_calibrated"}
            )
        },
        run_dir=tmp_path / "completa",
    )
    assert other.run_context.status == "done"
    for key in ("detail", "groups", "summary"):
        pd.testing.assert_frame_equal(
            p.study.artifacts.get("provisioning_internal", key),
            other.artifacts.get("provisioning_internal", key),
            check_exact=True,
        )
    assert p.summary("provisioning_internal").table is not None
    assert "provisión" in p.summary().text().lower()
    assert "no aplica" in p.summary().validation.lower()
    assert ("calibration", "calibrated_pd_frame") in p.study._injected_artifacts


def test_oraculo_grupal_por_puerta_publica(tmp_path: Path) -> None:
    import bayesrisk
    from bayesrisk.core.config import BayesRiskConfig

    p = puerta(tmp_path)
    cfg = p.config.model_dump(mode="python", by_alias=True)
    cfg["provisioning_internal"].update(grouping="provided", group_col="grupo")
    study = bayesrisk.run(
        BayesRiskConfig.model_validate(cfg),
        artifacts={
            ("calibration", "calibrated_pd_frame"): cartera()[["pd"]].rename(
                columns={"pd": "pd_calibrated"}
            )
        },
        run_dir=tmp_path / "oraculo",
    )
    assert study.run_context.status == "done"
    assert study.artifacts.get("provisioning_internal", "card").total_internal_provision == Decimal(
        "50.00"
    )


def test_parar_reanudar_y_exportar_evidencia(tmp_path: Path) -> None:
    import zipfile

    pytest.importorskip("openpyxl")
    p = puerta(tmp_path)
    p.run(until="provisioning_internal", raise_on_error=True)
    old = p.study.run_context.run_id
    p.resume()
    assert p.study.run_context.status == "done"
    assert p.study.run_context.run_id != old
    assert any("Provisión interna" in path.name for path in p.export_excel())
    out = p.export(tmp_path / "proyecto.zip")
    with zipfile.ZipFile(out) as z:
        assert any("input/" in name for name in z.namelist())
        assert any("external" in name for name in z.namelist())


def test_fuente_mutada_no_se_reutiliza(tmp_path: Path) -> None:
    p = puerta(tmp_path)
    source = Path(p.config.data.load.source)
    source.write_bytes(b"otra cartera")
    with pytest.raises(Exception, match="cambió"):
        p.run()


def test_resume_aisla_las_entradas_del_artefacto_publico(tmp_path: Path) -> None:
    p = puerta(tmp_path)
    p.run(raise_on_error=True)
    before = p.study.artifacts.get("provisioning_internal", "detail").copy(deep=True)
    p.study.artifacts.get("calibration", "calibrated_pd_frame").iloc[0, 0] = 0.9
    p.resume()
    pd.testing.assert_frame_equal(
        p.study.artifacts.get("provisioning_internal", "detail"),
        before,
        check_exact=True,
    )


def test_identificador_duplicado_rechaza_y_no_imputa(tmp_path: Path) -> None:
    from bayesrisk import Provision

    data = cartera()
    data["operacion"] = "repetida"
    p = Provision(
        data,
        as_of="fecha",
        portfolio="cartera",
        exposure="exposicion",
        pd="pd",
        lgd="lgd",
        id="operacion",
        run_dir=tmp_path,
        formats=(),
    )
    p.run()
    assert p.study.run_context.status == "failed"
    assert not p.study.artifacts.has("provisioning_internal", "detail")


@pytest.mark.parametrize("lgd_method", ["provided", "fitted"])
def test_desde_scorecard_preserva_config_snapshot_y_decisiones(
    tmp_path: Path, fake_binning_process, lgd_method
) -> None:
    from _ui_f1 import write_stacked_behavior_parquet

    from bayesrisk import Provision, Scorecard
    from bayesrisk.core.config import config_hash
    from bayesrisk.guided.provision import ProvisionInputError

    source = tmp_path / "fuente.parquet"
    write_stacked_behavior_parquet(source, repeats=50)
    frame = pd.read_parquet(source)
    frame["bad_flag"] = frame["bad_flag"].astype("Float64")
    frame.loc[frame.index[:20], "bad_flag"] = pd.NA
    frame["fecha"], frame["cartera"], frame["exposicion"], frame["lgd"] = (
        "2026-01-01",
        "A",
        100.0,
        0.4,
    )
    sc = Scorecard(
        frame,
        target="bad_flag",
        id="loan_id",
        cohort="cohort",
        oot_cohorts=["oot"],
        name="original",
        run_dir=tmp_path,
        features=["score", "segment", "exposicion"],
    )
    sc.exclude("exposicion", reason="decisión explícita del modelador")
    sc.run(until="model", raise_on_error=True)
    before = sc.config.model_dump(mode="json", by_alias=True)
    digest = config_hash(sc.config)
    snapshot = Path(sc.config.data.load.source).read_bytes()
    args = {"as_of": "fecha", "portfolio": "cartera", "exposure": "exposicion", "lgd": "lgd"}
    if lgd_method == "fitted":
        from test_h3_lgd_training import historia

        from bayesrisk import Lgd

        history = historia().rename(columns={"=ratio": "score", "NA": "exposicion"})
        fitted = Lgd(
            history,
            target="lgd",
            features=["score", "exposicion"],
            entity="deudor",
            sample="muestra",
            default="incumplio",
            resolved="completo",
            id="operacion",
            run_dir=tmp_path / "historia",
            formats=(),
        ).run(raise_on_error=True)
        args["lgd"] = fitted.model_
    with pytest.raises(ProvisionInputError, match="coincide"):
        Provision.from_scorecard(sc, name="original", run_dir=tmp_path, **args)
    p = Provision.from_scorecard(sc, name="combinado", run_dir=tmp_path, **args)
    assert p.config.provisioning_internal.type == "full_population"
    assert p.config.binning == sc.config.binning
    assert p.config.selection == sc.config.selection
    assert p.config.model == sc.config.model
    assert p.config.decisions == sc.config.decisions
    assert Path(p.config.data.load.source).read_bytes() == snapshot
    assert p.config.data.load.source != sc.config.data.load.source
    assert sc.config.model_dump(mode="json", by_alias=True) == before
    assert config_hash(sc.config) == digest
    assert Path(sc.config.data.load.source).read_bytes() == snapshot
    p.run(until="provisioning_internal", raise_on_error=True)
    assert len(p.study.artifacts.get("provisioning_internal", "detail")) == len(frame)
    assert len(p.study.artifacts.get("calibration", "out_of_model_calibrated_pd_frame")) == 20
    assert p.summary("provisioning_internal").extra_tables[0][0] == "Cobertura de PD"
    prefix_hash = config_hash(p.study.config)
    prefix_run = p.study.run_context.run_id
    detail = p.study.artifacts.get("provisioning_internal", "detail").copy(deep=True)
    p.resume()
    assert p.study.run_context.status == "done", p.study.run_context.error
    assert p.study.run_context.run_id != prefix_run
    assert config_hash(p.study.config) != prefix_hash
    pd.testing.assert_frame_equal(
        p.study.artifacts.get("provisioning_internal", "detail"), detail, check_exact=True
    )
    assert sc.study.run_context.status == "done"
    assert not sc.study.artifacts.has("provisioning_internal", "detail")

    import bayesrisk

    data_cfg = p.config.data
    disabled = data_cfg.model_copy(
        update={"partition": data_cfg.partition.model_copy(update={"ttd_includes_excluded": False})}
    )
    config = p.config.model_copy(update={"data": disabled, "report": None})
    inputs = (
        {("lgd_training", "model_table"): args["lgd"].to_frame()}
        if lgd_method == "fitted"
        else None
    )
    failed = bayesrisk.run(config, artifacts=inputs, run_dir=tmp_path / "sin-ttd")
    assert failed.run_context.status == "failed"
    assert "Falta PD para 20 operaciones" in failed.run_context.error.message
    assert failed.artifacts.has("calibration", "calibrated_pd_frame")
    assert not failed.artifacts.has("provisioning_internal", "detail")
