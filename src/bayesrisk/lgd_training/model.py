"""Predictor LGD experimental inmutable y transporte tabular cerrado, formato 1.

La procedencia identifica el ajuste; no autentica al autor ni certifica su población.
Ningún texto del transporte se evalúa como fórmula, ruta, import o clase Python.
"""

from __future__ import annotations

import base64
import binascii
import io
import math
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from bayesrisk.lgd_training.exceptions import LgdTrainingError

if TYPE_CHECKING:
    import pandas as pd

MODEL_COLUMNS: Final = (
    "format_version",
    "method",
    "position",
    "term_kind",
    "feature",
    "coefficient",
    "source_config_hash",
    "source_data_hash",
    "source_run_id",
    "fit_environment",
    "declaration_status",
    "declaration_text",
)
_ENCODED: Final = ("feature", "source_run_id", "fit_environment", "declaration_text")
_NOMINAL: Final = tuple(
    c for c in MODEL_COLUMNS if c not in {"format_version", "position", "coefficient"}
)
_HASH: Final = re.compile(r"[0-9a-f]{64}\Z")
_TEXT: Final = re.compile(r"text:[A-Za-z0-9_-]*\Z")


def _encode(value: str) -> str:
    return "text:" + base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode(value: Any) -> str:
    if not isinstance(value, str) or _TEXT.fullmatch(value) is None:
        raise LgdTrainingError("La tabla del modelo exige texto codificado canónico (text:).")
    raw = value[5:]
    try:
        decoded = base64.b64decode(
            raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True
        ).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeError) as exc:
        raise LgdTrainingError(
            "Texto del modelo inválido: exige base64url y UTF-8 estrictos."
        ) from exc
    if _encode(decoded) != value:
        raise LgdTrainingError("La codificación de texto del modelo no es canónica.")
    return decoded


