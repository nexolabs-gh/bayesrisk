"""Tests de ``SchemaValidator`` (SDD-02 §4/§7): pandera, errores lazy y coerción."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from bayesrisk.core.exceptions import DataValidationError
from bayesrisk.data import schema as schema_module
from bayesrisk.data.config import ColumnSpec, SchemaConfig
from bayesrisk.data.schema import SchemaValidator


def _cfg(*columns: ColumnSpec, **kwargs: object) -> SchemaConfig:
    return SchemaConfig(columns=columns, **kwargs)


@pytest.mark.parametrize("coerce", [False, True])
def test_columnas_repetidas_validas_conservan_contrato(coerce: bool) -> None:
    frame = pd.DataFrame([[1, 2], [3, 4]], columns=["x", "x"], dtype="int64")
    validador = SchemaValidator(_cfg(ColumnSpec(name="x", dtype="int", coerce=coerce)))
    assert_frame_equal(validador.validate(frame), frame)


@pytest.mark.parametrize("coerce", [False, True])
def test_ultima_declaracion_del_schema_es_la_efectiva(coerce: bool) -> None:
    frame = pd.DataFrame({"x": [1, 2]})
    validador = SchemaValidator(
        _cfg(ColumnSpec(name="x", dtype="int"), ColumnSpec(name="x", dtype="float", coerce=coerce))
    )
    if coerce:
        assert_frame_equal(validador.validate(frame), frame.astype("float64"))
    else:
        with pytest.raises(DataValidationError):
            validador.validate(frame)


def test_columnas_repetidas_con_distintos_anchos_conservan_todas_las_reglas() -> None:
    frame = pd.concat([pd.Series([1, 2], dtype="int32"), pd.Series([3, 4], dtype="uint64")], axis=1)
    frame.columns = ["x", "x"]
    cfg = _cfg(ColumnSpec(name="x", dtype="int", ge=0, le=4, nullable=False))
    assert_frame_equal(SchemaValidator(cfg).validate(frame), frame)
    frame.iloc[0, 1] = 5
    with pytest.raises(DataValidationError, match="rango"):
        SchemaValidator(cfg).validate(frame)


def test_coercion_no_oculta_perdida_de_precision_extendida() -> None:
    if np.finfo(np.longdouble).eps == np.finfo(np.float64).eps:
        pytest.skip("longdouble no ofrece precisión adicional en esta plataforma")
    frame = pd.DataFrame({"x": [np.nextafter(np.longdouble(1), np.longdouble(2))]})
    with pytest.raises(DataValidationError, match="perdería valores"):
        SchemaValidator(_cfg(ColumnSpec(name="x", dtype="float", coerce=True))).validate(frame)


def test_coercion_exacta_con_filtro_de_columnas_extra() -> None:
    frame = pd.DataFrame({"extra": [9, 8], "x": [1, 2]})
    cfg = _cfg(ColumnSpec(name="x", dtype="float", coerce=True), strict="filter")
    assert_frame_equal(SchemaValidator(cfg).validate(frame), frame[["x"]].astype("float64"))


def test_coercion_revisa_cada_columna_repetida() -> None:
    frame = pd.DataFrame([[1, 2**64 - 1]], columns=["x", "x"], dtype="uint64")
    with pytest.raises(DataValidationError, match="perdería valores"):
        SchemaValidator(_cfg(ColumnSpec(name="x", dtype="int", coerce=True))).validate(frame)


@pytest.mark.parametrize("dtype", ["object", "category"])
@pytest.mark.parametrize("valor,logico", [(1.5, "int"), (2**53 + 1, "float")])
def test_coercion_de_escalares_numericos_no_pierde_valores(
    dtype: str, valor: int | float, logico: str
) -> None:
    frame = pd.DataFrame({"x": pd.Series([valor], dtype=dtype)})
    original = frame.copy(deep=True)
    with pytest.raises(DataValidationError, match="perdería valores"):
        SchemaValidator(_cfg(ColumnSpec(name="x", dtype=logico, coerce=True))).validate(frame)
    assert_frame_equal(frame, original)


@pytest.mark.parametrize("dtype", ["object", "category"])
@pytest.mark.parametrize(
    "valores,logico,final",
    [
        ([1, 2], "int", "int64"),
        ([1.25, 2.5], "float", "float64"),
        (["1", "2"], "int", "int64"),
        (["0.1", "2.5"], "float", "float64"),
    ],
)
def test_coercion_exacta_de_objetos_y_parseo_de_texto_se_conservan(
    dtype: str, valores: list[object], logico: str, final: str
) -> None:
    frame = pd.DataFrame({"x": pd.Series(valores, dtype=dtype)})
    original = frame.copy(deep=True)
    validado = SchemaValidator(_cfg(ColumnSpec(name="x", dtype=logico, coerce=True))).validate(
        frame
    )
    assert_frame_equal(validado, frame.astype(final))
    assert_frame_equal(frame, original)


def test_from_config_y_config_default() -> None:
    cfg = SchemaConfig()

    validator = SchemaValidator.from_config(cfg)

    assert validator.config is cfg
    assert SchemaValidator().config == SchemaConfig()


def test_build_schema_produce_contrato_pandera_esperado() -> None:
    cfg = _cfg(
        ColumnSpec(name="loan_id", dtype="str", nullable=False, coerce=True, unique=True),
        ColumnSpec(name="edad", dtype="int", ge=18),
        ColumnSpec(name="saldo", dtype="float", le=1_000),
        ColumnSpec(name="estado", dtype="category", isin=("vigente", "castigado")),
        ColumnSpec(name="fecha", dtype="datetime"),
        ColumnSpec(name="activo", dtype="bool"),
        ColumnSpec(name="score", dtype="float", ge=0, le=1),
        strict=True,
        ordered=True,
        unique_keys=("loan_id", "fecha"),
        index_col="loan_id",
    )

    schema = SchemaValidator(cfg).build_schema()

    assert schema.strict is True
    assert schema.ordered is True
    assert schema.unique == ["loan_id", "fecha"]
    assert schema.index.name == "loan_id"
    assert schema.index.unique is True
    assert {name: str(column.dtype) for name, column in schema.columns.items()} == {
        "loan_id": "str",
        "edad": "int64",
        "saldo": "float64",
        "estado": "category",
        "fecha": "datetime64[ns]",
        "activo": "bool",
        "score": "float64",
    }

    loan_id = schema.columns["loan_id"]
    assert loan_id.nullable is False
    assert loan_id.coerce is True
    assert loan_id.required is True
    assert loan_id.unique is True
    assert [check.name for check in schema.columns["edad"].checks] == ["greater_than_or_equal_to"]
    assert [check.name for check in schema.columns["saldo"].checks] == ["less_than_or_equal_to"]
    assert [check.name for check in schema.columns["estado"].checks] == ["isin"]
    assert [check.name for check in schema.columns["score"].checks] == ["in_range"]


def test_todos_los_dtypes_logicos_validan_con_pandera_real() -> None:
    df = pd.DataFrame(
        {
            "entero": pd.Series([1, 2], dtype="int64"),
            "monto": pd.Series([10.5, 20.0], dtype="float64"),
            "texto": ["A", "B"],
            "flag": [True, False],
            "segmento": pd.Series(["retail", "pyme"], dtype="category"),
            "fecha": pd.to_datetime(["2024-01-01", "2024-02-01"]),
        }
    )
    validator = SchemaValidator(
        _cfg(
            ColumnSpec(name="entero", dtype="int"),
            ColumnSpec(name="monto", dtype="float"),
            ColumnSpec(name="texto", dtype="str"),
            ColumnSpec(name="flag", dtype="bool"),
            ColumnSpec(name="segmento", dtype="category"),
            ColumnSpec(name="fecha", dtype="datetime"),
        )
    )

    validated = validator.validate(df)

    assert_frame_equal(validated, df)


def test_canonico_lazy_agrega_columna_faltante_tipo_y_rango() -> None:
    validator = SchemaValidator(
        _cfg(
            ColumnSpec(name="columna_faltante", dtype="int"),
            ColumnSpec(name="edad", dtype="int"),
            ColumnSpec(name="saldo", dtype="float", ge=0, le=100),
        )
    )
    df = pd.DataFrame({"edad": ["no-num"], "saldo": [999.0]})

    with pytest.raises(DataValidationError) as exc_info:
        validator.validate(df)

    message = str(exc_info.value)
    assert "(3 problemas)" in message
    assert message.count("\n- «") == 3
    assert "«columna_faltante»: el dataset no la trae" in message
    assert "«edad»: su tipo de dato no es el declarado" in message
    assert "«saldo»: queda fuera del rango declarado" in message
    assert "999.0" in message
    assert "999.0" in message


def test_nullable_false_rechaza_nulos_y_nullable_true_los_admite() -> None:
    df = pd.DataFrame({"segmento": ["retail", None]})
    nullable_false = SchemaValidator(_cfg(ColumnSpec(name="segmento", dtype="str", nullable=False)))
    nullable_true = SchemaValidator(_cfg(ColumnSpec(name="segmento", dtype="str", nullable=True)))

    with pytest.raises(DataValidationError) as exc_info:
        nullable_false.validate(df)

    assert "segmento" in str(exc_info.value)
    assert "tiene valores vacíos y se declaró que no los admite" in str(exc_info.value)
    assert_frame_equal(nullable_true.validate(df), df)


def test_unique_de_columna_y_unique_keys_rechazan_duplicados() -> None:
    duplicated_column = pd.DataFrame({"loan_id": ["A", "A"]})
    duplicated_rows = pd.DataFrame(
        {"cliente_id": ["C1", "C1"], "mes": ["2024-01", "2024-01"], "saldo": [10.0, 20.0]}
    )

    with pytest.raises(DataValidationError) as column_exc:
        SchemaValidator(_cfg(ColumnSpec(name="loan_id", dtype="str", unique=True))).validate(
            duplicated_column
        )

    with pytest.raises(DataValidationError) as keys_exc:
        SchemaValidator(
            _cfg(
                ColumnSpec(name="cliente_id", dtype="str"),
                ColumnSpec(name="mes", dtype="str"),
                ColumnSpec(name="saldo", dtype="float"),
                unique_keys=("cliente_id", "mes"),
            )
        ).validate(duplicated_rows)

    assert "tiene valores repetidos y se declaró única" in str(column_exc.value)
    assert "la combinación de llaves de unicidad se repite" in str(keys_exc.value)
    assert "cliente_id" in str(keys_exc.value)
    assert "mes" in str(keys_exc.value)


@pytest.mark.parametrize(
    ("spec", "valid_value", "invalid_value", "explicacion"),
    [
        (
            ColumnSpec(name="estado", dtype="str", isin=("vigente", "mora")),
            "vigente",
            "otro",
            "no es ninguno de los valores admitidos",
        ),
        (
            ColumnSpec(name="edad", dtype="int", ge=18),
            18,
            17,
            "es menor que el mínimo declarado",
        ),
        (
            ColumnSpec(name="saldo", dtype="float", le=100),
            100.0,
            101.0,
            "es mayor que el máximo declarado",
        ),
        (
            ColumnSpec(name="score", dtype="float", ge=0, le=1),
            0.5,
            -0.1,
            "queda fuera del rango declarado",
        ),
    ],
)
def test_checks_isin_ge_le_e_in_range_aceptan_y_rechazan(
    spec: ColumnSpec, valid_value: object, invalid_value: object, explicacion: str
) -> None:
    validator = SchemaValidator(_cfg(spec))

    valid = pd.DataFrame({spec.name: [valid_value]})
    invalid = pd.DataFrame({spec.name: [invalid_value]})

    assert_frame_equal(validator.validate(valid), valid)
    with pytest.raises(DataValidationError) as exc_info:
        validator.validate(invalid)

    assert spec.name in str(exc_info.value)
    assert explicacion in str(exc_info.value)
    assert str(invalid_value) in str(exc_info.value)


def test_strict_true_filter_y_false_manejan_columnas_extra() -> None:
    df = pd.DataFrame({"saldo": [100.0], "extra": ["no-declarada"]})
    spec = ColumnSpec(name="saldo", dtype="float")

    with pytest.raises(DataValidationError) as strict_exc:
        SchemaValidator(_cfg(spec, strict=True)).validate(df)

    filtered = SchemaValidator(_cfg(spec, strict="filter")).validate(df)
    allowed = SchemaValidator(_cfg(spec, strict=False)).validate(df)

    assert "el dataset la trae y el esquema no la declara" in str(strict_exc.value)
    assert "extra" in str(strict_exc.value)
    assert filtered.to_dict(orient="list") == {"saldo": [100.0]}
    assert_frame_equal(allowed, df)


def test_ordered_valida_el_orden_de_columnas() -> None:
    validator = SchemaValidator(
        _cfg(ColumnSpec(name="a", dtype="int"), ColumnSpec(name="b", dtype="int"), ordered=True)
    )

    with pytest.raises(DataValidationError) as exc_info:
        validator.validate(pd.DataFrame({"b": [1], "a": [2]}))

    message = str(exc_info.value)
    assert "column_ordered" in message
    assert "a" in message
    assert "b" in message


def test_required_false_permite_columna_ausente_y_coerce_no_muta_df_original() -> None:
    original = pd.DataFrame({"saldo": ["10", "20"]})
    validator = SchemaValidator(
        _cfg(
            ColumnSpec(name="saldo", dtype="int", coerce=True),
            ColumnSpec(name="comentario", dtype="str", required=False),
            strict=True,
        )
    )

    validated = validator.validate(original)

    assert validated.to_dict(orient="list") == {"saldo": [10, 20]}
    assert str(validated["saldo"].dtype) == "int64"
    assert original.to_dict(orient="list") == {"saldo": ["10", "20"]}
    assert str(original["saldo"].dtype) == "object"


def test_index_col_valida_indice_pandas_existente_y_no_una_columna_ordinaria() -> None:
    validator = SchemaValidator(_cfg(ColumnSpec(name="saldo", dtype="float"), index_col="loan_id"))
    con_indice = pd.DataFrame({"saldo": [10.0, 20.0]}, index=pd.Index(["A", "B"], name="loan_id"))
    con_columna = pd.DataFrame({"loan_id": ["A", "B"], "saldo": [10.0, 20.0]})
    indice_duplicado = pd.DataFrame(
        {"saldo": [10.0, 20.0]}, index=pd.Index(["A", "A"], name="loan_id")
    )

    assert_frame_equal(validator.validate(con_indice), con_indice)
    with pytest.raises(DataValidationError) as column_exc:
        validator.validate(con_columna)
    with pytest.raises(DataValidationError) as duplicated_exc:
        validator.validate(indice_duplicado)

    assert "el índice no se llama como el esquema espera" in str(column_exc.value)
    assert "tiene valores repetidos y se declaró única" in str(duplicated_exc.value)
    assert "loan_id" in str(duplicated_exc.value)


def test_datavalidationerror_tiene_reporte_en_espanol_con_columna_check_y_valor() -> None:
    """El mensaje es copy público: lo lee un humano en el panel de la UI, no un desarrollador.

    Por eso NO puede llevar los literales de `pandera` (`in_range`, `not_nullable`,
    `column_in_dataframe`, `lazy=True`): el D1 midió que llegaban crudos hasta la pantalla.
    """
    validator = SchemaValidator(_cfg(ColumnSpec(name="score", dtype="float", ge=0, le=1)))

    with pytest.raises(DataValidationError) as exc_info:
        validator.validate(pd.DataFrame({"score": [2.5]}))

    message = str(exc_info.value)
    assert "El dataset no cumple el esquema declarado en data.schema" in message
    assert "«score»: queda fuera del rango declarado (valor: 2.5, fila 0)." in message
    for jerga in ("in_range", "lazy=True", "DataFrame no cumple", "valor ofensor"):
        assert jerga not in message


def test_helpers_de_reporte_cubren_fallbacks_defensivos() -> None:
    class BadArray:
        """Objeto mínimo para forzar el camino defensivo de ``pd.isna``."""

        def __array__(self, dtype: object = None) -> object:
            raise TypeError("isna no disponible")

    assert (
        schema_module._format_failure_row({"schema_context": "DataFrameSchema"})
        == "- «DataFrameSchema»: no cumple el esquema."
    )
    assert schema_module._format_failure_row({}) == "- «<dataframe>»: no cumple el esquema."
    # Un check que la tabla no conoce CONSERVA su literal: perder información sería peor que
    # mostrarla fea. Y la familia manda sobre los argumentos en los checks parametrizados.
    assert "no cumple «inventado_v2»" in schema_module._format_failure_row(
        {"column": "x", "check": "inventado_v2"}
    )
    assert "queda fuera del rango declarado" in schema_module._format_failure_row(
        {"column": "x", "check": "in_range(0, 10)"}
    )
    assert schema_module._format_value([1]) == "[1]"
    assert schema_module._is_missing(BadArray()) is False


@pytest.mark.parametrize(
    ("dtype", "valores", "logico"),
    [
        ("int32", [-(2**31), 0, 2**31 - 1], "int"),
        ("float32", [-0.0, 0.1, float("nan")], "float"),
        ("uint64", [0, 2**53 - 1, 2**53 + 1, 2**63 - 1, 2**63, 2**64 - 1], "int"),
        ("Int32", [-(2**31), None, 2**31 - 1], "int"),
        ("Int32", [None, None], "int"),
        ("UInt64", [2**64 - 1, None], "int"),
        ("Float32", [-0.0, 0.1, None], "float"),
        ("int64", [-(2**63), 2**63 - 1], "int"),
        ("Int64", [1, None], "int"),
        ("float64", [0.1, float("nan")], "float"),
    ],
)
def test_inferencia_numerica_estricta_conserva_tipo_valores_nulos_e_indice(
    dtype: str, valores: list[object], logico: str
) -> None:
    """D-H10-3: el tipo lógico no obliga a perder el rango o el ancho físico."""
    from bayesrisk.guided.inference import columnas_esquema

    frame = pd.DataFrame({"x": pd.Series(valores, dtype=dtype)})
    frame.index = pd.Index([f"fila-{i}" for i in reversed(range(len(frame)))], name="id")
    original = frame.copy(deep=True)
    columnas = columnas_esquema(frame)
    assert columnas[0]["dtype"] == logico
    assert columnas[0]["coerce"] is False
    cfg = SchemaConfig(columns=columnas, index_col="id", strict=True)
    assert_frame_equal(SchemaValidator(cfg).validate(frame), original)
    assert_frame_equal(frame, original)


@pytest.mark.parametrize(
    ("dtype", "valores", "logico"),
    [
        ("float32", [1.5], "int"),
        ("int32", [1], "float"),
        ("bool", [True], "int"),
        ("object", [1], "int"),
        ("str", ["1"], "int"),
    ],
)
def test_tipo_logico_estricto_no_convierte_otra_familia(
    dtype: str, valores: list[object], logico: str
) -> None:
    frame = pd.DataFrame({"x": pd.Series(valores, dtype=dtype)})
    original = frame.copy(deep=True)
    with pytest.raises(DataValidationError, match="tipo de dato"):
        SchemaValidator(_cfg(ColumnSpec(name="x", dtype=logico))).validate(frame)
    assert_frame_equal(frame, original)


@pytest.mark.parametrize(
    ("valores", "dtype", "logico"),
    [
        ([2**63, 2**64 - 1], "uint64", "int"),
        ([2**53 + 1], "uint64", "float"),
        ([1.5], "float64", "int"),
    ],
)
def test_coercion_numerica_con_perdida_se_rechaza_sin_mutar(
    valores: list[object], dtype: str, logico: str
) -> None:
    frame = pd.DataFrame({"x": pd.Series(valores, dtype=dtype)})
    original = frame.copy(deep=True)
    with pytest.raises(DataValidationError, match="perdería valores"):
        SchemaValidator(_cfg(ColumnSpec(name="x", dtype=logico, coerce=True))).validate(frame)
    assert_frame_equal(frame, original)


@pytest.mark.parametrize("dtype", ["int32", "Int32", "uint64", "float32"])
def test_ancho_numerico_no_omite_las_restricciones(dtype: str) -> None:
    frame = pd.DataFrame({"x": pd.Series([1, 1, 3], dtype=dtype)})
    logico = "float" if dtype == "float32" else "int"
    with pytest.raises(DataValidationError, match="fuera del rango"):
        SchemaValidator(_cfg(ColumnSpec(name="x", dtype=logico, ge=0, le=2))).validate(frame)
    with pytest.raises(DataValidationError, match="valores repetidos"):
        SchemaValidator(_cfg(ColumnSpec(name="x", dtype=logico, unique=True))).validate(frame)
    if dtype == "Int32":
        frame.loc[0, "x"] = pd.NA
        with pytest.raises(DataValidationError, match="valores vacíos"):
            SchemaValidator(_cfg(ColumnSpec(name="x", dtype="int", nullable=False))).validate(frame)


@pytest.mark.parametrize(
    ("dtype", "valores", "logico", "esperado"),
    [
        ("int32", [0, 2**31 - 1], "int", "int64"),
        ("uint64", [0, 2**63 - 1], "int", "int64"),
        ("float32", [-0.0, 0.1], "float", "float64"),
    ],
)
def test_coercion_numerica_exacta_sigue_disponible(
    dtype: str, valores: list[object], logico: str, esperado: str
) -> None:
    frame = pd.DataFrame({"x": pd.Series(valores, dtype=dtype)})
    original = frame.copy(deep=True)
    validado = SchemaValidator(_cfg(ColumnSpec(name="x", dtype=logico, coerce=True))).validate(
        frame
    )
    assert_frame_equal(validado, frame.astype({"x": esperado}))
    assert_frame_equal(frame, original)
