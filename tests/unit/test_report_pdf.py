"""Tests de ``report.pdf`` y ``PdfReportRenderer``: render PDF real (WeasyPrint) y degradación.

Los tests que ejecutan WeasyPrint real (grupos (a) y (b)) van gateados con ``skipif``: WeasyPrint
exige librerías nativas (Pango/HarfBuzz/libffi) que no están en todos los entornos de desarrollo, y
se validan en el job ``test-pdf`` del CI (ubuntu, extra ``pdf`` instalado). El PDF NO es
byte-determinista, por lo que la verificación es estructural (``%PDF``, ≥1 página, texto extraíble
con ``pypdf``), nunca por digest cross-OS. Los grupos (c) y (d) corren SIEMPRE: cubren la ausencia
de WeasyPrint (bloqueando su import) y el import liviano del paquete ``report``.
"""

from __future__ import annotations

import builtins
import importlib.util
import subprocess
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from bayesrisk.core.config import BayesRiskConfig
from bayesrisk.core.lineage import LineageBundle
from bayesrisk.core.study import Study
from bayesrisk.report.config import PdfRenderConfig, ReportConfig, SectionPolicyConfig
from bayesrisk.report.exceptions import ReportDependencyError
from bayesrisk.report.pdf import render_pdf
from bayesrisk.report.renderer import HtmlReportRenderer, PdfReportRenderer
from bayesrisk.report.results import ReportInputBundle, ReportResult, ReportSection
from bayesrisk.report.step import REPORT_REQUIRED_CARDS, ReportStep


def _weasyprint_utilizable() -> bool:
    """¿Se puede RENDERIZAR un PDF aquí? No basta con que el paquete esté instalado.

    ``find_spec("weasyprint")`` sólo dice que existe el paquete de Python. WeasyPrint además carga
    librerías NATIVAS (Pango/HarfBuzz/libffi) por cffi al importarse, y ``pip install
    bayesrisk[pdf]`` no las trae: en un macOS o un Windows sin Pango el import revienta con
    ``OSError``. Gatear sólo por ``find_spec`` hacía que estos tests, en vez de saltarse, FALLARAN
    en cualquier máquina de desarrollo con los extras instalados y sin las nativas del sistema.

    En el CI el job de PDF instala las nativas explícitamente, así que allí esto sigue siendo
    ``True`` y los tests corren de verdad (si las nativas faltaran, ese job falla en su propio paso
    de instalación, no aquí en silencio).
    """
    if importlib.util.find_spec("weasyprint") is None:
        return False
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


