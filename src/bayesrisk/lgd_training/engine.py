"""Ajuste fraccional experimental sobre train; evaluación descriptiva separada."""

from __future__ import annotations

import json
import warnings
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

from bayesrisk.lgd_training.exceptions import LgdTrainingError
from bayesrisk.lgd_training.model import LgdModel, numeric_matrix

if TYPE_CHECKING:
    import pandas as pd

    from bayesrisk.lgd_training.config import LgdTrainingConfig

DECLARATION_MISSING = "Declaración de población y objetivo no aportada"
DECLARATION_PRESENT = "Declaración aportada; suficiencia y temporalidad no verificadas"
APPLICATION_LIMIT = (
    "La aplicación no acredita independencia ni transportabilidad; no se reajustó LGD"
)
POPULATION_LIMIT = (
    "Procesos abiertos excluidos; representatividad y ausencia de sesgo de selección no demostradas"
)
ID_LIMIT = "Sin identificador de operación declarado: unicidad económica no verificada"


def declaration(governance: Any) -> tuple[str, str]:
    """Transporta el texto institucional sin juzgar su suficiencia."""
    if isinstance(governance, dict):
        from bayesrisk.governance.config import GovernanceConfig

        governance = GovernanceConfig.model_validate(governance)
    if governance is None or not governance.assumptions:
        return "not_provided", "No aportada"
    return "provided_unverified", "\n".join(
        (
            "Propósito: " + governance.purpose,
            "Supuestos: " + "; ".join(governance.assumptions),
            "Limitaciones: " + ("; ".join(governance.limitations) or "No aportadas"),
        )
    )


def declaration_lines(model: LgdModel) -> tuple[str, ...]:
    """Una fuente legible para card, resumen, informe y export."""
    if model.declaration_status == "not_provided":
        return (DECLARATION_MISSING,)
    return (DECLARATION_PRESENT, model.declaration_text)


