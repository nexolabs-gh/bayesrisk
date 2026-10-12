"""Oráculo de la escala maestra con OptBinning real (SDD-32 §11), en un subproceso.

OR-Tools revienta el proceso de pytest (S20), así que la corrida guiada sobre
``consumo_comportamiento`` corre en un intérprete aparte y devuelve lo medido en JSON. Los valores
esperados son los de la medición de S41 (repo privado, ``evidencia/s41/``):

- los cortes y los conteos por tramo y muestra de la regla A de ``medir_h5.py`` (OptimalBinning
  con su solver por omisión; la librería usa ``mip``/``bop`` y forma los mismos, medido en S42);
- la PD de cada tramo, su ``δ`` y los semáforos de Jeffreys de ``oraculo_pd_tramo.py``, que
  calcula D-ESC-2 tal cual (conteos enteros, suavizado, PAVA, ``δ`` por bisección y Jeffreys).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Final

import pytest

#: Regla A de ``medir_h5.py`` sobre ``consumo_comportamiento`` (salida ``h5_consumo.txt``).
CORTES: Final = [493.5, 511.5, 526.5, 555.5]
CONTEOS: Final[dict[str, list[int]]] = {
    "desarrollo": [491, 1397, 956, 781, 336],
    "holdout": [131, 358, 240, 213, 89],
    "oot": [135, 369, 226, 190, 88],
}
#: ``oraculo_pd_tramo.py`` sobre esos conteos (salida ``oraculo_pd_tramo.txt``).
PD_PORCENTUAL: Final = [4.768, 13.962, 24.887, 36.85, 53.515]
DELTA: Final = -0.001826
SEMAFOROS: Final[dict[str, list[str]]] = {
    "desarrollo": ["green"] * 5,
    "holdout": ["amber", "green", "green", "green", "green"],
    "oot": ["red", "amber", "green", "green", "green"],
}

_CODIGO = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    from bayesrisk import Scorecard
    from bayesrisk.ui.datasets import materialize

    destino = Path(sys.argv[1])
    datos = materialize("consumo_comportamiento", workdir=destino)
    sc = Scorecard(datos, target="bad_flag", id="loan_id", cohort="cohorte",
                   oot_cohorts=["2024Q2"], name="oraculo", run_dir=destino / "corridas")
    sc._echo = lambda _t: None
    sc.run()
    ctx = sc.study.run_context
    ficha = sc.study.artifacts.get("master_scale", "card")
    tabla = sc.study.artifacts.get("master_scale", "grade_table")
    salida = {
        "status": ctx.status,
        "error": None if ctx.error is None else ctx.error.message,
        "cortes": list(ficha.cuts),
        "estado": ficha.solver_status,
        "pd": list(ficha.pd),
        "delta": ficha.delta,
        "conteos": {m: g["n"].tolist() for m, g in tabla.groupby("sample", sort=False)},
        "semaforos": {
            m: g["traffic_light"].tolist() for m, g in tabla.groupby("sample", sort=False)
        },
    }
    print("JSON " + json.dumps(salida))
    """
)


@pytest.fixture(scope="module")
def medido(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    pytest.importorskip("optbinning")
    destino: Path = tmp_path_factory.mktemp("oraculo_escala")
    proceso = subprocess.run(
        [sys.executable, "-c", _CODIGO, str(destino)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    lineas = [ln for ln in proceso.stdout.splitlines() if ln.startswith("JSON ")]
    assert proceso.returncode == 0 and lineas, proceso.stderr[-3000:]
    resultado: dict[str, Any] = json.loads(lineas[-1][5:])
    assert resultado["status"] == "done", resultado["error"]
    return resultado


def test_los_tramos_son_los_de_la_regla_medida(medido: dict[str, Any]) -> None:
    assert medido["cortes"] == CORTES
    assert medido["estado"] == "OPTIMAL"
    assert medido["conteos"] == CONTEOS


def test_la_pd_el_delta_y_jeffreys_son_los_del_oraculo(medido: dict[str, Any]) -> None:
    assert [round(100 * p, 3) for p in medido["pd"]] == PD_PORCENTUAL
    assert round(medido["delta"], 6) == DELTA
    assert medido["semaforos"] == SEMAFOROS
