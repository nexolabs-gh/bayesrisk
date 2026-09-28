"""Tests de ``bayesrisk.run`` (API pública mínima, SDD-23 §4.1) + export perezoso por capas (B23.1).

Cubre: (a) contrato de ``run`` (éxito → ``status="done"``; fallo → ``Study`` con ``status="failed"``
+ lineage, sin excepción propagada; publicación de inventario solo en éxito y solo si
``publish_to_inventory``), y (b) el **núcleo liviano por capas** verificado con snapshots de
``sys.modules`` en subprocesos limpios (tiers import → acceso a ``run`` → invoke).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import bayesrisk.api as api_module
from bayesrisk.audit import AuditConfig, JsonlAuditSink
from bayesrisk.binning.config import BinningConfig
from bayesrisk.calibration.config import CalibrationConfig
from bayesrisk.core.audit import AuditSink, FanOutSink, InMemoryAuditSink, NullAuditSink
from bayesrisk.core.config import BayesRiskConfig, ReproConfig
from bayesrisk.core.exceptions import BayesRiskError
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
from bayesrisk.governance import GovernanceConfig, InventoryEntry, ModelInventory
from bayesrisk.governance.inventory import InventoryRecord
from bayesrisk.governance.model_card import ModelCard
from bayesrisk.model.config import (
    IvContributionConfig,
    ModelConfig,
    SignPolicyConfig,
    StepwiseConfig,
)
from bayesrisk.scorecard.config import ScorecardConfig
from bayesrisk.selection.config import (
    CorrelationSelectionConfig,
    SelectionConfig,
    StabilitySelectionConfig,
    VifSelectionConfig,
)

ROOT_SEED = 20_240_628


# ─────────────────────────────── fixtures y helpers ───────────────────────────────


@pytest.fixture(autouse=True)
def _usar_fake_binning_process(fake_binning_process: object) -> None:
    """Evita OR-Tools dentro del proceso pytest para los tests in-process con binning."""
    del fake_binning_process


def _raw_frame() -> pd.DataFrame:
    """Dataset crudo estable (30 filas) compartido con el smoke end-to-end de scoring."""
    index = pd.Index([f"op-{position:03d}" for position in range(30)], name="loan_id")
    score = [
        0,
        0,
        1,
        1,
        2,
        2,
        3,
        3,
        0,
        1,
        2,
        3,
        0,
        1,
        2,
        3,
        0,
        1,
        2,
        3,
        0,
        1,
        2,
        3,
        0,
        1,
        2,
        3,
        1,
        2,
    ]
    segment = [
        "A",
        "B",
        "A",
        "B",
        "A",
        "B",
        "A",
        "B",
        "Z",
        "A",
        "B",
        "Z",
        "A",
        "Z",
        "A",
        "B",
        "B",
        "Z",
        "A",
        "Z",
        "A",
        "B",
        "Z",
        "A",
        "B",
        "Z",
        "A",
        "B",
        "Z",
        "A",
    ]
    bad = [1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1]
    cohort = ["dev"] * 24 + ["oot"] * 6
    return pd.DataFrame(
        {"score": score, "segment": segment, "bad_flag": bad, "cohort": cohort}, index=index
    )


def _write_parquet(path: Path) -> None:
    """Materializa el dataset crudo a parquet preservando el índice ``loan_id``."""
    _raw_frame().to_parquet(path)


def _data_config(*, source: str | None) -> DataConfig:
    """Config de datos F1; ``source=None`` fuerza el fallo "sin fuente de datos"."""
    return DataConfig(
        load=LoadingConfig(source=source),
        schema_=SchemaConfig(
            columns=(
                ColumnSpec(name="score", dtype="int", nullable=False),
                ColumnSpec(name="segment", dtype="str", nullable=False),
                ColumnSpec(name="bad_flag", dtype="int", nullable=False),
                ColumnSpec(name="cohort", dtype="str", nullable=False),
            ),
            index_col="loan_id",
        ),
        target=TargetConfig(bad_rule=Rule(all_of=(Predicate(col="bad_flag", op="==", value=1),))),
        partition=PartitionConfig(
            strategy=CohortSplitConfig(
                cohort_col="cohort", oot_cohorts=("oot",), holdout_fraction=0.20
            ),
            min_bads_per_partition=0,
        ),
    )


def _full_f1_config(source: str, **overrides: Any) -> BayesRiskConfig:
    """Config F1 completa data→binning→selection→model→scorecard→calibration desde parquet."""
    return BayesRiskConfig(
        repro=ReproConfig(seed=ROOT_SEED),
        data=_data_config(source=source),
        binning=BinningConfig(
            feature_columns=("score", "segment"),
            categorical_columns=("segment",),
            solver="mip",
            max_n_prebins=4,
            max_n_bins=4,
            min_bin_size=0.1,
            time_limit=5,
            monotonic_trend=None,
        ),
        selection=SelectionConfig(
            min_iv=0.0,
            correlation=CorrelationSelectionConfig(enabled=False),
            vif=VifSelectionConfig(enabled=False),
            stability=StabilitySelectionConfig(enabled=False),
        ),
        model=ModelConfig(
            stepwise=StepwiseConfig(direction="none"),
            sign_policy=SignPolicyConfig(action="flag", fail_on_forced_inverted=False),
            iv_contribution=IvContributionConfig(action="flag"),
        ),
        scorecard=ScorecardConfig(rounding_method="none"),
        calibration=CalibrationConfig(
            target_pd=0.31, anchor_source="business_input", min_fit_rows=1
        ),
        **overrides,
    )


class _SpyInventory:
    """Doble de ``ModelInventory`` que registra las entradas recibidas (verifica la publicación)."""

    def __init__(self) -> None:
        """Inicializa el registro de entradas capturadas."""
        self.entries: list[InventoryEntry] = []

    def register(self, entry: InventoryEntry) -> str:
        """Captura la entrada y devuelve un identificador de versión ficticio."""
        self.entries.append(entry)
        return f"v{len(self.entries)}"

    def get_active(self, model_name: str) -> InventoryRecord | None:
        """Sin backend real: no hay versión activa."""
        del model_name
        return None

    def list_versions(self, model_name: str) -> list[InventoryRecord]:
        """Sin backend real: no hay versiones."""
        del model_name
        return []


def _patch_assemble(
    monkeypatch: pytest.MonkeyPatch, *, sink: AuditSink, inventory: ModelInventory
) -> None:
    """Reemplaza ``assemble_run`` para inyectar un sink y un inventario espía (sin extra mlflow)."""

    def fake_assemble(
        config: BayesRiskConfig, *, run_dir: Path | None = None, workdir: Path | None = None
    ) -> tuple[AuditSink, ModelInventory]:
        del config, run_dir, workdir
        return sink, inventory

    monkeypatch.setattr(api_module, "assemble_run", fake_assemble)


# ─────────────────────────────── contrato de run ───────────────────────────────


def test_run_exito_devuelve_study_done_con_artefactos(tmp_path: Path) -> None:
    """``run`` de una corrida F1 completa devuelve el ``Study`` con ``status="done"``."""
    parquet = tmp_path / "cartera.parquet"
    _write_parquet(parquet)

    study = api_module.run(_full_f1_config(str(parquet)))

    assert study.run_context.status == "done"
    assert study.artifacts.has("calibration", "result")
    assert study.run_context.lineage is not None


def test_run_fallo_devuelve_study_failed_con_lineage_sin_relanzar() -> None:
    """Un paso que falla deja ``status="failed"`` + lineage y NO propaga la excepción (D-UI-2)."""
    # data.load.source=None y sin frame inyectado → DataStep levanta ConfigError (BayesRiskError).
    config = BayesRiskConfig(data=_data_config(source=None))

    study = api_module.run(config)  # no debe relanzar

    assert study.run_context.status == "failed"
    assert study.run_context.lineage is not None  # evidencia conservada en el fallo


def test_run_publica_inventario_solo_en_exito(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """En éxito con ``publish_to_inventory`` se registra UNA entrada bien formada."""
    parquet = tmp_path / "cartera.parquet"
    _write_parquet(parquet)
    trail = tmp_path / "trail.jsonl"
    audit_cfg = AuditConfig(enabled=True, trail_filename=str(trail))
    governance = GovernanceConfig(
        model_name="scoring-f1",
        purpose="Scorecard de comportamiento F1",
        cartera="consumo",
        motor="scoring",
        fase="F1",
        author="qa@nexolabs.cl",
        publish_to_inventory=True,
    )
    spy = _SpyInventory()
    _patch_assemble(monkeypatch, sink=JsonlAuditSink(trail, config=audit_cfg), inventory=spy)

    config = _full_f1_config(str(parquet), audit=audit_cfg, governance=governance)
    study = api_module.run(config)

    assert study.run_context.status == "done"
    assert len(spy.entries) == 1
    entry = spy.entries[0]
    assert entry.model_name == "scoring-f1"
    assert entry.run_id == study.run_context.run_id
    assert isinstance(entry.model_card, ModelCard)
    # La ancla de idempotencia (model_name, config_hash) viaja completa en la entrada.
    assert entry.config_hash == entry.model_card.config_hash
    assert entry.config_hash == study.lineage_bundle().config_hash
    # Los tags bayesrisk.* documentados en GovernanceConfig viajan en la entrada.
    assert entry.tags == {
        "nikodym.estado_validacion": "desarrollo",
        "nikodym.cartera": "consumo",
        "nikodym.motor": "scoring",
        "nikodym.fase": "F1",
        "nikodym.autor": "qa@nexolabs.cl",
    }


def test_el_inventario_recibe_el_mismo_card_que_queda_en_disco(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Con ``run_dir`` y trail RELATIVO, el inventario y ``model_card.json`` llevan UN solo card.

    🔴 Abierto 5 de D-GOB (revisión independiente del 2026-09-03): ``_escribir_layout_del_run``
    resolvía el trail contra el ``run_dir`` (D-GOB-7) y ``_build_inventory_entry`` reconstruía
    OTRO card con ``trail_filename`` crudo, relativo al ``cwd``. Con el default
    ``audit_trail.jsonl`` el inventario recibía ``decisions=[]`` y la limitación «audit-trail no
    disponible» mientras el archivo en disco llevaba las decisiones reales. El único test de la
    publicación usaba una ruta absoluta y no comparaba decisiones: no podía verlo.

    Aquí se recorre el ``assemble_run`` REAL —sólo se sustituye el extra ``tracking`` y el
    inventario MLflow por un espía— y se comparan los dos cards íntegros, byte a byte.
    """
    parquet = tmp_path / "cartera.parquet"
    _write_parquet(parquet)
    destino = tmp_path / "corrida"
    spy = _SpyInventory()
    monkeypatch.setattr(api_module, "require_extra", lambda extra, *modules: (object(),))
    monkeypatch.setattr(api_module, "MLflowInventory", lambda tracking_cfg: spy)
    governance = GovernanceConfig(
        model_name="scoring-f1",
        purpose="Scorecard de comportamiento F1",
        publish_to_inventory=True,
    )
    # `trail_filename` queda en su default RELATIVO: es el caso que dejaba el inventario sin
    # decisiones. Ninguna advertencia «trail no disponible» puede salir (filterwarnings=error).
    config = _full_f1_config(str(parquet), audit=AuditConfig(enabled=True), governance=governance)

    study = api_module.run(config, run_dir=destino)

    assert study.run_context.status == "done"
    assert len(spy.entries) == 1
    publicado = spy.entries[0].model_card
    en_disco = (destino / "model_card.json").read_text(encoding="utf-8")
    assert publicado.to_json() == en_disco, "disco e inventario tienen que llevar el MISMO card"
    assert publicado.decisions, "el card publicado tiene que traer las decisiones del trail"
    assert "audit-trail no disponible: decisiones no incluidas" not in publicado.limitations
    assert spy.entries[0].run_id == study.run_context.run_id


