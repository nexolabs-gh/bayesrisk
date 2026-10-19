"""Paridad de las puertas y perturbación diagnóstica; no mide latencia visible."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .canonical import canonizar, proyeccion_canonica
from .contract import SEED, dump
from .isolation import FitAudit


def calculation(study) -> dict:
    """Proyección histórica más escala maestra, declarada por separado."""
    return {
        "canonical": proyeccion_canonica(study),
        "master_scale": {
            key: canonizar(study.artifacts.get(domain, key))
            for domain, key in sorted(study.artifacts.keys())
            if domain == "master_scale"
        },
    }


def verify_doors(sc, frame, dev, target: str, output: Path, *, recorded_canonical=None) -> dict:
    """Ejecuta completa y backend real de pantalla con el YAML de la guiada."""
    from starlette.testclient import TestClient

    import bayesrisk
    from bayesrisk.core.config import config_hash, loads_config
    from bayesrisk.guided.summaries import build_stage_summary
    from bayesrisk.ui.runtime import TOKEN_HEADER, build_runtime
    from bayesrisk.ui.server import create_app
    from bayesrisk.ui.settings import UiConfig

    output.mkdir(parents=True, exist_ok=False)
    exported = sc.to_yaml()
    (output / "exported.yaml").write_text(exported, encoding="utf-8")
    config = loads_config(exported)
    if config_hash(config) != sc.config_hash:
        raise ValueError("YAML exportado distinto al config usado")
    # El YAML original identifica sus informes. Una reproducción conserva esa evidencia
    # y cambia sólo el destino de salida, excluido por contrato del hash computacional.
    config = config.model_copy(
        update={
            "report": config.report.model_copy(
                update={"output_dir": str((output / "complete-reports").resolve())}
            )
        }
    )
    if config_hash(config) != sc.config_hash:
        raise ValueError("reubicar informes cambió el hash computacional")
    dump(output / "complete-config.json", config.model_dump(mode="json"))
    with FitAudit(dev, target) as audit:
        complete = bayesrisk.run(config, run_dir=output / "complete")
        complete_audit = audit.result("fabrica", list(sc.config.binning.feature_columns))
    if complete.run_context.status != "done":
        raise ValueError(f"puerta completa falló: {complete.run_context.error}")
    observed = []
    original = bayesrisk.run

    def capture(*args, **kwargs):
        study = original(*args, **kwargs)
        observed.append(study)
        return study

    workdir = output / "screen"
    runtime = build_runtime(port=8000, workdir=workdir, token="prueba-local-no-secreto")
    app = create_app(UiConfig(workdir=str(workdir)), runtime)
    with patch.object(bayesrisk, "run", capture), FitAudit(dev, target) as audit:
        with TestClient(
            app,
            base_url=runtime.origin,
            headers={"Origin": runtime.origin, TOKEN_HEADER: runtime.token},
        ) as client:
            content = io.BytesIO()
            frame.to_parquet(content)
            uploaded = client.post(
                "/api/upload",
                files={"file": ("input.parquet", content.getvalue(), "application/octet-stream")},
            )
            if uploaded.status_code != 200:
                raise ValueError(f"upload falló: {uploaded.text}")
            response = client.post(
                "/api/run",
                json={
                    "config": config.model_dump(mode="json", by_alias=True),
                    "dataset_id": uploaded.json()["dataset_id"],
                },
            )
            if response.status_code != 200 or response.json().get("status") != "done":
                raise ValueError(f"pantalla falló: {response.text}")
            results = client.get(f"/api/results/{response.json()['run_id']}")
            if results.status_code != 200:
                raise ValueError(f"resultados pantalla fallaron: {results.text}")
            screen_payload = results.json()
        screen_audit = audit.result("fabrica", list(sc.config.binning.feature_columns))
    if len(observed) != 1:
        raise ValueError("número inesperado de corridas de pantalla")
    baseline = calculation(sc.study)
    if recorded_canonical is not None:
        if recorded_canonical["artifacts"] != baseline["canonical"]["artifacts"]:
            raise ValueError("artefactos recargados distintos al registro en vivo")
        baseline["canonical"] = recorded_canonical
    summaries = {}

    def normalize_paths(value, study):
        if isinstance(value, str):
            return value.replace(str(Path(study.config.report.output_dir).resolve()), "<informes>")
        if isinstance(value, dict):
            return {key: normalize_paths(item, study) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize_paths(item, study) for item in value]
        return value

    for name, study in (("complete", complete), ("screen", observed[0])):
        if calculation(study) != baseline or config_hash(study.config) != sc.config_hash:
            raise ValueError(f"cálculo/config divergente por puerta {name}")
        # Contexto común explícito: las rutas físicas de evidencia sí difieren por puerta.
        stages = {
            stage: build_stage_summary(stage, study, sc._context()).to_dict() for stage in sc.steps
        }
        wanted = {
            stage: build_stage_summary(stage, sc.study, sc._context()).to_dict()
            for stage in sc.steps
        }
        dump(output / f"{name}-summaries.json", stages)
        dump(output / "guided-summaries.json", wanted)
        if normalize_paths(stages, study) != normalize_paths(wanted, sc.study):
            raise ValueError(f"resúmenes divergentes por puerta {name}")
        summaries[name] = stages
    dump(output / "screen-payload.json", screen_payload)
    dump(output / "summaries-common-context.json", summaries)
    result = {
        "config_hash": sc.config_hash,
        "canonical_equal": True,
        "master_scale_equal": True,
        "summaries_equal_common_context": True,
        "summary_provenance_excluded": ["directorio físico de informes"],
        "complete_audit": complete_audit,
        "screen_audit": screen_audit,
        "visible_latency": "No medida aquí: requiere navegador y render real",
    }
    dump(output / "verification.json", result)
    return result


def verify_holdout(sc, frame, manifest: dict, exterior, output: Path) -> dict:
    """Permutar sólo labels Holdout no debe alterar ningún componente ajustado."""
    from bayesrisk import Scorecard

    output.mkdir(parents=True, exist_ok=False)
    target = manifest["target"]
    changed = frame.copy(deep=True)
    ids = manifest["partitions"]["holdout"]
    changed.loc[ids, target] = np.random.default_rng(SEED).permutation(
        frame.loc[ids, target].to_numpy()
    )
    if changed.loc[ids, target].equals(frame.loc[ids, target]):
        raise ValueError("perturbación Holdout no efectiva")
    dev = frame.loc[manifest["partitions"]["desarrollo"]]
    altered = Scorecard(
        changed, name="holdout", run_dir=output, formats=["html", "docx"], **manifest["kwargs"]
    )
    with FitAudit(dev, target) as audit:
        altered.run(raise_on_error=True)
        fitted_audit = audit.result("fabrica", manifest["features"])
        audit.applying = True
        actual = altered.apply(exterior.drop(columns=target))
    expected = sc.apply(exterior.drop(columns=target))
    keys = [
        ("binning", "tables"),
        ("binning", "summary"),
        ("binning", "bin_edges"),
        ("selection", "selected_features"),
        ("selection", "selected_woe_columns"),
        ("model", "coefficients"),
        ("model", "final_features"),
        ("calibration", "parameters"),
    ]
    fitted = {}
    for domain, key in keys:
        left = canonizar(sc.study.artifacts.get(domain, key))
        right = canonizar(altered.study.artifacts.get(domain, key))
        if left != right:
            raise ValueError(f"Holdout afectó el fit: {domain}.{key}")
        fitted[f"{domain}.{key}"] = left
    # El bundle incluye la huella de los datos de entrenamiento: cambiar labels Holdout
    # cambia su procedencia aunque todos los parámetros y resultados de scoring coincidan.
    scoring_columns = [column for column in expected if column != "bundle_hash"]
    if list(actual.columns) != list(expected.columns) or not actual[scoring_columns].equals(
        expected[scoring_columns]
    ):
        raise ValueError("Holdout afectó predicciones exteriores")
    if not changed.drop(columns=target).equals(frame.drop(columns=target)):
        raise ValueError("control alteró covariables")
    if not changed.loc[dev.index].equals(dev):
        raise ValueError("control alteró Desarrollo")
    changed.loc[ids, target] = frame.loc[ids, target]
    if not changed.equals(frame):
        raise ValueError("restauración de labels no exacta")
    result = {
        "holdout_labels_changed": True,
        "fit_equal": fitted,
        "exterior_equal": True,
        "scoring_columns": scoring_columns,
        "provenance_excluded": ["bundle_hash"],
        "original_frame_restored": True,
        "fit_audit": fitted_audit,
    }
    dump(output / "verification.json", result)
    return result