@dataclass(frozen=True, slots=True)
class LgdModel:
    """Media fraccional congelada; predict nunca ajusta ni lee un objetivo.

    **Experimental (fuera de la garantía SemVer 2.x).**
    """

    features: tuple[str, ...]
    intercept: float
    coefficients: tuple[float, ...]
    source_config_hash: str
    source_data_hash: str
    source_run_id: str
    fit_environment: str
    declaration_status: str
    declaration_text: str

    def __post_init__(self) -> None:
        """Exige estado inmutable y procedencia declarativa antes de cualquier uso."""
        if (
            not isinstance(self.features, tuple)
            or not self.features
            or any(
                not isinstance(c, str) or not c.strip() or c == "__intercept__"
                for c in self.features
            )
            or len(set(self.features)) != len(self.features)
        ):
            raise LgdTrainingError(
                "El modelo exige nombres de covariables únicos, no vacíos y no reservados."
            )
        if not isinstance(self.coefficients, tuple) or len(self.coefficients) != len(self.features):
            raise LgdTrainingError("El modelo exige un coeficiente por covariable.")
        if any(
            type(c) is not float or not math.isfinite(c)
            for c in (self.intercept, *self.coefficients)
        ):
            raise LgdTrainingError("Los coeficientes del modelo deben ser float finitos.")
        for name in ("source_config_hash", "source_data_hash"):
            value = getattr(self, name)
            if not isinstance(value, str) or _HASH.fullmatch(value) is None:
                raise LgdTrainingError(
                    f"La procedencia {name} exige una huella hexadecimal de 64 caracteres."
                )
        for name in ("source_run_id", "fit_environment", "declaration_text"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise LgdTrainingError(f"La procedencia {name} exige texto no vacío.")
        if self.declaration_status not in {"not_provided", "provided_unverified"}:
            raise LgdTrainingError("Estado de declaración del modelo desconocido.")
        if self.declaration_status == "not_provided" and self.declaration_text != "No aportada":
            raise LgdTrainingError(
                "Una declaración ausente debe conservar el marcador No aportada."
            )

    def validated(self) -> LgdModel:
        """Revalida también objetos recuperados desde un Study confiado por la persona."""
        if type(self) is not LgdModel:
            raise LgdTrainingError("Se admite exclusivamente el predictor LgdModel de formato 1.")
        return LgdModel(**{f.name: getattr(self, f.name) for f in fields(self)})

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Aplica por nombres de covariable; conserva índice y omite columnas adicionales."""
        import numpy as np
        import pandas as pd
        from scipy.special import expit

        model = self.validated()
        x = numeric_matrix(frame, model.features)
        with np.errstate(over="ignore", invalid="ignore"):
            linear = model.intercept + x @ np.asarray(model.coefficients)
        if not np.isfinite(linear).all():
            raise LgdTrainingError("La aplicación del modelo produjo valores no finitos.")
        predicted = expit(linear)
        if not np.isfinite(predicted).all() or ((predicted < 0) | (predicted > 1)).any():
            raise LgdTrainingError("La predicción LGD no es finita o está fuera de [0,1].")
        return pd.DataFrame({"lgd": predicted}, index=frame.index.copy())

    def to_frame(self) -> pd.DataFrame:
        """Tabla de transporte canónica; no es la presentación legible del informe."""
        import pandas as pd

        model = self.validated()
        rows = []
        for i, (feature, coefficient) in enumerate(
            zip(
                ("__intercept__", *model.features),
                (model.intercept, *model.coefficients),
                strict=True,
            )
        ):
            row = {
                "format_version": 1,
                "method": "fractional_response",
                "position": i,
                "term_kind": "intercept" if i == 0 else "feature",
                "feature": feature,
                "coefficient": coefficient,
                **{k: getattr(model, k) for k in MODEL_COLUMNS[6:]},
            }
            for name in _ENCODED:
                row[name] = _encode(str(row[name]))
            rows.append(row)
        return pd.DataFrame(rows, columns=MODEL_COLUMNS)

    @classmethod
    def from_frame(cls, table: pd.DataFrame) -> LgdModel:
        """Rechaza campos/versiones ajenos; construye un DTO fijo sólo tras validar la tabla."""
        import numpy as np
        import pandas as pd

        if (
            not isinstance(table, pd.DataFrame)
            or not table.columns.is_unique
            or set(table.columns) != set(MODEL_COLUMNS)
            or len(table) < 2
            or table.isna().any().any()
        ):
            raise LgdTrainingError(
                "La tabla del modelo exige las columnas exactas del formato 1 "
                "y al menos una covariable."
            )
        for name in ("format_version", "position"):
            if not pd.api.types.is_integer_dtype(table[name]) or pd.api.types.is_bool_dtype(
                table[name]
            ):
                raise LgdTrainingError(f"La columna {name} del modelo debe contener enteros.")
        if (
            not (table.format_version == 1).all()
            or not (table.method == "fractional_response").all()
        ):
            raise LgdTrainingError("Versión o método desconocido en la tabla del modelo.")
        if (
            table.coefficient.dtype != np.dtype("float64")
            or not np.isfinite(table.coefficient.to_numpy()).all()
        ):
            raise LgdTrainingError("Los coeficientes del modelo exigen float64 finitos.")
        ordered = table.sort_values("position").reset_index(drop=True).copy(deep=True)
        if list(ordered.position) != list(range(len(ordered))):
            raise LgdTrainingError(
                "Las posiciones del modelo deben ser únicas y contiguas desde cero."
            )
        for name in _NOMINAL:
            if not ordered[name].map(lambda x: isinstance(x, str)).all():
                raise LgdTrainingError(f"La columna nominal {name} exige texto sin nulos.")
        for name in MODEL_COLUMNS[6:]:
            if ordered[name].nunique(dropna=False) != 1:
                raise LgdTrainingError(f"Metadatos inconsistentes en {name}.")
        for name in _ENCODED:
            ordered[name] = ordered[name].map(_decode)
        if (
            list(ordered.term_kind) != ["intercept", *(["feature"] * (len(ordered) - 1))]
            or ordered.feature.iloc[0] != "__intercept__"
        ):
            raise LgdTrainingError(
                "La tabla debe comenzar con el intercepto y continuar con covariables."
            )
        return cls(
            features=tuple(ordered.feature.iloc[1:]),
            intercept=float(ordered.coefficient.iloc[0]),
            coefficients=tuple(float(c) for c in ordered.coefficient.iloc[1:]),
            **{k: str(ordered[k].iloc[0]) for k in MODEL_COLUMNS[6:]},
        )


def numeric_matrix(frame: pd.DataFrame, columns: tuple[str, ...]) -> Any:
    """Matriz numérica finita sin coerción textual ni mutación del frame."""
    import numpy as np
    import pandas as pd

    if (
        not isinstance(frame, pd.DataFrame)
        or not frame.columns.is_unique
        or not frame.index.is_unique
    ):
        raise LgdTrainingError("LGD exige columnas e índice técnico únicos.")
    for name in columns:
        if name not in frame:
            raise LgdTrainingError(f"Falta la covariable {name!r} requerida por el modelo LGD.")
        if not pd.api.types.is_numeric_dtype(frame[name]) or pd.api.types.is_complex_dtype(
            frame[name]
        ):
            raise LgdTrainingError(
                f"La covariable {name!r} debe ser numérica, sin codificación automática."
            )
    matrix = frame.loc[:, list(columns)].to_numpy(dtype="float64", na_value=np.nan)
    if not np.isfinite(matrix).all():
        raise LgdTrainingError("Las covariables LGD deben ser finitas y no contener nulos.")
    return matrix


def read_model_table(source: str | Path | bytes, *, file_format: str | None = None) -> pd.DataFrame:
    """Lector especializado compartido por código y HTTP, sin inferencia nominal ni pickle."""
    import pandas as pd

    if isinstance(source, bytes):
        stream: Any = io.BytesIO(source)
        suffix = file_format
    else:
        path = Path(source)
        suffix = file_format or path.suffix.lstrip(".").lower()
        stream = path
    nominal = {c: str for c in _NOMINAL}
    types: dict[str, Any] = {
        **nominal,
        "format_version": str,
        "position": str,
        "coefficient": "float64",
    }
    try:
        if suffix == "csv":
            table = pd.read_csv(
                stream, dtype=cast(Any, types), keep_default_na=False, float_precision="round_trip"
            )
        elif suffix == "xlsx":
            table = pd.read_excel(stream, dtype=types, keep_default_na=False)
        elif suffix == "parquet":
            table = pd.read_parquet(stream)
        else:
            raise LgdTrainingError("El modelo sólo admite una tabla CSV, XLSX o Parquet.")
        if suffix in {"csv", "xlsx"}:
            # Un cast directo de Excel float→int truncaría una posición fraccionaria. Exigir
            # representación decimal entera antes de convertir preserva el esquema cerrado.
            for name in ("format_version", "position"):
                if not table[name].str.fullmatch(r"0|[1-9][0-9]*").all():
                    raise LgdTrainingError(f"La columna {name} exige enteros sin truncamiento.")
                table[name] = table[name].astype("int64")
        return LgdModel.from_frame(table).to_frame()
    except LgdTrainingError:
        raise
    except Exception as exc:
        raise LgdTrainingError(
            "No se pudo leer una tabla LGD válida; no se admiten objetos serializados."
        ) from exc
