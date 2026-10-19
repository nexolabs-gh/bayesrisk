"""Sondas del arnés sobre muestras efectivas: no sustituyen cálculos ni defaults."""

from __future__ import annotations

import contextlib
import hashlib
import inspect
from collections import Counter
from unittest.mock import patch

import numpy as np
import pandas as pd


class FitAudit:
    """Rechaza filas/labels ajenas a Desarrollo y cualquier refit durante apply."""

    def __init__(self, dev: pd.DataFrame, target: str):
        self.index = dev.index.copy()
        self.dev = dev.copy(deep=True)
        self.target_name = target
        self.target = dev[target].to_numpy(copy=True)
        self.events: Counter = Counter()
        self.solvers: list[dict] = []
        self.applying = False
        self.reference_recipe = None
        self.reference_matrix = None
        self.stack = contextlib.ExitStack()

    def check(self, label: str, x, y=None, *, indexed: bool = True) -> None:
        """Comprueba muestra, orden, etiquetas y fase antes del ajuste efectivo."""
        if self.applying:
            raise ValueError(f"aislamiento: fit durante aplicación ({label})")
        if len(x) != len(self.index):
            raise ValueError(f"aislamiento: filas fuera de Desarrollo ({label})")
        if indexed and (not hasattr(x, "index") or not x.index.equals(self.index)):
            raise ValueError(f"aislamiento: índice/orden fuera de Desarrollo ({label})")
        if y is not None and not np.array_equal(np.asarray(y), self.target):
            raise ValueError(f"aislamiento: etiquetas/orden fuera de Desarrollo ({label})")
        self.events[label] += 1
        if label in {"binning", "reference_process"} and not x.equals(self.dev[x.columns]):
            raise ValueError(f"aislamiento: X cruda diferente de Desarrollo ({label})")

    def _guard(self, owner, name, label, x_name, y_name=None, *, returned=False, indexed=True):
        original = getattr(owner, name)
        signature = inspect.signature(original)

        def guarded(*args, **kwargs):
            bound = signature.bind(*args, **kwargs).arguments
            if not returned:
                self.check(label, bound[x_name], bound.get(y_name), indexed=indexed)
            result = original(*args, **kwargs)
            if returned:
                self.check(label, result)
                if "target_col" in bound:
                    self.check(label + "_target", result, result[bound["target_col"]])
            return result

        self.stack.enter_context(patch.object(owner, name, guarded))

    def __enter__(self):
        """Instala sondas temporales sin sustituir los cálculos originales."""
        from optbinning import OptimalBinning
        from sklearn.linear_model import LogisticRegression

        from bayesrisk.binning.transformer import WoEBinner
        from bayesrisk.calibration import calibrator
        from bayesrisk.model import estimator
        from bayesrisk.selection import selector

        self._guard(WoEBinner, "fit", "binning", "X", "y")
        self._guard(selector, "_development_frame", "selection", "frame", returned=True)
        self._guard(selector, "_apply_univariate_metrics", "selection_univariate", "dev", "target")
        self._guard(selector, "_apply_initial_filters", "selection_initial", "dev")
        self._guard(selector, "_correlation_matrix", "selection_correlation", "dev")
        self._guard(selector, "_apply_vif_filter", "selection_vif", "dev")
        self._guard(estimator, "_fit_statsmodels", "model", "frame", "target")
        original_anchor = calibrator._resolve_target_pd
        original_offset = calibrator._fit_intercept_offset

        def anchor(estimator, fit_frame, **kwargs):
            self.check("calibration", fit_frame, fit_frame[estimator.target_column])
            self.eta = fit_frame[estimator.linear_predictor_column].to_numpy()
            self.anchor = original_anchor(estimator, fit_frame, **kwargs)
            return self.anchor

        def offset(estimator, **kwargs):
            self.check("calibration_offset", kwargs["eta_dev"], indexed=False)
            if (
                not np.array_equal(kwargs["eta_dev"], self.eta)
                or kwargs["target_pd"] != self.anchor
            ):
                raise ValueError("aislamiento: offset usa predictor/ancla diferente de Desarrollo")
            return original_offset(estimator, **kwargs)

        self.stack.enter_context(patch.object(calibrator, "_resolve_target_pd", anchor))
        self.stack.enter_context(patch.object(calibrator, "_fit_intercept_offset", offset))
        original_logistic = LogisticRegression.fit

        def logistic(model, X, y, *args, **kwargs):  # noqa: N803 — firma de sklearn
            self.check("reference_logistic", X, y, indexed=False)
            if isinstance(X, pd.DataFrame):
                expected = (
                    pd.RangeIndex(len(self.index))
                    if self.reference_recipe == "scorecardpy"
                    else self.index
                )
                if not X.index.equals(expected):
                    raise ValueError(
                        "aislamiento: índice efectivo del referente logístico alterado"
                    )
            elif self.reference_recipe == "optbinning_mip":
                if self.reference_matrix is None or not np.array_equal(
                    X, self.reference_matrix, equal_nan=True
                ):
                    raise ValueError(
                        "aislamiento: matriz logística distinta a la transformación de Desarrollo"
                    )
            return original_logistic(model, X, y, *args, **kwargs)

        self.stack.enter_context(patch.object(LogisticRegression, "fit", logistic))
        original = OptimalBinning.fit

        def optimal(model, x, y, *args, **kwargs):
            self.check("optimal_binning", x, y, indexed=False)
            result = original(model, x, y, *args, **kwargs)
            self.solvers.append(
                {
                    "feature": model.name,
                    "status": model.status,
                    "solver": model.solver,
                    "mip_solver": model.mip_solver,
                    "time_limit": model.time_limit,
                }
            )
            if model.status != "OPTIMAL":
                raise ValueError(f"solver no óptimo: {model.name}={model.status}")
            return result

        self.stack.enter_context(patch.object(OptimalBinning, "fit", optimal))
        return self

    def references(self, recipe: str) -> None:
        """Instala las sondas propias del referente declarado."""
        self.reference_recipe = recipe
        if recipe == "optbinning_mip":
            from optbinning import BinningProcess

            self._guard(BinningProcess, "fit", "reference_process", "X", "y")
            original = BinningProcess.transform

            def transform(model, X, *args, **kwargs):  # noqa: N803 — firma de OptBinning
                result = original(model, X, *args, **kwargs)
                if not self.applying:
                    self.check("reference_transform", X)
                    if not X.equals(self.dev[X.columns]):
                        raise ValueError("aislamiento: transformación de X ajena a Desarrollo")
                    self.reference_matrix = np.array(result, copy=True)
                return result

            self.stack.enter_context(patch.object(BinningProcess, "transform", transform))
        elif recipe == "skorecard_mip":
            from category_encoders import WOEEncoder
            from skorecard.bucketers.base_bucketer import BaseBucketer

            self._guard(BaseBucketer, "fit", "reference_bucketing", "X", "y")
            self._guard(WOEEncoder, "fit", "reference_woe", "X", "y")
        elif recipe == "scorecardpy":
            import scorecardpy

            original = scorecardpy.woebin

            def woebin(dt, *args, **kwargs):
                self.check("reference_woebin", dt, dt[kwargs["y"]], indexed=False)
                if not dt.equals(self.dev[dt.columns].reset_index(drop=True)):
                    raise ValueError(
                        "aislamiento: correspondencia RangeIndex de scorecardpy alterada"
                    )
                return original(dt, *args, **kwargs)

            self.stack.enter_context(patch.object(scorecardpy, "woebin", woebin))

    def verify_solvers(self) -> None:
        """Un resultado no óptimo nunca queda oculto por una exclusión posterior."""
        if any(s["status"] != "OPTIMAL" or s["solver"] != "mip" for s in self.solvers):
            raise ValueError(
                "solver no óptimo/MIP: no se oculta aunque el consumidor omita la variable"
            )

    def result(self, recipe: str, features: list[str]) -> dict:
        """Exige las sondas y estados esperados antes de acreditar aislamiento."""
        self.verify_solvers()
        required = (
            {
                "binning",
                "selection",
                "selection_univariate",
                "selection_initial",
                "selection_correlation",
                "selection_vif",
                "model",
                "calibration",
                "calibration_offset",
            }
            if recipe not in {"optbinning_mip", "skorecard_mip", "scorecardpy"}
            else {"reference_logistic"}
        )
        if recipe == "skorecard_mip":
            required |= {"reference_bucketing", "reference_woe"}
        if recipe == "scorecardpy":
            required |= {"reference_woebin"}
        if recipe == "optbinning_mip":
            required |= {"reference_process", "reference_transform"}
        if not required <= self.events.keys():
            raise ValueError(f"aislamiento: sondas no ejercitadas: {required - self.events.keys()}")
        if recipe not in {"scorecardpy", "skorecard_mip", "optbinning_mip"} and not self.solvers:
            raise ValueError("aislamiento: ninguna sonda de solver bayesrisk ejercitada")
        if recipe in {"skorecard_mip", "optbinning_mip"} and (
            {s["feature"] for s in self.solvers} != set(features)
            or len(self.solvers) != len(features)
        ):
            raise ValueError("censo de solver diferente de predictores declarados")
        return {
            "rows": len(self.index),
            "index_sha256": hashlib.sha256(
                pd.util.hash_pandas_object(self.index).values.tobytes()
            ).hexdigest(),
            "effective_fit_calls": dict(self.events),
            "solvers": self.solvers,
            "apply_refits": 0,
        }

    def __exit__(self, *exc):
        """Restaura exactamente todas las funciones interceptadas."""
        return self.stack.__exit__(*exc)
