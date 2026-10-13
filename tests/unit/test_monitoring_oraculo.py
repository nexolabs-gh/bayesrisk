"""Oráculo del monitoreo con OptBinning real (SDD-33 §0.3 y §11), en un subproceso.

OR-Tools revienta el proceso de pytest (S20), así que las dos corridas guiadas del scorecard
—``consumo_comportamiento`` y ``consumo_drift``— y sus monitoreos corren en un intérprete aparte y
devuelven lo medido en JSON. Los valores esperados son los de la medición de S44 (repo privado,
``evidencia/s44/``: ``veredictos_h4.txt``, ``medir_h4_b.txt``, ``medir_h4_d.txt``):

- el PSI del puntaje, la tasa de malos y la PD esperada de la cartera, el AUC sobre los tramos y la
  pendiente de calibración de cada cohorte, a los decimales que S44 publicó;
- el p-valor de la prueba del BCE contra el AUC inicial de Holdout, a 0,002 del de S44: S44 lo
  calculó con cifras intermedias redondeadas —el AUC inicial implícito en sus p-valores va de
  0,67875 a 0,67893 según la cohorte, y el exacto es 0,678790— y con un guion que no quedó en la
  evidencia (``veredictos_h4.txt`` sin su generador). Dos valores de S44 no se reproducen y no se
  cotejan (``None``): la cartera estable en 2023Q2 y 2023Q4 (0,9461 y 0,8948; el motor, 0,9278 y
  0,9008), con el motor igual al anexo 3.1 par a par (``test_monitoring_engine.py``) y el mismo
  semáforo verde; ninguno es una cifra que publique el SDD;
- el veredicto de cada cohorte con la tabla de §3.5 y la precisión de Cami del 2026-10-13 (el
  ámbar de un tramo suelto no pide vigilar).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Final

import pytest

_CODIGO = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    import numpy as np
    import pandas as pd
    from bayesrisk import FittedScorecardBundle, Monitor, Scorecard
    from bayesrisk.monitoring import engine
    from bayesrisk.ui.datasets import materialize

    raiz = Path(sys.argv[1])

    def datos(nombre):
        return pd.read_parquet(materialize(nombre, workdir=raiz / "datos" / nombre))

    def tarjeta(nombre):
        sc = Scorecard(datos(nombre), target="bad_flag", id="loan_id", cohort="cohorte",
                       oot_cohorts=["2024Q2"], name=f"dev-{nombre}", run_dir=raiz / "corridas")
        sc._echo = lambda _t: None
        sc.run()
        assert sc.study.run_context.status == "done", sc.study.run_context.error
        return FittedScorecardBundle.from_study(sc.study)

    def monitorear(caso, card, frame):
        mon = Monitor(card, frame, period="cohorte", default="bad_flag", name=caso,
                      run_dir=raiz / "monitoreos")
        mon._echo = lambda _t: None
        mon.run()
        ctx = mon.study.run_context
        assert ctx.status == "done", ctx.error
        p = mon.study.artifacts.get("monitoring", "periods")
        columnas = ["period", "psi_score", "bad_rate", "expected_pd", "portfolio_light",
                    "portfolio_direction", "auc", "auc_std", "auc_p_value", "auc_light", "slope",
                    "slope_p_value", "slope_light", "red_grades", "verdict"]
        return json.loads(p[columnas].to_json(orient="records"))

    comportamiento = tarjeta("consumo_comportamiento")
    drift = tarjeta("consumo_drift")
    salida = {
        "pd": comportamiento.manifest["master_scale"]["grade_pd"],
        "auc_inicial": {
            "comportamiento": comportamiento.manifest["monitoring_reference"]["auc_initial"],
            "drift": drift.manifest["monitoring_reference"]["auc_initial"],
        },
        "misma": monitorear("misma", comportamiento, datos("consumo_comportamiento")),
        "trasladada": monitorear("trasladada", comportamiento, datos("consumo_drift")),
        "drift_propia": monitorear("drift-propia", drift, datos("consumo_drift")),
    }

    # La deriva de calibración de S44: en la cohorte OOT, un tercio de los buenos de los tramos 3
    # a 5 pasa a malo (semilla fija), con los tramos que la tarjeta asigna.
    frame = datos("consumo_comportamiento")
    grados = comportamiento.apply(frame).application_frame["grade"]
    rng = np.random.default_rng(20261012)
    marcar = (frame["cohorte"].eq("2024Q2") & frame["bad_flag"].eq(0)
              & (grados.fillna(0) >= 3) & (rng.random(len(frame)) < 1 / 3))
    frame.loc[marcar, "bad_flag"] = 1
    salida["calibracion"] = monitorear("calibracion", comportamiento, frame)

    # La discriminación rota: las variables de la OOT barajadas entre sus filas —el modelo deja de
    # ordenar, la población no cambia—, por la puerta guiada.
    frame = datos("consumo_comportamiento")
    oot = frame.index[frame["cohorte"].eq("2024Q2")]
    variables = comportamiento.manifest["model"]["features"]
    frame.loc[oot, variables] = frame.loc[oot, variables].to_numpy()[
        np.random.default_rng(7).permutation(len(oot))
    ]
    salida["barajada"] = monitorear("barajada", comportamiento, frame)

    # Y la de S44 tal cual (los tramos de la OOT barajados con la semilla 7), por el motor.
    frame = datos("consumo_comportamiento")
    base = frame[["cohorte", "bad_flag"]].join(
        comportamiento.apply(frame).application_frame[["grade"]]).dropna()
    base["grade"] = base["grade"].astype(int)
    oot = base["cohorte"].eq("2024Q2")
    base.loc[oot, "grade"] = np.random.default_rng(7).permutation(base.loc[oot, "grade"].to_numpy())
    g, y = base.loc[oot, "grade"].to_numpy(), base.loc[oot, "bad_flag"].to_numpy()
    k = len(salida["pd"])
    malos = [int(((g == t) & (y == 1)).sum()) for t in range(1, k + 1)]
    buenos = [int(((g == t) & (y == 0)).sum()) for t in range(1, k + 1)]
    pendiente = engine.pendiente_de_calibracion(
        [m + b for m, b in zip(malos, buenos)], malos, salida["pd"])
    salida["barajada_s44"] = {
        "auc": engine.auc_sobre_tramos(malos, buenos).auc, "slope": pendiente.slope}
    print("JSON " + json.dumps(salida))
    """
)


