"""H3 entrega las mismas celdas y la misma procedencia en los artefactos finales."""

import zipfile
from pathlib import Path

import pandas as pd
import pytest
from test_h3_provision import cartera

from bayesrisk import Provision
from bayesrisk.report.document import table_title
from bayesrisk.report.exports import exportable_table


def test_csv_excel_word_html_zip_conservan_detalle_y_supuestos(tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    docx = pytest.importorskip("docx")
    # Supera el límite de vista previa: el descargable debe conservar todas las operaciones.
    frame = pd.concat([cartera()] * 151, ignore_index=True).iloc[:301]
    p = Provision(
        frame,
        as_of="fecha",
        portfolio="cartera",
        exposure="exposicion",
        pd="pd",
        lgd="lgd",
        run_dir=tmp_path,
        formats=["csv", "xlsx", "docx"],
    )
    p.run(raise_on_error=True)
    reports = p.project_dir / "reports"
    key = "provisioning_internal.detail"
    detail = p.study.artifacts.get(*key.split("."))
    csv = next(reports.glob("*provisioning_internal_detail.csv"))
    actual = pd.read_csv(csv, index_col=0, keep_default_na=False)
    expected = exportable_table(detail)
    assert list(actual.index) == list(detail.index)
    assert list(actual.columns) == list(detail.columns)
    assert len(actual) == len(detail)
    # El CSV no pierde ni modifica ningún valor; Decimal queda representado como texto decimal.
    import io

    pd.testing.assert_frame_equal(
        actual, pd.read_csv(io.StringIO(expected.to_csv()), index_col=0, keep_default_na=False)
    )
    libros = p.export_excel()
    stage = next(path for path in libros if "Provisión interna" in path.name)
    wb = openpyxl.load_workbook(stage, read_only=True)
    try:
        indice = list(wb["Índice"].values)
        header = list(indice[0])
        sheet = next(
            row[header.index("Hoja")]
            for row in indice[1:]
            if row[header.index("Contenido")] == table_title(key)
        )
        stage_rows = list(wb[sheet].values)
    finally:
        wb.close()
    wb = openpyxl.load_workbook(next(reports.glob("*por_observacion.xlsx")), read_only=True)
    try:
        report_rows = list(wb[key.replace(".", "_")[:31]].values)
    finally:
        wb.close()
    assert stage_rows == report_rows
    assert len(stage_rows) == len(detail) + 1
    html = next(reports.glob("*.html")).read_text(encoding="utf-8")
    word = docx.Document(next(reports.glob("*.docx")))
    word_text = "\n".join(para.text for para in word.paragraphs)
    for text in (html, word_text):
        assert "Supuestos" in text
        assert "PD externa" in text
        assert "prorrat" in text
        assert "Informe de Provisión Interna" in text
        assert "construcción y evaluación del scorecard" not in text
        assert "Provisiones regulatorias" not in text
        assert "No certifica la calidad de PD o LGD" in text
    out = p.export(tmp_path / "evidencia.zip")
    with zipfile.ZipFile(out) as archive:
        matches = [name for name in archive.namelist() if name.endswith(csv.name)]
        assert len(matches) == 1
        assert archive.read(matches[0]) == csv.read_bytes()