_HAS_WEASYPRINT = _weasyprint_utilizable()
_MARCA = "marcaunicaxyzbayesrisk"


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="WeasyPrint nativo se verifica en CI PDF")
@pytest.mark.parametrize("kind", ["figura", "tabla"])
def test_pdf_no_recorta_figuras_ni_encabezados_anchos(kind: str) -> None:
    """Regresión de la recaptura 2.17: contenido real dentro del ancho imprimible."""
    from importlib.resources import files

    from weasyprint import HTML

    from bayesrisk.report.renderer import _font_faces

    css = files("bayesrisk.report.templates").joinpath("scorecard_report.css").read_text()
    if kind == "figura":
        body = (
            '<figure class="chart-slot"><svg xmlns="http://www.w3.org/2000/svg" '
            'width="619.2pt" height="403.2pt" viewBox="0 0 619.2 403.2" '
            'style="max-width:100%;height:auto">'
            '<rect x="0" y="0" width="619.2" height="400" fill="blue"/>'
            "</svg></figure>"
        )
    else:
        headers = "".join(f"<th>Semáforo Fuera de tiempo (OOT) {i}</th>" for i in range(13))
        cells = "<td>0,123456</td>" * 13
        body = (
            '<figure class="table-block table-block--wide"><table>'
            f"<thead><tr>{headers}</tr></thead><tbody><tr>{cells}</tr></tbody>"
            "</table></figure>"
        )
    document = HTML(string=f"<style>{_font_faces()}{css}</style><main>{body}</main>").render()
    measured = []
    for page in document.pages:
        box = page._page_box
        left, right = box.margin_left, box.margin_left + box.width
        for item in box.descendants():
            tag = item.element_tag or ""
            if tag.endswith("svg") or tag in {"table", "th", "td"}:
                measured.append(tag)
                assert item.position_x >= left - 0.01
                assert item.position_x + item.width <= right + 0.01, (
                    kind,
                    tag,
                    item.position_x + item.width,
                    right,
                )
    assert measured


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="WeasyPrint nativo se verifica en CI PDF")
def test_h3_pdf_final_muestra_procedencia_y_supuestos(tmp_path: Path) -> None:
    """La evidencia final H3 se publica por el job PDF para inspección visual del writer."""
    import os

    from bayesrisk import Provision

    pypdf = pytest.importorskip("pypdf")
    directory = Path(os.environ.get("BAYESRISK_H3_PDF_EVIDENCE", str(tmp_path)))
    frame = pd.DataFrame(
        {
            "fecha": ["2026-01-01"] * 2,
            "cartera": ["A"] * 2,
            "exposicion": [100.0] * 2,
            "pd": [0.1, 0.9],
            "lgd": [0.2, 0.8],
        }
    )
    p = Provision(
        frame,
        as_of="fecha",
        portfolio="cartera",
        exposure="exposicion",
        pd="pd",
        lgd="lgd",
        run_dir=directory,
        formats=["pdf", "csv"],
    )
    p.run(raise_on_error=True)
    path = next((p.project_dir / "reports").glob("*.pdf"))
    reader = pypdf.PdfReader(path)
    # El estilo del documento convierte los encabezados a mayúsculas. La extracción
    # puede introducir saltos de línea; el gate exige el contenido, no su capitalización.
    text = " ".join(" ".join(page.extract_text() for page in reader.pages).split()).casefold()
    assert "supuestos" in text and "pd externa" in text
    assert "prorratea" in text and "74" in text
    # Los nombres largos se parten visualmente entre líneas; deben conservar todos sus
    # caracteres y corresponder al adjunto realmente entregado.
    detail = next((p.project_dir / "reports").glob("*provisioning_internal_detail.csv"))
    assert detail.name.casefold() in "".join(text.split())


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="WeasyPrint nativo se verifica en CI PDF")
def test_h3_pdf_entrenamiento_y_aplicacion_conservan_declaracion(tmp_path: Path) -> None:
    """PDF final de las dos etapas B, con diagnóstico y límites institucionales visibles."""
    import os

    from pypdf import PdfReader

    from bayesrisk import Lgd, Provision
    from bayesrisk.ui.datasets import materialize

    directory = Path(os.environ.get("BAYESRISK_H3_PDF_EVIDENCE", str(tmp_path)))
    p = Lgd(
        materialize("lgd_historia_sintetica", workdir=directory),
        target="lgd_observada",
        features=["deuda_ingreso", "antiguedad_meses"],
        entity="deudor",
        sample="muestra",
        default="incumplio",
        resolved="resuelto",
        id="loan_id",
        run_dir=directory,
        purpose="Prueba funcional con datos inventados",
        assumptions=["Entidad declarada; objetivo sintético; disponibilidad declarada"],
        limitations=["No acredita independencia del pipeline completo ni transportabilidad"],
        formats=["pdf", "csv"],
    ).run(raise_on_error=True)
    frame = pd.DataFrame(
        {
            "deuda_ingreso": [0.2, 1.0],
            "antiguedad_meses": [12.0, 36.0],
            "fecha": ["2026-01-01"] * 2,
            "cartera": ["A"] * 2,
            "exposicion": [100.0] * 2,
            "pd": [0.1, 0.9],
        }
    )
    q = Provision(
        frame,
        as_of="fecha",
        portfolio="cartera",
        exposure="exposicion",
        pd="pd",
        lgd=p.model_,
        run_dir=directory,
        name="aplicacion_lgd",
        formats=["pdf", "csv"],
    )
    q.run(raise_on_error=True)
    for project, title in ((p, "entrenamiento lgd"), (q, "provisión interna")):
        path = next((project.project_dir / "reports").glob("*.pdf"))
        text = " ".join(
            " ".join(page.extract_text() for page in PdfReader(path).pages).split()
        ).casefold()
        for literal in (
            title,
            "objetivo sintético",
            "disponibilidad declarada",
            "transportabilidad",
        ):
            assert literal in text
        if project is p:
            for literal in ("evaluación", "entrenamiento", "media de entrenamiento", "coeficiente"):
                assert literal in text
        else:
            assert "no se reajustó" in text


