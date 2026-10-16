"""Vistas de consumo del target, sin alterar los artefactos publicados (D-H10-3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from bayesrisk.core.study import Study


def canonical_target_frame(frame: pd.DataFrame, study: Study) -> pd.DataFrame:
    """Proyecta el target derivado sólo si falta el canónico y consta su procedencia.

    Model conserva el nombre que ya publicaba, también para calibraciones personalizadas y ML.
    Los consumidores canónicos reciben una copia; un artefacto inyectado ya canónico no requiere
    labels. Sin procedencia suficiente se conserva la entrada para que el consumidor rechace la
    columna ausente con su error habitual, sin adivinar etiquetas.
    """
    if "target" in frame.columns or not study.artifacts.has("data", "labels"):
        return frame
    labels = study.artifacts.get("data", "labels")
    target_col = getattr(labels, "target_col", None)
    if (
        not isinstance(target_col, str)
        or target_col in {"partition", "linear_predictor", "pd_raw", "label_status"}
        or target_col not in frame.columns
    ):
        return frame
    return frame.rename(columns={target_col: "target"}).copy(deep=True)
