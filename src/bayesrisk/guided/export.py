"""Excel opcional por etapa y paquete de la corrida (D-FLU-5, D-SIM-7; hallazgo #8 de INTEGRACION).

``export_excel()`` escribe en ``<run_dir>/<name>/excel/`` un libro por etapa, numerado en el orden
de las etapas (§3.2 de la enmienda) y rotulado con el mismo nombre que el resumen, más un último
libro con las decisiones. Cada familia de resúmenes numera sus propias etapas: el scorecard, de ``01
Datos y muestras`` a ``12 Decisiones`` (``11 Escala maestra`` desde la capa B del SDD-32); la
provisión IFRS 9 (FLUJO-GUIADO-IFRS9 D-ECL-10), de ``01 Cartera`` a ``05 Decisiones`` (``03
Escenarios`` desde IFRS9-FIRMABLE capa C). Cada libro lleva el
resumen de la etapa, su **tabla de decisión** (la de ``sc.results[<etapa>]``, con rótulos en
español) y las **tablas completas** que el informe publica para ese dominio —las del anexo y las que
el informe entrega por observación como exports—, escritas por :mod:`bayesrisk.report.exports` con
la misma protección de celdas: una tabla escrita por las dos vías es la misma celda a celda (gate
§6-9). Las tablas adicionales de una etapa (``StageSummary.extra_tables``: la curva por sus
coeficientes y por cartera, la provisión por etapa y gatillo) van en hojas propias tras la de
decisión, con su título. Nunca es obligatorio ni la vía para ver un resultado (D-SIM-7): el
resultado se ve en el notebook o en pantalla.

``export(destino)`` empaqueta la carpeta del proyecto —config vigente, snapshot de datos, evidencia
de la corrida, informe y el Excel si se pidió— en un ``.zip`` que viaja entero.

Nada de esto se configura (D-FLU-12): la numeración, los nombres y qué tabla es «de decisión» son
constantes con su razón en el código.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from bayesrisk.core.exceptions import MissingDependencyError
from bayesrisk.guided.summaries import StageSummary, stage_labels
from bayesrisk.report.document import (
    MASTER_SCALE_CUTOFFS_TABLE,
    MASTER_SCALE_SCALE_TABLE,
    table_title,
)

if TYPE_CHECKING:
    import pandas as pd

    from bayesrisk.core.study import Study
    from bayesrisk.report.config import ReportConfig

__all__ = [
    "DECISIONS_BOOK",
    "EXCEL_SUBDIR",
    "STAGE_BOOKS",
    "decisions_book",
    "pack_project",
    "stage_books",
    "write_stage_workbooks",
]

#: Subdirectorio del proyecto donde queda el Excel opcional (fuera de ``run/``, que
#: ``bayesrisk.run`` sustituye entero al consolidar).
EXCEL_SUBDIR: Final = "excel"


#: Las etapas sin libro: sólo el informe (su entregable es el documento).
_SIN_LIBRO: Final = frozenset({"report"})

#: Las tablas del cuerpo del informe que el informe arma desde el resumen de la etapa y escribe como
#: texto (SDD-32, capa B): en el libro ya son la hoja «Decisión» y la de la tabla adicional, con sus
#: números; repetirlas como texto daría dos hojas con lo mismo.
_TABLAS_DEL_INFORME_DESDE_EL_RESUMEN: Final = frozenset(
    {MASTER_SCALE_SCALE_TABLE, MASTER_SCALE_CUTOFFS_TABLE}
)


def stage_books(family: str = "scorecard") -> dict[str, str]:
    """Nombre de archivo del libro de cada etapa de una familia, en el orden del pipeline.

    Las etapas con libro son todas menos ``report``, que no publica tablas y cuyo entregable es el
    propio informe. El número es la posición de la etapa en su familia, y por eso no depende de
    qué etapas corrieron: una corrida parcial deja los primeros libros y los números no se mueven.
    """
    rotulos = stage_labels(family)
    # «Escenarios» (IFRS9-FIRMABLE) tiene su libro desde la capa C, con el número de su posición
    # (Cami, 2026-10-09): `03 Escenarios.xlsx`, y la provisión en el `04` también sin escenarios.
    # «Escala maestra» (SDD-32 §6.4) tiene su libro `11 Escala maestra` desde la capa B, con la
    # pantalla y el informe (D-ESC-9), y las decisiones pasan al `12`: la etapa va al final del
    # scorecard y por eso sólo mueve ese número.
    etapas = [stage for stage in rotulos if stage not in _SIN_LIBRO]
    return {stage: f"{numero:02d} {rotulos[stage]}.xlsx" for numero, stage in enumerate(etapas, 1)}


def decisions_book(family: str = "scorecard") -> str:
    """El último libro de una familia: las decisiones del trail (humanas, puerta y motor)."""
    return f"{len(stage_books(family)) + 1:02d} Decisiones.xlsx"


#: El libro único de una corrida de monitoreo (SDD-33 §6.4): no tiene etapas previas que numerar.
MONITORING_BOOK: Final = "Monitoreo.xlsx"
_HOJA_PERIODOS: Final = "Periodos"
_HOJA_TRAMOS: Final = "Tramos por periodo"
_HOJA_VARIABLES: Final = "Variables"
#: El libro único de una comparación (SDD-34 §6.3): Resumen, Modelos, Pruebas, Muestras, Variables
#: (o Provisión por etapa), Corridas e Índice, desde el resumen «Comparación».
COMPARISON_BOOK: Final = "Comparación.xlsx"
_HOJA_MODELOS: Final = "Modelos"
_HOJA_PRUEBAS: Final = "Pruebas"
_HOJA_MUESTRAS: Final = "Muestras"
_HOJA_PROVISION: Final = "Provisión por etapa"
_HOJA_CORRIDAS: Final = "Corridas"
#: Las familias de un libro único, sin libros por etapa ni de decisiones.
_LIBRO_UNICO: Final = frozenset({"monitoreo", "comparacion"})

#: Los libros del scorecard: ``01 Datos y muestras.xlsx`` … ``11 Escala maestra.xlsx``.
STAGE_BOOKS: Final[dict[str, str]] = stage_books("scorecard")
#: El último libro del scorecard: ``12 Decisiones.xlsx``.
DECISIONS_BOOK: Final = decisions_book("scorecard")

_SHEET_SUMMARY: Final = "Resumen"
_SHEET_DECISION: Final = "Decisión"
_SHEET_INDEX: Final = "Índice"
_SHEET_MAX: Final = 31  # límite duro de Excel para el nombre de una hoja
_SHEET_FORBIDDEN: Final = frozenset("[]:*?/\\")

_XLSX_MISSING: Final = (
    'Exportar a Excel necesita openpyxl: instala el extra con `pip install "bayesrisk[excel]"` y '
    "vuelve a llamar a export_excel()."
)


def write_stage_workbooks(
    study: Study,
    summaries: Mapping[str, StageSummary],
    *,
    directory: Path,
    report_config: ReportConfig | None,
    trail_path: Path | None,
    family: str = "scorecard",
) -> tuple[Path, ...]:
    """Escribe los libros de las etapas que corrieron y el de decisiones; devuelve sus rutas.

    ``family`` es la familia de resúmenes de la corrida (``"scorecard"`` o ``"cartera"``), que
    decide qué etapas tienen libro y cómo se numeran.

    La carpeta se construye **entera y aparte** y sustituye a la anterior en un solo movimiento:
    una exportación de una corrida parcial no conserva los libros de la corrida completa previa
    (serían de otra corrida, y ``export()`` los empaquetaría como vigentes), y un fallo a mitad de
    escritura deja la exportación anterior intacta (pasada 2 de Codex sobre la capa B). La
    carpeta es un derivado regenerable de la corrida vigente: nada de lo que hubiera dentro
    sobrevive a una exportación nueva.
    """
    from bayesrisk.report.exports import write_workbook

    if not _openpyxl_disponible():
        raise MissingDependencyError(_XLSX_MISSING)
    directory.parent.mkdir(parents=True, exist_ok=True)
    tablas = _tablas_del_informe(study, report_config)
    token = uuid.uuid4().hex[:8]
    temporal = directory.with_name(f".{directory.name}.{token}.tmp")
    temporal.mkdir()
    nombres: list[str] = []
    libros = {} if family in _LIBRO_UNICO else stage_books(family)
    try:
        if family == "monitoreo" and (resumen := summaries.get("monitoring")) is not None:
            # SDD-33 §6.4: un libro único —resumen, periodos, tramos × periodo, variables—, desde
            # el MISMO resumen de la etapa que el notebook, la pantalla y el informe (D-SIM-5).
            write_workbook(_hojas_del_monitoreo(resumen), temporal / MONITORING_BOOK, index=False)
            nombres.append(MONITORING_BOOK)
        if family == "comparacion" and (resumen := summaries.get("comparison")) is not None:
            # SDD-34 §6.3: un libro único desde el MISMO resumen «Comparación» que el notebook,
            # la pantalla y el informe (D-SIM-5).
            write_workbook(
                _hojas_de_la_comparacion(resumen), temporal / COMPARISON_BOOK, index=False
            )
            nombres.append(COMPARISON_BOOK)
        for stage, libro in libros.items():
            resumen = summaries.get(stage)
            if resumen is None:
                continue
            hojas, con_indice = _hojas_de_la_etapa(stage, resumen, tablas)
            write_workbook(hojas, temporal / libro, index=con_indice)
            nombres.append(libro)
        decisiones = _hojas_de_decisiones(trail_path) if family not in _LIBRO_UNICO else {}
        if decisiones:
            write_workbook(decisiones, temporal / decisions_book(family), index=False)
            nombres.append(decisions_book(family))
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    _publicar_carpeta(temporal, directory, token)
    return tuple(directory / nombre for nombre in nombres)


#: Indirección para que un test pueda hacer fallar la publicación sin tocar ``os.rename`` global.
_renombrar = os.rename


def _publicar_carpeta(temporal: Path, directory: Path, token: str) -> None:
    """Sustituye ``directory`` por ``temporal`` y, si el segundo paso falla, restaura la anterior.

    Dos movimientos: la carpeta vigente se aparta a un respaldo lateral y el temporal ocupa su
    sitio. Si el segundo falla —permisos, OneDrive, antivirus— la anterior vuelve a su ruta
    canónica y el temporal se retira, con el error original (pasada 3 de Codex sobre la capa B);
    sólo con las dos hechas se borra el respaldo, que es un derivado de esta misma función.
    """
    anterior = directory.with_name(f".{directory.name}.old.{token}") if directory.exists() else None
    if anterior is not None:
        _renombrar(directory, anterior)
    try:
        _renombrar(temporal, directory)
    except BaseException:
        if anterior is not None and not directory.exists():
            _renombrar(anterior, directory)
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    if anterior is not None:
        shutil.rmtree(anterior, ignore_errors=True)


def pack_project(project_dir: Path, destination: Path) -> Path:
    """Empaqueta la carpeta del proyecto en ``destination`` (``.zip``) y devuelve su ruta.

    Entran el config vigente, ``input/`` (snapshot de datos), ``run/`` (evidencia: trail,
    lineage, estudio), ``reports/`` y ``excel/`` si existe. Quedan fuera el candado y los respaldos
    laterales de corridas anteriores (``.run.old.*``, ``.reports.*``): el paquete es la corrida
    vigente, no la historia de la carpeta. Se escribe en un temporal y se publica con ``replace``.
    """
    if not project_dir.is_dir():
        raise FileNotFoundError(
            f"No hay carpeta de proyecto que empaquetar en {project_dir}: llama a run() primero."
        )
    destino = Path(destination)
    if destino.suffix.lower() != ".zip":
        destino = destino.with_suffix(".zip")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{destino.name}.tmp")
    excluidos = {destino.resolve(), temporal.resolve()}
    raiz = project_dir.name
    with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for ruta in sorted(_archivos_del_proyecto(project_dir)):
            if ruta.resolve() in excluidos:
                continue  # el paquete que se está escribiendo, o uno anterior en la carpeta
            zf.write(ruta, arcname=f"{raiz}/{ruta.relative_to(project_dir).as_posix()}")
    temporal.replace(destino)
    return destino


# ────────────────────────────── hojas de cada libro ──────────────────────────────


def _hojas_de_la_etapa(
    stage: str, resumen: StageSummary, tablas: Mapping[str, pd.DataFrame]
) -> tuple[dict[str, pd.DataFrame], dict[str, bool]]:
    """Resumen, tabla de decisión, tablas adicionales, tablas del informe del dominio e índice."""
    import pandas as pd

    hojas: dict[str, pd.DataFrame] = {}
    con_indice: dict[str, bool] = {}
    hojas[_SHEET_SUMMARY] = pd.DataFrame(
        {
            "Línea": [*resumen.lines, *(f"⚠ {alerta}" for alerta in resumen.alerts)],
        }
    )
    con_indice[_SHEET_SUMMARY] = False
    indice: list[dict[str, Any]] = [
        {"Hoja": _SHEET_SUMMARY, "Contenido": f"Resumen de «{resumen.label}»", "Filas": 0}
    ]
    if resumen.table is not None and not resumen.table.empty:
        hojas[_SHEET_DECISION] = resumen.table
        con_indice[_SHEET_DECISION] = False
        indice.append(
            {
                "Hoja": _SHEET_DECISION,
                "Contenido": f"Tabla de decisión de «{resumen.label}»",
                "Filas": len(resumen.table.index),
            }
        )
    for titulo, tabla, _formatos in resumen.extra_tables:
        if tabla.empty:
            continue
        hoja = _nombre_de_hoja(titulo, hojas, titulo=titulo)
        hojas[hoja] = tabla
        con_indice[hoja] = False
        indice.append({"Hoja": hoja, "Contenido": titulo, "Filas": len(tabla.index)})
    adicionales = [tabla for _titulo, tabla, _formatos in resumen.extra_tables]
    for clave in sorted(k for k in tablas if k.startswith(f"{stage}.")):
        if clave in _TABLAS_DEL_INFORME_DESDE_EL_RESUMEN:
            continue
        tabla = tablas[clave]
        if any(tabla.equals(adicional) for adicional in adicionales):
            # La tabla del informe que ES una tabla adicional del resumen —la PD por período y
            # cartera de la curva, que el informe arma con la misma función (D-ECL-12)— ya tiene
            # su hoja: repetirla daría dos hojas idénticas en el mismo libro.
            continue
        hoja = _nombre_de_hoja(clave, hojas)
        hojas[hoja] = tabla
        con_indice[hoja] = True  # como los exports del informe: el índice es el identificador
        indice.append({"Hoja": hoja, "Contenido": table_title(clave), "Filas": len(tabla.index)})
    indice[0]["Filas"] = len(hojas[_SHEET_SUMMARY].index)
    hojas[_SHEET_INDEX] = pd.DataFrame(indice)
    con_indice[_SHEET_INDEX] = False
    return hojas, con_indice


def _hojas_del_monitoreo(resumen: StageSummary) -> dict[str, pd.DataFrame]:
    """Las hojas de ``Monitoreo.xlsx``: el resumen, la serie, cada tramo y cada variable."""
    import pandas as pd

    from bayesrisk.guided.summaries import TITULO_TRAMOS_POR_PERIODO, TITULO_VARIABLES_POR_PERIODO

    hojas: dict[str, pd.DataFrame] = {
        _SHEET_SUMMARY: pd.DataFrame(
            {"Línea": [*resumen.lines, *(f"⚠ {alerta}" for alerta in resumen.alerts)]}
        )
    }
    contenido = [("Resumen del monitoreo: el veredicto, su acción y qué revisar", _SHEET_SUMMARY)]
    if resumen.table is not None and not resumen.table.empty:
        hojas[_HOJA_PERIODOS] = resumen.table
        contenido.append(("Cada periodo: los cuatro indicadores y su veredicto", _HOJA_PERIODOS))
    por_titulo = {titulo: tabla for titulo, tabla, _formatos in resumen.extra_tables}
    for titulo, hoja in (
        (TITULO_TRAMOS_POR_PERIODO, _HOJA_TRAMOS),
        (TITULO_VARIABLES_POR_PERIODO, _HOJA_VARIABLES),
    ):
        tabla = por_titulo.get(titulo)
        if tabla is not None and not tabla.empty:
            hojas[hoja] = tabla
            contenido.append((titulo, hoja))
    hojas[_SHEET_INDEX] = pd.DataFrame(
        [
            {"Hoja": hoja, "Contenido": texto, "Filas": len(hojas[hoja].index)}
            for texto, hoja in contenido
        ]
    )
    return hojas


def _hojas_de_la_comparacion(resumen: StageSummary) -> dict[str, pd.DataFrame]:
    """Las hojas de ``Comparación.xlsx`` (SDD-34 §6.3), desde el resumen «Comparación».

    Resumen (la lectura y qué revisar), Modelos (la tabla de decisión), Pruebas, Muestras,
    Variables —o, en IFRS 9, Provisión por etapa—, Corridas e Índice. Una hoja sin filas no se
    escribe: una comparación de provisiones no tiene pruebas, muestras ni variables.
    """
    import pandas as pd

    from bayesrisk.guided.summaries import (
        TITULO_CORRIDAS_COMPARADAS,
        TITULO_MUESTRAS_COMPARADAS,
        TITULO_PROVISION_POR_ETAPA,
        TITULO_PRUEBAS_PAREADAS,
        TITULO_VARIABLES_COMPARADAS,
    )

    hojas: dict[str, pd.DataFrame] = {
        _SHEET_SUMMARY: pd.DataFrame(
            {"Línea": [*resumen.lines, *(f"⚠ {alerta}" for alerta in resumen.alerts)]}
        )
    }
    contenido = [("Resumen de la comparación: la lectura y qué revisar", _SHEET_SUMMARY)]
    if resumen.table is not None and not resumen.table.empty:
        hojas[_HOJA_MODELOS] = resumen.table
        contenido.append(
            (
                "Cada modelo: discriminación, estabilidad, concentración, validación y frontera"
                if "AUC" in resumen.table.columns
                else "Cada provisión: fecha de corte, moneda, escenarios, exposición, ECL y "
                "cobertura",
                _HOJA_MODELOS,
            )
        )
    por_titulo = {titulo: tabla for titulo, tabla, _formatos in resumen.extra_tables}
    for titulo, hoja in (
        (TITULO_PRUEBAS_PAREADAS, _HOJA_PRUEBAS),
        (TITULO_MUESTRAS_COMPARADAS, _HOJA_MUESTRAS),
        (TITULO_VARIABLES_COMPARADAS, _HOJA_VARIABLES),
        (TITULO_PROVISION_POR_ETAPA, _HOJA_PROVISION),
        (TITULO_CORRIDAS_COMPARADAS, _HOJA_CORRIDAS),
    ):
        tabla = por_titulo.get(titulo)
        if tabla is not None and not tabla.empty:
            hojas[hoja] = tabla
            contenido.append((titulo, hoja))
    hojas[_SHEET_INDEX] = pd.DataFrame(
        [
            {"Hoja": hoja, "Contenido": texto, "Filas": len(hojas[hoja].index)}
            for texto, hoja in contenido
        ]
    )
    return hojas


def _nombre_de_hoja(clave: str, existentes: Mapping[str, Any], *, titulo: str | None = None) -> str:
    """Nombre de hoja válido para Excel y único en el libro, legible por una persona.

    Las claves dinámicas (una tabla por variable) nombran la variable; una tabla adicional del
    resumen, su ``titulo``; el resto usa el título del informe. Se recorta a 31 caracteres y, si aun
    así colisiona, se numera.
    """
    partes = clave.split(".")
    if titulo is not None:
        base = titulo
    elif clave.startswith("binning.tables."):
        base = f"WoE — {'.'.join(partes[2:])}"
    elif clave.startswith("eda.univariate.profiles."):
        base = f"Perfil — {'.'.join(partes[3:])}"
    else:
        base = table_title(clave)
    limpio = "".join("_" if c in _SHEET_FORBIDDEN else c for c in base).strip()
    candidato = limpio[:_SHEET_MAX]
    n = 2
    while candidato in existentes:
        sufijo = f" ({n})"
        candidato = f"{limpio[: _SHEET_MAX - len(sufijo)]}{sufijo}"
        n += 1
    return candidato


def _tablas_del_informe(study: Study, report_config: ReportConfig | None) -> dict[str, Any]:
    """Las tablas que el informe publica para esta corrida, con sus claves ``dominio.tabla``.

    Es la misma recolección del ``ReportBuilder`` (tablas agregadas del anexo y tablas por
    observación de los exports): aquí no se decide qué es una tabla, se reutiliza la decisión del
    informe.
    """
    from bayesrisk.report.builder import ReportBuilder
    from bayesrisk.report.config import ReportConfig

    base = report_config if report_config is not None else ReportConfig()
    # Una corrida parcial (`run(until=)`) no tiene las cards que el informe exige: aquí no se
    # construye un informe, se recolectan las tablas de lo que sí corrió.
    config = base.model_copy(
        update={"sections": base.sections.model_copy(update={"missing_policy": "skip"})}
    )
    return dict(ReportBuilder(config).collect(study).tables)


def _hojas_de_decisiones(trail_path: Path | None) -> dict[str, pd.DataFrame]:
    """Las decisiones del trail en tres hojas: humanas, de la puerta guiada y del motor."""
    import pandas as pd

    if trail_path is None or not trail_path.is_file():
        return {}
    filas: list[dict[str, Any]] = []
    for linea in trail_path.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        evento = json.loads(linea)
        if evento.get("kind") != "decision":
            continue
        carga = evento.get("payload") or {}
        filas.append(
            {
                "Momento": evento.get("ts"),
                "Etapa": evento.get("step") or "",
                "Regla": carga.get("regla"),
                "Acción": carga.get("accion"),
                "Umbral": _celda(carga.get("umbral")),
                "Valor": _celda(carga.get("valor")),
                "Autor": carga.get("autor") or "motor",
                "Motivo": carga.get("motivo") or "",
            }
        )
    if not filas:
        return {}
    todas = pd.DataFrame(filas)
    hojas: dict[str, pd.DataFrame] = {}
    humanas = todas[todas["Autor"] == "usuario"]
    puerta = todas[todas["Autor"] == "puerta_guiada"]
    motor = todas[~todas["Autor"].isin(["usuario", "puerta_guiada"])]
    if not humanas.empty:
        hojas["Decisiones humanas"] = humanas.reset_index(drop=True)
    if not puerta.empty:
        hojas["Inferencias de la puerta"] = puerta.reset_index(drop=True)
    if not motor.empty:
        hojas["Decisiones del motor"] = motor.reset_index(drop=True)
    return hojas


def _celda(valor: Any) -> Any:
    """Un valor del trail como celda: escalares tal cual, estructuras como JSON legible."""
    if valor is None or isinstance(valor, str | int | float | bool):
        return valor
    return json.dumps(valor, ensure_ascii=False, sort_keys=True)


#: Lo que entra al paquete, y nada más: un archivo que el usuario deje en la carpeta del
#: proyecto (un `credentials.json`, unas notas) no viaja en un ZIP que se comparte (pasada 3 de
#: Codex sobre la capa B). Los enlaces simbólicos tampoco: un paquete no sigue rutas ajenas.
_ARCHIVOS_DEL_PAQUETE: Final[tuple[str, ...]] = ("config.yaml",)
_CARPETAS_DEL_PAQUETE: Final[tuple[str, ...]] = ("input", "run", "reports", EXCEL_SUBDIR)


def _archivos_del_proyecto(project_dir: Path) -> Iterable[Path]:
    for nombre in _ARCHIVOS_DEL_PAQUETE:
        archivo = project_dir / nombre
        if archivo.is_file() and not archivo.is_symlink():
            yield archivo
    for nombre in _CARPETAS_DEL_PAQUETE:
        carpeta = project_dir / nombre
        if not carpeta.is_dir() or carpeta.is_symlink():
            continue
        for ruta in carpeta.rglob("*"):
            if (
                ruta.is_file()
                and not ruta.is_symlink()
                and not any(parte.startswith(".") for parte in ruta.relative_to(project_dir).parts)
            ):
                yield ruta


def _openpyxl_disponible() -> bool:
    from bayesrisk.report.exports import _openpyxl_disponible as disponible

    return disponible()
