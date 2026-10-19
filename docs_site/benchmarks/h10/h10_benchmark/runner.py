"""Ejecución secuencial del anexo: preparación anterior al fit y denominadores completos."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata as metadata
import io
import json
import os
import platform
import sys
import time
import traceback
import warnings
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from bayesrisk import Scorecard

from .artifacts import expected_artifacts
from .canonical import canonizar, proyeccion_canonica
from .contract import CASES, RECIPES, SEED, SOURCES, THREAD_ENV, dump, sha256, verify_coverage
from .data import load_case, outer_split, verify_classes, verify_partition
from .isolation import FitAudit
from .metrics import measure
from .presentation import layout_word
from .recipes import fit_reference

PROCESS_ID = f"{os.getpid()}:{time.time_ns()}"


def execution_environment() -> dict:
    """Acredita el entorno efectivo, incluso cuando run se importa desde un notebook."""
    from threadpoolctl import threadpool_info

    if os.environ.get("PYTHONHASHSEED") != "0" or sys.flags.hash_randomization != 0:
        raise ValueError("PYTHONHASHSEED=0 debe fijarse antes de iniciar el proceso")
    threads = {name: os.environ.get(name) for name in THREAD_ENV}
    pools = threadpool_info()
    if any(value != "1" for value in threads.values()) or any(p["num_threads"] != 1 for p in pools):
        raise ValueError("threads efectivos distintos de uno")
    return {
        "hash_seed": os.environ["PYTHONHASHSEED"],
        "thread_variables": threads,
        "thread_pools": pools,
        "execution": {
            "identity": PROCESS_ID,
            "pid": os.getpid(),
            "mechanism": "proceso Python independiente",
        },
    }


def prepare(cache: Path, destination: Path) -> None:
    """Congela cuatro fronteras y comprueba clases antes del primer ajuste."""
    execution_environment()
    if destination.exists():
        raise ValueError("preparación ya existe; se conserva sin sobrescribir")
    destination.mkdir(parents=True)
    for case in CASES:
        frame, kwargs, groups = load_case(case, cache)
        if case.startswith("consumo_"):
            input_frame = frame
            exterior = frame.loc[frame.cohorte.eq("2024Q2")]
            complement = frame.index[~frame.index.isin(exterior.index)]
        else:
            input_frame, exterior = outer_split(frame, groups)
            complement = input_frame.index
        verify_partition(
            frame.index,
            {"input_without_evaluation": complement, "evaluation": exterior.index},
            groups,
        )
        project = destination / case
        project.mkdir()
        frame.to_parquet(project / "source.parquet")
        input_frame.to_parquet(project / "input.parquet")
        exterior.to_parquet(project / "evaluation.parquet")
        groups.to_frame().to_parquet(project / "groups.parquet")
        with contextlib.redirect_stdout(io.StringIO()):
            sc = Scorecard(
                input_frame,
                name=case,
                run_dir=destination / "preflight",
                formats=["html", "docx"],
                **kwargs,
            )
            sc.run(until="data", raise_on_error=True)
        split = sc.study.artifacts.get("data", "splits").frame
        dev = split.index[split.partition.eq("desarrollo")]
        holdout = split.index[split.partition.eq("holdout")]
        parts = {"desarrollo": dev, "holdout": holdout, "evaluacion": exterior.index}
        verify_partition(frame.index, parts)
        verify_classes(frame, kwargs["target"], parts)
        features = list(sc.config.binning.feature_columns)
        if (
            kwargs["target"] in features
            or kwargs.get("id") in features
            or kwargs.get("cohort") in features
        ):
            raise ValueError("target/ID/cohorte entró en X")
        manifest = {
            "case": case,
            "seed_outer": SEED,
            "seed_inner": sc.config.repro.seed,
            "frame": canonizar(frame),
            "unit": "fila de la fuente; no se acredita entidad personal",
            "source": SOURCES.get(
                case, {"source": "generador bayesrisk", "license": "Apache-2.0", "synthetic": True}
            ),
            "kwargs": kwargs,
            "features": features,
            "partitions": {k: v.tolist() for k, v in parts.items()},
            "rows": len(frame),
            "groups": int(groups.nunique()),
            "evaluation_rows_fraction": len(exterior) / len(frame),
            "evaluation_groups_fraction": groups.loc[exterior.index].nunique() / groups.nunique(),
            "outer_rule": "OOT 2024Q2"
            if case.startswith("consumo_")
            else "GroupShuffleSplit 25% grupos, seed20261016",
            "input_rows": len(input_frame),
            "target": kwargs["target"],
            "class_counts": {
                k: {
                    "bad": int(frame.loc[v, kwargs["target"]].sum()),
                    "good": int(len(v) - frame.loc[v, kwargs["target"]].sum()),
                }
                for k, v in parts.items()
            },
            "inner_shared_x_groups": len(set(groups.loc[dev]) & set(groups.loc[holdout])),
            "independence": (
                "Sólo proxy X exacto; no independencia de personas acreditada. "
                "Holdout interior diagnóstico."
            ),
            "source_ids": frame.attrs.get("source_ids"),
            "config_hash": sc.config_hash,
            "files": {p.name: sha256(p) for p in project.glob("*.parquet")},
        }
        dump(project / "manifest.json", manifest)
        print(case, manifest["class_counts"], flush=True)
    dump(
        destination / "predeclared.json",
        {
            "cases": list(CASES),
            "recipes": RECIPES,
            "source": "H10 §§6/7/9; antes de fit",
            "complete": True,
        },
    )


def read_prepared(prepared: Path, case: str) -> tuple:
    """Nunca reutiliza una partición distinta de la congelada."""
    root = prepared / case
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        if sha256(root / name) != digest:
            raise ValueError(f"huella de partición cambió: {case}/{name}")
    frame = pd.read_parquet(root / "source.parquet")
    input_frame = pd.read_parquet(root / "input.parquet")
    test = pd.read_parquet(root / "evaluation.parquet")
    dev = frame.loc[manifest["partitions"]["desarrollo"]]
    groups = pd.read_parquet(root / "groups.parquet").iloc[:, 0]
    parts = {k: pd.Index(v) for k, v in manifest["partitions"].items()}
    verify_partition(frame.index, parts)
    verify_classes(frame, manifest["target"], parts)
    verify_partition(
        frame.index,
        {
            "input_without_evaluation": frame.index[~frame.index.isin(test.index)],
            "evaluation": test.index,
        },
        groups,
    )
    if not test.equals(frame.loc[parts["evaluacion"]]):
        raise ValueError("evaluación no coincide con fuente y manifiesto")
    expected_input = (
        frame if case.startswith("consumo_") else frame.loc[~frame.index.isin(test.index)]
    )
    if not input_frame.equals(expected_input):
        raise ValueError("input no coincide con frontera congelada")
    if "frame" in manifest and canonizar(frame) != manifest["frame"]:
        raise ValueError("huella lógica de fuente diferente")
    return manifest, input_frame, dev, test


def _frame_json(frame: pd.DataFrame) -> dict:
    """Forma legible de tablas; JSON de pandas representa ausentes como null."""
    return json.loads(frame.to_json(orient="split", date_format="iso", double_precision=15))


def fit_bayesrisk(
    case: str,
    recipe: str,
    manifest: dict,
    input_frame: pd.DataFrame,
    dev: pd.DataFrame,
    test: pd.DataFrame,
    output: Path,
    audit: FitAudit,
) -> dict:
    """Instrumenta costes por paso sin sustituir ningún cálculo del motor."""
    from bayesrisk.core.study import Study

    timings = {}
    original = Study._run_one

    def timed(study, step):
        start = time.perf_counter()
        try:
            return original(study, step)
        finally:
            timings[step.name] = time.perf_counter() - start

    started = time.perf_counter()
    sc = Scorecard(
        input_frame,
        name=f"{case}_{recipe}",
        run_dir=output / "projects",
        formats=["html", "docx"],
        **manifest["kwargs"],
        **RECIPES[recipe],
    )
    with patch.object(Study, "_run_one", timed):
        sc.run(raise_on_error=True)
    total = time.perf_counter() - started
    split = sc.study.artifacts.get("data", "splits").frame
    for part in ("desarrollo", "holdout"):
        if split.index[split.partition.eq(part)].tolist() != manifest["partitions"][part]:
            raise ValueError(f"partición {part} difiere del protocolo")
    summary = sc.study.artifacts.get("binning", "summary")
    if "status" in summary:
        bad_status = summary["status"].dropna().loc[lambda s: ~s.isin(["OPTIMAL", "SKIPPED"])]
        if len(bad_status):
            raise ValueError(f"solver no óptimo: {bad_status.tolist()}")
    target = manifest["target"]
    audit.applying = True
    applied = time.perf_counter()
    predicted = sc.apply(test.drop(columns=target))
    reference = sc.apply(dev.drop(columns=target))
    apply_seconds = time.perf_counter() - applied
    for actual, expected in ((predicted, test), (reference, dev)):
        if not actual.index.equals(expected.index) or not actual.scoring_status.eq("scored").all():
            raise ValueError("predicción omitida/desalineada")
    tables = {"binning": summary, "coefficients": sc.study.artifacts.get("model", "coefficients")}
    summaries = {}
    for stage in sc.steps:
        current = sc.summary(stage)
        summaries[stage] = {"text": current.text(), "html": current._repr_html_()}
        if current.table is not None:
            tables[f"summary_{stage}"] = current.table
    sc.export_excel()
    layout_word(sc.project_dir / "reports/scorecard_report.docx")
    expected_artifacts(sc, output / f"{case}_{recipe}_expected.json")
    dump(output / f"{case}_{recipe}_canonical.json", proyeccion_canonica(sc.study))
    dump(
        output / f"{case}_{recipe}_master_scale.json",
        {
            key: canonizar(sc.study.artifacts.get(domain, key))
            for domain, key in sorted(sc.study.artifacts.keys())
            if domain == "master_scale"
        },
    )
    dump(output / f"{case}_{recipe}_summaries.json", summaries)
    dump(output / f"{case}_{recipe}_config.json", sc.config.model_dump(mode="json"))
    dump(
        output / f"{case}_{recipe}_fit.json",
        {
            "features": list(sc.study.artifacts.get("model", "final_features")),
            "coefficients": _frame_json(tables["coefficients"]),
            "calibration": sc.study.artifacts.get("calibration", "parameters").model_dump(
                mode="json"
            ),
        },
    )
    return {
        "probability": predicted.pd_calibrated,
        "reference": reference.pd_calibrated,
        "tables": tables,
        "features": list(sc.study.artifacts.get("model", "final_features")),
        "fit_seconds": sum(v for k, v in timings.items() if k != "report"),
        "apply_seconds": apply_seconds,
        "report_seconds": timings.get("report", 0.0),
        "total_seconds": total,
        "step_seconds": timings,
        "config_hash": sc.config_hash,
        "data_hash": sc.study.artifacts.get("data", "data_hash"),
        "solver_status": _frame_json(summary),
        "project": sc.project_dir.name,
    }


def run(prepared: Path, output: Path) -> list[dict]:
    """Ejecución fresca: 28 filas y todos los errores; ningún fit concurrente."""
    environment = execution_environment()
    if output.exists():
        raise ValueError("salida existe; no mezclar ejecuciones independientes")
    output.mkdir(parents=True)
    packages = {d.metadata["Name"]: d.version for d in metadata.distributions()}
    dump(
        output / "environment.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": dict(sorted(packages.items())),
            **environment,
            "installed_prefix": str(Path(sys.prefix).resolve()),
        },
    )
    rows = [
        {"case": case, "recipe": recipe, "status": "pendiente", "error": "no ejecutado"}
        for case in CASES
        for recipe in RECIPES
    ]
    dump(output / "results.json", rows)
    for case in CASES:
        preparation_error = None
        try:
            manifest, input_frame, dev, test = read_prepared(prepared, case)
        except Exception as exc:
            preparation_error = f"{type(exc).__name__}: {exc}"
        for recipe, options in RECIPES.items():
            started = time.perf_counter()
            audit = None
            row = next(r for r in rows if r["case"] == case and r["recipe"] == recipe)
            caught = []
            try:
                if preparation_error is not None:
                    raise ValueError(f"preparación bloqueada: {preparation_error}")
                row.update(
                    dev_ids=dev.index.tolist(),
                    evaluation_ids=test.index.tolist(),
                    input_features=manifest["features"],
                    target=manifest["target"],
                )
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    with (
                        (output / f"{case}_{recipe}.log").open("w", encoding="utf-8") as log,
                        contextlib.redirect_stdout(log),
                        contextlib.redirect_stderr(log),
                        FitAudit(dev, manifest["target"]) as audit,
                    ):
                        audit.references(recipe)
                        result = (
                            fit_bayesrisk(
                                case, recipe, manifest, input_frame, dev, test, output, audit
                            )
                            if options is not None
                            else fit_reference(
                                recipe, dev, test, manifest["features"], manifest["target"], audit
                            )
                        )
                        row["isolation"] = audit.result(recipe, manifest["features"])
                row["warnings"] = sorted(
                    {f"{type(w.message).__name__}: {w.message}" for w in caught}
                )
                probability, reference = result.pop("probability"), result.pop("reference")
                row["metrics"] = measure(test[manifest["target"]], probability, reference)
                for label, table in result.pop("tables").items():
                    dump(output / "tables" / f"{case}_{recipe}_{label}.json", _frame_json(table))
                result.pop("model", None)
                row.update(result, status="ejecutado", error=None)
                predictions = pd.DataFrame({"y": test[manifest["target"]], "pd": probability})
                predictions.to_parquet(output / f"{case}_{recipe}_predictions.parquet")
                reference.to_frame("pd").to_parquet(output / f"{case}_{recipe}_reference.parquet")
                row["prediction_sha256"] = hashlib.sha256(
                    pd.util.hash_pandas_object(predictions, index=True).values.tobytes()
                ).hexdigest()
            except Exception as exc:
                row.update(
                    status="falló",
                    error=f"{type(exc).__name__}: {exc}",
                    traceback=traceback.format_exc(),
                )
            finally:
                row["warnings"] = sorted(
                    {f"{type(w.message).__name__}: {w.message}" for w in caught}
                )
                if audit is not None:
                    row["fit_events"] = dict(audit.events)
                    row["solver_events"] = audit.solvers
            row["wall_seconds"] = time.perf_counter() - started
            dump(output / "results.json", rows)
            print(
                case, recipe, row["status"], row["error"], round(row["wall_seconds"], 3), flush=True
            )
    dump(output / "coverage.json", verify_coverage(rows))
    return rows
