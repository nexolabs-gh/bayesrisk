"""El informe de una provisión IFRS 9 (FLUJO-GUIADO-IFRS9 capa C, D-ECL-12, enmienda §3.13).

Tres reglas, cada una con su control negativo:

1. **La página ejecutiva también para la familia IFRS 9.** «Resumen de la corrida» abre el informe
   de una provisión, tras la portada, con su resumen final —ejecución, **Supuestos** en lugar de
   «Validación técnica», las cinco cifras de la provisión, qué revisar, decisiones y archivos—,
   desde los mismos constructores que ``Ecl.summary()``, en HTML, Word y la fuente editable. Una
   corrida IFRS 9 cuyo resumen es del molde del scorecard sigue sin página.
2. **El cuerpo publica la curva.** El capítulo IFRS 9 gana la subsección de la curva de PD, antes
   de la ECL, con la PD acumulada por período y cartera —la misma tabla que la etapa «Curva de PD»
   del resumen— y los coeficientes del ajuste; el anexo C.2 conserva la card y el anexo B no las
   repite. La subsección atribuye la curva a la provisión sólo si la consumió tal cual.
3. **El scorecard no cambia**: su página ejecutiva lleva exactamente el payload de antes.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from bayesrisk.guided import Ecl
from bayesrisk.guided.summaries import CURVA_POR_CARTERA_TITULO, RESUMEN_FINAL_ROTULOS
from bayesrisk.report.builder import ReportBuilder
from bayesrisk.report.config import ReportConfig
from bayesrisk.report.document import EXECUTIVE_SUMMARY_ID, KEY_TABLES, table_title
from bayesrisk.report.results import ReportInputBundle
from bayesrisk.ui import datasets

pytest.importorskip("statsmodels", reason="la curva de PD exige el extra scoring")

_CURVA = "survival.pd_by_period"
_COEFICIENTES = "survival.coefficients"


def _ecl(datos: Path, run_dir: Path, **cambios: Any) -> Ecl:
    base: dict[str, Any] = {
        "id": "loan_id",
        "as_of": "as_of_date",
        "portfolio": "portfolio",
        "exposure": "ead",
        "lgd": "lgd",
        "rate": "eir",
        "days_past_due": "days_past_due",
        "default": "is_default",
        "duration": "duration",
        "event": "event",
        "period": "year",
        "horizon": 5,
        "covariates": ["days_past_due", "deuda_ingreso", "antiguedad_meses"],
        "run_dir": run_dir,
        "formats": ["md", "docx"],
    }
    base.update(cambios)
    ecl = Ecl(datos, **base)
    ecl._echo = lambda _texto: None
    return ecl


@pytest.fixture(scope="module")
def _semilla() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        yield


@pytest.fixture(scope="module")
def corrida(tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Ecl:
    """Una provisión completa con una decisión humana, para que la página la diga con su motivo."""
    datos = datasets.materialize("ifrs9_retail_latam", workdir=tmp_path_factory.mktemp("datos"))
    ecl = _ecl(datos, tmp_path_factory.mktemp("ecl"), name="informe")
    ecl.exclude("antiguedad_meses", reason="no viene en los próximos cierres")
    ecl.run()
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return ecl


def _informe(ecl: Ecl, sufijo: str) -> Path:
    resultado = ecl.study.artifacts.get("report", "result")
    ruta = Path(str(getattr(resultado, f"{sufijo}_path")))
    assert ruta.is_file(), ruta
    return ruta


@pytest.fixture(scope="module")
def html(corrida: Ecl) -> str:
    return _informe(corrida, "html").read_text(encoding="utf-8")


def _seccion(html: str, section_id: str) -> str:
    inicio = html.index(f'data-section-id="{section_id}"')
    inicio = html.rindex("<section", 0, inicio)
    return html[inicio : html.index("</section>", inicio)]


def _texto(fragmento: str) -> str:
    import html as html_mod

    sin_marcas = re.sub(r"<wbr>", "", fragmento)
    sin_marcas = re.sub(r"<[^>]+>", " ", sin_marcas)
    return re.sub(r"\s+", " ", html_mod.unescape(sin_marcas))


# ─────────────────────────── 1. la página ejecutiva de una provisión ───────────────────────────


def test_la_pagina_ejecutiva_abre_el_informe_de_una_provision(corrida: Ecl, html: str) -> None:
    portada = html.index('class="cover"')
    pagina = html.index(f'data-section-id="{EXECUTIVE_SUMMARY_ID}"')
    resumen_ejecutivo = html.index('id="exec-summary"')
    indice = html.index('data-kind="toc"')
    assert portada < pagina < resumen_ejecutivo < indice
    texto = _texto(_seccion(html, EXECUTIVE_SUMMARY_ID))
    final = corrida.summary()
    assert "Resumen de la corrida" in texto
    assert "Supuestos" in texto
    assert RESUMEN_FINAL_ROTULOS["validation"] not in texto
    assert final.assumptions
    for supuesto in final.assumptions:
        assert " ".join(supuesto.split()) in texto, supuesto
    assert len(final.figures) == 5
    for rotulo, valor in final.figures:
        assert rotulo in texto and valor in texto, (rotulo, valor)
    assert "no viene en los próximos cierres" in texto
    # La página no habla del scorecard ni de su validación.
    for palabra in ("malos", "Desarrollo", "Holdout", "validación técnica"):
        assert palabra not in texto, palabra


def test_word_y_fuente_editable_dicen_los_mismos_supuestos(corrida: Ecl) -> None:
    docx = pytest.importorskip("docx", reason="el Word exige el extra docx")
    supuestos = corrida.summary().assumptions
    documento = docx.Document(str(_informe(corrida, "docx")))
    parrafos = [p.text for p in documento.paragraphs]
    celdas = [c.text for t in documento.tables for fila in t.rows for c in fila.cells]
    palabra = "\n".join([*parrafos, *celdas])
    assert "Supuestos" in parrafos
    assert RESUMEN_FINAL_ROTULOS["validation"] not in palabra
    for supuesto in supuestos:
        assert supuesto in parrafos, supuesto

    qmd = _informe(corrida, "md").read_text(encoding="utf-8")
    pagina = qmd[: qmd.index("## Resumen ejecutivo")]
    literal = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", pagina)
    assert "**Supuestos**" in pagina
    assert f"**{RESUMEN_FINAL_ROTULOS['validation']}:**" not in pagina
    for supuesto in supuestos:
        assert f"- {supuesto}" in literal, supuesto


def test_un_resumen_del_molde_del_scorecard_no_abre_un_informe_ifrs9() -> None:
    """Gate de familia: la página de una corrida sin dominios del scorecard exige que su resumen
    sea el de una provisión; un payload del molde del scorecard no se emite."""
    cfg = ReportConfig(sections={"missing_policy": "skip"})
    base = {
        "lineage": _lineage(),
        "cards": {"provisioning_ifrs9": {"total_ecl_reported": 1.0, "total_ead": 10.0}},
        "tables": {},
        "figures": {},
        "sections": (),
    }
    molde = ReportInputBundle(**base, summary={"final": {"execution": "x"}, "error": None})
    cartera = ReportInputBundle(
        **base, summary={"final": {"execution": "x"}, "family": "cartera", "error": None}
    )
    assert EXECUTIVE_SUMMARY_ID not in [s.id for s in ReportBuilder(cfg).build_sections(molde)]
    assert EXECUTIVE_SUMMARY_ID in [s.id for s in ReportBuilder(cfg).build_sections(cartera)]


def test_el_payload_de_la_pagina_del_scorecard_no_cambia() -> None:
    """El informe del scorecard queda byte a byte: su página no gana familia ni supuestos."""
    import test_report_step as step_tests

    cfg = ReportConfig(sections={"missing_policy": "skip"})
    study = step_tests._study_with_report_artifacts(config=cfg)
    resumen = ReportBuilder(cfg).collect(study).summary
    assert resumen is not None
    assert set(resumen) == {"final", "labels", "sin_alertas", "sin_decisiones", "error"}
    assert resumen["labels"] == RESUMEN_FINAL_ROTULOS


# ───────────────────────────── 2. la curva en el cuerpo del informe ─────────────────────────────


def test_el_cuerpo_publica_la_curva_antes_de_la_ecl(html: str) -> None:
    assert KEY_TABLES["survival"] == (_CURVA, _COEFICIENTES)
    curva = html.index('data-section-id="ifrs9.survival"')
    ecl = html.index('data-section-id="ifrs9.provisioning_ifrs9"')
    assert curva < ecl
    seccion = _seccion(html, "ifrs9.survival")
    claves = re.findall(r'data-table-key="([^"]+)"', seccion)
    assert claves == [_CURVA, _COEFICIENTES]
    texto = _texto(seccion)
    assert "PD acumulada por período y cartera" in texto
    assert "Toda la cartera" in texto
    # El anexo B publica lo que el cuerpo no mostró; el C.2 conserva la card de la curva.
    anexo = re.findall(r'data-table-key="([^"]+)"', _seccion(html, "appendix_tables"))
    assert _CURVA not in anexo and _COEFICIENTES not in anexo
    assert 'data-section-id="appendix_parameters.survival"' in html


def test_la_curva_del_informe_es_la_del_resumen_de_la_etapa(corrida: Ecl) -> None:
    """Una sola fuente: la tabla del informe es la tabla adicional de «Curva de PD»."""
    config = corrida.config.report
    config = config.model_copy(
        update={"sections": config.sections.model_copy(update={"missing_policy": "skip"})}
    )
    tablas = ReportBuilder(config).collect(corrida.study).tables
    extra = dict((titulo, tabla) for titulo, tabla, _ in corrida.summary("survival").extra_tables)
    (titulo,) = extra
    assert titulo == CURVA_POR_CARTERA_TITULO == table_title(_CURVA)
    pd.testing.assert_frame_equal(tablas[_CURVA], extra[titulo])
    pd.testing.assert_frame_equal(
        tablas[_COEFICIENTES], corrida.study.artifacts.get("survival", "coefficients")
    )


def test_la_curva_se_atribuye_a_la_provision_solo_si_la_consumio_tal_cual() -> None:
    from bayesrisk.report import prose

    def cuerpo(card: dict[str, Any], params: dict[str, Any] | None = None) -> str:
        bundle = ReportInputBundle(
            lineage=_lineage(),
            cards={"survival": {"n_rows": 10}, "provisioning_ifrs9": card},
            tables={_CURVA: pd.DataFrame({"Período": [1]}), _COEFICIENTES: pd.DataFrame()},
            figures={},
            sections=(),
            pipeline_params={"provisioning_ifrs9": params or {}},
        )
        return " ".join(prose.results_body(bundle, "survival"))

    tal_cual = {"term_structure_source": "survival", "pit_mode": "ttc_only"}
    assert "La provisión de este capítulo parte de esta curva" in cuerpo(tal_cual)
    assert "tope" not in cuerpo(tal_cual)
    con_tope = cuerpo(tal_cual, {"pd": {"max_lifetime_periods": 3}})
    assert "sólo usa sus períodos hasta el 3" in con_tope
    vasicek = cuerpo({"term_structure_source": "survival", "pit_mode": "apply_vasicek"})
    escenarios = cuerpo({"term_structure_source": "forward", "pit_mode": "ttc_only"})
    for texto in (vasicek, escenarios):
        assert "parte de esta curva" not in texto
        assert "no usa esta curva tal cual" in texto
    assert "Vasicek" in vasicek
    assert "escenarios" in escenarios


# ──────────────────────────────────────────── helpers ────────────────────────────────────────────


def _lineage() -> Any:
    import test_report_pagina_ejecutiva as pagina

    return pagina._lineage()


def test_el_paquete_de_la_corrida_trae_el_informe_con_la_pagina(
    corrida: Ecl, tmp_path: Path
) -> None:
    """El artefacto final que circula —el ``.zip`` de ``export()``— lleva el HTML con la página."""
    paquete = corrida.export(tmp_path / "corrida.zip")
    with zipfile.ZipFile(paquete) as zf:
        nombres = [n for n in zf.namelist() if n.endswith(".html") and "/reports/" in f"/{n}"]
        assert nombres, zf.namelist()
        contenido = zf.read(nombres[0]).decode("utf-8")
    assert f'data-section-id="{EXECUTIVE_SUMMARY_ID}"' in contenido
    assert 'data-section-id="ifrs9.survival"' in contenido
