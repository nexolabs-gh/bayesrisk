"""Capa C de IFRS9-FIRMABLE (D-FIR-11, §3.11; S40): las tres puertas para escenarios y las dos PD.

Lo que la capa A y la B dejaron funcionando por ``bayesrisk.Ecl`` y el YAML llega a la pantalla, al
informe y al Excel, y la puerta guiada deja de ser experimental. Reglas de esta capa, cada una con
su test y su control negativo (``privado/evidencia/s40/cn_capa_c.py``):

1. **La ubicación de las dos tablas no es identidad** (Cami, 2026-10-09; «Respuestas de Cami»,
   S40): ``forward.input.macro_source.path`` y ``forward.scenarios.scenarios[*].macro_path_path``
   salen del ``config_hash``, como ``data.load.source`` (SDD-01 §329), y la huella del contenido de
   cada tabla se publica en ``("forward", "cycle_model")``.
2. **«Escenarios» tiene su libro** (Cami, 2026-10-09): la regla de D-ECL-10 tal cual —el número es
   la posición de la etapa—, ``03 Escenarios.xlsx`` y la provisión en el ``04``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from bayesrisk.core.config import BayesRiskConfig, config_hash
from bayesrisk.guided import Ecl
from bayesrisk.ui import datasets

pytest.importorskip("statsmodels", reason="la curva de PD exige el extra scoring")


def _historia() -> pd.DataFrame:
    trimestres = pd.date_range("2005-01-01", "2025-04-01", freq="QS")
    u = 7.0 + 2.0 * np.sin(np.arange(len(trimestres)) / 6.0)
    return pd.DataFrame(
        {"date": trimestres, "default_rate": 1 / (1 + np.exp(4.0 - 0.15 * (u - 7.0))), "u": u}
    )


def _escenarios(adverso_final: float = 10.0) -> pd.DataFrame:
    futuro = pd.date_range("2025-07-01", periods=8, freq="QS")
    return pd.DataFrame(
        {
            "scenario": ["base"] * 8 + ["adverso"] * 8,
            "weight": [0.7] * 8 + [0.3] * 8,
            "date": list(futuro) * 2,
            "u": [7.0] * 8 + list(np.linspace(7.0, adverso_final, 8)),
        }
    )


_ARGUMENTOS: dict[str, Any] = {
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
}


def _ecl(datos: Path, run_dir: Path, **cambios: Any) -> Ecl:
    ecl = Ecl(datos, **{**_ARGUMENTOS, "run_dir": run_dir, **cambios})
    ecl._echo = lambda _texto: None
    return ecl


@pytest.fixture(scope="module")
def _semilla() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        yield


@pytest.fixture(scope="module")
def datos(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return datasets.materialize("ifrs9_retail_latam", workdir=tmp_path_factory.mktemp("datos"))


@pytest.fixture(scope="module")
def con_escenarios(datos: Path, tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Ecl:
    ecl = _ecl(
        datos,
        tmp_path_factory.mktemp("con_escenarios"),
        history=_historia(),
        scenarios=_escenarios(),
    )
    ecl.run()
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return ecl


# ─────────────────── 1. La ubicación de las dos tablas no es identidad ───────────────────


def test_la_misma_provision_en_otra_carpeta_tiene_el_mismo_config_hash(
    datos: Path, tmp_path: Path
) -> None:
    """Mismas tablas, otra carpeta del proyecto: las rutas cambian y la identidad no."""
    una = _ecl(datos, tmp_path / "una", history=_historia(), scenarios=_escenarios())
    otra = _ecl(datos, tmp_path / "otra", history=_historia(), scenarios=_escenarios())
    fw_una, fw_otra = una.config.forward, otra.config.forward
    assert fw_una is not None and fw_otra is not None
    assert fw_una.input.macro_source.path != fw_otra.input.macro_source.path
    assert [e.macro_path_path for e in fw_una.scenarios.scenarios] != [
        e.macro_path_path for e in fw_otra.scenarios.scenarios
    ]
    assert una.config_hash == otra.config_hash


def test_lo_que_si_es_identidad_sigue_moviendo_el_hash(datos: Path, tmp_path: Path) -> None:
    """Los pesos, los nombres, la columna de la tasa y las variables siguen en la identidad: sólo
    la ubicación de las dos tablas sale, y el resto de ``forward`` no."""
    base = _ecl(datos, tmp_path / "base", history=_historia(), scenarios=_escenarios()).config
    volcado = base.model_dump(mode="json", by_alias=True)
    cambios: list[tuple[str, Any]] = [
        ("scenarios.scenarios.0.weight", 0.6),
        ("scenarios.scenarios.1.weight", 0.4),
    ]
    otro = BayesRiskConfig.model_validate(_poner(volcado, "forward", cambios))
    assert config_hash(otro) != config_hash(base)
    renombrado = BayesRiskConfig.model_validate(
        _poner(volcado, "forward", [("scenarios.scenarios.0.name", "central")])
    )
    assert config_hash(renombrado) != config_hash(base)
    # Y la ruta del resto de la librería que no es una de las dos tablas sigue en la identidad.
    con_tabla = BayesRiskConfig.model_validate(
        _poner(volcado, "forward", [("satellite.coefficient_table_path", "coeficientes.csv")])
    )
    assert config_hash(con_tabla) != config_hash(base)


def _poner(volcado: dict[str, Any], seccion: str, cambios: list[tuple[str, Any]]) -> dict[str, Any]:
    import copy

    salida = copy.deepcopy(volcado)
    for ruta, valor in cambios:
        nodo: Any = salida[seccion]
        tramos = ruta.split(".")
        for tramo in tramos[:-1]:
            nodo = nodo[int(tramo)] if isinstance(nodo, list) else nodo[tramo]
        if isinstance(nodo, list):
            nodo[int(tramos[-1])] = valor
        else:
            nodo[tramos[-1]] = valor
    return salida


def test_la_huella_de_cada_tabla_se_publica_en_la_corrida(con_escenarios: Ecl) -> None:
    """La huella del contenido —la que ya registraba el trail— viaja con el modelo del ciclo."""
    import json

    modelo = con_escenarios.study.artifacts.get("forward", "cycle_model")
    assert modelo.history_hash is not None and len(modelo.history_hash) == 64
    huellas = {e.name: e.content_hash for e in modelo.scenarios}
    assert set(huellas) == {"base", "adverso"} and all(
        h is not None and len(h) == 64 for h in huellas.values()
    )
    assert huellas["base"] != huellas["adverso"]
    trail = con_escenarios.project_dir / "run" / "audit_trail.jsonl"
    eventos = [json.loads(linea) for linea in trail.read_text(encoding="utf-8").splitlines()]
    por_regla = {
        (e.get("payload") or {}).get("regla"): (e.get("payload") or {}).get("valor")
        for e in eventos
        if e.get("kind") == "decision"
    }
    assert por_regla["forward_satellite_model"]["history_hash"] == modelo.history_hash
    assert por_regla["forward_scenarios"]["path_hashes"] == huellas


def test_otro_contenido_cambia_la_huella_y_no_el_config_hash(
    datos: Path, tmp_path: Path, _semilla: None
) -> None:
    """El contenido lo ancla la huella, como el ``data_hash`` al dataset: el config es el mismo."""
    corridas = []
    for final in (10.0, 11.0):
        ecl = _ecl(
            datos,
            tmp_path / f"adverso_{final:g}",
            name="misma",
            history=_historia(),
            scenarios=_escenarios(final),
        )
        ecl.run(until="forward")
        assert ecl.study.run_context.status == "done", ecl.study.run_context.error
        corridas.append(ecl)
    a, b = (c.study.artifacts.get("forward", "cycle_model") for c in corridas)
    assert corridas[0].config_hash == corridas[1].config_hash
    assert a.history_hash == b.history_hash
    assert a.scenarios[0].content_hash == b.scenarios[0].content_hash  # «base» no cambió
    assert a.scenarios[1].content_hash != b.scenarios[1].content_hash  # «adverso» sí


# ─────────────────────────── 2. «Escenarios» tiene su libro ───────────────────────────


def test_escenarios_es_el_libro_03_y_la_provision_el_04() -> None:
    from bayesrisk.guided.export import decisions_book, stage_books

    assert list(stage_books("cartera").values()) == [
        "01 Cartera.xlsx",
        "02 Curva de PD.xlsx",
        "03 Escenarios.xlsx",
        "04 Provisión IFRS 9.xlsx",
    ]
    assert decisions_book("cartera") == "05 Decisiones.xlsx"


def test_el_libro_de_escenarios_trae_su_resumen(con_escenarios: Ecl) -> None:
    openpyxl = pytest.importorskip("openpyxl", reason="el Excel opcional exige bayesrisk[excel]")
    libros = {ruta.name: ruta for ruta in con_escenarios.export_excel()}
    assert list(libros) == [
        "01 Cartera.xlsx",
        "02 Curva de PD.xlsx",
        "03 Escenarios.xlsx",
        "04 Provisión IFRS 9.xlsx",
        "05 Decisiones.xlsx",
    ]
    resumen = con_escenarios.summary("forward")
    libro = openpyxl.load_workbook(libros["03 Escenarios.xlsx"], read_only=True)
    try:
        hojas = list(libro.sheetnames)
        lineas = [fila[0] for fila in libro["Resumen"].iter_rows(min_row=2, values_only=True)]
    finally:
        libro.close()
    assert hojas[:2] == ["Resumen", "Decisión"] and hojas[-1] == "Índice", hojas
    assert lineas[: len(resumen.lines)] == list(resumen.lines)


# ─────────────── 3. La pantalla siembra lo que corre, lo mismo que la puerta guiada ───────────────
#
# El config de la pantalla se arma con la réplica Python del esqueleto del front
# (`test_jobs_ejecutables._esqueleto`, atada a `jobSkeleton` por su gate de cuatro pasos) más las
# respuestas que el usuario escribe en los esenciales; y, con escenarios, la réplica de
# `encenderSeccion` (`web/src/lib/jobs.ts`): la proyección canónica de la sección, lo que el trabajo
# siembra al encenderla y, encima, lo que devuelve `POST /api/scenario-tables`.

#: Las respuestas a los esenciales de la pantalla que equivalen a los argumentos de `_ARGUMENTOS`.
_RESPUESTAS_DE_LA_PANTALLA: dict[str, Any] = {
    "data.schema.index_col": "loan_id",
    "survival.input.duration_col": "duration",
    "survival.input.event_col": "event",
    "survival.time_grid.time_unit": "year",
    "survival.time_grid.horizon_periods": 5,
    "provisioning_ifrs9.as_of_date_col": "as_of_date",
    "provisioning_ifrs9.portfolio_col": "portfolio",
    "provisioning_ifrs9.ead.ead_col": "ead",
    "provisioning_ifrs9.lgd.lgd_col": "lgd",
    "provisioning_ifrs9.ecl.eir_col": "eir",
    "provisioning_ifrs9.staging.days_past_due_col": "days_past_due",
    "provisioning_ifrs9.staging.is_default_col": "is_default",
}

#: Lo que la puerta guiada declara además, y por qué la pantalla no lo escribe igual (D-SIM-1: la
#: procedencia puede diferir). Ninguna mueve un resultado: el test de la cifra lo mide.
#:
#: - ``data.schema.columns``: la puerta infiere y DECLARA el esquema de las columnas (D-SIM-2);
#: - ``provisioning_ifrs9.pd.horizon_12m_periods``: la puerta escribe el número que infirió; la
#:   pantalla lo siembra en blanco y el motor infiere el mismo (Cami, 2026-10-05);
#: - ``repro.seed``: la puerta parte del preset F4 entero; la pantalla, de la semilla de la sesión.
#:
#: Por la pantalla, el mismo ``config_hash`` que la puerta guiada se obtiene cargando su YAML.
_DIFERENCIAS_DECLARADAS = frozenset(
    {"data.schema.columns", "provisioning_ifrs9.pd.horizon_12m_periods", "repro.seed"}
)

#: Lo que no es identidad: las secciones de infraestructura (las rutas las quita `_hash_exclude`).
_FUERA_DE_LA_IDENTIDAD = ("name", "governance", "audit", "tracking", "report", "decisions")


def _poner_ruta(cfg: dict[str, Any], ruta: str, valor: Any) -> None:
    import copy

    tramos = ruta.split(".")
    nodo = cfg
    for tramo in tramos[:-1]:
        if not isinstance(nodo.get(tramo), dict):
            nodo[tramo] = {}
        nodo = nodo[tramo]
    nodo[tramos[-1]] = copy.deepcopy(valor)


def _fusionar(base: dict[str, Any], encima: dict[str, Any]) -> dict[str, Any]:
    import copy

    salida = copy.deepcopy(base)
    for clave, valor in encima.items():
        if isinstance(valor, dict) and isinstance(salida.get(clave), dict):
            salida[clave] = _fusionar(salida[clave], valor)
        else:
            salida[clave] = copy.deepcopy(valor)
    return salida


def _trabajo_ifrs9() -> dict[str, Any]:
    from bayesrisk.ui.jobs import list_jobs

    return next(j for j in list_jobs(incluir_referencia=True) if j["id"] == "provisiones_ifrs9")


def _config_de_la_pantalla(datos: Path, forward: dict[str, Any] | None = None) -> BayesRiskConfig:
    from test_jobs_ejecutables import _esqueleto, _hijos_de, _proyeccion_canonica

    from bayesrisk.core.config.effective_defaults import build_effective_defaults

    job = _trabajo_ifrs9()
    catalogo = build_effective_defaults()
    cfg = _esqueleto(job, catalogo)
    _poner_ruta(cfg, "data.load.source", str(datos))
    for ruta, valor in _RESPUESTAS_DE_LA_PANTALLA.items():
        _poner_ruta(cfg, ruta, valor)
    if forward is not None:
        # Réplica de `encenderSeccion`: proyección canónica, lo que el trabajo siembra al encender
        # la sección y, encima, la sección que armó el servidor con las dos tablas.
        cfg["forward"] = _proyeccion_canonica(_hijos_de(catalogo["sections"]["forward"]))
        for ruta, valor in job["toggle_overrides"]["forward"]["on"]:
            _poner_ruta(cfg, ruta, valor)
        cfg["forward"] = _fusionar(cfg["forward"], forward)
    return BayesRiskConfig.model_validate(cfg)


def _aplanar(valor: Any, prefijo: str = "") -> dict[str, Any]:
    if isinstance(valor, dict):
        salida: dict[str, Any] = {}
        for clave, hijo in valor.items():
            salida.update(_aplanar(hijo, f"{prefijo}.{clave}" if prefijo else clave))
        return salida
    return {prefijo: valor}


def _diferencias(a: BayesRiskConfig, b: BayesRiskConfig) -> set[str]:
    """Las hojas de identidad en que difieren dos configs (lo que `config_hash` sí mira)."""
    from bayesrisk.core.config.hashing import _hash_exclude

    planos = [
        _aplanar(c.model_dump(mode="json", by_alias=True, exclude=_hash_exclude())) for c in (a, b)
    ]
    return {
        k
        for k in set(planos[0]) | set(planos[1])
        if planos[0].get(k, "<sin>") != planos[1].get(k, "<sin>")
        and not k.startswith(_FUERA_DE_LA_IDENTIDAD)
    }


def test_el_trabajo_ifrs9_siembra_las_constantes_de_la_puerta_guiada(
    datos: Path, tmp_path: Path
) -> None:
    """Entrar por el trabajo y llenar los esenciales da el config de `Ecl`, salvo lo declarado."""
    pantalla = _config_de_la_pantalla(datos)
    guiada = _ecl(datos, tmp_path / "guiada").config
    assert _diferencias(pantalla, guiada) == _DIFERENCIAS_DECLARADAS


def test_entrar_por_el_trabajo_ifrs9_corre_y_da_la_cifra_de_la_puerta_guiada(
    datos: Path, tmp_path: Path, _semilla: None
) -> None:
    """Hasta la 2.9.0, con los esenciales llenos, la corrida se detenía: la EAD por CCF pedía una
    columna «drawn» y el PIT con ``forward`` pedía escenarios (los defaults de fábrica)."""
    import bayesrisk

    estudio = bayesrisk.run(_config_de_la_pantalla(datos), run_dir=tmp_path / "pantalla")
    assert estudio.run_context.status == "done", estudio.run_context.error
    guiada = _ecl(datos, tmp_path / "guiada")
    guiada.run()
    tarjetas = [e.artifacts.get("provisioning_ifrs9", "card") for e in (estudio, guiada.study)]
    assert (
        float(tarjetas[0].total_ecl_reported).hex() == float(tarjetas[1].total_ecl_reported).hex()
    )
    for clave in ("detail", "staging"):
        pd.testing.assert_frame_equal(
            estudio.artifacts.get("provisioning_ifrs9", clave),
            guiada.study.artifacts.get("provisioning_ifrs9", clave),
            check_exact=True,
        )


def test_los_escenarios_entran_al_trabajo_ifrs9_apagados() -> None:
    """Sin las dos tablas no hay escenarios: la sección se ve y se siembra en ``null``, y la
    provisión queda a lo largo del ciclo (sin escenarios, bit a bit con la 2.9.0)."""
    from test_jobs_ejecutables import _esqueleto

    from bayesrisk.core.config.effective_defaults import build_effective_defaults

    job = _trabajo_ifrs9()
    secciones = job["sections"]
    assert (
        secciones.index("survival")
        < secciones.index("forward")
        < secciones.index("provisioning_ifrs9")
    )
    assert "forward" in job["latent_sections"]
    esqueleto = _esqueleto(job, build_effective_defaults())
    assert esqueleto["forward"] is None
    assert esqueleto["provisioning_ifrs9"]["pd"]["pit_mode"] == "ttc_only"
    assert esqueleto["provisioning_ifrs9"]["scenarios"]["source"] == "single"


def test_encender_y_apagar_los_escenarios_mueve_la_provision_con_ellos() -> None:
    """Encender la sección pone la vía de los escenarios de la institución; apagarla devuelve la
    provisión a lo largo del ciclo. Son datos del catálogo: la pantalla los aplica sin saber qué
    significan."""
    job = _trabajo_ifrs9()
    encender = dict(job["toggle_overrides"]["forward"]["on"])
    apagar = dict(job["toggle_overrides"]["forward"]["off"])
    assert encender["provisioning_ifrs9.pd.pit_mode"] == "cycle"
    assert encender["provisioning_ifrs9.scenarios.source"] == "forward"
    assert encender["forward.satellite.mode"] == "reference_rate"
    assert encender["forward.macro.kind"] == "scenario_paths"
    assert apagar == {
        "provisioning_ifrs9.pd.pit_mode": "ttc_only",
        "provisioning_ifrs9.scenarios.source": "single",
    }


# ──────────── 4. Las dos tablas por la pantalla: la misma regla que la puerta guiada ────────────


def _subir(cliente: Any, nombre: str, tabla: pd.DataFrame) -> str:
    respuesta = cliente.post(
        "/api/upload",
        files={"file": (nombre, tabla.to_csv(index=False).encode("utf-8"), "text/csv")},
    )
    assert respuesta.status_code == 200, respuesta.text
    return str(respuesta.json()["dataset_id"])


@pytest.fixture
def cliente(tmp_path: Path) -> Any:
    pytest.importorskip("fastapi", reason="la pantalla exige el extra ui")
    from _ui_client import build_test_runtime, ui_client

    from bayesrisk.ui.settings import UiConfig

    settings = UiConfig(workdir=str(tmp_path / "ui"))
    with ui_client(settings, runtime=build_test_runtime(settings.workdir)) as c:
        yield c


def test_las_dos_tablas_por_la_pantalla_arman_la_seccion_de_la_puerta_guiada(
    cliente: Any, datos: Path, tmp_path: Path
) -> None:
    """`POST /api/scenario-tables` lee las dos tablas subidas con la misma función que `Ecl`: la
    sección que devuelve, sobre lo que el trabajo siembra, es la de la puerta guiada."""
    historia = _subir(cliente, "historia.csv", _historia())
    escenarios = _subir(cliente, "escenarios.csv", _escenarios())
    respuesta = cliente.post(
        "/api/scenario-tables",
        json={
            "history_dataset_id": historia,
            "scenarios_dataset_id": escenarios,
            "reference_rate_col": "default_rate",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert "Escenarios: 2 (base, adverso)" in cuerpo["summary"]
    pantalla = _config_de_la_pantalla(datos, forward=cuerpo["forward"])
    guiada = _ecl(datos, tmp_path / "guiada", history=_historia(), scenarios=_escenarios()).config
    assert _diferencias(pantalla, guiada) == _DIFERENCIAS_DECLARADAS
    # Las tablas quedaron en el `workdir` del servidor, una por escenario, y existen.
    fw = pantalla.forward
    assert fw is not None
    rutas = [fw.input.macro_source.path, *(e.macro_path_path for e in fw.scenarios.scenarios)]
    assert all(r is not None and Path(r).is_file() for r in rutas), rutas
    # Absolutas aunque el `workdir` sea relativo (medido en vivo en S40: `.bayesrisk_ui\...`).
    assert all(Path(str(r)).is_absolute() for r in rutas), rutas


def test_las_tablas_quedan_con_ruta_absoluta_aunque_el_workdir_sea_relativo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bayesrisk-ui` arranca con un `workdir` relativo (`.bayesrisk_ui`): la sección que arma la
    pantalla tiene que leer las tablas desde cualquier directorio (medido en vivo en S40)."""
    from bayesrisk.ui.datasets import ingest_upload
    from bayesrisk.ui.routes import scenario_tables_payload

    monkeypatch.chdir(tmp_path)
    workdir = Path("ui")
    ids = [
        ingest_upload(tabla.to_csv(index=False).encode("utf-8"), nombre, workdir=workdir)[
            "dataset_id"
        ]
        for nombre, tabla in (("historia.csv", _historia()), ("escenarios.csv", _escenarios()))
    ]
    forward = scenario_tables_payload(
        {"history_dataset_id": ids[0], "scenarios_dataset_id": ids[1]}, workdir=workdir
    )["forward"]
    rutas = [
        forward["input"]["macro_source"]["path"],
        *(e["macro_path_path"] for e in forward["scenarios"]["scenarios"]),
    ]
    assert all(Path(r).is_absolute() and Path(r).is_file() for r in rutas), rutas


