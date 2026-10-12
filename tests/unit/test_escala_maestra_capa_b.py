"""La escala maestra en la pantalla, el informe y el Excel (SDD-32 capa B, D-ESC-8 y D-ESC-9).

Los dos trabajos del scorecard la siembran encendida con sus dos esenciales; el informe gana la
subsección «Escala maestra y puntos de corte» con las líneas y las tablas del resumen de la etapa
(una sola fuente, D-SIM-5); el Excel, el libro ``11 Escala maestra`` —y las decisiones pasan al
``12``—; las tres puertas —guiada, YAML y pantalla— dan el mismo ``config_hash`` y los mismos
artefactos; y con las tres puertas cerradas la etapa es estable (D-SIM-1). Sin la escala, el
informe no cambia.
"""

from __future__ import annotations

import copy
import html as html_lib
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from _ui_f1 import write_stacked_behavior_parquet

import bayesrisk
from bayesrisk.core.config import config_hash, loads_config
from bayesrisk.guided import Scorecard

#: El id de la subsección en el HTML del informe: capítulo «Resultados», dominio de la escala.
_SUBSECCION = 'data-section-id="results.master_scale"'


@pytest.fixture(autouse=True)
def _usar_fake_binning_process(fake_binning_process: object) -> None:
    """OR-Tools revienta el proceso de pytest (SDD-32 §11): la formación corre con el doble."""
    del fake_binning_process


@pytest.fixture
def fuente(tmp_path: Path) -> Path:
    ruta = tmp_path / "cartera.parquet"
    write_stacked_behavior_parquet(ruta, repeats=50)
    return ruta


def _puerta(fuente: Path, tmp_path: Path, **kwargs: Any) -> Scorecard:
    base: dict[str, Any] = {
        "target": "bad_flag",
        "id": "loan_id",
        "cohort": "cohort",
        "oot_cohorts": ["oot"],
        "name": "escala",
        "run_dir": tmp_path / "corridas",
        "min_iv": 0.0,
    }
    base.update(kwargs)
    sc = Scorecard(fuente, **base)
    sc._echo = lambda _texto: None
    return sc


def _con_corte(fuente: Path, tmp_path: Path) -> Scorecard:
    sc = _puerta(fuente, tmp_path).run()
    corte = float(sc.study.artifacts.get("master_scale", "card").cuts[0])
    sc.set_cutoff(corte, reason="la del comité")
    sc.resume()
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    return sc


def _informe_guiado(tmp_path: Path) -> Path:
    """El informe de la última corrida guiada: ``<proyecto>/reports/`` (el previo, de respaldo)."""
    return tmp_path / "corridas" / "escala" / "reports" / "scorecard_report.html"


def _informe_de_la_pantalla(tmp_path: Path) -> Path:
    informes = list((tmp_path / "ui").rglob("report.html"))
    assert len(informes) == 1, informes
    return informes[0]


def _subseccion_de_la_escala(informe: Path) -> str:
    documento = informe.read_text(encoding="utf-8")
    inicio = documento.index(_SUBSECCION)
    return documento[inicio : documento.index("</section>", inicio)]


# ───────────────────────────── 1. La pantalla la siembra encendida ─────────────────────────────


@pytest.mark.parametrize("trabajo", ["scorecard_pd", "pd_y_lgd"])
def test_los_dos_trabajos_del_scorecard_la_siembran_encendida(trabajo: str) -> None:
    """D-ESC-8: corre por defecto en los trabajos del scorecard, tras la validación formal."""
    pytest.importorskip("fastapi", reason="el catálogo de trabajos vive en la capa ui")
    from test_jobs_ejecutables import _esqueleto

    from bayesrisk.core.config.effective_defaults import build_effective_defaults
    from bayesrisk.ui.jobs import list_jobs

    job = copy.deepcopy(next(j for j in list_jobs(incluir_referencia=True) if j["id"] == trabajo))
    secciones = list(job["sections"])
    assert secciones.index("master_scale") == secciones.index("validation") + 1
    assert "master_scale" not in job["latent_sections"]
    esqueleto = _esqueleto(job, build_effective_defaults())
    # Sembrada en blanco: los tramos los forman los datos y no hay corte de la institución;
    # validada, es la misma sección que siembra la puerta guiada.
    assert esqueleto["master_scale"] == {"grade_edges": None, "approval_cutoff": None}
    from bayesrisk.master_scale.config import MasterScaleConfig

    assert MasterScaleConfig.model_validate(esqueleto["master_scale"]) == MasterScaleConfig()


def test_la_seccion_declara_sus_dos_esenciales() -> None:
    """§13: las dos hojas son las dos decisiones de la institución; no hay «Avanzado»."""
    from bayesrisk.master_scale.config import MasterScaleConfig

    schema = MasterScaleConfig.model_json_schema()
    assert schema.get("ui_essentials_declared") is True
    for hoja in ("grade_edges", "approval_cutoff"):
        nodo = schema["properties"][hoja]
        assert nodo.get("ui_essential") is True, hoja
        assert nodo.get("ui_help"), hoja