def fit_history(
    frame: pd.DataFrame,
    cfg: LgdTrainingConfig,
    *,
    provenance: dict[str, str],
    id_columns: tuple[str, ...] = (),
    index_name: str | None = None,
) -> dict[str, Any]:
    """Valida toda identidad antes de excluir; ajusta sólo train sin fallback."""
    import numpy as np
    import pandas as pd

    try:
        import statsmodels.api as sm
    except ImportError as exc:
        from bayesrisk.core.exceptions import MissingDependencyError

        raise MissingDependencyError(
            'Entrenar LGD requiere statsmodels: instala `pip install "bayesrisk[scoring]"`.'
        ) from exc

    if not frame.columns.is_unique or not frame.index.is_unique:
        raise LgdTrainingError("La historia LGD exige columnas e índice técnico únicos.")
    roles = (cfg.target_col, cfg.entity_col, cfg.sample_col, cfg.default_col, cfg.resolved_col)
    missing = set((*roles, *cfg.covariate_cols, *id_columns)) - set(frame.columns)
    if missing:
        raise LgdTrainingError(f"Faltan columnas declaradas de historia LGD: {sorted(missing)}.")
    if id_columns and (
        frame[list(id_columns)].isna().any().any() or frame.duplicated(list(id_columns)).any()
    ):
        raise LgdTrainingError(
            "El ID de operación debe ser no nulo y único, también entre filas excluidas."
        )
    if index_name is not None and (frame.index.name != index_name or frame.index.hasnans):
        raise LgdTrainingError("El índice declarado de operaciones no coincide o contiene nulos.")
    entity = frame[cfg.entity_col]
    if entity.isna().any():
        raise LgdTrainingError("La entidad de separación no puede ser nula, incluso en excluidas.")
    sample = frame[cfg.sample_col]
    if not sample.isin(["train", "evaluation", "excluded"]).all():
        raise LgdTrainingError("La muestra LGD exige train, evaluation o excluded, sin nulos.")
    flags = []
    for name in (cfg.default_col, cfg.resolved_col):
        values = frame[name]
        valid = values.map(
            lambda x: (
                isinstance(x, (bool, np.bool_, int, np.integer, float, np.floating)) and x in (0, 1)
            )
        )
        if not valid.all():
            raise LgdTrainingError(f"La marca {name!r} exige booleanos o 0/1, sin nulos ni texto.")
        flags.append(values.eq(1))
    default, resolved = flags
    eligible = default & resolved & sample.ne("excluded")
    train, evaluation = eligible & sample.eq("train"), eligible & sample.eq("evaluation")
    if not train.any() or not evaluation.any():
        raise LgdTrainingError(
            f"LGD exige train y evaluation elegibles no vacíos: "
            f"{int(train.sum())} y {int(evaluation.sum())}."
        )
    overlap = set(entity[train]) & set(entity[evaluation])
    if overlap:
        raise LgdTrainingError(
            f"Hay {len(overlap)} entidades entre train y evaluation; "
            f"ejemplos: {list(map(str, sorted(overlap, key=str)))[:5]}."
        )
    chosen = frame.loc[eligible]
    x = numeric_matrix(chosen, cfg.covariate_cols)
    y = numeric_matrix(chosen, (cfg.target_col,))[:, 0]
    if ((y < 0) | (y > 1)).any():
        raise LgdTrainingError("La LGD observada elegible debe estar entre cero y uno.")
    chosen_train = sample.loc[eligible].eq("train").to_numpy()
    x_train = np.column_stack([np.ones(int(train.sum())), x[chosen_train]])
    y_train = y[chosen_train]
    if len(y_train) <= x_train.shape[1] or np.linalg.matrix_rank(x_train) != x_train.shape[1]:
        raise LgdTrainingError(
            "El ajuste LGD exige más filas que parámetros y matriz de rango completo."
        )
    if np.ptp(y_train) == 0:
        raise LgdTrainingError(
            "El objetivo LGD de entrenamiento es constante; no se publica predictor."
        )
    try:
        with warnings.catch_warnings(record=True) as observed_warnings:
            warnings.simplefilter("always")
            fit = sm.GLM(y_train, x_train, family=sm.families.Binomial()).fit()
        if observed_warnings:
            raise LgdTrainingError(
                "El ajuste LGD emitió advertencias: "
                + "; ".join(str(w.message) for w in observed_warnings)
            )
        if not fit.converged or not np.isfinite(fit.params).all():
            raise LgdTrainingError("El ajuste LGD no convergió a coeficientes finitos.")
    except LgdTrainingError:
        raise
    except Exception as exc:
        raise LgdTrainingError(
            "Falló el ajuste fraccional LGD; revisa soporte y rango de la historia."
        ) from exc
    model = LgdModel(
        features=cfg.covariate_cols,
        intercept=float(fit.params[0]),
        coefficients=tuple(float(c) for c in fit.params[1:]),
        fit_environment=json.dumps(
            {k: version(k) for k in ("statsmodels", "numpy", "pandas", "scipy")}, sort_keys=True
        ),
        **provenance,
    )
    pred = model.predict(chosen).lgd.to_numpy()
    predictions = pd.DataFrame(
        {
            "row_id": chosen.index,
            "sample": sample[eligible].to_numpy(),
            "observed_lgd": y,
            "predicted_lgd": pred,
        },
        index=chosen.index,
    )
    for number, column in enumerate(id_columns, 1):
        name = "operation_id" if len(id_columns) == 1 else f"operation_id_{number}"
        predictions[name] = chosen[column].to_numpy()
    diagnostics = []
    baseline = float(y_train.mean())
    for label in ("train", "evaluation"):
        mask = sample[eligible].eq(label).to_numpy()
        observed = y[mask]
        for kind, estimates in (
            ("fitted", pred[mask]),
            ("train_mean", np.full(mask.sum(), baseline)),
        ):
            error = estimates - observed
            diagnostics.append(
                {
                    "sample": label,
                    "predictor": kind,
                    "n": len(observed),
                    "observed_mean": float(observed.mean()),
                    "predicted_mean": float(estimates.mean()),
                    "bias": float(error.mean()),
                    "mae": float(np.abs(error).mean()),
                    "rmse": float(np.sqrt(np.mean(error**2))),
                }
            )
    # Motivos mutuamente excluyentes con prioridad explícita; flags y nulos se cuentan aparte.
    reasons = np.select(
        [sample.eq("excluded"), ~default, ~resolved],
        ["declared_excluded", "not_default", "unresolved"],
        default="eligible",
    )
    population_input = pd.DataFrame(
        {
            "sample": sample,
            "default": default,
            "resolved": resolved,
            "reason": reasons,
            "missing_target": frame[cfg.target_col].isna(),
            "missing_features": frame[list(cfg.covariate_cols)].isna().any(axis=1),
        }
    )
    population = (
        population_input.groupby(
            ["sample", "default", "resolved", "reason", "missing_target", "missing_features"],
            dropna=False,
            sort=True,
        )
        .size()
        .rename("n")
        .reset_index()
    )
    notes = (*declaration_lines(model), POPULATION_LIMIT)
    if not id_columns and index_name is None:
        notes += (ID_LIMIT,)
    card = {
        "method": "fractional_response",
        "converged": True,
        "n_train": int(train.sum()),
        "n_evaluation": int(evaluation.sum()),
        "n_excluded": int((~eligible).sum()),
        "n_rows": len(frame),
        "features": list(cfg.covariate_cols),
        "baseline_train_mean": baseline,
        "provenance": {**provenance, "fit_environment": model.fit_environment},
        "warnings": list(notes),
        "effective_config": cfg.model_dump(mode="json"),
        "metric_sections": {},
    }
    return {
        "fitted_model": model,
        "model_table": model.to_frame(),
        "predictions": predictions,
        "evaluation": pd.DataFrame(diagnostics),
        "population": population,
        "card": card,
    }