def test_una_tabla_que_la_puerta_guiada_rechaza_la_pantalla_tambien(cliente: Any) -> None:
    """Un solo escenario no es un rango (§3.4): 422 con el mismo motivo que la puerta guiada."""
    historia = _subir(cliente, "historia.csv", _historia())
    uno = _escenarios()
    uno = uno.loc[uno["scenario"] == "base"].assign(weight=1.0)
    escenarios = _subir(cliente, "escenarios.csv", uno)
    respuesta = cliente.post(
        "/api/scenario-tables",
        json={
            "history_dataset_id": historia,
            "scenarios_dataset_id": escenarios,
            "reference_rate_col": "default_rate",
        },
    )
    assert respuesta.status_code == 422, respuesta.text
    assert "dos escenarios" in respuesta.json()["detail"].casefold()


def test_la_columna_de_la_tasa_es_la_que_dice_la_pantalla(cliente: Any) -> None:
    """La columna de la tasa es un esencial de la pantalla (con su default): otra columna se lee."""
    historia = _subir(
        cliente, "historia.csv", _historia().rename(columns={"default_rate": "castigos"})
    )
    escenarios = _subir(cliente, "escenarios.csv", _escenarios())
    respuesta = cliente.post(
        "/api/scenario-tables",
        json={
            "history_dataset_id": historia,
            "scenarios_dataset_id": escenarios,
            "reference_rate_col": "castigos",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    forward = respuesta.json()["forward"]
    assert forward["satellite"]["reference_rate_col"] == "castigos"
    assert forward["input"]["macro_source"]["variable_cols"] == ["u"]


# ─────────── 5. La curva que consumió la provisión: el desplazamiento por tramo ───────────


@pytest.fixture(scope="module")
def sin_escenarios(datos: Path, tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Ecl:
    ecl = _ecl(datos, tmp_path_factory.mktemp("sin_escenarios"))
    ecl.run()
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return ecl


def test_la_provision_dice_el_desplazamiento_de_cada_tramo_por_escenario(
    con_escenarios: Ecl, sin_escenarios: Ecl
) -> None:
    """Resultados pinta la curva consumida (abierto desde S32) desde el resumen de la etapa: una
    sola fuente para la pantalla, el Excel y el informe. Cada fila es un escenario y un tramo de
    calendario, con su desplazamiento en logit y su estado, en palabras."""
    resumen = con_escenarios.summary("provisioning_ifrs9")
    tablas = {titulo: (tabla, formatos) for titulo, tabla, formatos in resumen.extra_tables}
    assert "Desplazamiento por tramo" in tablas, list(tablas)
    tabla, formatos = tablas["Desplazamiento por tramo"]
    assert list(tabla.columns) == [
        "Escenario",
        "Tramo",
        "Desde",
        "Hasta",
        "u",
        "Desplazamiento",
        "Estado",
    ]
    ciclo = con_escenarios.study.artifacts.get("provisioning_ifrs9", "cycle_by_period")
    assert len(tabla) == len(ciclo)
    assert tabla["Desplazamiento"].tolist() == ciclo["cycle_shift"].tolist()
    assert set(tabla["Estado"]) <= {"escenario", "reversión", "largo plazo"}
    assert formatos["Desplazamiento"] == "num3" and formatos["Tramo"] == "int"
    # Sin escenarios no existe.
    assert all(
        titulo != "Desplazamiento por tramo"
        for titulo, _t, _f in sin_escenarios.summary("provisioning_ifrs9").extra_tables
    )


# ──────────── 6. El informe: «Escenarios y ajuste por ciclo» y la PD de tu modelo ────────────
#
# Una sola fuente: las líneas, las alertas y las tablas son las de los resúmenes de etapa
# (`guided.summaries`), ya escritas como las lee una persona; el informe no recalcula nada. Las dos
# subsecciones sólo existen cuando la corrida las trae: sin escenarios ni las dos PD, el capítulo
# IFRS 9 es el de siempre (test de abajo y los goldens del informe).

_GUIA = Path(__file__).resolve().parents[2] / "docs_site" / "guias" / "provision-ifrs9.md"


def _bloque_de_la_guia(nombre: str) -> str:
    texto = _GUIA.read_text(encoding="utf-8")
    inicio = f"<!-- {nombre}:start -->\n```python\n"
    fin = f"\n```\n<!-- {nombre}:end -->"
    return texto.split(inicio, maxsplit=1)[1].split(fin, maxsplit=1)[0]


@pytest.fixture(scope="module")
def firmable(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """La provisión firmable de la guía: contrato, escenarios y las dos PD del modelo; y la misma
    con una operación sin fecha de otorgamiento (la regla del 2026-10-08: no se compara, se
    cuenta)."""
    codigo = "\n".join(
        _bloque_de_la_guia(n)
        for n in ("provision-ifrs9-contrato", "provision-ifrs9-escenarios", "provision-ifrs9-pd")
    )
    directorio = tmp_path_factory.mktemp("firmable")
    espacio: dict[str, Any] = {"__name__": "__main__"}
    with pytest.MonkeyPatch.context() as parche:
        parche.chdir(directorio)
        parche.setenv("PYTHONHASHSEED", "0")
        exec(compile(codigo, str(_GUIA), "exec"), espacio)
        cartera = espacio["cartera"].copy()
        cartera["otorgamiento"] = cartera["otorgamiento"].astype("object")
        vivas = cartera.index[cartera["ead"] > 0]
        cartera.loc[vivas[0], "otorgamiento"] = None
        sin_fecha = Ecl(
            data=cartera,
            **{
                **_ARGUMENTOS,
                "period": "quarter",
                "horizon": 16,
                "origination": "otorgamiento",
                "maturity": "vencimiento",
                "installment": "cuota",
                "covariates": ["puntaje"],
                "history": espacio["historia"],
                "scenarios": espacio["escenarios"],
                "pd": "pd_hoy",
                "origination_pd": "pd_origen",
                "name": "con_una_fila_sin_fecha",
            },
        )
        sin_fecha._echo = lambda _texto: None
        sin_fecha.run()
    for ecl in (espacio["con_pd"], sin_fecha):
        assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return {"con_pd": espacio["con_pd"], "sin_fecha": sin_fecha}


def _bundle(ecl: Ecl) -> Any:
    from bayesrisk.report.builder import ReportBuilder

    config = ecl.config.report
    config = config.model_copy(
        update={"sections": config.sections.model_copy(update={"missing_policy": "skip"})}
    )
    return ReportBuilder(config).collect(ecl.study)


def _seccion_del_bundle(bundle: Any, section_id: str) -> Any:
    return next(s for s in bundle.sections if s.id == section_id)


def test_el_informe_cuenta_los_escenarios_y_el_ajuste_por_ciclo(firmable: dict[str, Any]) -> None:
    from bayesrisk.report.document import KEY_TABLES, table_title

    ecl = firmable["con_pd"]
    bundle = _bundle(ecl)
    ids = [s.id for s in bundle.sections if s.id.startswith("ifrs9.")]
    assert ids == [
        "ifrs9.survival",
        "ifrs9.forward",
        "ifrs9.provisioning_ifrs9",
        "ifrs9.pd_model",
    ], ids
    seccion = _seccion_del_bundle(bundle, "ifrs9.forward")
    assert seccion.title == "Escenarios y ajuste por ciclo"
    cuerpo = "\n".join(seccion.body)
    escenarios = ecl.summary("forward")
    for linea in escenarios.lines:
        assert linea in cuerpo, linea
    assert "Huella del contenido" in cuerpo
    # Con las fechas del contrato, una fila por escenario y tramo: la ventana completa de cada uno
    # (el artefacto trae además las parciales de las operaciones que vencen dentro del tramo).
    tramos = bundle.tables["provisioning_ifrs9.shift_by_period"]
    ciclo = ecl.study.artifacts.get("provisioning_ifrs9", "cycle_by_period")
    assert len(ciclo) > len(tramos) == ciclo[["scenario", "period"]].drop_duplicates().shape[0]
    assert not tramos.duplicated(["Escenario", "Tramo"]).any()
    modelo = ecl.study.artifacts.get("forward", "cycle_model")
    assert modelo.history_hash is not None and modelo.history_hash[:16] in cuerpo
    assert "ECL ponderada por 3 escenarios" in cuerpo
    assert "Ancla:" in cuerpo
    # Las tablas son las del resumen, celda a celda como las lee una persona.
    claves = KEY_TABLES["forward"]
    assert [table_title(k) for k in claves] == [
        "Escenarios de la institución, con sus pesos",
        "La sensibilidad estimada",
        "ECL por escenario frente a la curva a lo largo del ciclo",
        "Desplazamiento por tramo",
    ]
    resumen = ecl.summary("provisioning_ifrs9").to_dict()
    extra = {t["title"]: t for t in resumen["extra_tables"]}
    for clave, titulo in (
        (claves[2], "ECL por escenario"),
        (claves[3], "Desplazamiento por tramo"),
    ):
        tabla = bundle.tables[clave]
        assert list(tabla.columns) == extra[titulo]["columns"]
        assert tabla.astype(str).values.tolist() == extra[titulo]["rows"]
    decision = escenarios.to_dict()["table"]
    assert bundle.tables[claves[0]].astype(str).values.tolist() == decision["rows"]


def test_el_informe_cuenta_la_pd_de_tu_modelo_y_la_fila_sin_fecha(
    firmable: dict[str, Any],
) -> None:
    for nombre in ("con_pd", "sin_fecha"):
        ecl = firmable[nombre]
        seccion = _seccion_del_bundle(_bundle(ecl), "ifrs9.pd_model")
        assert seccion.title == "La PD de tu modelo y el aumento significativo del riesgo"
        cuerpo = "\n".join(seccion.body)
        assert "PD a 12 meses de tu modelo en" in cuerpo
        assert "Aumento significativo del riesgo por la PD de origen" in cuerpo
    cuerpo = "\n".join(_seccion_del_bundle(_bundle(firmable["sin_fecha"]), "ifrs9.pd_model").body)
    assert "sin fecha de otorgamiento" in cuerpo, cuerpo
    card = firmable["sin_fecha"].study.artifacts.get("provisioning_ifrs9", "card")
    assert card.metric_sections["sicr_origination_12m"]["n_rows_without_origination_date"] == 1


def test_el_html_pone_las_tablas_en_su_seccion_y_no_en_el_anexo(firmable: dict[str, Any]) -> None:
    import re

    from bayesrisk.report.document import KEY_TABLES

    resultado = firmable["con_pd"].study.artifacts.get("report", "result")
    html = Path(str(resultado.html_path)).read_text(encoding="utf-8")

    def seccion(section_id: str) -> str:
        inicio = html.rindex("<section", 0, html.index(f'data-section-id="{section_id}"'))
        return html[inicio : html.index("</section>", inicio)]

    assert re.findall(r'data-table-key="([^"]+)"', seccion("ifrs9.forward")) == list(
        KEY_TABLES["forward"]
    )
    anexo = re.findall(r'data-table-key="([^"]+)"', seccion("appendix_tables"))
    assert not set(KEY_TABLES["forward"]) & set(anexo)
    assert "Escenarios y ajuste por ciclo" in html
    assert "La PD de tu modelo y el aumento significativo del riesgo" in html


def test_sin_escenarios_ni_las_dos_pd_el_capitulo_ifrs9_es_el_de_siempre(
    sin_escenarios: Ecl,
) -> None:
    bundle = _bundle(sin_escenarios)
    ids = [s.id for s in bundle.sections if s.id.startswith("ifrs9.")]
    assert ids == ["ifrs9.survival", "ifrs9.provisioning_ifrs9"], ids
    assert not any(str(k).startswith("forward.") for k in bundle.tables)
    assert "provisioning_ifrs9.ecl_by_scenario" not in bundle.tables


# ──────────── 7. El gate de cierre: las tres puertas, el mismo config y la misma cifra ────────────
#
# D-SIM-1 (SDD-31 §4): las tres puertas producen el mismo config, el mismo `config_hash` y los
# mismos resultados. Con él, `Ecl(scenarios=, history=, pd=, origination_pd=)` deja de ser
# experimental (§3.11). Dos caminos por la pantalla:
#
# - **El YAML de la puerta guiada**, cargado en la pantalla (`/api/config/from-yaml`) y corrido por
#   ella (`/api/run`): el mismo `config_hash` y la misma cifra al bit (el precedente de S21).
# - **El formulario**, con las dos tablas subidas: la misma cifra al bit; su config difiere sólo en
#   lo que la puerta guiada declara además (`_DIFERENCIAS_DECLARADAS`, test de arriba).


def _total(estudio: Any) -> str:
    return float(estudio.artifacts.get("provisioning_ifrs9", "card").total_ecl_reported).hex()


def test_las_tres_puertas_con_escenarios_y_las_dos_pd_dan_el_mismo_hash_y_la_misma_cifra(
    firmable: dict[str, Any], cliente: Any, tmp_path: Path
) -> None:
    import bayesrisk
    from bayesrisk.core.config import loads_config

    guiada = firmable["con_pd"]
    yaml = guiada.to_yaml()
    # Puerta completa: el YAML por `bayesrisk.run`.
    completa = loads_config(yaml)
    assert config_hash(completa) == guiada.config_hash
    estudio = bayesrisk.run(completa, run_dir=tmp_path / "completa")
    assert estudio.run_context.status == "done", estudio.run_context.error
    assert _total(estudio) == _total(guiada.study)
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
    ifrs = resultados["provisioning_ifrs9"]
    assert float(ifrs["total_ecl_reported"]).hex() == _total(guiada.study)
    card = guiada.study.artifacts.get("provisioning_ifrs9", "card")
    assert ifrs["metric_sections"]["ecl_reported_by_scenario"] == {
        k: float(v) for k, v in card.metric_sections["ecl_reported_by_scenario"].items()
    }


def test_el_formulario_con_las_dos_tablas_da_la_cifra_de_la_puerta_guiada(
    cliente: Any, datos: Path, tmp_path: Path, con_escenarios: Ecl, _semilla: None
) -> None:
    import bayesrisk

    historia = _subir(cliente, "historia.csv", _historia())
    escenarios = _subir(cliente, "escenarios.csv", _escenarios())
    respuesta = cliente.post(
        "/api/scenario-tables",
        json={
            "history_dataset_id": historia,
            "scenarios_dataset_id": escenarios,
            "reference_rate_col": "default_rate",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    pantalla = _config_de_la_pantalla(datos, forward=respuesta.json()["forward"])
    estudio = bayesrisk.run(pantalla, run_dir=tmp_path / "pantalla")
    assert estudio.run_context.status == "done", estudio.run_context.error
    assert _total(estudio) == _total(con_escenarios.study)
    for clave in ("ecl_reported_by_scenario", "ecl_reported_ttc"):
        tarjetas = [
            e.artifacts.get("provisioning_ifrs9", "card").metric_sections[clave]
            for e in (estudio, con_escenarios.study)
        ]
        assert tarjetas[0] == tarjetas[1], clave
