"""``Study.load`` tipa las secciones del config aunque el proceso no haya importado sus dominios.

Defecto medido en S47 y corregido en S49: en un intérprete nuevo, el **primer**
``Study.load(ruta, trust=True)`` devolvía el config con las secciones de dominio (``data``,
``binning``, ``model``, ``scorecard``…) como ``dict``; el segundo load del mismo proceso ya las
tipaba, y ``FittedScorecardBundle.from_study`` reventaba sobre el primero
(``'dict' object has no attribute …``). La causa: ``Study.load`` validaba el YAML **antes** de que
las capas de dominio registraran su clase de config (``cargar_configs_de_dominio``), y las
importaba después, dentro de ``config_hash``. Es el mismo principio de D-HASH-1/D-HASH-5: que una
sección se valide o quede opaca no puede depender de qué importó el proceso antes.

Los dos tests corren el load en un intérprete **nuevo**: en el de pytest los dominios ya están
importados y el defecto no se ve.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from bayesrisk.core.config import BayesRiskConfig
from bayesrisk.core.config.schema import cargar_configs_expandibles
from bayesrisk.core.study import Study
from bayesrisk.ui.presets import standard_preset

_ENTORNO = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"}

#: El hijo: un solo ``Study.load`` y el tipo de cada sección declarada del config.
_TIPOS = textwrap.dedent(
    """
    import json, sys
    from bayesrisk.core.study import Study, _DOMAIN_CONFIG_CLASSES, _INFRA_CONFIG_CLASSES
    estudio = Study.load(sys.argv[1], trust=True)
    secciones = sorted({*_DOMAIN_CONFIG_CLASSES, *_INFRA_CONFIG_CLASSES})
    tipos = {n: type(getattr(estudio.config, n)).__name__ for n in secciones
             if getattr(estudio.config, n, None) is not None}
    print("JSON " + json.dumps(tipos))
    """
)


def _correr(codigo: str, *args: str) -> Any:
    proceso = subprocess.run(
        [sys.executable, "-c", codigo, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_ENTORNO,
        check=False,
    )
    lineas = [ln for ln in proceso.stdout.splitlines() if ln.startswith("JSON ")]
    assert proceso.returncode == 0 and lineas, proceso.stderr[-3000:]
    return json.loads(lineas[-1][5:])


def test_el_primer_load_de_un_proceso_tipa_cada_seccion_declarada(tmp_path: Path) -> None:
    """Con el preset F1 y la ficha declarada: ninguna sección vuelve como ``dict``."""
    cargar_configs_expandibles()
    crudo = standard_preset()["config"]
    crudo["governance"] = {"purpose": "Prueba del primer load de un proceso."}
    config = BayesRiskConfig.model_validate(crudo)
    destino = Study(config).save(tmp_path / "estudio")

    tipos = _correr(_TIPOS, str(destino))

    assert {"data", "binning", "model", "scorecard", "governance"} <= set(tipos)
    opacas = sorted(n for n, t in tipos.items() if t == "dict")
    assert not opacas, f"secciones opacas tras el primer load: {opacas}"


#: El hijo del caso de uso: una corrida guiada guardada, recargada en OTRO intérprete y congelada
#: en su tarjeta, que puntúa. Es lo que reventaba en S47.
_CORRIDA = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    import pandas as pd
    from bayesrisk import Scorecard
    from bayesrisk.ui.datasets import materialize
    raiz = Path(sys.argv[1])
    frame = pd.read_parquet(materialize("consumo_comportamiento", workdir=raiz / "datos"))
    sc = Scorecard(frame, target="bad_flag", id="loan_id", cohort="cohorte",
                   oot_cohorts=["2024Q2"], name="carga", run_dir=raiz / "corridas")
    sc._echo = lambda _t: None
    sc.run()
    assert sc.study.run_context.status == "done", sc.study.run_context.error
    print("JSON " + json.dumps({"filas": len(frame)}))
    """
)
_DESDE_LA_CARPETA = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    import pandas as pd
    from bayesrisk.core.study import Study
    from bayesrisk.scorecard.bundle import FittedScorecardBundle
    from bayesrisk.ui.datasets import materialize
    raiz = Path(sys.argv[1])
    estudio = Study.load(raiz / "corridas" / "carga" / "run" / "study", trust=True)
    tarjeta = FittedScorecardBundle.from_study(estudio)
    frame = pd.read_parquet(materialize("consumo_comportamiento", workdir=raiz / "datos"))
    puntajes = tarjeta.apply(frame).application_frame["score"]
    print("JSON " + json.dumps({"puntuadas": int(puntajes.notna().sum())}))
    """
)


def test_from_study_funciona_sobre_el_primer_load_de_una_corrida_guardada(tmp_path: Path) -> None:
    """La corrida guiada de verdad (OptBinning real): recargada en un proceso nuevo, se congela."""
    pytest.importorskip("optbinning")
    filas = _correr(_CORRIDA, str(tmp_path))["filas"]
    assert _correr(_DESDE_LA_CARPETA, str(tmp_path))["puntuadas"] == filas
