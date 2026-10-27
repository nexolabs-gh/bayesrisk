"""D-DOC-SC B: oráculos de evidencia íntegra y navegación del artefacto final."""

import html as html_module
import importlib.util
import io
import re
import zipfile
from datetime import UTC, datetime

import pandas as pd
import pytest

from bayesrisk.core.lineage import LineageBundle
from bayesrisk.guided.summaries import RESUMEN_FINAL_ROTULOS
from bayesrisk.report.builder import ReportBuilder
from bayesrisk.report.config import ReportConfig
from bayesrisk.report.docx import DocxReportRenderer
from bayesrisk.report.renderer import HtmlReportRenderer, build_document_view
from bayesrisk.report.results import ReportInputBundle

_HAS_DOCX = importlib.util.find_spec("docx") is not None


def bundle_documental(n=1001):
    config = ReportConfig(
        html={"render_charts": False},
        document={"placeholders": "hide"},
        sections={"missing_policy": "skip"},
    )
    frame = pd.DataFrame(
        {
            "feature": [f"variable_{i}" for i in range(n)],
            "beta": [0.12345678901234567] * n,
            "p_value": [0.000123456789012345] * n,
        },
        index=pd.Index([f"fuente_{i}" for i in range(n)], name="variable"),
    )
    bundle = ReportInputBundle(
        lineage=LineageBundle(
            git_sha="abc123",
            git_dirty=False,
            data_hash="datos",
            config_hash="config",
            root_seed=42,
            uv_lock_hash="uv",
            library_versions={},
            determinism_caveats=[],
            created_at=datetime(2026, 10, 27, tzinfo=UTC),
            schema_version="1.0.0",
        ),
        cards={"model": {"fit_statistics": {"converged": True}}},
        tables={"model.coefficients": frame},
        figures={},
        sections=(),
        summary={
            "family": "scorecard",
            "labels": RESUMEN_FINAL_ROTULOS,
            "sin_alertas": "Sin alertas registradas",
            "sin_decisiones": "Sin decisiones registradas",
            "final": {
                "execution": "completada",
                "validation": "No ejecutada",
                "figures": [],
                "review": ["Hallazgo único trazado"],
                "decisions": [],
                "files": [],
            },
        },
    )
    return (
        bundle.model_copy(update={"sections": ReportBuilder(config).build_sections(bundle)}),
        config,
        frame,
    )


def test_soporte_no_pierde_filas_precision_ni_indice_por_recorte_del_cuerpo():
    bundle, config, source = bundle_documental()
    view = build_document_view(bundle, config=config)
    support = [t for s in view["sections"] for t in s["tables"] if t.get("support")]
    assert support, "El cuerpo recortado no sustituye al soporte"
    html = HtmlReportRenderer(config).render(bundle)
    plain = html_module.unescape(re.sub(r"<[^>]+>", "", html))
    for value in ("fuente_1000", "variable_1000", repr(float(source.iloc[-1]["beta"]))):
        assert value in plain
    assert all(not t["truncated"] for t in support)


def test_entrada_unica_con_alias_compatibles_y_todos_los_enlaces_resueltos():
    bundle, config, _ = bundle_documental(2)
    html = HtmlReportRenderer(config).render(bundle)
    assert html.count('data-kind="summary"') == 1
    assert html.count('id="exec-summary"') == 1
    assert "POR COMPLETAR" not in re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    assert set(re.findall(r'href="#([^"]+)"', html)) <= set(ids)
    assert "Resultado y decisión pendiente" not in html or "Hallazgo único trazado" in html
    assert "<h2>Resumen ejecutivo</h2>" not in html


def test_componer_no_muta_el_resumen_original_ni_sus_archivos():
    import copy

    bundle, config, _ = bundle_documental(2)
    summary = bundle.summary
    summary["final"]["files"] = [("HTML", "corrida/reports/informe.html")]
    bundle = bundle.model_copy(update={"summary": summary})
    bundle = bundle.model_copy(update={"sections": ReportBuilder(config).build_sections(bundle)})
    before = copy.deepcopy(bundle.summary)
    before_sections = copy.deepcopy(bundle.sections)
    rendered = HtmlReportRenderer(config).render(bundle)
    assert bundle.summary == before
    assert bundle.sections == before_sections
    assert "corrida/reports/informe.html" in rendered
    assert HtmlReportRenderer(config).render(bundle) == rendered


@pytest.mark.skipif(not _HAS_DOCX, reason="requiere el extra docx")
def test_word_conserva_ultima_fila_soporte_y_links_nativos():
    bundle, config, _ = bundle_documental(501)
    payload = DocxReportRenderer(config).render(bundle)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        xml = archive.read("word/document.xml").decode()
    assert "fuente_500" in xml and "variable_500" in xml
    assert "w:bookmarkStart" in xml and "w:hyperlink" in xml
    assert "w:cantSplit" not in xml


