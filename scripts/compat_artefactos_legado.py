"""Artefactos de nikodym ≤ 1.20 que tienen que seguir cargando con bayesrisk (D-REN-6).

Dos modos, cada uno en su propio entorno limpio (enmienda RENOMBRE-BAYESRISK, §5.2):

``generar <salida>``
    Con ``nikodym[scoring,report]==X`` REAL instalado desde PyPI y el cwd fuera del checkout: corre
    el preset F1 y deja en ``<salida>`` un ``Study.save`` (artefactos joblib con clases
    ``nikodym.*``), los estimadores en un ``joblib.dump`` directo, el bundle público del
    scorecard y, en ``esperado/``, lo que esos objetos deben reproducir (WoE, PD y la aplicación del
    bundle).

``verificar <salida>``
    Con los wheels nuevos (``bayesrisk`` y ``nikodym`` 1.21) instalados: carga todo lo anterior y
    exige que reproduzca las salidas guardadas, bit a bit, con las clases de bayesrisk.

No es un test de la suite: necesita dos entornos y la versión real publicada. Lo corre el job
``compat`` de ``ci.yml`` y la verificación del renombre (A6).
"""

from __future__ import annotations

import json
import sys
import warnings
from copy import deepcopy
from pathlib import Path


def generar(salida: Path) -> None:
    """Corre el preset F1 con el nikodym instalado y deja los artefactos y sus salidas."""
    import joblib
    import nikodym
    import pandas as pd
    from nikodym.core.build import build_uv_lock_hash
    from nikodym.core.config import NikodymConfig
    from nikodym.core.config.hashing import config_hash
    from nikodym.ui.datasets import materialize
    from nikodym.ui.presets import standard_preset

    salida.mkdir(parents=True, exist_ok=False)
    (salida / "esperado").mkdir()
    preset = standard_preset()
    datos = materialize(preset["dataset_id"], workdir=salida / "wd")
    cfg_dict = deepcopy(preset["config"])
    cfg_dict["data"]["load"]["source"] = str(datos)
    config = NikodymConfig.model_validate(cfg_dict)

    study = nikodym.run(config, run_dir=salida / "corrida")
    assert study.run_context.status == "done", study.run_context.status
    study.save(salida / "study")

    binner = study.artifacts.get("binning", "process")
    modelo = study.artifacts.get("model", "estimator")
    joblib.dump({"binner": binner, "modelo": modelo}, salida / "estimadores.joblib")
    frame = pd.read_parquet(datos)
    woe = binner.transform(frame)
    woe.to_parquet(salida / "esperado" / "woe.parquet")
    columnas = list(study.artifacts.get("model", "final_woe_columns"))
    pd.DataFrame({"pd": modelo.predict_pd(woe[columnas])}).to_parquet(
        salida / "esperado" / "pd.parquet"
    )

    cfg_bundle = deepcopy(cfg_dict)
    cfg_bundle["audit"]["trail_filename"] = str(salida / "bundle_trail.jsonl")
    bundle = nikodym.fit_scorecard_bundle(NikodymConfig.model_validate(cfg_bundle), frame)
    bundle.save(salida / "bundle")
    aplicado = nikodym.apply(salida / "bundle", frame)
    aplicado.application_frame.to_parquet(salida / "esperado" / "bundle_apply.parquet")

    (salida / "meta.json").write_text(
        json.dumps(
            {
                "nikodym": nikodym.__version__,
                "config_hash": config_hash(config),
                "uv_lock_hash": build_uv_lock_hash(),
                "datos": str(datos),
                "columnas_modelo": columnas,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"generado con nikodym {nikodym.__version__}: {salida}")


def verificar(salida: Path) -> None:
    """Carga los artefactos con bayesrisk + nikodym 1.21 y exige reproducir sus salidas."""
    import joblib
    import pandas as pd
    from pandas.testing import assert_frame_equal

    import bayesrisk
    from bayesrisk.binning.transformer import WoEBinner
    from bayesrisk.core.config.hashing import config_hash
    from bayesrisk.core.study import Study
    from bayesrisk.model.estimator import LogisticPDModel

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import nikodym  # noqa: F401 — lo instala el usuario: el alias de los pickles viejos

    meta = json.loads((salida / "meta.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(meta["datos"])

    estudio = Study.load(salida / "study", trust=True)
    assert config_hash(estudio.config) == meta["config_hash"]
    binner = estudio.artifacts.get("binning", "process")
    assert type(binner) is WoEBinner, type(binner)

    estimadores = joblib.load(salida / "estimadores.joblib")
    assert type(estimadores["binner"]) is WoEBinner
    assert type(estimadores["modelo"]) is LogisticPDModel
    woe = estimadores["binner"].transform(frame)
    assert_frame_equal(woe, pd.read_parquet(salida / "esperado" / "woe.parquet"))
    pd_ = estimadores["modelo"].predict_pd(woe[meta["columnas_modelo"]])
    assert_frame_equal(
        pd.DataFrame({"pd": pd_}), pd.read_parquet(salida / "esperado" / "pd.parquet")
    )

    aplicado = bayesrisk.apply(salida / "bundle", frame)
    assert_frame_equal(
        aplicado.application_frame,
        pd.read_parquet(salida / "esperado" / "bundle_apply.parquet"),
    )
    print(
        f"artefactos de nikodym {meta['nikodym']} cargados y reproducidos con "
        f"bayesrisk {bayesrisk.__version__}"
    )


if __name__ == "__main__":
    modo, destino = sys.argv[1], Path(sys.argv[2]).resolve()
    {"generar": generar, "verificar": verificar}[modo](destino)
