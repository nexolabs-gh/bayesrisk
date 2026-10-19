"""Consolidación verificable: ningún ganador automático ni receta fuera del denominador."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .contract import CASES, RECIPES, dump, verify_coverage
from .metrics import grouped_auc_difference, measure


def compare_runs(left: list[dict], right: list[dict]) -> None:
    """Exige igualdad exacta de predicciones, métricas, variables y configuración."""
    keys = (
        "case",
        "recipe",
        "status",
        "prediction_sha256",
        "features",
        "config_hash",
        "data_hash",
        "metrics",
    )
    if len(left) != len(right) or any(
        {k: a.get(k) for k in keys} != {k: b.get(k) for k in keys}
        for a, b in zip(left, right, strict=True)
    ):
        raise ValueError("reproducibilidad: resultados distintos entre procesos independientes")


def verify_metrics(root: Path, rows: list[dict], prepared: Path) -> int:
    """Recalcula todas las cifras a partir de predicciones indexadas y referencia Dev."""
    cells = 0
    for row in rows:
        if row["status"] != "ejecutado":
            continue
        stem = f"{row['case']}_{row['recipe']}"
        predictions = pd.read_parquet(root / f"{stem}_predictions.parquet")
        reference = pd.read_parquet(root / f"{stem}_reference.parquet")["pd"]
        source = pd.read_parquet(prepared / row["case"] / "evaluation.parquet")
        if not predictions.y.equals(source[row["target"]].rename("y")):
            raise ValueError("labels/IDs exteriores diferentes de la fuente congelada")
        if predictions.index.tolist() != row["evaluation_ids"]:
            raise ValueError("IDs exteriores diferentes al manifiesto")
        if reference.index.tolist() != row["dev_ids"]:
            raise ValueError("IDs de referencia diferentes a Desarrollo")
        actual = measure(predictions.y, predictions.pd, reference)
        if actual != row["metrics"]:
            raise ValueError(f"métrica alterada en {stem}")
        digest = hashlib.sha256(
            pd.util.hash_pandas_object(predictions, index=True).values.tobytes()
        ).hexdigest()
        if digest != row["prediction_sha256"]:
            raise ValueError(f"huella de predicciones alterada en {stem}")
        cells += len(actual)
    return cells


def aggregate(prepared: Path, runs: list[Path], output: Path) -> dict:
    """Tres repeticiones medidas, calentamiento separado, bootstrap predeclarado."""
    if len(runs) != 3 or len(set(p.resolve() for p in runs)) != 3:
        raise ValueError("se requieren tres repeticiones independientes; no incluir calentamiento")
    all_rows = [json.loads((r / "results.json").read_text(encoding="utf-8")) for r in runs]
    environments = [json.loads((r / "environment.json").read_text(encoding="utf-8")) for r in runs]
    executions = [
        env.get("execution") or json.loads((root / "execution.json").read_text(encoding="utf-8"))
        for env, root in zip(environments, runs, strict=True)
    ]
    identities = [execution["identity"] for execution in executions]
    if len(set(identities)) != 3:
        raise ValueError("las repeticiones no pertenecen a tres procesos independientes")
    for root, rows in zip(runs, all_rows, strict=True):
        coverage = verify_coverage(rows)
        if coverage["executed"] != coverage["total"]:
            raise ValueError(
                "cobertura ejecutada incompleta; conservar y publicar la razón del fallo"
            )
        verify_metrics(root, rows, prepared)
    for rows in all_rows[1:]:
        compare_runs(all_rows[0], rows)
    canonical_count = 0
    for case in CASES:
        for recipe, options in RECIPES.items():
            if options is None:
                continue
            name = f"{case}_{recipe}_canonical.json"
            projections = [json.loads((r / name).read_text(encoding="utf-8")) for r in runs]
            if any(p != projections[0] for p in projections[1:]):
                raise ValueError(f"proyección canónica no reproducible: {case}/{recipe}")
            canonical_count += 1
            scales = [
                json.loads((r / f"{case}_{recipe}_master_scale.json").read_text(encoding="utf-8"))
                for r in runs
            ]
            if any(value != scales[0] for value in scales[1:]):
                raise ValueError(f"escala maestra no reproducible: {case}/{recipe}")
    records, intervals = [], []
    for i, row in enumerate(all_rows[0]):
        item = {k: row[k] for k in ("case", "recipe", "status", "error")}
        item.update(
            row["metrics"],
            variables_finales=len(row["features"]),
            variables_entrada=len(row["input_features"]),
        )
        for key in ("fit_seconds", "apply_seconds", "report_seconds"):
            values = [r[i][key] for r in all_rows]
            item.update(
                {
                    f"{key}_median": float(np.median(values)),
                    f"{key}_min": min(values),
                    f"{key}_max": max(values),
                }
            )
        records.append(item)
        if row["recipe"] == "fabrica":
            continue
        case, recipe = row["case"], row["recipe"]
        baseline = pd.read_parquet(runs[0] / f"{case}_fabrica_predictions.parquet")
        candidate = pd.read_parquet(runs[0] / f"{case}_{recipe}_predictions.parquet")
        if not baseline.y.equals(candidate.y):
            raise ValueError("etiquetas/orden exterior diferentes entre recetas")
        groups = pd.read_parquet(prepared / case / "groups.parquet").iloc[:, 0].loc[baseline.index]
        intervals.append(
            {
                "case": case,
                "recipe": recipe,
                **grouped_auc_difference(baseline.y, candidate.pd, baseline.pd, groups),
            }
        )
    dump(output / "metrics.json", records)
    pd.DataFrame(records).to_csv(output / "metrics.csv", index=False, float_format="%.17g")
    reread = pd.read_csv(output / "metrics.csv", float_precision="round_trip")
    if reread.astype(object).where(pd.notna(reread), None).to_dict(orient="records") != records:
        raise ValueError("CSV y JSON de métricas divergen")
    dump(output / "bootstrap.json", intervals)
    result = {
        "coverage": verify_coverage(all_rows[0]),
        "independent_processes": 3,
        "canonical_equal": canonical_count,
        "metrics_verified": len(records),
        "warming_included": False,
        "times": "pipeline sin informe / aplicación / informe; segundos",
        "scope": (
            "Cobertura parcial: German, Taiwan suplementario y dos sintéticos. "
            "R y LC/HC/PAKDD pendientes."
        ),
    }
    dump(output / "verification.json", result)
    return result
