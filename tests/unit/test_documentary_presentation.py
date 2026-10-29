"""Regresiones de lectura observadas en la aceptación humana A+B."""

import copy
import re

import pandas as pd
from test_documentary_layout import bundle_documental

from bayesrisk.report.builder import ReportBuilder
from bayesrisk.report.renderer import HtmlReportRenderer, build_document_view


def presentation_bundle():
    bundle, config, _ = bundle_documental(2)
    tables = {
        "performance.discriminant_metrics": pd.DataFrame(
            [
                {
                    "partition": "holdout",
                    "n_total": 10,
                    "n_bad": 2,
                    "auc": 0.7,
                    "gini": 0.4,
                    "ks": 0.3,
                    "extra": "original",
                }
            ]
        ),
        "performance.performance_table": pd.DataFrame(
            {
                "partition": ["holdout"] * 30,
                "n": list(range(30)),
                **{f"detalle_{i}": [i] * 30 for i in range(9)},
            }
        ),
    }
    bundle = bundle.model_copy(update={"cards": {"performance": {}}, "tables": tables})
    return bundle.model_copy(
        update={"sections": ReportBuilder(config).build_sections(bundle)}
    ), config


def test_lectura_compacta_y_detalle_en_anexo_con_anclas_anteriores():
    bundle, config = presentation_bundle()
    before = copy.deepcopy(bundle.tables)
    view = build_document_view(bundle, config=config)
    body = [t for s in view["sections"] if s["kind"] != "appendix" for t in s["tables"]]
    assert len(body) == 1, "El detalle por tramo y los bloques repetidos saturan el cuerpo"
    assert body[0]["columns"] == [
        "Muestra",
        "Observaciones",
        "Incumplimientos",
        "AUC",
        "Gini",
        "KS",
    ]
    assert body[0]["rows"][0][0] == "Holdout"
    supports = [t for s in view["sections"] for t in s["tables"] if t.get("support")]
    assert any(t["total_rows"] == 30 for t in supports)
    assert any("original" in str(t["rows"]) for t in supports)
    for key in before:
        pd.testing.assert_frame_equal(bundle.tables[key], before[key])
    html = HtmlReportRenderer(config).render(bundle)
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    assert set(re.findall(r'href="#([^"]+)"', html)) <= set(ids)
    assert "table-performance-performance_table-block-3" in ids
    assert any(e["title"] == "Evidencia íntegra" for e in view["toc"])


def test_titulo_del_soporte_no_duplica_etiqueta():
    from bayesrisk.report._documentary_layout import support_tables

    title = support_tables("binning.event_rate_by_partition", pd.DataFrame({"n": [1]}), 1)[0][
        "title"
    ]
    assert title.casefold().count("soporte íntegro") == 1


def test_enum_iv_none_no_es_ausencia_y_diccionario_local_usa_cifras_de_lectura():
    bundle, config, _ = bundle_documental(2)
    tables = {
        "binning.summary": pd.DataFrame({"name": ["none", "variable"], "iv_band": ["none", None]}),
        "binning.tables.none": pd.DataFrame(
            {
                "Bin": ["[0, 0.123456789)"],
                "Count": [1000],
                "Event": [123],
                "Event rate": [0.123],
                "WoE": [0.123456789],
            }
        ),
    }
    config = config.model_copy(
        update={"html": config.html.model_copy(update={"render_charts": True})}
    )
    bundle = bundle.model_copy(update={"tables": tables, "cards": {"binning": {}}})
    bundle = bundle.model_copy(update={"sections": ReportBuilder(config).build_sections(bundle)})
    view = build_document_view(bundle, config=config)
    table = next(
        t
        for s in view["sections"]
        for t in s["tables"]
        if t["key"] == "binning.summary" and not t.get("support")
    )
    assert table["rows"][0][1] == "sin poder"
    assert table["rows"][1][1] == "—"
    dictionary = next(
        t for s in view["sections"] for c in s["charts"] for t in c.get("local_tables", [])
    )
    assert dictionary["rows"][0][1:] == ("[0, 0.123456789)", "1.000", "123", "12,30 %", "0,1235")


def test_aliases_trasladados_existen_en_word_y_markdown():
    import importlib.util
    import io
    import zipfile

    from bayesrisk.report.docx import DocxReportRenderer, _bookmark_name
    from bayesrisk.report.markdown import MarkdownReportRenderer

    bundle, config = presentation_bundle()
    anchor = "table-performance-performance_table-block-3"
    assert f"[]{{#{anchor}}}" in MarkdownReportRenderer(config).render(bundle)
    if importlib.util.find_spec("docx") is not None:
        with zipfile.ZipFile(io.BytesIO(DocxReportRenderer(config).render(bundle))) as archive:
            assert _bookmark_name(anchor) in archive.read("word/document.xml").decode()