@pytest.fixture(scope="module")
def medido(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    pytest.importorskip("optbinning")
    destino: Path = tmp_path_factory.mktemp("oraculo_monitoreo")
    proceso = subprocess.run(
        [sys.executable, "-c", _CODIGO, str(destino)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        # El hijo escribe en UTF-8 aunque la consola de Windows sea cp1252 (sus avisos llevan
        # tildes): sin esto el hilo lector reventaba en el CI de Windows.
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"},
        check=False,
    )
    lineas = [ln for ln in proceso.stdout.splitlines() if ln.startswith("JSON ")]
    assert proceso.returncode == 0 and lineas, proceso.stderr[-3000:]
    resultado: dict[str, Any] = json.loads(lineas[-1][5:])
    return resultado


def _columna(filas: list[dict[str, Any]], clave: str, decimales: int | None = None) -> list[Any]:
    if decimales is None:
        return [f[clave] for f in filas]
    return [round(f[clave], decimales) for f in filas]


#: S44 (``veredictos_h4.txt``, ``medir_h4_b.txt``, ``medir_h4_d.txt``): la tarjeta de
#: ``consumo_comportamiento`` sobre su propia cartera.
MISMA: Final[dict[str, list[Any]]] = {
    "psi_score": [0.0056, 0.0034, 0.0043, 0.0105, 0.0074, 0.0068],
    "bad_rate": [0.2388, 0.2196, 0.2255, 0.2339, 0.2525, 0.2371],
    "expected_pd": [0.2339, 0.2311, 0.2371, 0.2311, 0.2347, 0.2295],
    "auc": [0.713, 0.7084, 0.6989, 0.7059, 0.6891, 0.6549],
    "auc_p_value": [0.9601, None, 0.8233, None, 0.6530, 0.0915],
    "slope": [1.050, 0.998, 0.924, 1.007, 0.865, 0.683],
    "verdict": ["no_action"] * 5 + ["watch"],
}
#: La misma tarjeta sobre ``consumo_drift``, una cartera que se deteriora (el uso real).
TRASLADADA: Final[dict[str, list[Any]]] = {
    "psi_score": [0.0094, 0.1082, 0.5136, 0.9266, 1.5918, 2.0405],
    "bad_rate": [0.2293, 0.2744, 0.3337, 0.3678, 0.4291, 0.4852],
    "expected_pd": [0.2248, 0.2777, 0.3359, 0.374, 0.4122, 0.4372],
    "auc": [0.6834, 0.6858, 0.6672, 0.662, 0.6732, 0.6642],
    "auc_p_value": [0.5353, 0.5912, 0.2014, 0.1178, 0.2905, 0.1187],
    "slope": [0.843, 0.900, 0.825, 0.902, 1.180, 1.247],
    "verdict": ["watch"] * 5 + ["recalibrate"],
}
#: ``consumo_drift`` con su propia tarjeta (7 tramos): la población se mueve y el modelo aguanta.
DRIFT_PROPIA: Final[dict[str, list[Any]]] = {
    "psi_score": [0.4938, 0.1551, 0.0186, 0.1133, 0.3835, 0.7454],
    "auc": [0.7195, 0.714, 0.7091, 0.6992, 0.7128, 0.7002],
    "auc_p_value": [0.9834, 0.9769, 0.9660, 0.8893, 0.9856, 0.9160],
    "slope": [1.035, 0.976, 0.902, 0.929, 1.023, 0.939],
    "verdict": ["watch", "watch", "no_action", "watch", "watch", "watch"],
}


def test_la_pd_de_los_tramos_y_el_auc_inicial_son_los_medidos(medido: dict[str, Any]) -> None:
    assert [round(100 * p, 3) for p in medido["pd"]] == [4.768, 13.962, 24.887, 36.85, 53.515]
    inicial = medido["auc_inicial"]
    assert inicial["comportamiento"]["source"] == inicial["drift"]["source"] == "holdout"
    assert round(inicial["comportamiento"]["auc"], 4) == 0.6816
    assert round(inicial["drift"]["auc"], 4) == 0.6788


@pytest.mark.parametrize(
    ("caso", "esperado"),
    [("misma", MISMA), ("trasladada", TRASLADADA), ("drift_propia", DRIFT_PROPIA)],
)
def test_las_cifras_y_los_veredictos_de_0_3(
    medido: dict[str, Any], caso: str, esperado: dict[str, list[Any]]
) -> None:
    filas = medido[caso]
    assert _columna(filas, "period") == ["2023Q1", "2023Q2", "2023Q3", "2023Q4", "2024Q1", "2024Q2"]
    for clave, valores in esperado.items():
        if clave == "verdict":
            assert _columna(filas, clave) == valores
        elif clave == "auc_p_value":
            for fila, s44 in zip(filas, valores, strict=True):
                if s44 is not None:
                    assert fila[clave] == pytest.approx(s44, abs=2e-3), (caso, fila["period"])
                assert fila["auc_light"] == "green", (caso, fila["period"])
        else:
            decimales = 3 if clave == "slope" else 4
            assert _columna(filas, clave, decimales) == valores, (caso, clave)


def test_la_tarjeta_trasladada_recalibra_cuando_el_nivel_se_desvia(medido: dict[str, Any]) -> None:
    ultima = medido["trasladada"][-1]
    assert (ultima["portfolio_light"], ultima["portfolio_direction"]) == ("red", "under")
    assert ultima["red_grades"] == "5"
    assert medido["trasladada"][0]["red_grades"] == "1"


def test_la_deriva_de_calibracion_la_ve_la_tasa_por_tramo_y_no_el_psi(
    medido: dict[str, Any],
) -> None:
    """§0.3: PSI 0,007 con cuatro tramos rojos; sólo la calibración lo detecta."""
    filas = medido["calibracion"]
    assert _columna(filas[:5], "verdict") == ["no_action"] * 5
    ultima = filas[-1]
    assert round(ultima["psi_score"], 4) == 0.0068
    assert (round(ultima["bad_rate"], 4), round(ultima["expected_pd"], 4)) == (0.3433, 0.2295)
    assert ultima["portfolio_light"] == "red" and ultima["red_grades"] == "1, 3, 4, 5"
    assert ultima["verdict"] == "recalibrate"


def test_la_discriminacion_rota_redesarrolla(medido: dict[str, Any]) -> None:
    """§0.3: la OOT deja de ordenar; las dos pruebas rojas. Y las cifras de S44, por el motor."""
    ultima = medido["barajada"][-1]
    assert (ultima["auc_light"], ultima["slope_light"], ultima["verdict"]) == (
        "red",
        "red",
        "redevelop",
    )
    assert ultima["auc"] < 0.55 and ultima["slope"] < 0.5
    assert _columna(medido["barajada"][:5], "verdict") == ["no_action"] * 5
    s44 = medido["barajada_s44"]
    assert (round(s44["auc"], 4), round(s44["slope"], 3)) == (0.4732, -0.115)
