"""bayesrisk corre en un entorno con distribuciones duplicadas, como Colab (2.0.1).

La imagen de Colab trae trece distribuciones instaladas dos veces con versiones distintas —el
``dist-packages`` de apt y el de pip— desde antes de cualquier ``pip install``; cualquier
Debian/Ubuntu con paquetes ``python3-*`` cae igual. En 2.0.0 ``runtime_environment_hash`` abortaba
con ``ReproducibilityError`` y, como el lineage se armaba en un ``finally`` sin registro de
fallo, la corrida quedaba en «running» para siempre.

Dos invariantes: (1) la huella cuenta la versión que Python importa —la primera en ``sys.path``— y
registra las sombreadas, y sin duplicados es la de 2.0.0; (2) un fallo al armar el lineage deja la
corrida en «failed» con su diagnóstico, sin tapar un fallo anterior de la resolución.
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

import pytest

import bayesrisk.api as api_module
import bayesrisk.core.build as build_module
from bayesrisk.core.config import BayesRiskConfig
from bayesrisk.core.exceptions import BayesRiskError, ConfigError, ReproducibilityError
from bayesrisk.core.study import Study
from bayesrisk.data.config import (
    CohortSplitConfig,
    ColumnSpec,
    DataConfig,
    LoadingConfig,
    PartitionConfig,
    Predicate,
    Rule,
    SchemaConfig,
    TargetConfig,
)

#: Una distribución base, instalada en todo entorno donde corre la suite.
_INSTALADA = "pydantic"


def _dist_info_falsa(carpeta: Path, nombre: str, version: str) -> Path:
    info = carpeta / f"{nombre}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {nombre}\nVersion: {version}\n", encoding="utf-8"
    )
    return carpeta


def test_una_distribucion_duplicada_no_aborta_y_cuenta_la_que_python_importa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    limpio = build_module.runtime_environment_hash()
    efectiva = metadata.version(_INSTALADA)
    # Como el dist-packages de apt en Colab: DESPUÉS del de pip en `sys.path`.
    carpeta = _dist_info_falsa(tmp_path / "apt", _INSTALADA, "0.0.1")
    monkeypatch.setattr(sys, "path", [*sys.path, str(carpeta)])

    sombreado = build_module.runtime_environment_hash()  # 2.0.0 levantaba ReproducibilityError

    assert metadata.version(_INSTALADA) == efectiva, "la que importa Python sigue siendo la misma"
    assert sombreado != limpio, "un entorno sombreado no se confunde con uno limpio"
    assert build_module.runtime_environment_hash() == sombreado, "la huella es determinista"


def test_un_duplicado_de_la_misma_version_no_mueve_la_huella(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin versiones distintas no hay sombra: el payload —y el hash— es el de 2.0.0."""
    limpio = build_module.runtime_environment_hash()
    carpeta = _dist_info_falsa(tmp_path / "copia", _INSTALADA, metadata.version(_INSTALADA))
    monkeypatch.setattr(sys, "path", [*sys.path, str(carpeta)])

    assert build_module.runtime_environment_hash() == limpio


def _config_que_falla_en_datos() -> BayesRiskConfig:
    """Resuelve bien y falla al ejecutar: sin fuente de datos."""
    return BayesRiskConfig(
        data=DataConfig(
            load=LoadingConfig(source=None),
            schema_=SchemaConfig(
                columns=(
                    ColumnSpec(name="score", dtype="int", nullable=False),
                    ColumnSpec(name="bad_flag", dtype="int", nullable=False),
                    ColumnSpec(name="cohort", dtype="str", nullable=False),
                ),
                index_col="loan_id",
            ),
            target=TargetConfig(
                bad_rule=Rule(all_of=(Predicate(col="bad_flag", op="==", value=1),))
            ),
            partition=PartitionConfig(
                strategy=CohortSplitConfig(
                    cohort_col="cohort", oot_cohorts=("oot",), holdout_fraction=0.20
                ),
                min_bads_per_partition=0,
            ),
        )
    )


def _lineage_que_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    def falla() -> str:
        raise ReproducibilityError("huella del entorno no calculable (doble de prueba)")

    monkeypatch.setattr(build_module, "runtime_environment_hash", falla)


def test_un_fallo_al_armar_el_lineage_deja_la_corrida_en_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """En 2.0.0 quedaba en «running», sin `error` ni `run_end`."""
    _lineage_que_falla(monkeypatch)

    study = api_module.run(_config_que_falla_en_datos())  # no relanza (D-UI-2)

    assert study.run_context.status == "failed"
    assert study.run_context.error is not None
    assert study.run_context.error.type == "ReproducibilityError"
    assert study.run_context.finished_at is not None


def test_un_fallo_del_lineage_no_tapa_el_de_la_resolucion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _lineage_que_falla(monkeypatch)

    def resolucion_que_falla(self: Study, nombres: object) -> object:
        raise ConfigError("el paso X requiere un artefacto que nadie produce (doble de prueba)")

    monkeypatch.setattr(Study, "_resolve_steps", resolucion_que_falla)

    study = api_module.run(_config_que_falla_en_datos())

    assert study.run_context.status == "failed"
    assert study.run_context.error is not None
    assert study.run_context.error.type == "ConfigError", "la causa es la de la resolución"
    assert study.run_context.lineage is None


def test_un_study_reutilizado_no_conserva_el_lineage_de_la_corrida_anterior(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Revisión adversarial del parche: si el lineage de la segunda corrida falla, la evidencia de
    la primera no se hace pasar por la de ésta —ni en memoria ni en lo que guarda `save`—."""
    study = Study(_config_que_falla_en_datos())
    with pytest.raises(BayesRiskError):
        study.run()  # falla en `data`, pero con su lineage
    anterior = study.run_context.lineage
    assert anterior is not None

    _lineage_que_falla(monkeypatch)
    with pytest.raises(ReproducibilityError):
        study.run()

    assert study.run_context.status == "failed"
    assert study.run_context.error is not None
    assert study.run_context.error.type == "ReproducibilityError"
    assert study.run_context.lineage is None
    guardado = study.save(tmp_path / "estudio")
    assert not (guardado / "lineage.json").exists()