def test_binning_dos_paneles_con_magnitudes_y_diccionario_local():
    bundle, config, _ = bundle_documental(2)
    frame = pd.DataFrame(
        {
            "Bin": ["[-inf, 1)", "[1, inf)", "Totals"],
            "Event rate": [0.1, 0.3, 0.2],
            "WoE": [0.8, -0.7, 0.0],
            "Count": [10, 10, 20],
            "Event": [1, 3, 4],
        }
    )
    bundle = bundle.model_copy(
        update={
            "cards": {**bundle.cards, "binning": {"summary": {}}},
            "tables": {**bundle.tables, "binning.tables.edad": frame},
        }
    )
    bundle = bundle.model_copy(update={"sections": ReportBuilder(config).build_sections(bundle)})
    config = config.model_copy(
        update={"html": config.html.model_copy(update={"render_charts": True})}
    )
    view = build_document_view(bundle, config=config)
    charts = [
        c
        for s in view["sections"]
        for c in s["charts"]
        if c.get("source_key") == "binning.tables.edad"
    ]
    assert len(charts) == 2
    assert {c["measure"] for c in charts} == {"Event rate", "WoE"}
    assert all("Desarrollo" in c["title"] for c in charts)
    assert all("T1" in c["svg"] and "T2" in c["svg"] and "Totals" not in c["svg"] for c in charts)
    assert all(c["links"] for c in charts)


def test_indice_de_hechos_resuelve_soporte_sin_inventar_ruta_de_auditoria():
    bundle, config, _ = bundle_documental(2)
    bundle = bundle.model_copy(
        update={"cards": {"model": {"fit_statistics": {"converged": False}}}}
    )
    view = build_document_view(bundle, config=config)
    reading = view["documentary_reading"]
    ids = {s["html_id"] for s in view["sections"]} | {
        t["html_id"] for s in view["sections"] for t in s["tables"]
    }
    assert reading["facts"]
    assert all(
        e["section_id"] in ids and e["local_path"] is None for e in reading["evidence_index"]
    )


@pytest.mark.skipif(not _HAS_DOCX, reason="requiere el extra docx")
def test_word_incrusta_originales_roboto_y_todos_los_destinos_de_links():
    from importlib.resources import files
    from uuid import UUID

    from lxml import etree

    bundle, config, _ = bundle_documental(2)
    with zipfile.ZipFile(io.BytesIO(DocxReportRenderer(config).render(bundle))) as archive:
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        fonts = etree.fromstring(archive.read("word/fontTable.xml"))
        for variant, element in (("Regular", "embedRegular"), ("Bold", "embedBold")):
            key = fonts.find(f'.//w:font[@w:name="Roboto"]/w:{element}', ns).get(
                f"{{{ns['w']}}}fontKey"
            )
            decoded = bytearray(archive.read(f"word/fonts/Roboto-{variant}.odttf"))
            mask = UUID(key).bytes[::-1]
            for i in range(32):
                decoded[i] ^= mask[i % 16]
            assert (
                decoded
                == files("bayesrisk.report")
                .joinpath("templates", "fonts", f"Roboto-{variant}.ttf")
                .read_bytes()
            )
        xml = etree.fromstring(archive.read("word/document.xml"))
        bookmarks = xml.xpath("//w:bookmarkStart/@w:name", namespaces=ns)
        assert len(bookmarks) == len(set(bookmarks))
        assert set(xml.xpath("//w:hyperlink/@w:anchor", namespaces=ns)) <= set(bookmarks)
        table_sizes = xml.xpath("//w:tbl//w:rPr/w:sz/@w:val", namespaces=ns)
        assert table_sizes and min(int(size) for size in table_sizes) >= 20  # medios puntos


