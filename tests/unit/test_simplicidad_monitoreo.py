"""Las cinco cifras de simplicidad del monitoreo (SDD-31 D-SIM-11; SDD-33 §13).

Gemelo de ``test_simplicidad_ifrs9.py``: cada cifra es un golden con la regla de
``HOJAS_DEL_FORMULARIO`` —moverla es legítimo; moverla sin actualizar el número y decir por qué,
no—. **Antes** (línea base sobre ``375e02e``, S45, 2026-10-13): el monitoreo no existía; medirlo a
mano eran ~100 líneas de código propio (``privado/evidencia/s44/medir_h4.py``). **Después**, capa A
(2.13.0): 3 · 3 · 3 · ≈ 1 s · 2.

| Cifra | ``375e02e`` | Capa A |
|---|---|---|
| Líneas de usuario del notebook mínimo | ~100 (a mano) | 3 |
| Esenciales de ``monitoring`` | — | 3 (``bundle``, ``period``, ``default``) |
| Perillas de ``monitoring`` | — | 3 hojas, cero umbrales |
| Segundos al primer resumen | — | ≈ 1 s (tope 30 s) |
| Conceptos antes del primer resultado | — | 2 (``Monitor``, ``run``) |

El SDD estimó 3 conceptos («tarjeta, periodo, desenlace»): son los tres argumentos; el conteo de
esta regla es el de los gemelos —lo que se importa de ``bayesrisk`` más los métodos llamados sobre
la puerta—, y da 2. Los esenciales se anclan en la firma de ``Monitor`` en la capa A; la marca
``ui_essential`` del schema llega con la pantalla (capa B), como en IFRS 9.
"""

from __future__ import annotations

import inspect
import re
import time
from pathlib import Path
from typing import Final

import pytest

_DOCS = Path(__file__).resolve().parents[2] / "docs_site" / "guias"
_BLOQUE = "monitoreo"

#: Cifra 1: líneas de usuario del notebook mínimo (sin vacías ni comentarios). Tope: 25.
LINEAS_DE_USUARIO: Final = 3
TOPE_LINEAS_DE_USUARIO: Final = 25
#: Cifra 5: lo que se importa de `bayesrisk` más los métodos llamados sobre la puerta. Tope: 5.
CONCEPTOS: Final[frozenset[str]] = frozenset({"Monitor", "run"})
TOPE_CONCEPTOS: Final = 5
#: Cifra 2: el mapeo argumento → hoja de §5.1; ``data`` escribe la sección de datos.
ESENCIALES: Final[dict[str, str]] = {
    "bundle": "monitoring.bundle",
    "data": "data.load.source",
    "period": "monitoring.period",
    "default": "monitoring.default",
}
ARGUMENTOS_DE_INFRAESTRUCTURA: Final = frozenset({"name", "run_dir"})
#: Cifra 3: las hojas de la sección (§13: tres, las entradas de la institución; cero umbrales).
PERILLAS: Final = 3
#: Cifra 4: segundos hasta el primer resumen («Cartera monitoreada»).
TOPE_SEGUNDOS_PRIMER_RESUMEN: Final = 30.0


def _notebook() -> str:
    texto = (_DOCS / "monitoreo.md").read_text(encoding="utf-8")
    inicio = f"<!-- {_BLOQUE}:start -->\n```python\n"
    fin = f"\n```\n<!-- {_BLOQUE}:end -->"
    assert texto.count(inicio) == 1 and texto.count(fin) == 1
    return texto.split(inicio, 1)[1].split(fin, 1)[0]


def _lineas_de_usuario(codigo: str) -> list[str]:
    return [ln for ln in codigo.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def test_cifra_1_lineas_de_usuario_del_notebook_minimo() -> None:
    lineas = _lineas_de_usuario(_notebook())
    assert len(lineas) == LINEAS_DE_USUARIO, lineas
    assert len(lineas) <= TOPE_LINEAS_DE_USUARIO


def test_cifra_5_conceptos_antes_del_primer_resultado() -> None:
    codigo = _notebook()
    importados: set[str] = set()
    for grupo in re.findall(r"^from bayesrisk[\w.]* import (.+)$", codigo, flags=re.M):
        importados.update(nombre.strip() for nombre in grupo.split(","))
    conceptos = importados | set(re.findall(r"\bmon\.(\w+)\(", codigo))
    assert conceptos == set(CONCEPTOS), conceptos
    assert len(conceptos) <= TOPE_CONCEPTOS


def test_cifra_2_cada_argumento_es_un_esencial_o_de_infraestructura() -> None:
    """Bidireccional: un argumento sin hoja y una hoja de la sección sin argumento ponen rojo."""
    from bayesrisk.guided import Monitor
    from bayesrisk.monitoring.config import MonitoringConfig

    argumentos = set(inspect.signature(Monitor).parameters)
    assert argumentos == set(ESENCIALES) | ARGUMENTOS_DE_INFRAESTRUCTURA, argumentos
    hojas = {f"monitoring.{campo}" for campo in MonitoringConfig.model_fields}
    assert hojas == {h for h in ESENCIALES.values() if h.startswith("monitoring.")}
    assert len(hojas) <= 6


def test_cifra_3_la_seccion_tiene_tres_hojas_y_ningun_umbral() -> None:
    from bayesrisk.monitoring.config import MonitoringConfig

    assert len(MonitoringConfig.model_fields) == PERILLAS
    for nombre, campo in MonitoringConfig.model_fields.items():
        assert campo.annotation in (str, str | None), (nombre, campo.annotation)


def test_cifra_4_el_primer_resumen_llega_antes_del_tope(tmp_path: Path) -> None:
    """La corrida de monitoreo sobre una tarjeta ya guardada (la de desarrollo no cuenta)."""
    from test_monitoring import cartera

    from bayesrisk.guided import Monitor, Scorecard
    from bayesrisk.scorecard.bundle import FittedScorecardBundle

    with pytest.MonkeyPatch.context() as parche:
        from conftest import parchar_optbinning

        parchar_optbinning(parche)
        sc = Scorecard(
            cartera(),
            target="bad_flag",
            id="loan_id",
            cohort="cohorte",
            oot_cohorts=["2024Q2"],
            name="dev",
            run_dir=tmp_path,
        )
        sc._echo = lambda _t: None
        sc.run()
        tarjeta = FittedScorecardBundle.from_study(sc.study)
    inicio = time.perf_counter()
    primero: list[float] = []
    mon = Monitor(tarjeta, cartera(), period="cohorte", default="bad_flag", run_dir=tmp_path)
    mon._echo = lambda _t: primero.append(time.perf_counter()) if not primero else None
    mon.run()
    assert mon.study.run_context.status == "done"
    assert primero and primero[0] - inicio <= TOPE_SEGUNDOS_PRIMER_RESUMEN
