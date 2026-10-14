"""La capa B del SDD-33: el monitoreo en la pantalla, el informe y el Excel; estable (D-MNT-8/9).

Una corrida guiada del scorecard (con los dobles de OptBinning: OR-Tools revienta el proceso de
pytest) deja la tarjeta; un ``Monitor`` sobre una cartera que se deteriora deja el informe y el
libro. Se mide: el capítulo del informe y su página ejecutiva, ``Monitoreo.xlsx`` celda a celda
contra el resumen, la tarjeta que la pantalla guarda con cada corrida del scorecard y la que se
sube como ``.zip``, las tres puertas con el mismo ``config_hash`` y los mismos artefactos, la
serie de PSI por período de ``stability`` (D-MNT-9) y la marca estable.
"""

from __future__ import annotations

import html as html_lib
import io
import json
import math
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from test_monitoring import cartera

import bayesrisk
from bayesrisk.core.config import config_hash, loads_config
from bayesrisk.guided import Monitor, Scorecard
from bayesrisk.scorecard.bundle import FittedScorecardBundle, _bundle_hash

_TITULO_SERIE = "PSI del puntaje por período contra Desarrollo"


@pytest.fixture(scope="module")
def entorno(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """El desarrollo con su tarjeta guardada y un monitoreo sobre una cartera que se deteriora."""
    from conftest import parchar_optbinning

    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        parchar_optbinning(parche)
        raiz = tmp_path_factory.mktemp("capa_b")
        sc = Scorecard(
            cartera(),
            target="bad_flag",
            id="loan_id",
            cohort="cohorte",
            oot_cohorts=["2024Q2"],
            name="desarrollo",
            run_dir=raiz / "corridas",
        )
        sc._echo = lambda _texto: None
        sc.run()
        assert sc.study.run_context.status == "done", sc.study.run_context.error
        ruta = FittedScorecardBundle.from_study(sc.study).save(raiz / "tarjeta")
        mon = Monitor(
            ruta,
            cartera(semilla=46, deriva=0.08, nivel=0.9),
            period="cohorte",
            default="bad_flag",
            name="capa-b",
            run_dir=raiz / "mon",
        )
        mon._echo = lambda _texto: None
        mon.run()
        assert mon.study.run_context.status == "done", mon.study.run_context.error
        yield {"raiz": raiz, "sc": sc, "ruta": ruta, "mon": mon}


def _informe(carpeta: Path, nombre: str) -> str:
    rutas = sorted(carpeta.rglob(nombre))
    assert rutas, f"no hay {nombre} bajo {carpeta}"
    return rutas[0].read_text(encoding="utf-8")


# ──────────────────────────── 1. El informe (§4.3, D-MNT-8) ────────────────────────────


def test_el_informe_tiene_el_capitulo_del_monitoreo_con_las_frases_del_resumen(
    entorno: dict[str, Any],
) -> None:
    documento = _informe(entorno["raiz"] / "mon", "monitoring_report.html")
    # El título del documento —portada y encabezado de página— es el del monitoreo (el CSS trae
    # un valor por defecto que la plantilla sobrescribe con el título real, como en IFRS 9).
    assert 'content: "Informe de Monitoreo del Modelo — CONFIDENCIAL"' in documento
    assert "<h1" in documento and "Informe de Monitoreo del Modelo</h1>" in documento
    for seccion in (
        "monitoring",
        "monitoring.verdict",
        "monitoring.grades",
        "monitoring.variables",
    ):
        assert f'data-section-id="{seccion}"' in documento, seccion
    # Una sola fuente (D-SIM-5): cada línea del resumen «Monitoreo» está en el cuerpo, tal cual.
    resumen = entorno["mon"].summary("monitoring")
    for linea in resumen.lines:
        assert html_lib.escape(linea if linea.endswith(".") else f"{linea}.") in documento, linea
    # La página ejecutiva dice «Veredicto», no «Validación técnica».
    assert "<dt>Veredicto</dt>" in documento
    assert "Validación técnica" not in documento
    # Y la metodología dice los umbrales fijos que la card publica.
    assert "Cómo se monitorea el modelo" in documento


def test_el_informe_del_scorecard_publica_la_serie_de_estabilidad(entorno: dict[str, Any]) -> None:
    """D-MNT-9: la serie de PSI por período que `stability` calculaba y no publicaba."""
    documento = _informe(entorno["raiz"] / "corridas", "scorecard_report.html")
    assert _TITULO_SERIE in documento
    resumen = entorno["sc"].summary("stability")
    serie = {titulo: tabla for titulo, tabla, _f in resumen.extra_tables}[_TITULO_SERIE]
    card = entorno["sc"].study.artifacts.get("stability", "card")
    n = card.model_dump()["metric_sections"]["stability"]["n_periods"]
    assert len(serie.index) == n > 1


# ─────────────────────────────── 2. Monitoreo.xlsx (§6.4) ───────────────────────────────


def _celda(valor: Any) -> Any:
    """La celda comparable: vacío como ``None`` y los números redondeados a 12 cifras.

    Excel guarda dobles con 15-17 cifras significativas: la última puede no volver idéntica.
    """
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    if isinstance(valor, int | float) and not isinstance(valor, bool):
        return float(f"{float(valor):.12g}")
    return valor


def test_monitoreo_xlsx_es_un_libro_unico_con_las_tablas_del_resumen(
    entorno: dict[str, Any],
) -> None:
    # El libro exige el extra `excel`: los jobs del CI sin extras lo saltan, como los demás tests
    # del Excel opcional (la matriz corrió sin él y este test cayó en `import openpyxl`).
    openpyxl = pytest.importorskip("openpyxl", reason="Monitoreo.xlsx exige el extra excel")
    load_workbook = openpyxl.load_workbook

    from bayesrisk.guided.summaries import TITULO_TRAMOS_POR_PERIODO, TITULO_VARIABLES_POR_PERIODO

    mon = entorno["mon"]
    (libro,) = mon.export_excel()
    assert libro.name == "Monitoreo.xlsx"
    wb = load_workbook(libro, read_only=True)
    assert wb.sheetnames == ["Resumen", "Periodos", "Tramos por periodo", "Variables", "Índice"]
    resumen = mon.summary("monitoring")
    extra = {titulo: tabla for titulo, tabla, _f in resumen.extra_tables}
    for hoja, tabla in (
        ("Periodos", resumen.table),
        ("Tramos por periodo", extra[TITULO_TRAMOS_POR_PERIODO]),
        ("Variables", extra[TITULO_VARIABLES_POR_PERIODO]),
    ):
        filas = [[_celda(c) for c in fila] for fila in wb[hoja].iter_rows(values_only=True)]
        assert filas[0] == [str(c) for c in tabla.columns], hoja
        esperadas = [[_celda(c) for c in fila] for fila in tabla.itertuples(index=False)]
        assert filas[1:] == esperadas, hoja
    lineas = [fila[0] for fila in wb["Resumen"].iter_rows(min_row=2, values_only=True)]
    assert lineas == [*resumen.lines, *(f"⚠ {a}" for a in resumen.alerts)]


# ───────────────────── 3. La tarjeta en la pantalla (§4.3) ─────────────────────


def test_la_pantalla_guarda_la_tarjeta_de_una_corrida_del_scorecard(
    entorno: dict[str, Any], tmp_path: Path
) -> None:
    from bayesrisk.ui import runs
    from bayesrisk.ui.cards import listar

    run_id = runs.save(entorno["sc"].study, workdir=tmp_path, governance=None)
    carpeta = tmp_path / "runs" / run_id / "tarjeta"
    leida = FittedScorecardBundle.load(carpeta)
    assert leida.manifest["schema_version"] == 4 and "monitoring_reference" in leida.manifest
    esperada = FittedScorecardBundle.from_study(entorno["sc"].study)
    assert leida.bundle_hash == esperada.bundle_hash
    (tarjeta,) = listar(tmp_path)
    assert tarjeta["origin"] == "run" and tarjeta["run_id"] == run_id
    assert tarjeta["path"] == str(carpeta.resolve()) and tarjeta["bundle_hash"] == leida.bundle_hash
    # Una corrida que no es del scorecard (el propio monitoreo) no deja tarjeta.
    otro = runs.save(entorno["mon"].study, workdir=tmp_path, governance=None)
    assert not (tmp_path / "runs" / otro / "tarjeta").exists()
    assert len(listar(tmp_path)) == 1


@pytest.fixture
def cliente(tmp_path: Path) -> Any:
    pytest.importorskip("fastapi", reason="la pantalla exige el extra ui")
    from _ui_client import build_test_runtime, ui_client

    from bayesrisk.ui.settings import UiConfig

    settings = UiConfig(workdir=str(tmp_path / "ui"))
    with ui_client(settings, runtime=build_test_runtime(settings.workdir)) as c:
        yield c


def _zip(archivos: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for nombre, contenido in archivos.items():
            z.writestr(nombre, contenido)
    return buffer.getvalue()


def _archivos_de(carpeta: Path, prefijo: str = "") -> dict[str, bytes]:
    return {f"{prefijo}{p.name}": p.read_bytes() for p in carpeta.iterdir()}


def _subir(cliente: Any, nombre: str, contenido: bytes) -> Any:
    return cliente.post("/api/cards/upload", files={"file": (nombre, contenido, "application/zip")})


def test_una_tarjeta_se_sube_como_zip_y_queda_en_la_lista(
    entorno: dict[str, Any], cliente: Any
) -> None:
    subida = _subir(cliente, "tarjeta.zip", _zip(_archivos_de(entorno["ruta"], "tarjeta/")))
    assert subida.status_code == 200, subida.text
    tarjeta = subida.json()
    assert tarjeta["origin"] == "upload"
    assert FittedScorecardBundle.load(tarjeta["path"]).bundle_hash == tarjeta["bundle_hash"]
    lista = cliente.post("/api/cards/list", json={})
    assert lista.status_code == 200, lista.text
    assert [t["path"] for t in lista.json()["cards"]] == [tarjeta["path"]]
    # La misma tarjeta, suelta en la raíz del .zip, es la misma carpeta (su nombre es su huella).
    otra = _subir(cliente, "suelta.zip", _zip(_archivos_de(entorno["ruta"])))
    assert otra.status_code == 200 and otra.json()["path"] == tarjeta["path"]


def test_una_tarjeta_de_esquema_3_se_rechaza_con_el_mensaje_del_monitor(
    entorno: dict[str, Any], cliente: Any, tmp_path: Path
) -> None:
    tarjeta = FittedScorecardBundle.load(entorno["ruta"])
    manifest = tarjeta.manifest
    manifest.pop("monitoring_reference")
    manifest["schema_version"] = 3
    manifest["files"] = {}
    manifest["bundle_hash"] = _bundle_hash(manifest)
    vieja = FittedScorecardBundle(manifest=manifest, rules=tarjeta._rules).save(tmp_path / "v3")
    respuesta = _subir(cliente, "v3.zip", _zip(_archivos_de(vieja)))
    assert respuesta.status_code == 422
    assert "esquema 3" in respuesta.json()["detail"]


@pytest.mark.parametrize(
    ("nombre", "entradas", "motivo"),
    [
        ("tarjeta.txt", None, ".zip"),
        ("extra.zip", {"manifest.json": b"{}", "bins.parquet": b"", "x.txt": b""}, "no es parte"),
        ("fuga.zip", {"../manifest.json": b"{}", "bins.parquet": b""}, "fuera de la tarjeta"),
        ("dos.zip", {"a/manifest.json": b"{}", "b/bins.parquet": b""}, "misma carpeta"),
        ("roto.zip", "no-es-un-zip", "no es un .zip"),
    ],
)
def test_un_zip_que_no_es_una_tarjeta_se_rechaza_antes_de_extraer(
    cliente: Any, tmp_path: Path, nombre: str, entradas: Any, motivo: str
) -> None:
    if entradas is None:
        contenido = b"hola"
    elif isinstance(entradas, str):
        contenido = entradas.encode()
    else:
        contenido = _zip(entradas)
    respuesta = _subir(cliente, nombre, contenido)
    assert respuesta.status_code == 422, respuesta.text
    assert motivo in respuesta.json()["detail"]
    assert not any((tmp_path / "ui" / "cards").glob("tarjeta-*"))


def test_un_zip_que_descomprimido_pasa_el_tope_se_rechaza_sin_extraer(tmp_path: Path) -> None:
    """Una bomba de compresión: pocos bytes subidos, megas al descomprimir. Se mide el tamaño
    declarado de cada entrada antes de extraer nada, contra el mismo tope de las subidas."""
    pytest.importorskip("fastapi", reason="la pantalla exige el extra ui")
    from _ui_client import build_test_runtime, ui_client

    from bayesrisk.ui.settings import UiConfig

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", b"{}")
        z.writestr("bins.parquet", bytes(3 * 1024 * 1024))
    assert len(buffer.getvalue()) < 1024 * 1024
    settings = UiConfig(workdir=str(tmp_path / "ui"), upload_max_mb=1)
    with ui_client(settings, runtime=build_test_runtime(settings.workdir)) as c:
        respuesta = _subir(c, "bomba.zip", buffer.getvalue())
    assert respuesta.status_code == 422, respuesta.text
    assert "descomprimida pasa el tope" in respuesta.json()["detail"]
    assert not any((tmp_path / "ui" / "cards").glob("*"))


def test_las_rutas_de_la_tarjeta_exigen_credenciales(tmp_path: Path) -> None:
    pytest.importorskip("fastapi", reason="la pantalla exige el extra ui")
    from _ui_client import build_test_runtime, ui_client

    from bayesrisk.ui.settings import UiConfig

    settings = UiConfig(workdir=str(tmp_path / "ui"))
    with ui_client(
        settings, runtime=build_test_runtime(settings.workdir), con_credenciales=False
    ) as c:
        assert c.post("/api/cards/list", json={}).status_code == 403
        assert _subir(c, "t.zip", _zip({"manifest.json": b"{}"})).status_code == 403


# ───────────────────────── 4. Las tres puertas (D-SIM-1) ─────────────────────────


def test_las_tres_puertas_dan_el_mismo_hash_y_los_mismos_artefactos(
    entorno: dict[str, Any], cliente: Any, tmp_path: Path
) -> None:
    mon = entorno["mon"]
    yaml = mon.to_yaml()
    completa = loads_config(yaml)
    assert config_hash(completa) == mon.config_hash
    estudio = bayesrisk.run(completa, run_dir=tmp_path / "completa")
    assert estudio.run_context.status == "done", estudio.run_context.error
    for clave in ("periods", "grades_by_period", "variables_by_period"):
        pd.testing.assert_frame_equal(
            estudio.artifacts.get("monitoring", clave),
            mon.study.artifacts.get("monitoring", clave),
            obj=clave,
        )
    cargado = cliente.post("/api/config/from-yaml", json={"yaml": yaml})
    assert cargado.status_code == 200, cargado.text
    assert cargado.json()["config_hash"] == mon.config_hash
    snapshot = Path(mon.config.data.load.source)
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
    assert corrida.json()["status"] == "done", corrida.json()
    resultados = cliente.get(f"/api/results/{corrida.json()['run_id']}").json()
    assert resultados["lineage"]["config_hash"] == mon.config_hash
    etapas = {e["stage"]: e for e in resultados["summaries"]["stages"]}
    assert etapas["monitoring"] == mon.summary("monitoring").to_dict()
    final = resultados["summaries"]["final"]
    assert final["family"] == "monitoreo"


# ───────────────────────────── 5. El catálogo y la marca ─────────────────────────────


def test_el_trabajo_monitorear_un_modelo_en_uso() -> None:
    from bayesrisk.ui.jobs import list_jobs

    (trabajo,) = [j for j in list_jobs() if j["id"] == "monitoreo_modelo"]
    assert trabajo["label"] == "Monitorear un modelo en uso"
    assert trabajo["sections"] == ["data", "monitoring", "report", "governance"]
    assert trabajo["latent_sections"] == ["governance"]
    assert [d["path"] for d in trabajo["required_decisions"]] == [
        "monitoring.bundle",
        "monitoring.period",
        "governance.purpose",
    ]
    assert dict(trabajo["overrides"]) == {"data.target": None, "data.partition": None}


def test_la_ayuda_del_eje_temporal_dice_lo_que_se_publica() -> None:
    """D-MNT-9: la ayuda prometía una evolución que el informe no mostraba."""
    from bayesrisk.ui.jobs import list_jobs

    decisiones = [
        opcion
        for job in list_jobs()
        for opcion in job["methodology_choices"]
        if opcion["path"] == "stability.temporal_axis"
    ]
    assert decisiones
    assert all("PSI del puntaje período a período" in d["help"] for d in decisiones)


def test_con_las_tres_puertas_el_monitoreo_es_estable() -> None:
    """D-MNT-8: la marca experimental se retira al cerrar las tres puertas."""
    import bayesrisk.guided.monitor as puerta
    import bayesrisk.monitoring as modulo
    from bayesrisk.testing.stability import (
        EXPERIMENTAL_DOMAINS,
        EXPERIMENTAL_SYMBOLS,
        STABLE_DOMAINS,
        declared_stability,
    )

    assert "monitoring" in STABLE_DOMAINS and "monitoring" not in EXPERIMENTAL_DOMAINS
    assert "bayesrisk.guided.monitor.Monitor" not in EXPERIMENTAL_SYMBOLS
    assert declared_stability("monitoring") == "estable"
    marca = "**Experimental (fuera de la garantía SemVer 2.x).**"
    for doc in (modulo.__doc__, puerta.__doc__, Monitor.__doc__, Monitor.export_excel.__doc__):
        assert marca not in (doc or "")


def test_la_ficha_de_la_tarjeta_es_json_legible(entorno: dict[str, Any], tmp_path: Path) -> None:
    """La ficha al lado de la tarjeta lleva lo que la lista muestra, sin abrir el results.json."""
    from bayesrisk.ui.cards import guardar_de_la_corrida

    ficha = guardar_de_la_corrida(entorno["sc"].study, tmp_path)
    assert ficha is not None
    assert json.loads((tmp_path / "tarjeta.json").read_text(encoding="utf-8")) == ficha
    assert ficha["name"] == "desarrollo" and ficha["n_grades"] >= 3


# ──────────────────── 6. La pasada 1 de Codex sobre la capa B ────────────────────


def test_el_informe_del_monitoreo_no_se_contradice(entorno: dict[str, Any]) -> None:
    """El resumen ejecutivo, las conclusiones y las limitaciones hablan del monitoreo: no dicen
    que la corrida no evaluó nada ni que construyó un scorecard."""
    documento = _informe(entorno["raiz"] / "mon", "monitoring_report.html")
    assert "Veredicto del monitoreo" in documento
    assert "Las métricas clave no están disponibles" not in documento
    assert "no evaluó desempeño, estabilidad ni calibración" not in documento
    assert "construcción y evaluación del scorecard" not in documento
    assert "El alcance de este informe es el monitoreo de un modelo en uso" in documento
    assert "seguir usándolo, recalibrarlo o redesarrollarlo" in documento


def test_una_carpeta_de_tarjeta_a_medias_no_se_reutiliza_ni_se_lista(
    entorno: dict[str, Any], cliente: Any, tmp_path: Path
) -> None:
    from bayesrisk.ui.cards import listar

    contenido = _zip(_archivos_de(entorno["ruta"]))
    primera = _subir(cliente, "t.zip", contenido)
    assert primera.status_code == 200, primera.text
    carpeta = Path(primera.json()["path"])
    (carpeta / "bins.parquet").unlink()
    assert listar(tmp_path / "ui") == []
    segunda = _subir(cliente, "t.zip", contenido)
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["path"] == str(carpeta)
    assert FittedScorecardBundle.load(carpeta).bundle_hash == primera.json()["bundle_hash"]
    assert [t["path"] for t in listar(tmp_path / "ui")] == [str(carpeta)]


def test_la_pantalla_monitorea_un_panel_con_la_identidad_en_el_indice(
    cliente: Any, tmp_path: Path, fake_binning_process: object
) -> None:
    """El parquet ORIGINAL —``loan_id`` en el índice, repetido entre periodos— corre por la
    pantalla como corre por ``Monitor``: la misma regla de aplanado, el mismo ``config_hash`` y la
    misma serie (antes el paso de datos lo rechazaba por el índice repetido)."""
    del fake_binning_process
    sc = Scorecard(
        cartera().set_index("loan_id"),
        target="bad_flag",
        id="loan_id",
        cohort="cohorte",
        oot_cohorts=["2024Q2"],
        name="dev-indice",
        run_dir=tmp_path / "dev",
    )
    sc._echo = lambda _t: None
    sc.run()
    tarjeta = FittedScorecardBundle.from_study(sc.study)
    datos = cartera(semilla=47).set_index("loan_id")
    panel = pd.concat([datos, datos.loc[datos["cohorte"] == "2024Q2"].assign(cohorte="2024Q3")])
    assert panel.index.has_duplicates
    mon = Monitor(tarjeta, panel, period="cohorte", default="bad_flag", run_dir=tmp_path / "m")
    mon._echo = lambda _t: None
    mon.run()
    assert mon.study.run_context.status == "done", mon.study.run_context.error
    original = tmp_path / "panel.parquet"
    panel.to_parquet(original)
    subida = cliente.post(
        "/api/upload",
        files={"file": ("panel.parquet", original.read_bytes(), "application/octet-stream")},
    )
    assert subida.status_code == 200, subida.text
    cargado = cliente.post("/api/config/from-yaml", json={"yaml": mon.to_yaml()})
    assert cargado.status_code == 200, cargado.text
    corrida = cliente.post(
        "/api/run",
        json={"config": cargado.json()["config"], "dataset_id": subida.json()["dataset_id"]},
    )
    assert corrida.status_code == 200, corrida.text
    assert corrida.json()["status"] == "done", corrida.json()
    resultados = cliente.get(f"/api/results/{corrida.json()['run_id']}").json()
    assert resultados["lineage"]["config_hash"] == mon.config_hash
    assert resultados["lineage"]["data_hash"] == mon.study.run_context.lineage.data_hash
    etapas = {e["stage"]: e for e in resultados["summaries"]["stages"]}
    assert etapas["monitoring"] == mon.summary("monitoring").to_dict()
    # Y el snapshot que guardó `Monitor` —ya aplanado, con la columna reservada, el que su YAML
    # referencia— corre igual por la pantalla (pasada 2 de Codex sobre la capa B).
    snapshot = Path(mon.config.data.load.source)
    subida2 = cliente.post(
        "/api/upload",
        files={"file": ("snapshot.parquet", snapshot.read_bytes(), "application/octet-stream")},
    )
    assert subida2.status_code == 200, subida2.text
    corrida2 = cliente.post(
        "/api/run",
        json={"config": cargado.json()["config"], "dataset_id": subida2.json()["dataset_id"]},
    )
    assert corrida2.status_code == 200, corrida2.text
    assert corrida2.json()["status"] == "done", corrida2.json()
    resultados2 = cliente.get(f"/api/results/{corrida2.json()['run_id']}").json()
    assert resultados2["lineage"]["config_hash"] == mon.config_hash
    assert resultados2["lineage"]["data_hash"] == mon.study.run_context.lineage.data_hash