def test_soporte_ancho_reconstruye_todas_las_columnas_y_multiindice_en_html():
    html = pytest.importorskip("lxml.html")

    bundle, config, _ = bundle_documental(2)
    frame = pd.DataFrame(
        [
            [0.12345678901234567, "=1+1", None, True, "última"],
            [0.0, "<script>literal</script>", float("nan"), False, "fin"],
        ],
        columns=["warning_codes", "green_alpha", "duplicada", "duplicada", "cola"],
        index=pd.MultiIndex.from_tuples([("A", 2), ("A", 2)], names=[None, "cola"]),
        dtype=object,
    )
    bundle = bundle.model_copy(update={"tables": {"model.model_card.embedded_table": frame}})
    bundle = bundle.model_copy(update={"sections": ReportBuilder(config).build_sections(bundle)})
    view = build_document_view(bundle, config=config)
    parsed = html.fromstring(HtmlReportRenderer(config).render(bundle))
    recovered = {}
    for block in [
        t
        for s in view["sections"]
        for t in s["tables"]
        if t.get("support") and t["key"] == "model.model_card.embedded_table"
    ]:
        table = parsed.get_element_by_id(block["html_id"])
        rows = table.xpath("./tbody/tr")
        assert len(rows) == 2
        for n, row in enumerate(rows):
            for identity, cell in zip(block["source_columns"], row.xpath("./td"), strict=True):
                recovered[n, identity] = cell.text_content()
    assert len(recovered) == 2 * (1 + 2 + 5)
    assert recovered[0, "index:0"] == '"A"' and recovered[0, "index:1"] == "2"
    assert recovered[0, "column:0"] == "0.12345678901234566"
    assert recovered[0, "column:1"] == '"=1+1"'
    assert recovered[0, "column:2"] == "None (ausente)"
    assert recovered[0, "column:3"] == "True"
    assert recovered[1, "column:0"] == "0.0"
    assert recovered[1, "column:1"] == '"<script>literal</script>"'
    assert recovered[1, "column:2"] == "NaN (no disponible)"
    assert recovered[1, "column:3"] == "False" and recovered[1, "column:4"] == '"fin"'
    assert not parsed.xpath("//table//script")

    # Los destinos editables conservan también cada bloque del MultiIndex y columnas homónimas.
    import string

    from bayesrisk.report.markdown import MarkdownReportRenderer

    qmd = MarkdownReportRenderer(config).render(bundle)
    punctuation = re.compile(r"\\([" + re.escape(string.punctuation) + r"])")
    word_tables = []
    if _HAS_DOCX:
        from lxml import etree

        with zipfile.ZipFile(io.BytesIO(DocxReportRenderer(config).render(bundle))) as archive:
            xml = etree.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        word_tables = [
            [
                [
                    "".join(c.xpath(".//w:t/text()", namespaces=ns))
                    for c in row.xpath("./w:tc", namespaces=ns)
                ]
                for row in table.xpath("./w:tr", namespaces=ns)
            ]
            for table in xml.xpath("//w:tbl", namespaces=ns)
        ]
    for block in [
        t
        for s in view["sections"]
        for t in s["tables"]
        if t.get("support") and t["key"] == "model.model_card.embedded_table"
    ]:
        table = parsed.get_element_by_id(block["html_id"])
        expected = [[c.text_content() for c in row] for row in table.xpath("./thead/tr|./tbody/tr")]
        if _HAS_DOCX:
            assert expected in word_tables
        fragment = qmd.split("{#" + block["html_id"] + "}", 1)[1].split("\n#### ", 1)[0]
        actual = [
            [punctuation.sub(r"\1", c.strip()) for c in re.split(r"(?<!\\)\|", line)[1:-1]]
            for line in fragment.splitlines()
            if line.startswith("| ") and not line.startswith("| ---")
        ]
        assert actual == expected


def test_panel_excluye_total_por_indice_y_no_atribuye_tasa_a_cero_casos(monkeypatch):
    import math

    from bayesrisk.report import charts

    frame = pd.DataFrame(
        {"Bin": ["[-inf, 1)", "Special", ""], "Count": [10, 0, 10], "Event rate": [0.2, 0.0, 0.2]},
        index=[0, 1, "Totals"],
    )
    captured = []

    def capture(figure, _title, _fmt):
        assert len(figure.axes) == 1
        captured.extend(figure.axes[0].lines[0].get_ydata())
        return "svg"

    monkeypatch.setattr(charts, "_render", capture)
    charts._binning_panel(frame, "Event rate", "Tasa", "svg")
    assert len(captured) == 2 and captured[0] == 0.2 and math.isnan(captured[1])


@pytest.mark.skipif(not _HAS_DOCX, reason="requiere el extra docx")
def test_soporte_de_tramos_categoricos_conserva_arrays_y_espacios_en_tres_formatos():
    import numpy as np

    from bayesrisk.report.markdown import MarkdownReportRenderer

    bundle, config, _ = bundle_documental(2)
    frame = pd.DataFrame({"Bin": [np.array(["A", "B"], dtype=object), "categoria  dos espacios"]})
    bundle = bundle.model_copy(update={"tables": {"binning.tables.segmento": frame}})
    bundle = bundle.model_copy(update={"sections": ReportBuilder(config).build_sections(bundle)})
    html = HtmlReportRenderer(config).render(bundle)
    assert '["A", "B"]' in html_module.unescape(html)
    assert "categoria  dos espacios" in html
    markdown = MarkdownReportRenderer(config).render(bundle)
    assert "categoria  dos espacios" in markdown
    with zipfile.ZipFile(io.BytesIO(DocxReportRenderer(config).render(bundle))) as archive:
        assert "categoria  dos espacios" in archive.read("word/document.xml").decode()


def test_gobernanza_del_snapshot_no_se_anuncia_como_ficha_consolidada_del_cierre():
    from bayesrisk.report.results import GovernanceDeclaration

    bundle, config, _ = bundle_documental(2)
    declaration = GovernanceDeclaration(
        model_name="Modelo", purpose="Prueba", review_period_months=12
    )
    bundle = bundle.model_copy(update={"governance": declaration})
    bundle = bundle.model_copy(update={"sections": ReportBuilder(config).build_sections(bundle)})
    view = build_document_view(bundle, config=config)
    entry = next(s for s in view["sections"] if s["kind"] == "summary")
    text = " ".join(entry["body"])
    assert "declaraciones institucionales" in text
    assert "se emite al cierre" in text and "si se solicita" in text
    assert "incluye la ficha consolidada" not in text
    assert any(link["href"] == "#section-model_card" for link in entry["links"])
