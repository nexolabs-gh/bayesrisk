"""El Excel opcional y el paquete de ``bayesrisk.Ecl`` (FLUJO-GUIADO-IFRS9 capa B, D-ECL-10).

§3.11 de la enmienda: ``ecl.export_excel()`` escribe ``01 Cartera.xlsx``, ``02 Curva de PD.xlsx``,
``03 Provisión IFRS 9.xlsx`` y ``04 Decisiones.xlsx`` con la misma mecánica, protección de celdas
y regla de numeración que el scorecard (el número es la posición de la etapa y no se mueve en una
corrida parcial); cada tabla del informe del dominio está en el libro de su etapa **celda a celda**
igual a como la escribe el informe, y las tablas adicionales del resumen —la curva por sus
coeficientes y por cartera, la provisión por etapa y gatillo— tienen hoja propia con las mismas
celdas que el resumen. ``ecl.export()`` empaqueta el Excel con la corrida.
"""

from __future__ import annotations

import math
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from bayesrisk.guided import Ecl
from bayesrisk.guided.export import EXCEL_SUBDIR, decisions_book, stage_books
from bayesrisk.report.exports import write_workbook
from bayesrisk.ui import datasets

openpyxl = pytest.importorskip("openpyxl", reason="el Excel opcional exige bayesrisk[excel]")
pytest.importorskip("statsmodels", reason="la curva de PD exige el extra scoring")