def _lineage() -> LineageBundle:
    """Lineage fijo mínimo para el bundle sintético."""
    return LineageBundle(
        git_sha="abc123",
        git_dirty=False,
        data_hash="data123456789abcdef",
        config_hash="cfg123456789abcdef",
        root_seed=42,
        uv_lock_hash="uv123",
        library_versions={"bayesrisk": "0.1.0"},
        determinism_caveats=["fixture controlado"],
        created_at=datetime(2026, 6, 24, 9, 30, tzinfo=UTC),
        schema_version="1.0.0",
    )


def _bundle() -> ReportInputBundle:
    """Bundle mínimo válido que renderiza HTML y sirve para escribir el PDF."""
    lineage = _lineage()
    sections = (
        ReportSection(
            id="model",
            title="Modelo PD",
            status="included",
            source_domain="model",
            source_key="card",
            payload={"pdo": 20, "offset": 600},
        ),
    )
    return ReportInputBundle(
        lineage=lineage,
        cards={"model": {"selected_features": ("saldo", "mora")}},
        tables={},
        figures={},
        sections=sections,
        missing_sections=(),
    )


def _coefficients_table() -> pd.DataFrame:
    """Tabla de coeficientes sintética (artefacto y card embebida) para el step end-to-end."""
    return pd.DataFrame(
        {"feature": ["mora", "saldo"], "beta": [-0.0, 1.25], "p_value": [0.04, 0.03]}
    )


def _performance_table() -> pd.DataFrame:
    """Tabla de performance mínima para el step end-to-end."""
    return pd.DataFrame({"decile": [2, 1], "pd": [0.1, 0.2], "default_rate": [0.05, 0.15]})


def _card(domain: str) -> dict[str, Any]:
    """Card sintética con ``metric_sections`` serializable y una tabla embebida en model."""
    if domain == "model":
        return {
            "summary": "model-card",
            "selected_features": ("saldo", "mora"),
            "embedded_table": _coefficients_table(),
            "metric_sections": {"model": {"p_value_max": 0.041}},
        }
    if domain == "performance":
        return {
            "summary": "performance-card",
            "metric_sections": {"performance": {"auc": 0.74321, "ks": 0.31234}},
        }
    if domain == "stability":
        return {
            "summary": "stability-card",
            "metric_sections": {"stability": {"score_psi": {"max_psi": 0.271, "band": "review"}}},
        }
    return {"summary": f"{domain}-card", "metric_sections": {domain: {"ok": 1}}}


def _study_with_report_artifacts(*, config: ReportConfig) -> Study:
    """``Study`` con las ocho cards requeridas y tablas de reporte, listo para ``ReportStep``."""
    study = Study(BayesRiskConfig(report=config))
    study.run_context.lineage = _lineage()
    for domain, key in REPORT_REQUIRED_CARDS:
        study.artifacts.set(domain, key, _card(domain))
    study.artifacts.set("performance", "performance_table", _performance_table())
    study.artifacts.set("model", "coefficients", _coefficients_table())
    return study


# ─────────────────────────── (a) render_pdf real (skipif weasyprint) ───────────────────────────


@pytest.mark.skipif(
    not _HAS_WEASYPRINT,
    reason="requiere el extra pdf (WeasyPrint + nativas Pango/HarfBuzz/libffi)",
)
def test_render_pdf_genera_pdf_valido_con_texto_extraible() -> None:
    """``render_pdf`` produce un PDF válido (``%PDF``, ≥1 página) con el texto extraíble."""
    from pypdf import PdfReader

    pdf = render_pdf(f"<h1>bayesrisk</h1><p>{_MARCA}</p>")

    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 0
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 1
    text = "".join(page.extract_text() for page in reader.pages)
    assert _MARCA in text


# ─────────────────────── (b) PdfReportRenderer real (skipif weasyprint) ───────────────────────