# ─────────────────────────────── 2. El Excel: 11 y 12 ───────────────────────────────


def test_la_escala_tiene_el_libro_11_y_las_decisiones_pasan_al_12() -> None:
    from bayesrisk.guided.export import DECISIONS_BOOK, STAGE_BOOKS

    assert list(STAGE_BOOKS.items())[-1] == ("master_scale", "11 Escala maestra.xlsx")
    assert DECISIONS_BOOK == "12 Decisiones.xlsx"


def test_el_libro_de_la_escala_trae_sus_tablas_sin_repetirlas(fuente: Path, tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl", reason="el Excel opcional exige bayesrisk[excel]")
    sc = _con_corte(fuente, tmp_path)
    libros = {ruta.name: ruta for ruta in sc.export_excel()}
    assert list(libros)[-2:] == ["11 Escala maestra.xlsx", "12 Decisiones.xlsx"]
    libro = openpyxl.load_workbook(libros["11 Escala maestra.xlsx"], read_only=True)
    try:
        hojas = list(libro.sheetnames)
        lineas = [fila[0] for fila in libro["Resumen"].iter_rows(min_row=2, values_only=True)]
        indice = [fila[1] for fila in libro["Índice"].iter_rows(min_row=2, values_only=True)]
    finally:
        libro.close()
    resumen = sc.summary("master_scale")
    assert hojas[:3] == ["Resumen", "Decisión", "Tabla de puntos de corte"], hojas
    assert hojas[-1] == "Índice", hojas
    assert lineas[: len(resumen.lines)] == list(resumen.lines)
    # Las tablas completas del informe —por muestra y tramo, y los cortes con sus conteos— van tras
    # las del resumen; las dos que el informe arma desde el resumen no se repiten como texto.
    assert "Escala maestra por muestra y tramo" in indice, indice
    assert "Puntos de corte por muestra" in indice, indice
    assert "Escala maestra — los tramos y su PD" not in indice, indice
    assert indice.count("Tabla de puntos de corte") == 1, indice


# ──────────────────────────────── 3. El informe ────────────────────────────────


def test_el_informe_trae_la_escala_con_las_lineas_y_tablas_del_resumen(
    fuente: Path, tmp_path: Path
) -> None:
    sc = _con_corte(fuente, tmp_path)
    subseccion = _subseccion_de_la_escala(_informe_guiado(tmp_path))
    texto = html_lib.unescape(re.sub(r"<[^>]+>", " ", subseccion))
    texto = re.sub(r"\s+", " ", texto)
    assert "Escala maestra y puntos de corte" in texto
    resumen = sc.summary("master_scale")
    for linea in resumen.lines:
        assert re.sub(r"\s+", " ", linea).rstrip(".") in texto, linea
    for alerta in resumen.alerts:
        legible = re.sub(r"\s+", " ", alerta).rstrip(".")
        assert f"Qué revisar: {legible}" in texto, alerta
    assert "Escala maestra — los tramos y su PD" in texto
    assert "Tabla de puntos de corte" in texto
    assert "Corte de la institución" in texto
    # Las celdas son las del resumen, ya escritas (la PD del primer tramo, como la lee la persona).
    primera_pd = resumen.to_dict()["table"]["rows"][0][2]
    assert primera_pd in texto, primera_pd
    # El anexo completa lo que el cuerpo cura: las tres tablas completas de la etapa (con sus
    # conteos y contrastes) y la sección del config en los parámetros.
    documento = _informe_guiado(tmp_path).read_text(encoding="utf-8")
    assert 'data-section-id="appendix_parameters.master_scale"' in documento
    for titulo in (
        "Tramos de la escala maestra",
        "Escala maestra por muestra y tramo",
        "Puntos de corte por muestra",
    ):
        assert documento.count(titulo) == 1, titulo


def test_sin_la_escala_el_informe_no_la_menciona(fuente: Path, tmp_path: Path) -> None:
    """Una corrida sin la sección —el preset, un YAML de la 2.10.0— no gana la subsección."""
    sc = _puerta(fuente, tmp_path)
    informes = tmp_path / "informe_sin_escala"
    cfg = sc.config.model_copy(
        update={
            "master_scale": None,
            "report": sc.config.report.model_copy(update={"output_dir": str(informes)}),
        }
    )
    estudio = bayesrisk.run(cfg, run_dir=tmp_path / "sin_escala")
    assert estudio.run_context.status == "done", estudio.run_context.error
    documento = (informes / "scorecard_report.html").read_text(encoding="utf-8")
    assert _SUBSECCION not in documento
    assert "Escala maestra" not in documento


# ──────────────────────────────── 4. Las tres puertas ────────────────────────────────


@pytest.fixture
def cliente(tmp_path: Path) -> Any:
    pytest.importorskip("fastapi", reason="la pantalla exige el extra ui")
    from _ui_client import build_test_runtime, ui_client

    from bayesrisk.ui.settings import UiConfig

    settings = UiConfig(workdir=str(tmp_path / "ui"))
    with ui_client(settings, runtime=build_test_runtime(settings.workdir)) as c:
        yield c


def test_las_tres_puertas_dan_el_mismo_hash_y_los_mismos_artefactos(
    fuente: Path, tmp_path: Path, cliente: Any
) -> None:
    guiada = _con_corte(fuente, tmp_path)
    yaml = guiada.to_yaml()
    # Puerta completa: el YAML por `bayesrisk.run`.
    completa = loads_config(yaml)
    assert config_hash(completa) == guiada.config_hash
    estudio = bayesrisk.run(completa, run_dir=tmp_path / "completa")
    assert estudio.run_context.status == "done", estudio.run_context.error
    for clave in ("grades", "grade_table", "cutoff_table", "assignment"):
        pd.testing.assert_frame_equal(
            estudio.artifacts.get("master_scale", clave),
            guiada.study.artifacts.get("master_scale", clave),
            obj=clave,
        )
    # Pantalla: el mismo YAML cargado y corrido por la interfaz, con la copia de los datos de la
    # puerta guiada subida como cualquier archivo.
    cargado = cliente.post("/api/config/from-yaml", json={"yaml": yaml})
    assert cargado.status_code == 200, cargado.text
    assert cargado.json()["config_hash"] == guiada.config_hash
    snapshot = Path(guiada.config.data.load.source)
    subida = cliente.post(
        "/api/upload",
        files={"file": ("cartera.parquet", snapshot.read_bytes(), "application/octet-stream")},
    )
    assert subida.status_code == 200, subida.text
    corrida = cliente.post(
        "/api/run",
        json={"config": cargado.json()["config"], "dataset_id": subida.json()["dataset_id"]},
    )
    assert corrida.status_code == 200, corrida.text
    assert corrida.json()["status"] == "done"
    resultados = cliente.get(f"/api/results/{corrida.json()['run_id']}").json()
    assert resultados["lineage"]["config_hash"] == guiada.config_hash
    # Resultados pinta la escala desde su resumen: el mismo de la puerta guiada, celda a celda.
    etapas = {e["stage"]: e for e in resultados["summaries"]["stages"]}
    assert etapas["master_scale"] == guiada.summary("master_scale").to_dict()
    # Y el informe de la pantalla dice lo mismo que el de la puerta guiada.
    assert _subseccion_de_la_escala(_informe_de_la_pantalla(tmp_path)) == _subseccion_de_la_escala(
        _informe_guiado(tmp_path)
    )


# ──────────────────────────────── 5. Estable ────────────────────────────────


def test_con_las_tres_puertas_la_escala_es_estable() -> None:
    """D-SIM-1: la marca experimental se retira al cerrar las tres puertas (D-ESC-9)."""
    import bayesrisk.master_scale as modulo
    from bayesrisk.testing.stability import (
        EXPERIMENTAL_DOMAINS,
        STABLE_DOMAINS,
        declared_stability,
    )

    assert "master_scale" in STABLE_DOMAINS
    assert "master_scale" not in EXPERIMENTAL_DOMAINS
    assert declared_stability("master_scale") == "estable"
    marca = "**Experimental (fuera de la garantía SemVer 2.x).**"
    for metodo in (Scorecard.set_grades, Scorecard.set_cutoff, Scorecard.apply):
        assert marca not in (metodo.__doc__ or ""), metodo.__name__
    assert marca not in (modulo.__doc__ or "")


# ──────────────── pasada 1 de Codex sobre la capa B: los cortes, exactos ────────────────


def test_los_cortes_de_la_escala_se_escriben_exactos_en_el_informe() -> None:
    """Un corte redondeado describiría otra política (D-INF, cifras): los límites de cada tramo y el
    corte de aprobación se escriben exactos en las tablas completas y en la ficha del anexo, como
    en el cuerpo y en los parámetros (pasada 1 de Codex sobre la capa B)."""
    from bayesrisk.report import renderer

    for ruta in (
        ("master_scale.cutoff_table", "cutoff_score"),
        ("master_scale.grades", "score_min"),
        ("master_scale.grades", "score_max"),
        ("approval_cutoff",),
        ("cuts",),
    ):
        assert renderer._format_number(512.123456, key_path=ruta) == "512,123456", ruta
    # Lo que la escala MIDE sigue la regla de las cifras observadas.
    assert renderer._format_number(0.123456789, key_path=("master_scale.grades", "pd")) == "0,1235"


def test_encender_los_campos_de_la_escala_no_inventa_una_decision() -> None:
    """§13: el corte es apetito de riesgo y los tramos, de la institución o de los datos; encender
    un campo en la pantalla lo deja en blanco —ni un 0 que aprueba todo ni una lista vacía—, y en
    blanco cada uno dice lo que significa."""
    from bayesrisk.master_scale.config import MasterScaleConfig

    propiedades = MasterScaleConfig.model_json_schema()["properties"]
    assert propiedades["approval_cutoff"].get("ui_activate_blank") is True
    assert propiedades["grade_edges"].get("ui_activate_blank") is True
    assert propiedades["grade_edges"]["ui_null_label"] == "los forman los datos"
    assert propiedades["approval_cutoff"]["ui_null_label"] == "sin corte declarado"