_LIBROS = ("01 Cartera.xlsx", "02 Curva de PD.xlsx", "03 Provisión IFRS 9.xlsx")


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
        "formats": ["csv"],
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
def datos(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return datasets.materialize("ifrs9_retail_latam", workdir=tmp_path_factory.mktemp("datos"))


@pytest.fixture(scope="module")
def corrida(datos: Path, tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Ecl:
    """Una corrida completa con una decisión humana, para que el libro de decisiones la traiga."""
    ecl = _ecl(datos, tmp_path_factory.mktemp("ecl"), name="excel")
    ecl.exclude("antiguedad_meses", reason="efecto nulo y sin sentido de negocio")
    ecl.run()
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return ecl


@pytest.fixture(scope="module")
def libros(corrida: Ecl) -> dict[str, Path]:
    return {ruta.name: ruta for ruta in corrida.export_excel()}


def _filas(ruta: Path, hoja: str) -> list[tuple[Any, ...]]:
    libro = openpyxl.load_workbook(ruta, read_only=True)
    try:
        return [tuple(fila) for fila in libro[hoja].iter_rows(values_only=True)]
    finally:
        libro.close()


def _hojas(ruta: Path) -> list[str]:
    libro = openpyxl.load_workbook(ruta, read_only=True)
    try:
        return list(libro.sheetnames)
    finally:
        libro.close()


def _misma_fila(celdas: Sequence[Any], valores: Sequence[Any]) -> bool:
    """Celda a celda; un real, salvo el último dígito que el ``.xlsx`` no conserva (openpyxl lo
    escribe con 15 cifras significativas: le pasa igual a toda tabla del informe)."""
    if len(celdas) != len(valores):
        return False
    for celda, valor in zip(celdas, valores, strict=True):
        if isinstance(valor, float) and math.isnan(valor):
            if celda is not None:
                return False
        elif isinstance(valor, float) and isinstance(celda, int | float):
            if not math.isclose(celda, valor, rel_tol=1e-14):
                return False
        elif celda != valor:
            return False
    return True


def _indice(ruta: Path) -> pd.DataFrame:
    filas = _filas(ruta, "Índice")
    return pd.DataFrame(filas[1:], columns=filas[0])


def test_un_libro_numerado_por_etapa_de_la_provision_y_el_de_decisiones(
    corrida: Ecl, libros: dict[str, Path]
) -> None:
    assert list(libros) == [*_LIBROS, "04 Decisiones.xlsx"]
    assert all(ruta.parent == corrida.project_dir / EXCEL_SUBDIR for ruta in libros.values())
    # La numeración y los nombres son los de la familia: los rótulos de sus etapas, sin «report».
    assert list(stage_books("cartera").values()) == list(_LIBROS)
    assert decisions_book("cartera") == "04 Decisiones.xlsx"
    # Y el scorecard no se movió.
    assert stage_books("scorecard")["validation"] == "10 Validación formal.xlsx"
    assert decisions_book("scorecard") == "11 Decisiones.xlsx"
    for nombre in _LIBROS:
        hojas = _hojas(libros[nombre])
        assert hojas[0] == "Resumen" and hojas[1] == "Decisión" and hojas[-1] == "Índice", nombre
    humanas = _filas(libros["04 Decisiones.xlsx"], "Decisiones humanas")
    assert any("efecto nulo y sin sentido de negocio" in fila for fila in humanas[1:]), humanas


def test_el_resumen_y_las_tablas_adicionales_son_las_del_resumen_de_la_etapa(
    corrida: Ecl, libros: dict[str, Path]
) -> None:
    """La misma fuente que ``summary()``: líneas, tabla de decisión y cada tabla adicional."""
    comparadas = 0
    for stage, nombre in stage_books("cartera").items():
        resumen = corrida.summary(stage)
        libro = libros[nombre]
        lineas = [fila[0] for fila in _filas(libro, "Resumen")[1:]]
        assert lineas[: len(resumen.lines)] == list(resumen.lines), stage
        decision = _filas(libro, "Decisión")
        assert decision[0] == tuple(resumen.table.columns), stage
        assert len(decision) - 1 == len(resumen.table.index), stage
        indice = _indice(libro)
        for titulo, tabla, _formatos in resumen.extra_tables:
            fila = indice[indice["Contenido"] == titulo]
            assert len(fila) == 1, (stage, titulo, indice)
            hoja = str(fila["Hoja"].iloc[0])
            celdas = _filas(libro, hoja)
            assert celdas[0] == tuple(str(c) for c in tabla.columns), (stage, titulo)
            filas = [tuple(f) for f in tabla.itertuples(index=False)]
            assert len(celdas) - 1 == len(filas), (stage, titulo)
            assert all(_misma_fila(c, f) for c, f in zip(celdas[1:], filas, strict=True)), (
                stage,
                titulo,
            )
            comparadas += 1
    # La curva trae su PD por período y cartera (su tabla de decisión son los coeficientes); la
    # provisión, las operaciones por etapa y gatillo (S30): dos tablas adicionales.
    assert comparadas == 2


def test_cada_tabla_del_informe_esta_celda_a_celda_en_el_libro_de_su_etapa(
    corrida: Ecl, libros: dict[str, Path], tmp_path: Path
) -> None:
    """La tabla que el informe recolecta, escrita por la vía de sus exports, es la misma celda."""
    from bayesrisk.report.builder import ReportBuilder

    config = corrida.config.report
    config = config.model_copy(
        update={"sections": config.sections.model_copy(update={"missing_policy": "skip"})}
    )
    tablas = ReportBuilder(config).collect(corrida.study).tables
    comparadas = 0
    for stage, nombre in stage_books("cartera").items():
        indice = _indice(libros[nombre])
        for clave in sorted(k for k in tablas if k.startswith(f"{stage}.")):
            # Como la escribe el informe (con índice) o, si es la tabla adicional del resumen que
            # el informe arma con la misma función —la PD por período y cartera, D-ECL-12—, como
            # su hoja de tabla adicional (sin índice): una sola vez en el libro.
            referencias = []
            for con_indice in (True, False):
                referencia = tmp_path / f"{clave}-{con_indice}.xlsx"
                write_workbook({"t": tablas[clave]}, referencia, index=con_indice)
                referencias.append(_filas(referencia, "t"))
            hojas = [
                str(h)
                for h, filas in zip(indice["Hoja"], indice["Filas"], strict=True)
                if filas == len(tablas[clave].index)
                and _filas(libros[nombre], str(h)) in referencias
            ]
            assert len(hojas) == 1, (stage, clave, hojas)
            comparadas += 1
    # Las de la curva (PD por período y cartera, coeficientes) y la de la provisión.
    assert comparadas >= 3, sorted(tablas)


def test_una_corrida_parcial_deja_los_primeros_libros_sin_mover_los_numeros(
    datos: Path, tmp_path: Path, _semilla: None
) -> None:
    ecl = _ecl(datos, tmp_path / "corridas", name="parcial")
    ecl.run(until="survival")
    assert [ruta.name for ruta in ecl.export_excel()] == [
        "01 Cartera.xlsx",
        "02 Curva de PD.xlsx",
        "04 Decisiones.xlsx",
    ]


def test_export_empaqueta_el_excel_con_la_corrida(
    corrida: Ecl, libros: dict[str, Path], tmp_path: Path
) -> None:
    paquete = corrida.export(tmp_path / "corrida.zip")
    with zipfile.ZipFile(paquete) as zf:
        nombres = set(zf.namelist())
    raiz = corrida.project_dir.name
    for nombre in libros:
        assert f"{raiz}/{EXCEL_SUBDIR}/{nombre}" in nombres, sorted(nombres)
    assert f"{raiz}/config.yaml" in nombres
