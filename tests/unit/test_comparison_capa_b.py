"""La capa B, parte 1, del SDD-34: la comparación en el informe, el notebook y el Excel (§6.3).

Comparaciones sobre resúmenes comparables sintéticos (los de ``test_comparison_step``), escritos
como ``comparable.json`` y comparados por la puerta guiada, que ahora declara ``report``. Se mide:

- el informe: su título, el capítulo «Comparación de modelos» con sus subsecciones, la lectura en
  la página ejecutiva con la «Elección», la metodología y, en IFRS 9, la provisión por etapa sin
  gráficos;
- los dos gráficos: la frontera marcada, los modelos fuera del gráfico declarados con su razón, el
  mismo SVG en el informe y en el ``_repr_html_`` del resumen, PNG en el Word, y determinista en el
  mismo proceso y en otro;
- ``Comparación.xlsx``: un libro único, celda a celda contra el resumen;
- una sola fuente (D-SIM-5): las celdas de las tablas del informe son las del resumen;
- la puerta guiada declara ``report`` sin mover el ``config_hash`` (``report`` es INFRA).
"""

from __future__ import annotations

import html as html_lib
import math
import re
import subprocess
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_comparison_step import _provision, _resumen

from bayesrisk.comparison.comparable import bytes_canonicos
from bayesrisk.core.config import config_hash
from bayesrisk.guided import Comparison

pytest.importorskip("matplotlib", reason="los gráficos de la comparación exigen el extra report")

_TITULOS = (
    "Discriminación y estabilidad: AUC frente a PSI común",
    "Discriminación y concentración: Gini frente al índice del BCE",
)


