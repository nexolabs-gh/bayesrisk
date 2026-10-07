"""Las cinco cifras de simplicidad de IFRS 9 (SDD-31 D-SIM-11; FLUJO-GUIADO-IFRS9 §13).

Gemelo de ``test_simplicidad_scorecard.py``: cada cifra es un golden con la regla de
``HOJAS_DEL_FORMULARIO`` —moverla es legítimo; moverla sin actualizar el número y decir por qué,
no—. Línea base medida sobre ``3cc9654`` (S28, ``privado/evidencia/s28/ifrs9-mediciones.md``) y
el después, en la capa A (S30, 2026-10-04) y la B (S31, 2026-10-05); la capa B de CASO-REAL-IFRS9
(S35, 2026-10-06) suma las tres columnas opcionales del contrato (§13 de esa enmienda), y la capa A
de IFRS9-FIRMABLE (S37, 2026-10-07; línea base medida sobre ``698423a``: 21 · 5 y 10 · 233 · 0,74 s
· 5) suma a la puerta las dos tablas de escenarios, experimentales, que escriben la sección
``forward`` —fuera de las tres secciones del trabajo, cuyas perillas no cambian—:

| Cifra | ``3cc9654`` | Capas A y B | CASO-REAL-IFRS9 B | IFRS9-FIRMABLE A | Objetivo |
|---|---|---|---|---|---|
| Líneas de usuario | YAML de 268 líneas | 21 | 21 | 21 | ≤ 25 |
| Esenciales por sección | 0 (enteras) | 5 y 7 | 5 y 10 | 5, 10 y 2 (``forward``) | 5, 12 y 3 |
| Perillas de las tres secciones | 230 (158 + 24 + 48) | 230 | 233 (+ 3) | 233 | la enmienda |
| Segundos al primer resumen | ECL a los 4,8 a 6,4 s | ≈ 1 s («Cartera») | ≈ 1 s | ≈ 1 s | ≤ 30 s |
| Conceptos antes del primer resultado | ≥ 8 | 5 | 5 | 5 | ≤ 5 |

La capa A ancló los esenciales en la firma de ``Ecl``; la B los marca en el schema
(``ui_essential``) y la pantalla los pinta abiertos: el mismo mapeo, atado aquí a los dos.
"""

from __future__ import annotations

import inspect
import re
import time
from collections import Counter
from pathlib import Path
from typing import Final

import pytest
from test_copy_del_formulario import _campos_visibles

_DOCS = Path(__file__).resolve().parents[2] / "docs_site"
_BLOQUE = "primera-provision-ifrs9"

#: Cifra 1: líneas de usuario del notebook mínimo (sin vacías ni comentarios). Tope de Cami
#: (SDD-31 §12.2): 25. 21 el 2026-10-04 (capa A: datos, la puerta, correr, una decisión, `resume`).
LINEAS_DE_USUARIO: Final = 21
TOPE_LINEAS_DE_USUARIO: Final = 25

#: Cifra 5: lo que se importa de `bayesrisk` más los métodos llamados sobre la puerta. 5 el
#: 2026-10-04, los mismos que la enmienda fijó en su §13. Tope: 5 (SDD-31 §5).
CONCEPTOS: Final[frozenset[str]] = frozenset({"Ecl", "materialize", "run", "exclude", "resume"})
TOPE_CONCEPTOS: Final = 5