def test_run_no_publica_en_fallo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con ``publish_to_inventory`` pero corrida fallida NO se registra nada."""
    governance = GovernanceConfig(purpose="F1", publish_to_inventory=True)
    spy = _SpyInventory()
    _patch_assemble(monkeypatch, sink=NullAuditSink(), inventory=spy)

    config = BayesRiskConfig(data=_data_config(source=None), governance=governance)
    study = api_module.run(config)

    assert study.run_context.status == "failed"
    assert spy.entries == []  # un modelo fallido no entra al inventario


def test_run_no_publica_si_publish_to_inventory_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Con ``publish_to_inventory=False`` no se registra aunque la corrida tenga éxito."""
    parquet = tmp_path / "cartera.parquet"
    _write_parquet(parquet)
    governance = GovernanceConfig(purpose="F1", publish_to_inventory=False)
    spy = _SpyInventory()
    _patch_assemble(monkeypatch, sink=NullAuditSink(), inventory=spy)

    config = _full_f1_config(str(parquet), governance=governance)
    study = api_module.run(config)

    assert study.run_context.status == "done"
    assert spy.entries == []


def test_run_publica_sin_audit_construye_card_parcial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Con ``publish`` pero sin audit habilitado: la ModelCard es parcial (sin trail) y publica."""
    parquet = tmp_path / "cartera.parquet"
    _write_parquet(parquet)
    governance = GovernanceConfig(purpose="F1", publish_to_inventory=True)  # cartera/motor/… = None
    spy = _SpyInventory()
    _patch_assemble(monkeypatch, sink=NullAuditSink(), inventory=spy)

    config = _full_f1_config(str(parquet), governance=governance)  # sin audit → trail_path=None
    with pytest.warns(UserWarning, match="trail no disponible"):
        study = api_module.run(config)

    assert study.run_context.status == "done"
    assert len(spy.entries) == 1
    # Sin cartera/motor/fase/autor, solo viaja el tag de estado (default "desarrollo").
    assert spy.entries[0].tags == {"nikodym.estado_validacion": "desarrollo"}


def test_run_cierra_los_sinks_de_un_fanout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``run`` cierra los sumideros hijos de un ``FanOutSink`` (no fuga el descriptor del JSONL)."""
    trail = tmp_path / "trail.jsonl"
    audit_cfg = AuditConfig(enabled=True, trail_filename=str(trail))
    inner = JsonlAuditSink(trail, config=audit_cfg)
    fan = FanOutSink([inner, InMemoryAuditSink()])
    _patch_assemble(monkeypatch, sink=fan, inventory=_SpyInventory())

    # Corrida que falla (sin fuente de datos): igual debe cerrar el sink compuesto.
    study = api_module.run(BayesRiskConfig(data=_data_config(source=None)))

    assert study.run_context.status == "failed"
    assert inner._handle is None  # el JsonlAuditSink hijo quedó cerrado (recursión de cierre)