@pytest.mark.skipif(
    not _HAS_WEASYPRINT,
    reason="requiere el extra pdf (WeasyPrint + nativas Pango/HarfBuzz/libffi)",
)
def test_pdf_renderer_escribe_pdf_valido_y_devuelve_manifest_html(tmp_path: Path) -> None:
    """``PdfReportRenderer`` habilitado escribe ``{basename}.pdf`` válido y devuelve manifest."""
    renderer = PdfReportRenderer(ReportConfig(pdf=PdfRenderConfig(enabled=True)))
    manifest = renderer.render(_bundle(), output_dir=str(tmp_path))

    assert manifest.output_format == "html"
    html_path = tmp_path / "scorecard_report.html"
    pdf_path = tmp_path / "scorecard_report.pdf"
    assert html_path.is_file()
    assert pdf_path.is_file()
    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 0


@pytest.mark.skipif(
    not _HAS_WEASYPRINT,
    reason="requiere el extra pdf (WeasyPrint + nativas Pango/HarfBuzz/libffi)",
)
def test_write_pdf_from_html_escribe_pdf_valido_y_devuelve_path(tmp_path: Path) -> None:
    """``write_pdf_from_html`` escribe ``{basename}.pdf`` válido y devuelve su ``Path`` real."""
    renderer = PdfReportRenderer(ReportConfig())
    html = HtmlReportRenderer.from_config(renderer.config).render(_bundle())

    path = renderer.write_pdf_from_html(html, output_dir=str(tmp_path))

    assert path == tmp_path / "scorecard_report.pdf"
    assert path.is_file()
    assert path.read_bytes()[:4] == b"%PDF"


@pytest.mark.skipif(
    not _HAS_WEASYPRINT,
    reason="requiere el extra pdf (WeasyPrint + nativas Pango/HarfBuzz/libffi)",
)
def test_report_step_formats_pdf_escribe_pdf_real(tmp_path: Path) -> None:
    """``ReportStep`` con ``"pdf"`` en ``formats`` escribe un PDF real y lo refleja en ``pdf_path``.

    Cablea el objetivo de B6 de punta a punta: ``formats`` pide el PDF, el step lo genera del MISMO
    HTML renderizado y ``ReportResult.pdf_path`` apunta al archivo en disco. El PDF NO entra al
    manifest (sigue siendo el del HTML determinístico).
    """
    cfg = ReportConfig(
        output_dir=str(tmp_path),
        formats=("pdf",),
        sections=SectionPolicyConfig(max_table_rows=10),
    )
    study = _study_with_report_artifacts(config=cfg)

    result = ReportStep.from_config(cfg).execute(study, np.random.default_rng(20_240_629))

    assert isinstance(result, ReportResult)
    assert result.pdf_path == str(tmp_path / "scorecard_report.pdf")
    pdf_file = tmp_path / "scorecard_report.pdf"
    assert pdf_file.is_file()
    assert pdf_file.read_bytes()[:4] == b"%PDF"
    assert result.manifest.output_format == "html"