#: Cifra 2: el mapeo exhaustivo argumento → hoja de §3.7. Es el mismo en la firma de la puerta
#: (capa A) y en las marcas `ui_essential` del schema que pinta la pantalla (capa B, golden de
#: catorce secciones en `test_esenciales_por_seccion.py`).
ESENCIALES: Final[dict[str, dict[str, str]]] = {
    "data": {"data": "data.load.source", "id": "data.schema.index_col | unique_keys"},
    "survival": {
        "duration": "survival.input.duration_col",
        "event": "survival.input.event_col",
        "period": "survival.time_grid.time_unit",
        "horizon": "survival.time_grid.horizon_periods",
        "covariates": "survival.input.covariate_cols",
    },
    "provisioning_ifrs9": {
        "as_of": "provisioning_ifrs9.as_of_date_col",
        "portfolio": "provisioning_ifrs9.portfolio_col",
        "exposure": "provisioning_ifrs9.ead.ead_col",
        "lgd": "provisioning_ifrs9.lgd.lgd_col",
        "rate": "provisioning_ifrs9.ecl.eir_col",
        "days_past_due": "provisioning_ifrs9.staging.days_past_due_col",
        "default": "provisioning_ifrs9.staging.is_default_col",
        # CASO-REAL-IFRS9 D-CRE-8 (§8-3): las tres del contrato, opcionales.
        "origination": "provisioning_ifrs9.origination_date_col",
        "maturity": "provisioning_ifrs9.maturity_date_col",
        "installment": "provisioning_ifrs9.ead.installment_col",
    },
    # IFRS9-FIRMABLE D-FIR-11 (§8-5): las dos tablas de los escenarios, experimentales en la capa A.
    # Escriben la sección `forward` (la historia, su fuente; los escenarios, una trayectoria por
    # escenario con su peso); sus marcas en el schema llegan con la pantalla (capa C).
    "forward": {
        "history": "forward.input.macro_source.path",
        "scenarios": "forward.scenarios.scenarios",
    },
}
#: Los argumentos que no son esenciales de una sección de cálculo: los de `governance`, `report` y
#: `tracking`, como en `Scorecard`, y dónde queda la evidencia.
ARGUMENTOS_DE_INFRAESTRUCTURA: Final = frozenset(
    {"name", "run_dir", "purpose", "owner", "review_every", "track", "document", "formats"}
)
#: El tope de SDD-31 §12.1 y su única excepción, aprobada por Cami el 2026-10-03 (§8-4) con 7 y
#: ampliada a 10 el 2026-10-05 (CASO-REAL-IFRS9 §8-3).
TOPE_ESENCIALES_POR_SECCION: Final = 6
EXCEPCION_AL_TOPE: Final = {"provisioning_ifrs9": 10}

#: Cifra 3: perillas de las tres secciones de cálculo con el barrido del formulario. 230 el
#: 2026-10-02 (S28) y el 2026-10-04: la capa A no añade ni retira hojas (D-ECL-15, presupuesto
#: cero; `rebut_backstops` es una acción de `decisions`, fuera del formulario y del hash). 233 desde
#: la capa B de CASO-REAL-IFRS9 (S35, 2026-10-06): las tres hojas del contrato, con su evidencia
#: de que el default falla en un caso real (§3.8 de esa enmienda); 48 → 51 en la provisión.
SECCIONES_DE_CALCULO: Final[tuple[str, ...]] = ("data", "survival", "provisioning_ifrs9")
PERILLAS_DE_LAS_TRES_SECCIONES: Final = 233

#: Cifra 4: segundos hasta el primer resumen («Cartera») con el dataset del paquete.
TOPE_SEGUNDOS_PRIMER_RESUMEN: Final = 30.0


def _notebook() -> str:
    texto = (_DOCS / "getting-started.md").read_text(encoding="utf-8")
    inicio = f"<!-- {_BLOQUE}:start -->\n```python\n"
    fin = f"\n```\n<!-- {_BLOQUE}:end -->"
    assert texto.count(inicio) == 1 and texto.count(fin) == 1
    return texto.split(inicio, 1)[1].split(fin, 1)[0]


