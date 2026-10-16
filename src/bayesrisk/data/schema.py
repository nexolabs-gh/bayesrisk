"""Validación declarativa de esquemas tabulares para la capa ``data`` (SDD-02 §4/§7).

``SchemaValidator`` traduce :class:`~bayesrisk.data.config.SchemaConfig` a un esquema pandera y
valida ``pandas.DataFrame`` con ``lazy=True`` para acumular todos los incumplimientos en un único
``DataValidationError`` de bayesrisk.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

from numbers import Integral
from typing import Any, Final

import pandas as pd
import pandera.pandas as pa

from bayesrisk.core.audit import AuditSink
from bayesrisk.core.exceptions import DataValidationError
from bayesrisk.data.config import ColumnSpec, SchemaConfig

__all__ = ["SchemaValidator"]

_PANDERA_DTYPES: Final[dict[str, str]] = {
    "int": "int64",
    "float": "float64",
    "str": "str",
    "bool": "bool",
    "category": "category",
    "datetime": "datetime64[ns]",
}


class SchemaValidator:
    """Valida columnas, tipos y reglas simples mediante pandera.

    ``index_col`` se interpreta como el nombre del índice pandas ya existente: el validador no
    ejecuta ``set_index`` ni consume una columna ordinaria con ese nombre. Si el identificador vive
    como columna, debe declararse como ``ColumnSpec`` o en ``unique_keys``; si vive en el índice,
    ``index_col`` exige que el índice tenga ese nombre y sea único.
    """

    def __init__(self, config: SchemaConfig | None = None) -> None:
        """Construye el validador con las reglas declarativas de ``SchemaConfig``."""
        self.config = config or SchemaConfig()

    @classmethod
    def from_config(cls, cfg: SchemaConfig) -> SchemaValidator:
        """Construye un validador desde ``DataConfig.schema_`` / ``SchemaConfig``."""
        return cls(cfg)

    def build_schema(self) -> pa.DataFrameSchema:
        """Traduce ``SchemaConfig`` al contrato imperativo de pandera.

        Returns
        -------
        pandera.pandas.DataFrameSchema
            Esquema con representaciones canónicas: ``int``→``int64``, ``float``→``float64``,
            ``str``→``str``, ``bool``→``bool``, ``category``→``category`` y
            ``datetime``→``datetime64[ns]``. Al validar sin coerción, los tipos lógicos numéricos
            conservan el ancho y la nulabilidad del dtype físico de entrada.
        """
        columns: dict[str, Any] = {}
        for spec in self.config.columns:
            columns[spec.name] = pa.Column(
                _dtype_for(spec),
                checks=_checks_for(spec),
                nullable=spec.nullable,
                coerce=spec.coerce,
                required=spec.required,
                unique=spec.unique,
            )

        return pa.DataFrameSchema(
            columns,
            strict=self.config.strict,
            ordered=self.config.ordered,
            unique=list(self.config.unique_keys) if self.config.unique_keys is not None else None,
            index=self._build_index(),
        )

    def validate(self, df: pd.DataFrame, *, audit: AuditSink | None = None) -> pd.DataFrame:
        """Valida ``df`` y devuelve el ``DataFrame`` resultante de pandera.

        Parameters
        ----------
        df : pandas.DataFrame
            Dataset a validar. No se muta in-place; si ``coerce=True`` pandera devuelve una copia
            con los tipos coaccionados.
        audit : AuditSink or None
            Reservado para la orquestación de ``DataStep``; la validación de esquema no emite
            decisiones todavía.

        Returns
        -------
        pandas.DataFrame
            ``DataFrame`` validado, posiblemente coaccionado según ``ColumnSpec.coerce``.

        Raises
        ------
        DataValidationError
            Si pandera detecta incumplimientos. El mensaje agrega todos los fallos de
            ``failure_cases`` **explicados en español**: qué columna falta, qué tipo se esperaba o
            qué regla se incumplió. Es copy público, así que **no** transporta los literales de
            ``pandera`` (``column_in_dataframe``, ``not_nullable``, ``in_range``) ni el vocabulario
            de su volcado — los lee un usuario, no quien desarrolla la librería.
        """
        del audit
        schema = self.build_schema()
        # build_schema conserva la última declaración de cada nombre, también aquí.
        specs = {spec.name: spec for spec in self.config.columns}
        for spec in specs.values():
            if spec.coerce or spec.name not in df.columns:
                continue
            dtypes = df.loc[:, [spec.name]].dtypes.tolist()
            if all(_compatible_numeric_dtype(spec, dtype) for dtype in dtypes):
                # SDD-02 declara tipos lógicos, no anchos. No convertir el frame: además de
                # perder rango/nulos, cambiar el dtype alteraría su data_hash (D-H10-3).
                # Pandera admite nombres repetidos: si sus anchos difieren, la comprobación
                # lógica anterior valida todos los tipos y Pandera conserva los demás checks.
                dtype = dtypes[0] if all(dtype == dtypes[0] for dtype in dtypes) else None
                schema = schema.update_column(spec.name, dtype=dtype)
        try:
            validated = schema.validate(df, lazy=True)
        except pa.errors.SchemaErrors as exc:
            raise DataValidationError(_format_schema_errors(exc)) from exc
        _validate_numeric_coercion(df, validated, specs)
        return validated

    def _build_index(self) -> Any | None:
        """Construye el índice pandera si ``index_col`` está declarado."""
        if self.config.index_col is None:
            return None
        return pa.Index(name=self.config.index_col, unique=True)


def _dtype_for(spec: ColumnSpec) -> str:
    """Devuelve el dtype pandera asociado al dtype lógico de una columna."""
    return _PANDERA_DTYPES[spec.dtype]


def _compatible_numeric_dtype(spec: ColumnSpec, dtype: Any) -> bool:
    return bool(
        (
            spec.dtype == "int"
            and pd.api.types.is_integer_dtype(dtype)
            and not pd.api.types.is_bool_dtype(dtype)
        )
        or (spec.dtype == "float" and pd.api.types.is_float_dtype(dtype))
    )


def _numeric_identity(value: Any) -> tuple[int, int] | float:
    """Valor exacto incluso para uint64 y floats de precisión extendida."""
    if isinstance(value, Integral):
        return (int(value), 1)
    try:
        return value.as_integer_ratio()  # type: ignore[no-any-return]
    except OverflowError:  # ±inf: el resto del contrato decide si se admite.
        return float(value)


def _validate_numeric_coercion(
    original: pd.DataFrame, validated: pd.DataFrame, specs: dict[str, ColumnSpec]
) -> None:
    """Una coerción declarada puede cambiar el tipo, nunca desbordar ni redondear el dato."""
    for spec in specs.values():
        if not spec.coerce or spec.dtype not in {"int", "float"} or spec.name not in original:
            continue
        origen = original.loc[:, [spec.name]]
        destino = validated.loc[:, [spec.name]]
        for position in range(len(origen.columns)):
            serie = origen.iloc[:, position]
            if not (
                pd.api.types.is_integer_dtype(serie.dtype)
                or pd.api.types.is_float_dtype(serie.dtype)
            ):
                continue
            for antes, despues in zip(
                serie.tolist(), destino.iloc[:, position].tolist(), strict=True
            ):
                if pd.isna(antes) and pd.isna(despues):
                    continue
                # Comparar escalares Python: numpy puede convertir uint64 a float durante == y
                # declarar iguales dos enteros distintos por encima de 2**53.
                if _numeric_identity(antes) != _numeric_identity(despues):
                    raise DataValidationError(
                        f"La coerción de «{spec.name}» a {spec.dtype} perdería valores; "
                        "conserve el tipo de origen y revise el esquema declarado."
                    )


def _checks_for(spec: ColumnSpec) -> list[Any]:
    """Construye los checks pandera derivados de cotas e inclusión declaradas."""
    checks: list[Any] = []
    if spec.ge is not None and spec.le is not None:
        checks.append(pa.Check.in_range(spec.ge, spec.le))
    elif spec.ge is not None:
        checks.append(pa.Check.ge(spec.ge))
    elif spec.le is not None:
        checks.append(pa.Check.le(spec.le))

    if spec.isin is not None:
        checks.append(pa.Check.isin(list(spec.isin)))
    return checks


def _format_schema_errors(exc: pa.errors.SchemaErrors) -> str:
    """Convierte ``failure_cases`` de pandera en un reporte accionable en español."""
    failure_cases = exc.failure_cases
    count = len(failure_cases.index)
    plural = "problema" if count == 1 else "problemas"
    header = f"El dataset no cumple el esquema declarado en data.schema ({count} {plural}):"
    rows = [_format_failure_row(row) for row in failure_cases.to_dict(orient="records")]
    return "\n".join([header, *rows])


#: Traducción de los ``check`` de pandera a lo que le pasa al dato, en el idioma del lector.
#:
#: El literal crudo es jerga de la librería —``column_in_dataframe``, ``not_nullable``,
#: ``coerce_dtype('int64')``— y viajaba tal cual al panel de la UI, que es copy público. **Las
#: claves se midieron**, no se dedujeron: se provocó cada fallo contra `pandera` y se leyó el
#: literal que emite (dos lotes, 2026-07-29). Lo que no esté aquí conserva su literal: perder
#: información sería peor que mostrarla fea, y el prefijo antes del paréntesis cubre las familias
#: parametrizadas (``in_range(0, 10)``, ``isin([...])``) sin repetir sus argumentos.
_EXPLICACION_DEL_CHECK: dict[str, str] = {
    "column_in_dataframe": "el dataset no la trae, y el esquema la declara obligatoria",
    "column_in_schema": "el dataset la trae y el esquema no la declara (data.schema.strict)",
    "not_nullable": "tiene valores vacíos y se declaró que no los admite",
    "field_uniqueness": "tiene valores repetidos y se declaró única",
    "multiple_fields_uniqueness": "la combinación de llaves de unicidad se repite",
    "dtype": "su tipo de dato no es el declarado",
    "coerce_dtype": "su valor no se pudo convertir al tipo declarado",
    "field_name": "el índice no se llama como el esquema espera",
    "in_range": "queda fuera del rango declarado",
    "greater_than_or_equal_to": "es menor que el mínimo declarado",
    "less_than_or_equal_to": "es mayor que el máximo declarado",
    "isin": "no es ninguno de los valores admitidos",
}


def _explicacion(check: str) -> str:
    """Qué le pasa al dato, en español; el literal crudo si el check no está traducido."""
    directa = _EXPLICACION_DEL_CHECK.get(check)
    if directa is not None:
        return directa
    # Los checks parametrizados llegan como `in_range(0, 10)`: la familia manda, no sus argumentos,
    # que ya viajan en el propio literal y no hace falta repetir.
    familia, _, _ = check.partition("(")
    return _EXPLICACION_DEL_CHECK.get(familia, f"no cumple «{check}»")


def _format_failure_row(row: dict[Any, Any]) -> str:
    """Formatea una fila de ``failure_cases`` como una frase, no como un volcado de pandera."""
    column = _column_label(row)
    check = row.get("check")
    explicacion = _explicacion(check) if isinstance(check, str) else "no cumple el esquema"

    detalle = ""
    failure_case = row.get("failure_case")
    if not _is_missing(failure_case) and _format_value(failure_case) != column:
        detalle = f" (valor: {_format_value(failure_case)}"
        index = row.get("index")
        detalle += f", fila {_format_value(index)})" if not _is_missing(index) else ")"

    return f"- «{column}»: {explicacion}{detalle}."


def _column_label(row: dict[Any, Any]) -> str:
    """Obtiene una columna legible incluso para fallos de esquema a nivel DataFrame."""
    column = row.get("column")
    if not _is_missing(column):
        return _format_value(column)

    failure_case = row.get("failure_case")
    if not _is_missing(failure_case):
        return _format_value(failure_case)

    schema_context = row.get("schema_context")
    if not _is_missing(schema_context):
        return _format_value(schema_context)
    return "<dataframe>"


def _format_value(value: Any) -> str:
    """Normaliza valores de pandera/pandas a texto estable para el reporte."""
    if _is_missing(value):
        return "<sin valor>"
    return str(value)


def _is_missing(value: Any) -> bool:
    """Detecta escalares nulos sin romper con listas/arrays devueltos por pandera."""
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(result, bool):
        return result
    return False