def _escribir(carpeta: Path, resumenes: list[dict[str, Any]]) -> list[Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for i, resumen in enumerate(resumenes):
        ruta = carpeta / f"r{i}" / "comparable.json"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(bytes_canonicos(resumen))
        rutas.append(ruta)
    return rutas


def _comparar(rutas: list[Path], run_dir: Path, name: str) -> Comparison:
    comp = Comparison(rutas, name=name, run_dir=run_dir)
    comp._echo = lambda _texto: None
    comp.run()
    assert comp.study.run_context.status == "done", comp.study.run_context.error
    return comp


@pytest.fixture(scope="module")
def entorno(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """Cinco scorecards —uno superado, uno sin OOT ni Holdout, uno sin escala— y dos provisiones."""
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        yield _armar(tmp_path_factory.mktemp("capa_b_cmp"))


def _armar(raiz: Path) -> dict[str, Any]:
    tramos = [0.10, 0.20, 0.40, 0.20, 0.10]
    scorecards = [
        _resumen("base", participacion=tramos),
        _resumen("parejo", participacion=[0.2, 0.2, 0.2, 0.2, 0.2]),
        _resumen(
            "ruidoso",
            riesgo=[0.0] * 300 + [1.0] * 300,
            participacion=tramos,
            psi=0.12,
            banda="review",
        ),
        _resumen("solo_desarrollo", evaluacion="desarrollo", participacion=tramos),
        _resumen("sin_escala"),
    ]
    comp = _comparar(_escribir(raiz / "sc", scorecards), raiz / "cmp", "comparacion")
    comp.choose("parejo", reason="misma discriminación, tramos parejos")
    provisiones = [
        _provision("f4", "cartera", [100.0, 300.0, 500.0]),
        _provision("horizonte", "cartera", [100.0, 250.0, 500.0]),
    ]
    ifrs9 = _comparar(_escribir(raiz / "pr", provisiones), raiz / "cmp", "provisiones")
    return {"raiz": raiz, "comp": comp, "ifrs9": ifrs9}


def _informe(comp: Comparison, sufijo: str = ".html") -> Path:
    rutas = sorted((comp._project_dir / "reports").rglob(f"comparison_report{sufijo}"))
    assert rutas, f"no hay comparison_report{sufijo} en {comp._project_dir}"
    return rutas[0]


def _texto_del_svg(svg: str) -> str:
    """El texto visible de un SVG, con los saltos del ajuste de línea como espacios."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", svg))


def _svgs(texto: str) -> list[str]:
    return re.findall(r"<svg\b.*?</svg>", texto, flags=re.DOTALL)


# ── 1. El informe ────────────────────────────────────────────────────────────────────────────


def test_el_informe_tiene_el_capitulo_de_la_comparacion(entorno: dict[str, Any]) -> None:
    comp = entorno["comp"]
    documento = _informe(comp).read_text(encoding="utf-8")
    assert "Informe de Comparación de Modelos</h1>" in documento
    assert 'content: "Informe de Comparación de Modelos — CONFIDENCIAL"' in documento
    for seccion in (
        "comparison",
        "comparison.reading",
        "comparison.discrimination",
        "comparison.concentration",
        "comparison.variables",
        "comparison.choice",
    ):
        assert f'data-section-id="{seccion}"' in documento, seccion
    assert 'data-section-id="comparison.provision"' not in documento
    assert "Cómo se comparan los modelos" in documento
    # La página ejecutiva dice la «Elección», no «Validación técnica», y trae la lectura.
    assert "<dt>Elección</dt>" in documento
    assert "Validación técnica" not in documento
    resumen = comp.summary("comparison")
    for linea in resumen.lines:
        texto = html_lib.escape(linea if linea.endswith(".") else f"{linea}.", quote=False)
        assert documento.count(texto) >= 2, linea  # la página ejecutiva y el capítulo
    for alerta in resumen.alerts:
        assert html_lib.escape(f"Qué revisar: {alerta}", quote=False) in documento, alerta
    assert "La institución eligió parejo, con este motivo" in documento


def test_las_tablas_del_informe_son_las_del_resumen(entorno: dict[str, Any]) -> None:
    """D-SIM-5: cada celda de la tabla de modelos del informe es la del resumen, ya escrita."""
    from bayesrisk.guided.summaries import comparison_report_extras
    from bayesrisk.report.document import COMPARISON_MODELS_TABLE

    comp = entorno["comp"]
    tablas = {k: (c, f) for k, c, f in comparison_report_extras(comp.study)["tables"]}
    columnas, filas = tablas[COMPARISON_MODELS_TABLE]
    resumen = comp.summary("comparison").to_dict()["table"]
    for fila in filas:
        original = next(r for r in resumen["rows"] if r[0] == fila[0])
        for columna, celda in zip(columnas, fila, strict=True):
            assert celda == original[resumen["columns"].index(columna)], (fila[0], columna)
    documento = _informe(comp).read_text(encoding="utf-8").replace("<wbr>", "")
    for fila in filas:
        for celda in fila:
            assert html_lib.escape(celda, quote=False) in documento, celda


def test_los_dos_graficos_estan_en_el_informe_con_la_frontera_marcada(
    entorno: dict[str, Any],
) -> None:
    documento = _informe(entorno["comp"]).read_text(encoding="utf-8")
    svgs = [s for s in _svgs(documento) if any(t in s for t in _TITULOS)]
    assert len(svgs) == 2
    estabilidad, concentracion = svgs
    assert (
        "En la frontera" in estabilidad and "Superado por un modelo de la frontera" in estabilidad
    )
    assert "base (referencia)" in estabilidad
    # Los modelos fuera del gráfico se declaran con su razón (SDD-34 §3.5, §8).
    estabilidad, concentracion = _texto_del_svg(estabilidad), _texto_del_svg(concentracion)
    assert "solo_desarrollo (sin OOT ni Holdout: cifras de Desarrollo)" in estabilidad
    assert "sin_escala (sin escala maestra)" in concentracion
    # Sin escala, el modelo sí está en el primer gráfico: sólo le falta la segunda cifra del otro.
    assert "sin_escala" in estabilidad and "sin_escala (" not in estabilidad


def test_el_svg_del_informe_es_el_del_resumen(entorno: dict[str, Any]) -> None:
    """Una sola fuente: el ``_repr_html_`` del resumen lleva el mismo SVG que el informe."""
    comp = entorno["comp"]
    etapa = comp.summary("comparison")
    assert [t for t, _svg in etapa.charts] == list(_TITULOS)
    cuaderno = etapa._repr_html_()
    documento = _informe(comp).read_text(encoding="utf-8")
    for _titulo, svg in etapa.charts:
        assert cuaderno.count(svg) == 1
        assert svg in documento
    # El gráfico vive sólo en el notebook: ni el texto ni el JSON de la pantalla lo traen.
    assert "<svg" not in etapa.text()
    assert "charts" not in etapa.to_dict()


def test_el_word_lleva_los_graficos_como_png(entorno: dict[str, Any]) -> None:
    pytest.importorskip("docx", reason="el Word exige el extra report")
    with zipfile.ZipFile(_informe(entorno["comp"], ".docx")) as libro:
        imagenes = [n for n in libro.namelist() if n.startswith("word/media/")]
        texto = libro.read("word/document.xml").decode("utf-8")
    assert len(imagenes) >= 2
    assert all(n.endswith(".png") for n in imagenes)
    assert "Informe de Comparación de Modelos" in texto
    assert "Comparación de modelos" in texto


def test_el_informe_de_provisiones_tiene_la_provision_por_etapa_sin_graficos(
    entorno: dict[str, Any],
) -> None:
    documento = _informe(entorno["ifrs9"]).read_text(encoding="utf-8")
    assert "Informe de Comparación de Modelos</h1>" in documento
    for seccion in ("comparison.reading", "comparison.provision", "comparison.choice"):
        assert f'data-section-id="{seccion}"' in documento, seccion
    for seccion in (
        "comparison.discrimination",
        "comparison.concentration",
        "comparison.variables",
    ):
        assert f'data-section-id="{seccion}"' not in documento, seccion
    assert not any(t in documento for t in _TITULOS)
    assert "La institución no registró una elección" in documento
    assert "En provisiones, más no es mejor" in documento


# ── 2. Los gráficos: deterministas ───────────────────────────────────────────────────────────


_SONDA = """
import sys, json
import pandas as pd
from bayesrisk.report.charts import comparison_charts
modelos = pd.read_pickle(sys.argv[1])  # exacto: el JSON de pandas redondea a 10 cifras
card = json.loads(open(sys.argv[2], encoding="utf-8").read())
for _eje, _t, svg in comparison_charts(modelos, card, fmt="svg"):
    sys.stdout.buffer.write(svg.encode("utf-8") + b"\\x00")
"""


def test_el_svg_es_determinista_en_el_mismo_proceso_y_en_otro(
    entorno: dict[str, Any], tmp_path: Path
) -> None:
    import json

    from bayesrisk.report.charts import comparison_charts

    comp = entorno["comp"]
    modelos = comp.study.artifacts.get("comparison", "models")
    card = comp.study.artifacts.get("comparison", "card").model_dump(mode="json")
    primera = [svg for _e, _t, svg in comparison_charts(modelos, card)]
    segunda = [svg for _e, _t, svg in comparison_charts(modelos, card)]
    assert len(primera) == 2 and primera == segunda
    archivo_modelos = tmp_path / "modelos.pkl"
    modelos.to_pickle(archivo_modelos)
    archivo_card = tmp_path / "card.json"
    archivo_card.write_text(json.dumps(card), encoding="utf-8")
    sonda = tmp_path / "sonda.py"
    sonda.write_text(_SONDA, encoding="utf-8")
    import os

    entorno_proc = {**os.environ, "PYTHONHASHSEED": "12345"}
    salida = subprocess.run(
        [sys.executable, "-X", "utf8", str(sonda), str(archivo_modelos), str(archivo_card)],
        capture_output=True,
        check=True,
        env=entorno_proc,
        timeout=180,
    ).stdout
    otra = [parte.decode("utf-8") for parte in salida.split(b"\x00") if parte]
    assert otra == primera


# ── 3. Comparación.xlsx ──────────────────────────────────────────────────────────────────────


def _celda(valor: Any) -> Any:
    """La celda comparable: vacío como ``None`` y los números redondeados a 12 cifras."""
    if valor is None or valor == "" or (isinstance(valor, float) and math.isnan(valor)):
        return None
    if isinstance(valor, int | float) and not isinstance(valor, bool):
        return float(f"{float(valor):.12g}")
    return valor


def _cotejar_libro(comp: Comparison, hojas_esperadas: list[str]) -> None:
    openpyxl = pytest.importorskip("openpyxl", reason="Comparación.xlsx exige el extra excel")
    from bayesrisk.guided.summaries import (
        TITULO_CORRIDAS_COMPARADAS,
        TITULO_MUESTRAS_COMPARADAS,
        TITULO_PROVISION_POR_ETAPA,
        TITULO_PRUEBAS_PAREADAS,
        TITULO_VARIABLES_COMPARADAS,
    )

    escritos = comp.export_excel()
    assert [p.name for p in escritos] == ["Comparación.xlsx"]
    wb = openpyxl.load_workbook(escritos[0], read_only=True)
    assert wb.sheetnames == hojas_esperadas
    resumen = comp.summary("comparison")
    extra = {titulo: tabla for titulo, tabla, _f in resumen.extra_tables}
    por_hoja = {
        "Modelos": resumen.table,
        "Pruebas": extra.get(TITULO_PRUEBAS_PAREADAS),
        "Muestras": extra.get(TITULO_MUESTRAS_COMPARADAS),
        "Variables": extra.get(TITULO_VARIABLES_COMPARADAS),
        "Provisión por etapa": extra.get(TITULO_PROVISION_POR_ETAPA),
        "Corridas": extra.get(TITULO_CORRIDAS_COMPARADAS),
    }
    for hoja in hojas_esperadas:
        if hoja in {"Resumen", "Índice"}:
            continue
        tabla = por_hoja[hoja]
        filas = [[_celda(c) for c in fila] for fila in wb[hoja].iter_rows(values_only=True)]
        assert filas[0] == [str(c) for c in tabla.columns], hoja
        esperadas = [[_celda(c) for c in fila] for fila in tabla.itertuples(index=False)]
        assert filas[1:] == esperadas, hoja
    lineas = [fila[0] for fila in wb["Resumen"].iter_rows(min_row=2, values_only=True)]
    assert lineas == [*resumen.lines, *(f"⚠ {a}" for a in resumen.alerts)]
    indice = [fila[0] for fila in wb["Índice"].iter_rows(min_row=2, values_only=True)]
    assert indice == hojas_esperadas[:-1]


def test_comparacion_xlsx_es_un_libro_unico_con_las_tablas_del_resumen(
    entorno: dict[str, Any],
) -> None:
    _cotejar_libro(
        entorno["comp"],
        ["Resumen", "Modelos", "Pruebas", "Muestras", "Variables", "Corridas", "Índice"],
    )


def test_el_libro_de_provisiones_trae_la_provision_por_etapa(entorno: dict[str, Any]) -> None:
    _cotejar_libro(
        entorno["ifrs9"], ["Resumen", "Modelos", "Provisión por etapa", "Corridas", "Índice"]
    )


# ── 4. La puerta guiada declara el informe sin mover la identidad ───────────────────────────


def test_la_puerta_declara_report_sin_mover_el_config_hash(entorno: dict[str, Any]) -> None:
    comp = entorno["comp"]
    assert comp.config.report is not None
    assert tuple(comp.config.report.sections.required_sections) == ()
    sin_informe = comp.config.model_copy(update={"report": None})
    assert config_hash(sin_informe) == comp.config_hash


def test_una_oot_no_evaluable_queda_fuera_de_los_graficos_con_su_alerta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La alerta del resumen y la nota de los dos gráficos dicen por qué el modelo no está."""
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    sin_auc = _resumen("sin_auc", participacion=[0.2, 0.2, 0.2, 0.2, 0.2])
    oot = next(s for s in sin_auc["samples"] if s["sample"] == "oot")
    oot.update(auc=None, gini=None, ks=None, status="not_evaluable")
    ref = _resumen("ref", participacion=[0.1, 0.2, 0.4, 0.2, 0.1])
    comp = _comparar(_escribir(tmp_path / "sc", [ref, sin_auc]), tmp_path / "cmp", "oot")
    etapa = comp.summary("comparison")
    assert "La discriminación de sin_auc no es evaluable en OOT." in etapa.alerts
    assert len(etapa.charts) == 2
    for _titulo, svg in etapa.charts:
        assert "sin_auc (discriminación no evaluable en OOT)" in _texto_del_svg(svg)