@pytest.mark.skipif(
    not _HAS_WEASYPRINT,
    reason="requiere el extra pdf (WeasyPrint + nativas Pango/HarfBuzz/libffi)",
)
def test_el_pdf_incrusta_roboto_y_lleva_la_pagina_ejecutiva(tmp_path: Path) -> None:
    """Capa C2 (corre en el job `test-pdf` de CI, Linux): el PDF se dibuja con la fuente del
    sitio incrustada desde el CSS —no con la que tenga el runner— y trae la página ejecutiva de
    C1 tras la portada. Se verifica sobre el artefacto: los `BaseFont` de la primera página
    nombran Roboto y el texto extraído contiene la página."""
    from pypdf import PdfReader

    cfg = ReportConfig(
        output_dir=str(tmp_path),
        formats=("pdf",),
        sections=SectionPolicyConfig(max_table_rows=10),
    )
    study = _study_with_report_artifacts(config=cfg)
    result = ReportStep.from_config(cfg).execute(study, np.random.default_rng(20_240_629))
    assert result.pdf_path is not None
    reader = PdfReader(result.pdf_path)
    fuentes: set[str] = set()
    for page in reader.pages:
        recursos = page.get("/Resources") or {}
        for fuente in (recursos.get("/Font") or {}).values():
            fuentes.add(str(fuente.get_object().get("/BaseFont")))
    assert any("Roboto" in nombre for nombre in fuentes), fuentes
    texto = "".join(page.extract_text() for page in reader.pages)
    assert "Resultados del scorecard" in texto
    assert "Resumen ejecutivo" not in texto
    assert texto.index("Resultados del scorecard") < texto.index("Introducción")


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="WeasyPrint nativo se verifica en CI PDF")
def test_documental_pdf_final_conserva_1001_filas_indices_fuentes_y_enlaces(tmp_path: Path) -> None:
    """Artefacto publicable del gate B: lectura compacta más soporte íntegro, sin demo."""
    import json
    import os

    from pypdf import PdfReader
    from test_documentary_layout import bundle_documental
    from weasyprint import HTML

    bundle, config, _ = bundle_documental(1001)
    html = HtmlReportRenderer(config).render(bundle)
    rendered = HTML(string=html).render()
    # El árbol de páginas permite medir el ancho efectivo, no sólo el CSS declarado.
    cells = []
    for page in rendered.pages:
        for box in page._page_box.descendants():
            if box.element_tag == "td" and type(box).__name__ == "TextBox":
                assert box.style["font_size"] >= 10 * 96 / 72 - 0.01
                assert box.position_x >= 0 and box.position_x + box.width <= page.width + 1
                cells.append(box)
    assert cells
    destination = Path(os.environ.get("BAYESRISK_DOCUMENTARY_PDF_EVIDENCE", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    payload = rendered.write_pdf()
    (destination / "scorecard-integridad.pdf").write_bytes(payload)
    (destination / "scorecard-integridad.html").write_text(html, encoding="utf-8")
    reader = PdfReader(BytesIO(payload))
    text = "\n".join(p.extract_text() for p in reader.pages)
    for i in range(1001):
        assert f"fuente_{i}" in text and f"variable_{i}" in text
    assert "0.12345678901234566" in text
    links = sum(len(p.get("/Annots", ())) for p in reader.pages)
    assert links > 0
    fonts = {
        str(f.get_object().get("/BaseFont"))
        for page in reader.pages
        for f in (page.get("/Resources", {}).get("/Font", {})).values()
    }
    assert any("Roboto" in f for f in fonts)
    (destination / "medicion.json").write_text(
        json.dumps(
            {
                "pages": len(reader.pages),
                "rows": 1001,
                "links": links,
                "fonts": sorted(fonts),
                "table_text_boxes": len(cells),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="WeasyPrint nativo se verifica en CI PDF")
def test_documental_pdf_corrida_completa_del_dataset_del_paquete(tmp_path: Path) -> None:
    """Conserva el entregable real de F1 con escala, además del caso adversarial de 1001 filas."""
    import os

    from pypdf import PdfReader

    import bayesrisk
    from bayesrisk.core.config import BayesRiskConfig
    from bayesrisk.ui.datasets import materialize
    from bayesrisk.ui.presets import standard_preset

    destination = Path(os.environ.get("BAYESRISK_DOCUMENTARY_PDF_EVIDENCE", str(tmp_path)))
    preset = standard_preset()
    source = materialize(preset["dataset_id"], workdir=tmp_path / "data")
    raw = preset["config"]
    raw["data"]["load"]["source"] = str(source)
    raw["master_scale"] = {}
    steps = raw["run"].get("steps")
    if steps and "master_scale" not in steps:
        steps.insert(steps.index("report"), "master_scale")
    raw["report"]["output_dir"] = str(destination / "corrida-completa")
    raw["report"]["formats"] = ["pdf"]  # HTML es base always-on, no un formato adicional.
    config = BayesRiskConfig.model_validate(raw)
    study = bayesrisk.run(config, run_dir=tmp_path / "run")
    assert study.run_context.status == "done", study.run_context.error
    pdf = destination / "corrida-completa" / f"{config.report.basename}.pdf"
    text = "\n".join(page.extract_text() for page in PdfReader(pdf).pages)
    for expected in ("Resultados del scorecard", "Evidencia íntegra", "calibración pendiente"):
        assert expected in text
    assert study.artifacts.get("master_scale", "grade_table") is not None


# ─────────────────────── (c) fallback SIN weasyprint (corre SIEMPRE) ───────────────────────


def _bloquear_weasyprint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fuerza ``ModuleNotFoundError`` al importar ``weasyprint`` (ausencia determinista)."""
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "weasyprint":
            raise ModuleNotFoundError("weasyprint")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_render_pdf_sin_weasyprint_lanza_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``render_pdf`` traduce la ausencia de WeasyPrint a ``ReportDependencyError`` accionable."""
    _bloquear_weasyprint(monkeypatch)
    with pytest.raises(ReportDependencyError, match="WeasyPrint"):
        render_pdf("<h1>bayesrisk</h1>")


def _romper_nativas_de_weasyprint(monkeypatch: pytest.MonkeyPatch) -> None:
    """WeasyPrint instalado pero SIN sus librerías nativas: el import levanta ``OSError``.

    Es el escenario real de ``pip install bayesrisk[pdf]`` en un macOS o un Windows sin Pango: el
    paquete de Python está, las librerías del sistema no.
    """
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals_: Any = None,
        locals_: Any = None,
        fromlist: Any = (),
        level: int = 0,
    ) -> Any:
        if name == "weasyprint":
            raise OSError("cannot load library 'libgobject-2.0-0'")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_render_pdf_sin_librerias_nativas_lanza_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Las nativas ausentes se traducen a ``ReportDependencyError``, no escapan como ``OSError``.

    Si el ``OSError`` escapa crudo, ``fail_if_unavailable=False`` no lo atrapa y la corrida entera
    muere: el usuario pierde hasta el HTML, que sí se podía generar.
    """
    _romper_nativas_de_weasyprint(monkeypatch)
    with pytest.raises(ReportDependencyError, match="nativas"):
        render_pdf("<h1>bayesrisk</h1>")


def test_pdf_renderer_degrada_sin_librerias_nativas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Con las nativas rotas y ``fail_if_unavailable=False``, la corrida SIGUE y entrega el HTML."""
    _romper_nativas_de_weasyprint(monkeypatch)

    renderer = PdfReportRenderer(
        ReportConfig(pdf=PdfRenderConfig(enabled=True, fail_if_unavailable=False))
    )
    with pytest.warns(RuntimeWarning):
        manifest = renderer.render(_bundle(), output_dir=str(tmp_path / "degradado"))

    assert manifest.output_format == "html"
    assert (tmp_path / "degradado" / "scorecard_report.html").is_file()
    assert not (tmp_path / "degradado" / "scorecard_report.pdf").exists()


def test_pdf_renderer_degrada_o_falla_sin_weasyprint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Sin WeasyPrint: ``fail_if_unavailable=False`` degrada a HTML; ``True`` re-lanza."""
    _bloquear_weasyprint(monkeypatch)
    bundle = _bundle()

    fallback = PdfReportRenderer(
        ReportConfig(pdf=PdfRenderConfig(enabled=True, fail_if_unavailable=False))
    )
    with pytest.warns(RuntimeWarning, match="falta WeasyPrint"):
        manifest = fallback.render(bundle, output_dir=str(tmp_path / "fallback"))
    assert manifest.output_format == "html"
    assert (tmp_path / "fallback" / "scorecard_report.html").is_file()
    assert not (tmp_path / "fallback" / "scorecard_report.pdf").exists()

    strict = PdfReportRenderer(
        ReportConfig(pdf=PdfRenderConfig(enabled=True, fail_if_unavailable=True))
    )
    with pytest.raises(ReportDependencyError, match="WeasyPrint"):
        strict.render(bundle, output_dir=str(tmp_path / "strict"))


def test_write_pdf_from_html_degrada_o_falla_sin_weasyprint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``write_pdf_from_html`` sin WeasyPrint: degrada a ``None`` (False) o re-lanza (True)."""
    _bloquear_weasyprint(monkeypatch)
    html = "<h1>bayesrisk</h1>"

    lenient = PdfReportRenderer(ReportConfig(pdf=PdfRenderConfig(fail_if_unavailable=False)))
    with pytest.warns(RuntimeWarning, match="falta WeasyPrint"):
        path = lenient.write_pdf_from_html(html, output_dir=str(tmp_path / "lenient"))
    assert path is None
    assert not (tmp_path / "lenient" / "scorecard_report.pdf").exists()

    strict = PdfReportRenderer(ReportConfig(pdf=PdfRenderConfig(fail_if_unavailable=True)))
    with pytest.raises(ReportDependencyError, match="WeasyPrint"):
        strict.write_pdf_from_html(html, output_dir=str(tmp_path / "strict"))


def test_warning_del_fallback_distingue_nativas_ausentes_de_paquete_ausente(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """El warning del fallback dice CUÁL de los dos fallos ocurrió, no un genérico.

    Es el caso más común fuera de Linux: ``pip install bayesrisk[pdf]`` sí instaló WeasyPrint, pero
    Pango/HarfBuzz/libffi no están en el sistema y el import revienta con ``OSError``. Un warning
    genérico ("WeasyPrint no está disponible") mandaba al usuario a reinstalar un paquete que ya
    tenía, escondiendo que lo que falta es una librería del sistema. ``render_pdf`` ya distinguía
    ambos casos; el fallback descartaba ese diagnóstico al reformular el mensaje.
    """
    real_import = builtins.__import__

    def import_sin_nativas(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "weasyprint":
            raise OSError("cannot load library 'libpango-1.0-0': no such file")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_sin_nativas)

    renderer = PdfReportRenderer(ReportConfig(pdf=PdfRenderConfig(fail_if_unavailable=False)))
    with pytest.warns(RuntimeWarning) as capturado:
        path = renderer.write_pdf_from_html("<h1>bayesrisk</h1>", output_dir=str(tmp_path / "sin"))

    assert path is None
    mensaje = str(capturado[0].message)
    # El diagnóstico correcto: el paquete ESTÁ, faltan las nativas del sistema.
    assert "no encuentra sus librerías" in mensaje
    assert "libpango" in mensaje, "el detalle del enlazador debe llegar al usuario"
    # Y NO el diagnóstico equivocado, que mandaba a reinstalar el extra.
    assert "falta WeasyPrint" not in mensaje


# ─────────────────────── (d) import liviano (corre SIEMPRE) ───────────────────────


def test_import_report_no_arrastra_weasyprint_por_subprocess() -> None:
    """``import bayesrisk.report`` NO importa WeasyPrint (import perezoso en ``render_pdf``)."""
    code = (
        "import sys;"
        # Bloquea weasyprint: si algo intentara importarlo en import-time, `import bayesrisk.report`
        # reventaría (ImportError) en vez de continuar.
        "sys.modules['weasyprint'] = None;"
        "import bayesrisk.report as report;"
        "assert report.__name__ == 'bayesrisk.report';"
        "assert sys.modules.get('weasyprint') is None;"
        "blocked=[m for m in ('matplotlib', 'plotly') if m in sys.modules];"
        "assert not blocked, blocked"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="requiere WeasyPrint y nativas")
def test_hlc_pdf_real_conserva_contexto_y_tablas_descriptivas() -> None:
    """La puerta PDF de CI ejerce el HTML de producto, no una tabla rearmada en el test."""
    from pypdf import PdfReader
    from test_validation_step import _scorecard_study

    from bayesrisk.report.builder import ReportBuilder
    from bayesrisk.validation.config import ValidationConfig
    from bayesrisk.validation.step import ValidationStep

    cfg = ValidationConfig(families=("calibration",), calibration={"binomial_by_grade": False})
    study = _scorecard_study(config=cfg)
    study.run_context.lineage = _lineage()
    ValidationStep(cfg).execute(study, np.random.default_rng(0))
    report_cfg = ReportConfig(sections={"missing_policy": "skip"})
    bundle = ReportBuilder(report_cfg).collect(study)
    html = HtmlReportRenderer(report_cfg).render(bundle)
    reader = PdfReader(BytesIO(render_pdf(html)))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Evaluación contextual: No evaluable" in text
    assert "contraste de calibración validado para este contexto" in text
    assert "diagnóstico descriptivo de calibración" in text.casefold()
    assert "Resultado convencional de HL y estado histórico" in text
    assert "PD mínima" in text
    assert "Bajo mínimo histórico" in text
    assert "FALTA-DATO-VAL-HL-CONTEXTO" not in text
