"""Tres referentes con recetas congeladas; ajustan únicamente Desarrollo."""

from __future__ import annotations

import time

import pandas as pd
from sklearn.linear_model import LogisticRegression

from .contract import SEED
from .isolation import FitAudit


def fit_reference(
    name: str,
    dev: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    target: str,
    audit: FitAudit,
) -> dict:
    """Devuelve predicciones indexadas y tablas, sin fabricar un Study de un tercero."""
    x, y, z = dev[features], dev[target], test[features]
    if not dev.index.is_unique or set(dev.index).intersection(test.index):
        raise ValueError("Desarrollo/evaluación se solapan")
    cats = list(x.select_dtypes(include=["object", "category", "string"]).columns)
    started = time.perf_counter()
    estimator = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000, random_state=SEED)
    if name == "optbinning_mip":
        from optbinning import BinningProcess, Scorecard

        process = BinningProcess(
            variable_names=features,
            categorical_variables=cats,
            max_n_bins=6,
            min_bin_size=0.05,
            binning_fit_params={
                f: {"monotonic_trend": "auto_asc_desc", "solver": "mip"} for f in features
            },
        )
        model = Scorecard(
            binning_process=process,
            estimator=estimator,
            scaling_method="pdo_odds",
            scaling_method_params={"pdo": 20, "odds": 50, "scorecard_points": 600},
        )
        model.fit(x, y)
        fit_seconds = time.perf_counter() - started
        audit.applying = True
        applied = time.perf_counter()
        probability, reference = model.predict_proba(z)[:, 1], model.predict_proba(x)[:, 1]
        apply_seconds = time.perf_counter() - applied
        tables = {"card": model.table(style="detailed")}
        statuses = {f: model.binning_process_.get_binned_variable(f).status for f in features}
        if any(s != "OPTIMAL" for s in statuses.values()):
            raise ValueError(f"solver no óptimo: {statuses}")
        features_final = features
    elif name == "scorecardpy":
        import scorecardpy as sc

        bins = sc.woebin(
            dev[[*features, target]].reset_index(drop=True),
            y=target,
            x=features,
            positive="1",
            print_step=0,
            no_cores=1,
        )
        a = sc.woebin_ply(x.reset_index(drop=True), bins, print_step=0)
        estimator.fit(a, y)
        fit_seconds = time.perf_counter() - started
        audit.applying = True
        applied = time.perf_counter()
        b = sc.woebin_ply(z.reset_index(drop=True), bins, print_step=0)
        probability, reference = estimator.predict_proba(b)[:, 1], estimator.predict_proba(a)[:, 1]
        apply_seconds = time.perf_counter() - applied
        tables = sc.scorecard(bins, estimator, a.columns, points0=600, odds0=50, pdo=20)
        statuses = {"solver": "tree; sin optimizador MIP"}
        features_final = list(bins)
        model = estimator
    elif name == "skorecard_mip":
        from sklearn.pipeline import make_pipeline
        from skorecard import Skorecard
        from skorecard.bucketers import (
            DecisionTreeBucketer,
            OptimalBucketer,
            OrdinalCategoricalBucketer,
        )
        from skorecard.pipeline import BucketingProcess
        from skorecard.rescale import ScoreCardPoints

        nums = [f for f in features if f not in cats]
        pre = make_pipeline(
            DecisionTreeBucketer(variables=nums, max_n_bins=100, random_state=SEED),
            OrdinalCategoricalBucketer(variables=cats, tol=0.01),
        )
        coarse = make_pipeline(
            OptimalBucketer(variables=nums, max_n_bins=6, min_bin_size=0.05, solver="mip"),
            OptimalBucketer(
                variables=cats,
                variables_type="categorical",
                max_n_bins=6,
                min_bin_size=0.05,
                solver="mip",
            ),
        )
        model = Skorecard(
            bucketing=BucketingProcess(prebucketing_pipeline=pre, bucketing_pipeline=coarse),
            random_state=SEED,
            lr_kwargs={"solver": "lbfgs", "max_iter": 1000, "penalty": None},
        )
        model.fit(x, y)
        fit_seconds = time.perf_counter() - started
        audit.applying = True
        applied = time.perf_counter()
        probability, reference = model.predict_proba(z)[:, 1], model.predict_proba(x)[:, 1]
        apply_seconds = time.perf_counter() - applied
        tables = {
            "card": ScoreCardPoints(
                model, pdo=20, ref_score=600, ref_odds=50
            ).get_scorecard_points()
        }
        statuses = {s["feature"]: s["status"] for s in audit.solvers}
        features_final = features
    else:
        raise ValueError(f"receta no admitida: {name}")
    return {
        "probability": pd.Series(probability, index=test.index),
        "reference": pd.Series(reference, index=dev.index),
        "tables": tables,
        "fit_seconds": fit_seconds,
        "apply_seconds": apply_seconds,
        "report_seconds": 0.0,
        "features": features_final,
        "solver_status": statuses,
        "model": model,
    }