def _lineas_de_usuario(codigo: str) -> list[str]:
    return [ln for ln in codigo.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _conceptos(codigo: str) -> set[str]:
    importados: set[str] = set()
    for grupo in re.findall(r"^from bayesrisk[\w.]* import (.+)$", codigo, flags=re.M):
        importados.update(nombre.strip() for nombre in grupo.split(","))
    return importados | set(re.findall(r"\becl\.(\w+)\(", codigo))


def test_cifra_1_lineas_de_usuario_del_notebook_minimo() -> None:
    lineas = _lineas_de_usuario(_notebook())
    assert len(lineas) == LINEAS_DE_USUARIO, lineas
    assert len(lineas) <= TOPE_LINEAS_DE_USUARIO


def test_cifra_5_conceptos_antes_del_primer_resultado() -> None:
    conceptos = _conceptos(_notebook())
    assert conceptos == set(CONCEPTOS), conceptos
    assert len(conceptos) <= TOPE_CONCEPTOS


def test_cifra_2_cada_argumento_de_la_puerta_es_un_esencial_o_de_infraestructura() -> None:
    """Bidireccional: un argumento sin hoja y una hoja esencial sin argumento ponen rojo."""
    from bayesrisk.guided import Ecl

    argumentos = set(inspect.signature(Ecl).parameters)
    esenciales = {arg for seccion in ESENCIALES.values() for arg in seccion}
    assert argumentos == esenciales | ARGUMENTOS_DE_INFRAESTRUCTURA, argumentos ^ (
        esenciales | ARGUMENTOS_DE_INFRAESTRUCTURA
    )
    assert {s: len(a) for s, a in ESENCIALES.items() if s != "data"} == {
        "survival": 5,
        "provisioning_ifrs9": 10,
        "forward": 2,
    }
    for seccion, args in ESENCIALES.items():
        tope = EXCEPCION_AL_TOPE.get(seccion, TOPE_ESENCIALES_POR_SECCION)
        assert len(args) <= tope, (seccion, len(args))


def test_cifra_2_las_marcas_del_schema_son_los_argumentos_de_la_puerta() -> None:
    """La pantalla abre exactamente las hojas que la puerta pide como argumento (capa B, §3.7)."""
    from test_esenciales_por_seccion import ESENCIALES_POR_SECCION

    for seccion in ("survival", "provisioning_ifrs9"):
        assert sorted(ESENCIALES[seccion].values()) == sorted(ESENCIALES_POR_SECCION[seccion])


def test_cifra_2_cada_argumento_escribe_su_hoja(tmp_path: Path) -> None:
    """El mapeo de §3.7 se mide sobre el config que arma la puerta, no se afirma."""
    from bayesrisk.guided import Ecl
    from bayesrisk.ui.datasets import materialize

    datos = materialize("ifrs9_retail_latam", workdir=tmp_path / "datos")
    ecl = Ecl(
        datos,
        id="loan_id",
        as_of="as_of_date",
        portfolio="portfolio",
        exposure="ead",
        lgd="lgd",
        rate="eir",
        days_past_due="days_past_due",
        default="is_default",
        duration="duration",
        event="event",
        period="quarter",
        horizon=3,
        covariates=["deuda_ingreso"],
        run_dir=tmp_path / "corridas",
    )
    cfg = ecl.config
    ifrs = cfg.provisioning_ifrs9
    assert cfg.data.load.source.endswith(".parquet") and "input" in cfg.data.load.source
    assert cfg.data.schema_.index_col == "loan_id"
    assert (cfg.survival.input.duration_col, cfg.survival.input.event_col) == ("duration", "event")
    assert cfg.survival.time_grid.time_unit == "quarter"
    assert cfg.survival.time_grid.horizon_periods == 3
    assert tuple(cfg.survival.input.covariate_cols) == ("deuda_ingreso",)
    assert (ifrs.as_of_date_col, ifrs.portfolio_col) == ("as_of_date", "portfolio")
    assert (ifrs.ead.ead_col, ifrs.lgd.lgd_col, ifrs.ecl.eir_col) == ("ead", "lgd", "eir")
    assert ifrs.staging.days_past_due_col == "days_past_due"
    assert ifrs.staging.is_default_col == "is_default"


def test_cifra_2_las_tablas_de_escenarios_escriben_su_hoja(tmp_path: Path) -> None:
    """IFRS9-FIRMABLE §3.11: ``history=`` y ``scenarios=`` arman la sección ``forward`` y el ajuste
    por ciclo de la provisión; sin ellas, la sección no existe (sin escenarios, nada cambia)."""
    import numpy as np
    import pandas as pd

    from bayesrisk.guided import Ecl
    from bayesrisk.ui.datasets import materialize

    datos = materialize("ifrs9_retail_latam", workdir=tmp_path / "datos")
    trimestres = pd.date_range("2010-01-01", "2025-04-01", freq="QS")
    u = 7.0 + np.sin(np.arange(len(trimestres)) / 5.0)
    historia = pd.DataFrame({"date": trimestres, "default_rate": 0.02 + 0.002 * (u - 7.0), "u": u})
    futuro = pd.date_range("2025-07-01", periods=8, freq="QS")
    escenarios = pd.DataFrame(
        {
            "scenario": ["base"] * 8 + ["adverso"] * 8,
            "weight": [0.7] * 8 + [0.3] * 8,
            "date": list(futuro) * 2,
            "u": [7.0] * 8 + [9.0] * 8,
        }
    )
    argumentos = dict(
        id="loan_id",
        as_of="as_of_date",
        portfolio="portfolio",
        exposure="ead",
        lgd="lgd",
        rate="eir",
        days_past_due="days_past_due",
        duration="duration",
        event="event",
        period="year",
        horizon=5,
        run_dir=tmp_path / "corridas",
    )
    cfg = Ecl(datos, history=historia, scenarios=escenarios, **argumentos).config
    assert cfg.forward is not None
    assert cfg.forward.input.macro_source.path.endswith(".parquet")
    assert [(e.name, e.weight) for e in cfg.forward.scenarios.scenarios] == [
        ("base", 0.7),
        ("adverso", 0.3),
    ]
    assert cfg.forward.satellite.mode == "reference_rate"
    assert cfg.provisioning_ifrs9.pd.pit_mode == "cycle"
    sin = Ecl(datos, name="sin_escenarios", **argumentos).config
    assert sin.forward is None
    assert sin.provisioning_ifrs9.pd.pit_mode == "ttc_only"


def test_cifra_3_las_perillas_de_las_tres_secciones_no_crecen() -> None:
    por_seccion = Counter(ruta.split(".", 1)[0] for ruta, _ in _campos_visibles())
    total = sum(por_seccion[s] for s in SECCIONES_DE_CALCULO)
    assert total == PERILLAS_DE_LAS_TRES_SECCIONES, {
        s: por_seccion[s] for s in SECCIONES_DE_CALCULO
    }


def test_cifra_4_el_primer_resumen_llega_antes_de_treinta_segundos(tmp_path: Path) -> None:
    """Sobre el dataset del paquete, con el motor real."""
    pytest.importorskip("statsmodels")
    from bayesrisk import Ecl
    from bayesrisk.ui.datasets import materialize

    datos = materialize("ifrs9_retail_latam", workdir=tmp_path / "datasets")
    t0 = time.perf_counter()
    ecl = Ecl(
        datos,
        id="loan_id",
        as_of="as_of_date",
        portfolio="portfolio",
        exposure="ead",
        lgd="lgd",
        rate="eir",
        days_past_due="days_past_due",
        duration="duration",
        event="event",
        period="year",
        horizon=5,
        run_dir=tmp_path / "corridas",
    )
    marcas: list[float] = []
    ecl._echo = lambda _texto: marcas.append(time.perf_counter() - t0)
    ecl.run(until="data")
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    assert marcas, "la etapa «Cartera» no contó nada"
    assert marcas[0] <= TOPE_SEGUNDOS_PRIMER_RESUMEN, marcas[0]
