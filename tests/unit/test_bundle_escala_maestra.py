"""La tarjeta lleva la escala maestra y respeta ``clip`` (SDD-32 D-ESC-6 y §12-9).

El bundle de esquema 3 congela ``model.clip`` —con límites de puntaje y ``clip=False`` la corrida
no recorta y la tarjeta tampoco— y, si la corrida tiene escala, su bloque ``master_scale``: los
cortes, la PD de cada tramo y el corte de aprobación. ``apply`` agrega ``grade``, ``grade_pd`` y,
con corte, ``decision``. Un bundle guardado antes (esquemas 1 y 2) conserva su comportamiento.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from _ui_f1 import full_f1_config, write_behavior_parquet

import bayesrisk.scorecard.bundle as bundle_module
from bayesrisk.api import run
from bayesrisk.data.config import MissingConfig, SpecialValueSpec
from bayesrisk.master_scale.config import MasterScaleConfig
from bayesrisk.scorecard.bundle import FittedScorecardBundle
from bayesrisk.scorecard.exceptions import ScorecardBundleError

#: Las columnas de ``apply`` de siempre, sin escala (las de la 2.10.0).
_COLUMNAS_DE_SIEMPRE = [
    "input_position",
    "input_id",
    "input_row_hash",
    "scoring_status",
    "treatment_flags",
    "rejection_reason",
    "not_scorable_reason",
    "eta",
    "linear_predictor",
    "pd_raw",
    "score_unrounded",
    "score",
    "pd_calibrated",
    "warning_codes",
    "bundle_hash",
    "treatment_trace_hash",
]


@pytest.fixture(autouse=True)
def _usar_fake_binning_process(fake_binning_process: object) -> None:
    """Evita OR-Tools: el binning y la formación de la escala usan los dobles deterministas."""
    del fake_binning_process


def _corrida(
    tmp_path: Path,
    *,
    escala: dict[str, Any] | None,
    scorecard: dict[str, Any] | None = None,
) -> tuple[Any, pd.DataFrame]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "development.parquet"
    write_behavior_parquet(source)
    frame = pd.read_parquet(source)
    config = full_f1_config(str(source))
    assert config.data is not None and config.scorecard is not None
    updates: dict[str, Any] = {
        "data": config.data.model_copy(
            update={
                "missing": MissingConfig(
                    special_values=(
                        SpecialValueSpec(
                            columns=("score",), sentinels=(-99999.0,), label="sin_score"
                        ),
                    )
                )
            }
        )
    }
    if escala is not None:
        updates["master_scale"] = MasterScaleConfig(**escala)
    if scorecard is not None:
        updates["scorecard"] = type(config.scorecard).model_validate(
            {**config.scorecard.model_dump(mode="python"), **scorecard}
        )
    study = run(config.model_copy(update=updates))
    assert study.run_context.status == "done", study.run_context.error
    return study, frame.drop(columns=["bad_flag", "cohort"])


def test_la_tarjeta_congela_la_escala_y_apply_devuelve_tramo_pd_y_decision(
    tmp_path: Path,
) -> None:
    sin_corte, _ = _corrida(tmp_path / "a", escala={})
    cortes = sin_corte.artifacts.get("master_scale", "card").cuts
    assert cortes, "el doble de OptBinning forma al menos un corte"
    corte = float(cortes[len(cortes) // 2])
    study, solicitudes = _corrida(tmp_path / "b", escala={"approval_cutoff": corte})
    bundle = FittedScorecardBundle.from_study(study)
    manifest = bundle.manifest
    assert manifest["schema_version"] == 3
    ficha = study.artifacts.get("master_scale", "card")
    assert manifest["master_scale"] == {
        "cuts": list(ficha.cuts),
        "grade_pd": list(ficha.pd),
        "approval_cutoff": corte,
        "source": "formed",
    }
    cargado = FittedScorecardBundle.load(bundle.save(tmp_path / "tarjeta"))
    assert cargado.bundle_hash == bundle.bundle_hash
    aplicada = cargado.apply(solicitudes).application_frame
    asignacion = study.artifacts.get("master_scale", "assignment")
    comun = aplicada.index.intersection(asignacion.index)
    assert len(comun) == len(asignacion.index)
    assert aplicada.loc[comun, "grade"].tolist() == asignacion.loc[comun, "grade"].tolist()
    assert aplicada.loc[comun, "grade_pd"].tolist() == asignacion.loc[comun, "grade_pd"].tolist()
    esperada = np.where(aplicada["score"].astype(float) >= corte, "approve", "reject")
    assert aplicada["decision"].tolist() == esperada.tolist()
    assert list(aplicada.columns) == [*_COLUMNAS_DE_SIEMPRE, "grade", "grade_pd", "decision"]


def test_sin_corte_no_hay_decision_y_una_fila_no_puntuable_no_tiene_tramo(
    tmp_path: Path,
) -> None:
    study, solicitudes = _corrida(tmp_path, escala={})
    bundle = FittedScorecardBundle.from_study(study)
    mezcla = solicitudes.iloc[:3].copy()
    mezcla.iloc[1, mezcla.columns.get_loc("score")] = -99999
    aplicada = bundle.apply(mezcla).application_frame
    assert aplicada["scoring_status"].tolist() == ["scored", "not_scorable", "scored"]
    assert "decision" not in aplicada.columns
    assert pd.isna(aplicada.iloc[1]["grade"]) and pd.isna(aplicada.iloc[1]["grade_pd"])
    assert aplicada.iloc[[0, 2]]["grade"].notna().all()


def test_sin_escala_apply_devuelve_las_columnas_y_valores_de_siempre(tmp_path: Path) -> None:
    study, solicitudes = _corrida(tmp_path, escala=None)
    assert not study.artifacts.has("master_scale", "card")
    bundle = FittedScorecardBundle.from_study(study)
    assert "master_scale" not in bundle.manifest
    aplicada = bundle.apply(solicitudes).application_frame
    assert list(aplicada.columns) == _COLUMNAS_DE_SIEMPRE
    assert (aplicada["bundle_hash"] == bundle.bundle_hash).all()
    puntaje = study.artifacts.get("scorecard", "score")["score"]
    pd.testing.assert_series_equal(
        aplicada["score"].astype("float64"),
        puntaje.loc[solicitudes.index].astype("float64"),
        check_names=False,
    )


@pytest.mark.parametrize("direccion", ["higher_is_lower_risk", "higher_is_higher_risk"])
def test_apply_decide_con_la_regla_unica_en_las_dos_direcciones(direccion: str) -> None:
    corte = 541.0
    puntajes = [541.0, 540.0, 542.0, float(np.nextafter(541.0, 0)), 493.5, np.nan]
    aplicacion = pd.DataFrame(
        {
            "score": pd.array(puntajes, dtype="Float64"),
            "scoring_status": ["scored"] * 5 + ["not_scorable"],
        }
    )
    escala = {
        "cuts": [493.5, 541.0],
        "grade_pd": [0.05, 0.2, 0.5],
        "approval_cutoff": corte,
        "source": "institution",
    }
    bundle_module._aplicar_escala(aplicacion, escala, score_direction=direccion)
    lado_mayor = [True, False, True, False, False]
    if direccion == "higher_is_lower_risk":
        assert aplicacion["decision"].tolist()[:5] == [
            "approve" if m else "reject" for m in lado_mayor
        ]
        assert aplicacion["grade"].tolist()[:5] == [1, 2, 1, 2, 2]
    else:
        assert aplicacion["decision"].tolist()[:5] == [
            "reject" if m else "approve" for m in lado_mayor
        ]
        assert aplicacion["grade"].tolist()[:5] == [3, 2, 3, 2, 2]
    assert aplicacion["decision"].iloc[5] is None
    assert pd.isna(aplicacion["grade"].iloc[5])


# ───────────────────────────── §12-9: la tarjeta respeta `clip` ─────────────────────────────


def _limites_dentro(tmp_path: Path) -> tuple[float, float]:
    study, _ = _corrida(tmp_path, escala=None)
    puntaje = study.artifacts.get("scorecard", "score")["score"].astype(float)
    bajo, alto = float(np.quantile(puntaje, 0.25)), float(np.quantile(puntaje, 0.75))
    assert puntaje.min() < bajo < alto < puntaje.max()
    return bajo, alto


@pytest.mark.parametrize("clip", [False, True])
def test_la_tarjeta_nueva_recorta_exactamente_como_la_corrida(tmp_path: Path, clip: bool) -> None:
    bajo, alto = _limites_dentro(tmp_path / "base")
    study, solicitudes = _corrida(
        tmp_path / "con_limites",
        escala=None,
        scorecard={"min_score": bajo, "max_score": alto, "clip": clip},
    )
    bundle = FittedScorecardBundle.from_study(study)
    assert bundle.manifest["model"]["clip"] is clip
    aplicada = bundle.apply(solicitudes).application_frame["score"].astype("float64")
    corrida = study.artifacts.get("scorecard", "score")["score"].astype("float64")
    pd.testing.assert_series_equal(aplicada, corrida.loc[solicitudes.index], check_names=False)
    fuera = (corrida < bajo) | (corrida > alto)
    assert fuera.any() is not clip


def test_un_bundle_guardado_sin_clip_recorta_como_antes(tmp_path: Path) -> None:
    """Esquema 2 (sin ``model.clip``): recorta siempre, como antes de la 2.11.0."""
    bajo, alto = _limites_dentro(tmp_path / "base")
    study, solicitudes = _corrida(
        tmp_path / "con_limites",
        escala={},
        scorecard={"min_score": bajo, "max_score": alto, "clip": False},
    )
    nuevo = FittedScorecardBundle.from_study(study)
    manifest = nuevo.manifest
    manifest["schema_version"] = 2
    del manifest["model"]["clip"]
    del manifest["master_scale"]
    manifest["bundle_hash"] = bundle_module._bundle_hash(manifest)
    viejo = FittedScorecardBundle(manifest=manifest, rules=nuevo._rules)
    aplicada = viejo.apply(solicitudes).application_frame
    assert aplicada["score"].astype(float).between(bajo, alto).all()
    assert "grade" not in aplicada.columns
    assert viejo.apply(solicitudes).lineage["bundle_schema_version"] == 2


def test_el_manifest_de_esquema_3_se_valida(tmp_path: Path) -> None:
    study, _ = _corrida(tmp_path, escala={})
    bundle = FittedScorecardBundle.from_study(study)

    def mutado(cambio: Any) -> dict[str, Any]:
        manifest = bundle.manifest
        cambio(manifest)
        manifest["bundle_hash"] = bundle_module._bundle_hash(manifest)
        return manifest

    malos = [
        lambda m: m["model"].__setitem__("clip", "no"),
        lambda m: m["model"].pop("clip"),
        lambda m: m["master_scale"].__setitem__("cuts", [2.0, 1.0]),
        lambda m: m["master_scale"].__setitem__("grade_pd", [0.1]),
        lambda m: m["master_scale"].__setitem__("source", "inventada"),
        lambda m: m["master_scale"].__setitem__("extra", 1),
        lambda m: m.__setitem__("schema_version", 2),  # el bloque no existe en el esquema 2
    ]
    for cambio in malos:
        with pytest.raises(ScorecardBundleError):
            FittedScorecardBundle(manifest=mutado(cambio), rules=bundle._rules)