def test_run_cierra_sink_ante_excepcion_inesperada(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """El ``finally`` de la API cierra el sink incluso si el primitivo levanta fuera del dominio."""
    trail = tmp_path / "trail.jsonl"
    sink = JsonlAuditSink(trail)
    _patch_assemble(monkeypatch, sink=sink, inventory=_SpyInventory())

    def _boom(self: object) -> None:
        del self
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(Study, "run", _boom)

    with pytest.raises(RuntimeError, match="fallo inesperado"):
        api_module.run(BayesRiskConfig())

    assert sink._handle is None


def test_run_cierra_sink_si_falla_durante_la_inyeccion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La nueva fase previa a ``Study.run`` también queda dentro del ``finally``."""

    class _ExplodingSink:
        closed = False

        def emit(self, event: object) -> None:
            del event
            raise RuntimeError("fallo al auditar la inyección")

        def close(self) -> None:
            self.closed = True

    sink = _ExplodingSink()
    _patch_assemble(monkeypatch, sink=sink, inventory=_SpyInventory())

    with pytest.raises(RuntimeError, match="fallo al auditar"):
        api_module.run(BayesRiskConfig(), artifacts={("data", "frame"): object()})

    assert sink.closed is True


def test_trail_jsonl_registra_inyeccion_y_aviso_de_clave_inerte(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """La procedencia y el aviso de inercia llegan a un ``JsonlAuditSink`` real."""
    trail = tmp_path / "trail.jsonl"
    sink = JsonlAuditSink(trail)
    _patch_assemble(monkeypatch, sink=sink, inventory=_SpyInventory())

    study = api_module.run(BayesRiskConfig(), artifacts={("data", "frame"): [1, 2, 3]})

    assert study.run_context.status == "done"
    events = [json.loads(line) for line in trail.read_text().splitlines()]
    artifact = next(event for event in events if event["kind"] == "artifact")
    assert artifact["payload"] == {"domain": "data", "key": "frame", "overwrite": False}
    warning = next(
        event
        for event in events
        if event["kind"] == "decision"
        and event["payload"].get("regla") == "artefacto_inyectado_inerte"
    )
    assert warning["payload"]["accion"] == "advertir"


def test_data_hash_inyectado_se_adopta_sin_caveat_de_ausencia() -> None:
    """Sin ``data`` activo, el lineage adopta ``('data', 'data_hash')`` desde el store."""
    digest = "a" * 64

    study = api_module.run(BayesRiskConfig(), artifacts={("data", "data_hash"): digest})
    lineage = study.lineage_bundle()

    assert lineage.data_hash == digest
    assert lineage.injected_artifacts == ("data.data_hash",)
    assert not any("data_hash ausente" in caveat for caveat in lineage.determinism_caveats)


# --- Study reutilizado: el lineage sólo toma lo de su corrida (decisión de Cami del 2026-09-28) ---


def _study_con_datos_publicados(tmp_path: Path, origen: str) -> tuple[Study, str]:
    """Primera corrida: su ``data_hash`` queda en el store, publicado por el paso de datos o
    inyectado por la puerta pública de artefactos (D-ART-8)."""
    if origen == "inyectado":
        study = api_module.run(BayesRiskConfig(), artifacts={("data", "data_hash"): "a" * 64})
    else:
        parquet = tmp_path / "raw.parquet"
        _write_parquet(parquet)
        study = Study(BayesRiskConfig(data=_data_config(source=str(parquet))))
        study.run()
    digest = study.lineage_bundle().data_hash
    assert digest is not None and study.artifacts.get("data", "data_hash") == digest
    return study, digest


@pytest.mark.parametrize("origen", ["paso-de-datos", "inyectado"])
@pytest.mark.parametrize(
    "steps",
    [
        pytest.param(["no_existe"], id="la-segunda-falla-al-resolver"),
        pytest.param([], id="la-segunda-no-corre-datos"),
    ],
)
def test_un_study_reutilizado_no_hereda_el_data_hash_de_la_corrida_anterior(
    tmp_path: Path, steps: list[str], origen: str
) -> None:
    """Revisión de Codex del parche 2.0.1 (y pasada 1 de S24, para el inyectado): la segunda
    corrida se atribuía los datos de la primera, en memoria y en el ``lineage.json`` de ``save()``.
    Ahora queda vacío y declarado, y el store no se toca."""
    study, digest = _study_con_datos_publicados(tmp_path, origen)

    if steps:
        with pytest.raises(BayesRiskError):
            study.run(steps=steps)
        assert study.run_context.status == "failed"
    else:
        study.run(steps=steps)
        assert study.run_context.status == "done"

    lineage = study.lineage_bundle()
    assert lineage.data_hash is None
    assert any("data_hash ausente" in caveat for caveat in lineage.determinism_caveats)
    assert study.artifacts.get("data", "data_hash") == digest, "el Study conserva sus artefactos"
    if origen == "inyectado":
        assert lineage.injected_artifacts == ("data.data_hash",), (
            "la procedencia se sigue declarando"
        )

    guardado = json.loads(
        (study.save(tmp_path / "estudio") / "lineage.json").read_text(encoding="utf-8")
    )
    assert guardado["data_hash"] is None


def test_input_frame_opcional_se_consume_y_no_se_declara_inerte() -> None:
    """El precedente en memoria de DataStep no puede producir un aviso falso de typo."""
    config = BayesRiskConfig(data=_data_config(source=None))
    artifacts = {("data", "input_frame"): _raw_frame()}

    check = api_module.check_pipeline(config, artifacts=artifacts)
    study = api_module.run(config, artifacts=artifacts)

    assert check.executable is True
    assert check.inert_artifacts == ()
    assert study.run_context.status == "done"
    assert study.artifacts.has("data", "data_hash")


def test_artefactos_no_entran_al_config_hash() -> None:
    """La puerta cambia el lineage, nunca la identidad del config (D-ART-7)."""
    config = BayesRiskConfig()

    baseline = api_module.run(config).lineage_bundle().config_hash
    injected = api_module.run(config, artifacts={("data", "frame"): object()}).lineage_bundle()

    assert injected.config_hash == baseline
    assert injected.injected_artifacts == ("data.frame",)


def test_f1_partido_conserva_coeficientes_lineage_y_save_load(tmp_path: Path) -> None:
    """Data→artefactos→binning conserva betas y la procedencia sobrevive al round-trip."""
    parquet = tmp_path / "cartera.parquet"
    _write_parquet(parquet)
    complete = api_module.run(_full_f1_config(str(parquet)))
    assert complete.run_context.status == "done"

    keys = ("frame", "labels", "splits", "special")
    injected = {("data", key): complete.artifacts.get("data", key) for key in keys}
    partial_config = complete.config.model_copy(
        update={
            "data": None,
            "binning": complete.config.binning.model_dump(mode="python"),
        }
    )
    assert isinstance(partial_config.binning, dict), "precondición: config opaco"

    check = api_module.check_pipeline(partial_config, artifacts=injected)
    partial = api_module.run(partial_config, artifacts=injected)

    assert check.executable is True
    assert check.steps[0] == "binning"
    assert partial.run_context.status == "done"
    pd.testing.assert_frame_equal(
        partial.artifacts.get("model", "coefficients"),
        complete.artifacts.get("model", "coefficients"),
    )

    lineage = partial.lineage_bundle()
    assert lineage.injected_artifacts == (
        "data.frame",
        "data.labels",
        "data.special",
        "data.splits",
    )
    assert lineage.data_hash is None
    assert any("4 clave(s)" in caveat for caveat in lineage.determinism_caveats)
    assert any("data_hash ausente" in caveat for caveat in lineage.determinism_caveats)

    restored = Study.load(partial.save(tmp_path / "partial-study"), trust=True)
    assert restored.lineage_bundle().injected_artifacts == lineage.injected_artifacts
    assert restored.lineage_bundle().determinism_caveats == lineage.determinism_caveats


def test_paridad_run_check_pipeline_en_fallo_por_faltante_y_colision(tmp_path: Path) -> None:
    """El preflight predice los dos fallos estructurales de la superficie de ejecución."""
    parquet = tmp_path / "cartera.parquet"
    _write_parquet(parquet)
    complete = api_module.run(_full_f1_config(str(parquet)))
    keys = ("frame", "labels", "splits", "special")
    injected = {("data", key): complete.artifacts.get("data", key) for key in keys}
    partial_config = complete.config.model_copy(update={"data": None})

    missing = dict(injected)
    missing.pop(("data", "special"))
    missing_check = api_module.check_pipeline(partial_config, artifacts=missing)
    missing_run = api_module.run(partial_config, artifacts=missing)

    collision_artifacts = {("data", "frame"): complete.artifacts.get("data", "frame")}
    collision_check = api_module.check_pipeline(complete.config, artifacts=collision_artifacts)
    collision_run = api_module.run(complete.config, artifacts=collision_artifacts)

    assert missing_check.executable is False
    assert missing_run.run_context.status == "failed"
    assert collision_check.executable is False
    assert collision_run.run_context.status == "failed"
    assert collision_run.run_context.error is not None
    assert "colisiona" in collision_run.run_context.error.message


def test_caveat_data_hash_mira_steps_resueltos_no_solo_seccion_activa() -> None:
    """Un ``run.steps=[]`` no ejecuta data aunque su sección siga presente."""
    config = BayesRiskConfig(data=_data_config(source=None)).model_copy(
        update={"run": BayesRiskConfig().run.model_copy(update={"steps": []})}
    )

    study = api_module.run(config, artifacts={("data", "frame"): [1, 2, 3]})

    assert study.run_context.status == "done"
    assert any("data_hash ausente" in item for item in study.lineage_bundle().determinism_caveats)


def test_bayesrisk_run_accesible_perezoso_desde_paquete_raiz() -> None:
    """``bayesrisk.run`` (export perezoso) es la misma función pública que ``bayesrisk.api.run``."""
    import bayesrisk

    assert bayesrisk.run is api_module.run
    assert bayesrisk.assemble_run is api_module.assemble_run
    assert {"run", "assemble_run"} <= set(dir(bayesrisk))  # __dir__ expone los símbolos perezosos
    with pytest.raises(AttributeError):
        _ = bayesrisk.simbolo_inexistente  # __getattr__ rechaza nombres no perezosos


# ─────────────────── núcleo liviano por capas (snapshots de sys.modules) ───────────────────


def test_import_bayesrisk_liviano_y_export_perezoso_por_capas() -> None:
    """Subproceso limpio: ``import bayesrisk`` no arrastra api/stack; acceder ``run`` sí, sin ML."""
    code = textwrap.dedent(
        """
        import sys
        import bayesrisk

        # Tier 1: import bayesrisk no arrastra la capa api ni su stack (audit/governance/tracking).
        assert bayesrisk.__version__
        for m in ("bayesrisk.api", "bayesrisk.audit", "bayesrisk.governance", "bayesrisk.tracking",
                  "fastapi"):
            assert m not in sys.modules, "tier1 fuga: " + m

        # Tier 2: acceder bayesrisk.run importa api + audit/governance/tracking, pero NO fastapi,
        # NO pandas y NO el stack ML de dominio.
        run = bayesrisk.run
        assert callable(run)
        assert callable(bayesrisk.assemble_run)
        for m in ("bayesrisk.api", "bayesrisk.audit", "bayesrisk.governance", "bayesrisk.tracking"):
            assert m in sys.modules, "tier2 falta: " + m
        for m in ("fastapi", "optbinning", "sklearn", "pandas", "bayesrisk.data",
        "bayesrisk.binning"):
            assert m not in sys.modules, "tier2 fuga: " + m

        print("ok")
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert completed.stdout.strip() == "ok"


def test_invoke_run_carga_el_stack_de_computo_de_dominio(tmp_path: Path) -> None:
    """Subproceso limpio: ``import bayesrisk`` NO carga el dominio; invocar ``run`` sí lo carga.

    Marcadores ortools-safe: el paso de datos importa ``bayesrisk.data``/``pandas``. NO se usa
    ``optbinning`` como marcador porque importar OR-Tools segfaultea en algunas plataformas y la
    suite entera fakea el binning; que el stack ML tampoco viaje con el *acceso* a ``run`` se
    verifica por AUSENCIA en :func:`test_import_bayesrisk_liviano_y_export_perezoso_por_capas`.
    """
    parquet = tmp_path / "cartera.parquet"
    _write_parquet(parquet)
    script = tmp_path / "tier3.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys
            import bayesrisk

            run = bayesrisk.run
            # Tras acceder a run, el stack de cómputo/dominio NO está cargado (frontera perezosa).
            for m in ("bayesrisk.data", "pandas", "optbinning", "sklearn"):
                assert m not in sys.modules, "fuga tras acceso: " + m

            from bayesrisk.core.config import BayesRiskConfig, ReproConfig
            from bayesrisk.data.config import (
                CohortSplitConfig, ColumnSpec, DataConfig, LoadingConfig,
                PartitionConfig, Predicate, Rule, SchemaConfig, TargetConfig,
            )

            cfg = BayesRiskConfig(
                repro=ReproConfig(seed=20240628),
                data=DataConfig(
                    load=LoadingConfig(source=sys.argv[1]),
                    schema_=SchemaConfig(
                        columns=(
                            ColumnSpec(name="score", dtype="int", nullable=False),
                            ColumnSpec(name="segment", dtype="str", nullable=False),
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
                ),
            )

            study = bayesrisk.run(cfg)  # invocar corre el pipeline y carga el stack de cómputo
            assert study.run_context.status == "done", study.run_context.status
            for m in ("bayesrisk.data", "pandas"):
                assert m in sys.modules, "no cargó el stack de cómputo al invocar: " + m
            print("ok")
            """
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(script), str(parquet)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert completed.stdout.strip() == "ok"


class _SinkQueFallaEnRunStart:
    """Un trail que no puede escribir, como un disco lleno: falla desde el primer evento."""

    def emit(self, event: object) -> None:
        raise OSError("disco lleno (doble de prueba)")


def test_un_study_reutilizado_cuyo_trail_falla_al_arrancar_no_conserva_la_corrida_anterior(
    tmp_path: Path,
) -> None:
    """Pasada 2 de Codex en S24: si `run_start` falla, el Study quedaba en «running» con el
    lineage —y el `data_hash`— de la corrida anterior, y `save()` lo persistía."""
    study, _digest = _study_con_datos_publicados(tmp_path, "paso-de-datos")
    study.set_audit_sink(_SinkQueFallaEnRunStart())

    with pytest.raises(OSError, match="disco lleno"):
        study.run(steps=[])

    assert study.run_context.status == "failed"
    assert study.run_context.error is not None
    assert study.run_context.error.type == "OSError"
    assert study.run_context.finished_at is not None
    assert study.run_context.lineage is None
    assert not (study.save(tmp_path / "estudio") / "lineage.json").exists()


def test_un_reintento_exitoso_no_conserva_el_error_de_la_corrida_anterior() -> None:
    study = Study(BayesRiskConfig())
    with pytest.raises(BayesRiskError):
        study.run(steps=["no_existe"])
    assert study.run_context.error is not None

    study.run(steps=[])

    assert study.run_context.status == "done"
    assert study.run_context.error is None


def test_un_fallo_parcial_de_run_start_cierra_el_trail_que_si_lo_escribio() -> None:
    """Pasada 3 de Codex en S24: con un sink compuesto, el primer hijo escribe `run_start` y el
    segundo falla; ese trail tiene que quedar con su `run_end` y el diagnóstico."""
    escrito = InMemoryAuditSink()
    study = Study(BayesRiskConfig())
    study.set_audit_sink(FanOutSink([escrito, _SinkQueFallaEnRunStart()]))

    with pytest.raises(OSError, match="disco lleno"):
        study.run(steps=[])

    assert study.run_context.status == "failed"
    assert [evento.kind for evento in escrito.events] == ["run_start", "run_end"]
    assert escrito.events[-1].payload["error_type"] == "OSError"


def test_volver_a_correr_datos_sobre_un_study_reutilizado_no_deja_un_hash_sin_sus_artefactos(
    tmp_path: Path,
) -> None:
    """Pasada 3 de Codex en S24: el paso de datos escribía el hash nuevo en el lineage antes de
    publicar, y la publicación falla en un Study que ya tiene esos artefactos; `save()` guardaba el
    hash nuevo junto a los artefactos viejos."""
    parquet = tmp_path / "raw.parquet"
    _write_parquet(parquet)
    study = Study(BayesRiskConfig(data=_data_config(source=str(parquet))))
    study.run()
    anterior = study.artifacts.get("data", "data_hash")
    _raw_frame().assign(score=lambda frame: frame["score"] + 1).to_parquet(parquet)

    with pytest.raises(BayesRiskError):
        study.run()

    assert study.lineage_bundle().data_hash is None
    assert study.artifacts.get("data", "data_hash") == anterior
    guardado = json.loads(
        (study.save(tmp_path / "estudio") / "lineage.json").read_text(encoding="utf-8")
    )
    assert guardado["data_hash"] is None


class _SinkQueFallaAlAuditarLaFichaDeDatos:
    """Escribe todo menos el evento del último artefacto de datos (`data_card`)."""

    def emit(self, event: Any) -> None:
        if event.kind == "artifact" and event.payload.get("key") == "data_card":
            raise OSError("disco lleno (doble de prueba)")


def test_un_fallo_al_auditar_la_ficha_de_datos_no_borra_el_hash_que_quedo(tmp_path: Path) -> None:
    """Pasada 4 de Codex en S24: el store guarda antes de emitir, así que los seis artefactos de
    datos —`data_hash` incluido— quedan aunque el sink falle en el último; el lineage y `save()`
    tienen que traer su identidad."""
    parquet = tmp_path / "raw.parquet"
    _write_parquet(parquet)
    study = Study(BayesRiskConfig(data=_data_config(source=str(parquet))))
    study.set_audit_sink(_SinkQueFallaAlAuditarLaFichaDeDatos())

    with pytest.raises(OSError, match="disco lleno"):
        study.run()

    guardado_en_store = study.artifacts.get("data", "data_hash")
    assert study.lineage_bundle().data_hash == guardado_en_store
    guardado = json.loads(
        (study.save(tmp_path / "estudio") / "lineage.json").read_text(encoding="utf-8")
    )
    assert guardado["data_hash"] == guardado_en_store
