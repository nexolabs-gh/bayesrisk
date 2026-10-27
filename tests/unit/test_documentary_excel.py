"""Excel documental: tipos originales, formatos y destinos internos efectivos."""

import pandas as pd
import pytest

from bayesrisk.guided.export import _hojas_de_la_etapa, _nombre_de_hoja
from bayesrisk.guided.summaries import StageSummary
from bayesrisk.report.exports import write_workbook

openpyxl = pytest.importorskip("openpyxl")


def test_formatos_y_navegacion_sin_convertir_numeros_en_texto(tmp_path):
    source = pd.DataFrame({"Tasa": [0.125, 0.0], "Casos": [80, 0], "Nombre": ["=1+1", "O'Brien"]})
    summary = StageSummary(
        "model",
        "Modelo",
        ("Resultado de prueba",),
        table=source,
        formats={"Tasa": "pct", "Casos": "int"},
    )
    sheets, indices = _hojas_de_la_etapa("model", summary, {})
    for sheet in sheets.values():
        sheet.attrs["_documentary"] = True
    path = write_workbook(sheets, tmp_path / "modelo.xlsx", index=indices)
    book = openpyxl.load_workbook(path)
    assert book.sheetnames == ["Resumen", "Decisión", "Índice"]
    decision = book["Decisión"]
    assert decision["A2"].value == 0.125 and decision["A2"].data_type == "n"
    assert decision["A3"].value == 0 and decision["B2"].value == 80
    assert decision["C2"].value == "'=1+1" and decision["C2"].data_type == "s"
    assert decision["A2"].number_format == "0.00%"
    assert decision["B2"].number_format == "#,##0"
    assert decision.freeze_panes == "A2" and decision.auto_filter.ref == "A1:C3"
    assert decision["A1"].hyperlink.location == "'Índice'!A1"
    assert book["Índice"]["A3"].hyperlink.location == "'Decisión'!A1"
    assert decision["A2"].font.sz >= 10
    book.close()


def test_nombres_colisionan_sin_distinguir_mayusculas_y_reservan_indice():
    assert _nombre_de_hoja("", {"ABC": None}, titulo="abc") == "abc (2)"
    assert _nombre_de_hoja("", {}, titulo="Índice") == "Índice (2)"


def test_enlaces_usan_nombre_real_con_apostrofes_y_cortes_como_texto(tmp_path):
    cuts = pd.DataFrame({"Regla exacta": ["0,12345678901234566 ≤ x < +inf"]})
    summary = StageSummary("binning", "Tramos", (), extra_tables=(("Tramos d'edad", cuts, {}),))
    sheets, indices = _hojas_de_la_etapa("binning", summary, {})
    for sheet in sheets.values():
        sheet.attrs["_documentary"] = True
    path = write_workbook(sheets, tmp_path / "cortes.xlsx", index=indices)
    book = openpyxl.load_workbook(path)
    assert book["Índice"]["A3"].value == "Tramos d'edad"
    assert book["Índice"]["A3"].hyperlink.location == "'Tramos d''edad'!A1"
    cell = book["Tramos d'edad"]["A2"]
    assert cell.data_type == "s" and cell.value == cuts.iloc[0, 0]
    book.close()


def test_libro_de_decisiones_tambien_tiene_indice_y_retorno(monkeypatch, tmp_path):
    from bayesrisk.guided import export
    from bayesrisk.report.config import ReportConfig

    monkeypatch.setattr(export, "_tablas_del_informe", lambda *_: {})
    monkeypatch.setattr(
        export,
        "_hojas_de_decisiones",
        lambda *_: {"Decisiones del motor": pd.DataFrame({"Motivo": ["x"]})},
    )
    paths = export.write_stage_workbooks(
        None,
        {},
        directory=tmp_path / "excel",
        report_config=ReportConfig(),
        trail_path=tmp_path / "trail",
    )
    book = openpyxl.load_workbook(paths[0])
    assert book.sheetnames == ["Decisiones del motor", "Índice"]
    assert book["Índice"]["A2"].hyperlink.location == "'Decisiones del motor'!A1"
    assert book["Decisiones del motor"]["A1"].hyperlink.location == "'Índice'!A1"
    book.close()
