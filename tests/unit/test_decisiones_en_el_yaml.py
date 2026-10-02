"""D-DEC-1…4: las decisiones humanas con motivo viajan en el YAML (enmienda HL-Y-DECISIONES §2).

Lo medido en S26 (``privado/guiones/medir_decisiones_yaml.py``): una exclusión con motivo de la
puerta guiada se perdía al correr su YAML —1 decisión humana en la corrida guiada, 0 en
``bayesrisk.run(loads_config(yaml))`` con el mismo ``config_hash``— y la pantalla decía «Ninguna
decisión humana registrada». Contratos:

1. **D-DEC-1** — sección INFRA ``decisions``: registro en orden ``{action, columns, reason,
   author, value}`` con la huella del efecto; fuera del ``config_hash``; vacía, no se vuelca (el
   YAML sin decisiones queda como el de la 2.2.0); ``load(dump(c)) == c``.
2. **D-DEC-2** — la puerta guiada agrega ahí (sólo agregar, con su historia) y ``Study.run``
   emite un ``decision_del_usuario`` por registro con el payload de hoy: la corrida guiada y la
   del YAML dan las mismas decisiones humanas (trail, ficha, hoja «Decisiones humanas», líneas de
   la página ejecutiva); la procedencia de la puerta sigue siendo sólo suya.
3. **D-DEC-3 (a)** — cotejo por variable del último registro de cada familia: aplicada, en
   suspenso (D-EXC-1) o sin efecto; lo sin efecto se declara (``decision_sin_efecto``, alerta) y
   no se atribuye; un registro aplicado en parte emite lo aplicado con ``valor`` restringido y las
   claves aditivas ``registro`` y ``huella``.
4. **D-DEC-4** — el resumen final de la pantalla trae las decisiones del preámbulo.

Contrato: ``docs/design/_ENMIENDA-HL-Y-DECISIONES-EN-EL-YAML.md`` §2 y §6.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from _ui_f1 import write_stacked_behavior_parquet

import bayesrisk
from bayesrisk.core.config import BayesRiskConfig, config_hash, dump_config, loads_config
from bayesrisk.core.config.hashing import INFRA_SECTIONS
from bayesrisk.guided import Scorecard

MOTIVO = "comité de riesgo 2026-09: variable sin sustento de negocio"


def _decisiones() -> Any:
    """El módulo nuevo, resuelto al llamar: así cada test nace rojo por su cuenta."""
    return importlib.import_module("bayesrisk.core.decisions")


@pytest.fixture(autouse=True)
def _usar_fake_binning_process(fake_binning_process: object) -> None:
    del fake_binning_process


@pytest.fixture(scope="module")
def fuente(tmp_path_factory: pytest.TempPathFactory) -> Path:
    ruta = tmp_path_factory.mktemp("decisiones_fuente") / "cartera.parquet"
    write_stacked_behavior_parquet(ruta, repeats=50)
    return ruta


def _puerta(fuente: Path, raiz: Path, *, name: str = "dec") -> Scorecard:
    sc = Scorecard(
        fuente,
        target="bad_flag",
        id="loan_id",
        cohort="cohort",
        oot_cohorts=["oot"],
        name=name,
        run_dir=raiz / "corridas",
        min_iv=0.0,
    )
    sc._echo = lambda _texto: None
    return sc


def _con(config: BayesRiskConfig, **hojas: Any) -> BayesRiskConfig:
    """El config con hojas reescritas a mano por el YAML: lo que haría una persona."""
    datos = yaml.safe_load(dump_config(config))
    for ruta, valor in hojas.items():
        seccion, campo = ruta.split("__")
        datos[seccion][campo] = valor
    return loads_config(yaml.safe_dump(datos, sort_keys=False, allow_unicode=True))


def _con_registros(config: BayesRiskConfig, registros: list[dict[str, Any]]) -> BayesRiskConfig:
    datos = yaml.safe_load(dump_config(config))
    datos["decisions"] = registros
    return loads_config(yaml.safe_dump(datos, sort_keys=False, allow_unicode=True))


def _humanas(eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in eventos if e["regla"] == "decision_del_usuario"]


# ───────────────────────── D-DEC-1: la sección y su volcado ─────────────────────────


def test_decisions_es_infra_y_no_mueve_el_config_hash(fuente: Path, tmp_path: Path) -> None:
    assert "decisions" in INFRA_SECTIONS
    sc = _puerta(fuente, tmp_path)
    antes = config_hash(sc.config)
    sc.exclude("segment", reason=MOTIVO)
    con = sc.config
    assert len(con.decisions) == 1
    sin = con.model_copy(update={"decisions": ()})
    assert config_hash(con) == config_hash(sin)
    assert config_hash(con) != antes  # la exclusión sí cambia el modelo: está en `binning`


def test_to_yaml_trae_la_decision_con_su_motivo_y_hace_round_trip(
    fuente: Path, tmp_path: Path
) -> None:
    sc = _puerta(fuente, tmp_path)
    sc.exclude("segment", reason=MOTIVO)
    texto = sc.to_yaml()
    assert MOTIVO in texto
    cargado = loads_config(texto)
    (registro,) = cargado.decisions
    assert registro.action == "exclude"
    assert registro.columns == ("segment",)
    assert registro.reason == MOTIVO
    assert registro.author == "usuario"
    assert registro.value == {"binning.exclude_columns": ["segment"]}
    assert loads_config(dump_config(cargado)) == cargado
    assert config_hash(cargado) == config_hash(sc.config)


def test_sin_decisiones_el_yaml_no_trae_la_clave(fuente: Path, tmp_path: Path) -> None:
    """Ni ``decisions: []`` ni ``null``: el YAML queda como el de la 2.2.0 y lo carga una
    librería anterior (``extra="forbid"`` rechazaría la clave)."""
    sc = _puerta(fuente, tmp_path)
    assert "decisions" not in yaml.safe_load(sc.to_yaml())
    assert "decisions" not in yaml.safe_load(dump_config(BayesRiskConfig()))
    # La pantalla manda el config con sus defaults explícitos: `decisions: []` tampoco se vuelca.
    explicito = BayesRiskConfig.model_validate({"name": "x", "decisions": []})
    assert "decisions" not in yaml.safe_load(dump_config(explicito, exclude_unset=True))
    assert "decisions" not in yaml.safe_load(dump_config(explicito))


@pytest.mark.parametrize(
    ("registro", "fragmento"),
    [
        ({"action": "exclude", "columns": ["x"], "reason": "  ", "value": {}}, "reason"),
        ({"action": "exclude", "columns": [], "reason": "m", "value": {}}, "columns"),
        ({"action": "borrar", "columns": ["x"], "reason": "m", "value": {}}, "action"),
        (
            {"action": "set_bins", "columns": ["x", "y"], "reason": "m", "value": {}},
            "una sola variable",
        ),
    ],
)
def test_un_registro_invalido_se_rechaza_al_cargar(
    registro: dict[str, Any], fragmento: str
) -> None:
    from bayesrisk.core.exceptions import ConfigError

    texto = yaml.safe_dump({"decisions": [registro]}, allow_unicode=True)
    with pytest.raises(ConfigError, match=fragmento):
        loads_config(texto)


# ───────────────────────── D-DEC-2: una sola fuente, con su historia ─────────────────────────


def test_la_puerta_agrega_al_config_y_no_al_preambulo(fuente: Path, tmp_path: Path) -> None:
    sc = _puerta(fuente, tmp_path)
    sc.exclude("segment", reason="primero")
    sc.keep("segment", reason="después")
    assert [(r.action, r.reason) for r in sc.config.decisions] == [
        ("exclude", "primero"),
        ("keep", "después"),
    ]
    reglas = [payload["regla"] for _paso, payload in sc._preamble()]
    assert "decision_del_usuario" not in reglas
    assert reglas[0] == "puerta_de_entrada"


def test_exclude_y_luego_keep_dejan_dos_registros_y_dos_eventos(
    fuente: Path, tmp_path: Path
) -> None:
    sc = _puerta(fuente, tmp_path)
    sc.exclude("segment", reason="primero")
    sc.keep("segment", reason="después")
    eventos = _decisiones().eventos_de_decisiones(sc.config)
    assert [(e["regla"], e["accion"], e["motivo"]) for e in eventos] == [
        ("decision_del_usuario", "exclude", "primero"),
        ("decision_del_usuario", "keep", "después"),
    ]
    # El payload de hoy, sin claves nuevas en un registro aplicado entero.
    assert eventos[0] == {
        "regla": "decision_del_usuario",
        "umbral": None,
        "valor": {"binning.exclude_columns": ["segment"]},
        "accion": "exclude",
        "autor": "usuario",
        "motivo": "primero",
        "variables": ["segment"],
    }


# ───────────────────────── D-DEC-3 (a): lo sin efecto se declara ─────────────────────────


def test_un_exclude_aplicado_en_parte_atribuye_solo_lo_aplicado(
    fuente: Path, tmp_path: Path
) -> None:
    sc = _puerta(fuente, tmp_path)
    sc.exclude(["score", "segment"], reason=MOTIVO)
    # Alguien retira a mano `score` de las excluidas (un YAML editado, o el formulario).
    editado = _con(sc.config, binning__exclude_columns=["segment"])
    humana, sin_efecto = _decisiones().eventos_de_decisiones(editado)
    assert humana["regla"] == "decision_del_usuario"
    assert humana["variables"] == ["segment"]
    assert humana["valor"] == {"binning.exclude_columns": ["segment"]}
    assert humana["huella"] == {"binning.exclude_columns": ["score", "segment"]}
    assert humana["registro"] == 0
    assert humana["autor"] == "usuario"
    assert sin_efecto["regla"] == "decision_sin_efecto"
    assert sin_efecto["variables"] == ["score"]
    assert sin_efecto["valor"] == {"binning.exclude_columns": ["score"]}
    assert sin_efecto["registro"] == 0
    assert sin_efecto["umbral"] == "binning.exclude_columns"
    assert sin_efecto["motivo"] == MOTIVO
    # No lo firma una persona: va con las decisiones del motor.
    assert "autor" not in sin_efecto


def test_la_huella_acumulada_no_atribuye_otra_variable_sin_efecto(
    fuente: Path, tmp_path: Path
) -> None:
    """Pasada 1 de Codex sobre el código: ``exclude(score)`` y luego ``exclude(segment)`` guardan
    la hoja acumulada ``[score, segment]``; si alguien retira ``score`` a mano, el segundo registro
    sigue aplicado, pero su ``valor`` —lo que conservan la ficha y el Excel— no puede nombrar la
    exclusión de ``score``."""
    sc = _puerta(fuente, tmp_path)
    sc.exclude("score", reason="primero")
    sc.exclude("segment", reason="después")
    assert sc.config.decisions[1].value == {"binning.exclude_columns": ["score", "segment"]}
    # Con todo aplicado, el payload es exactamente el de siempre.
    assert "huella" not in _decisiones().eventos_de_decisiones(sc.config)[1]
    editado = _con(sc.config, binning__exclude_columns=["segment"])
    sin_efecto, humana = _decisiones().eventos_de_decisiones(editado)
    assert sin_efecto["regla"] == "decision_sin_efecto"
    assert sin_efecto["variables"] == ["score"]
    assert humana["regla"] == "decision_del_usuario"
    assert humana["variables"] == ["segment"]
    assert humana["valor"] == {"binning.exclude_columns": ["segment"]}
    assert humana["huella"] == {"binning.exclude_columns": ["score", "segment"]}
    assert humana["registro"] == 1


def test_la_historia_con_una_decision_posterior_se_emite_como_hoy(
    fuente: Path, tmp_path: Path
) -> None:
    """``exclude(score)``, ``exclude(segment)`` y ``keep(score)``: la huella de la segunda nombra
    ``score``, que salió de las excluidas por OTRA decisión humana, no a mano. Es historia y se
    emite tal cual, sin ``registro`` ni ``huella``."""
    sc = _puerta(fuente, tmp_path)
    sc.exclude("score", reason="primero")
    sc.exclude("segment", reason="después")
    sc.keep("score", reason="al final")
    eventos = _decisiones().eventos_de_decisiones(sc.config)
    assert [e["regla"] for e in eventos] == ["decision_del_usuario"] * 3
    assert eventos[1]["valor"] == {"binning.exclude_columns": ["score", "segment"]}
    assert all("huella" not in e and "registro" not in e for e in eventos)


def test_un_keep_desforzado_a_mano_no_se_atribuye(fuente: Path, tmp_path: Path) -> None:
    sc = _puerta(fuente, tmp_path)
    sc.keep("segment", reason=MOTIVO)
    editado = _con(sc.config, model__force_include=[])
    (evento,) = _decisiones().eventos_de_decisiones(editado)
    assert evento["regla"] == "decision_sin_efecto"
    assert evento["umbral"] == "model.force_include"
    assert evento["variables"] == ["segment"]


def _cortes_fijados(config: BayesRiskConfig, cortes: list[float]) -> BayesRiskConfig:
    return _con(
        config,
        binning__variable_overrides=[
            {"name": "score", "user_splits": cortes, "user_splits_fixed": [True] * len(cortes)}
        ],
    )


def _registro_de_cortes(config: BayesRiskConfig, cortes: list[float]) -> dict[str, Any]:
    hoja = next(
        o.model_dump(mode="json") for o in config.binning.variable_overrides if o.name == "score"
    )
    return {
        "action": "set_bins",
        "columns": ["score"],
        "reason": "los cortes del manual",
        "value": {"binning.variable_overrides": [hoja]},
    }


def test_set_bins_con_los_cortes_reescritos_a_mano_queda_sin_efecto(
    fuente: Path, tmp_path: Path
) -> None:
    base = _cortes_fijados(_puerta(fuente, tmp_path).config, [0.5, 2.5])
    con_registro = _con_registros(base, [_registro_de_cortes(base, [0.5, 2.5])])
    (aplicada,) = _decisiones().eventos_de_decisiones(con_registro)
    assert aplicada["regla"] == "decision_del_usuario"
    reescrito = _con(
        con_registro,
        binning__variable_overrides=[
            {"name": "score", "user_splits": [1.0, 2.0], "user_splits_fixed": [True, True]}
        ],
    )
    (evento,) = _decisiones().eventos_de_decisiones(reescrito)
    assert evento["regla"] == "decision_sin_efecto"
    assert evento["umbral"] == "binning.variable_overrides"
    assert evento["accion"] == "set_bins"


def test_set_bins_y_despues_exclude_deja_los_cortes_en_suspenso_no_sin_efecto(
    fuente: Path, tmp_path: Path
) -> None:
    base = _cortes_fijados(_puerta(fuente, tmp_path).config, [0.5, 2.5])
    excluida = _con(base, binning__exclude_columns=["score"])
    con_registros = _con_registros(
        excluida,
        [
            _registro_de_cortes(base, [0.5, 2.5]),
            {
                "action": "exclude",
                "columns": ["score"],
                "reason": "dato no disponible",
                "value": {"binning.exclude_columns": ["score"]},
            },
        ],
    )
    eventos = _decisiones().eventos_de_decisiones(con_registros)
    assert [(e["regla"], e["accion"]) for e in eventos] == [
        ("decision_del_usuario", "set_bins"),
        ("decision_del_usuario", "exclude"),
    ]


# ───────────────────────── paridad entre puertas, sobre corridas reales ─────────────────────────


@pytest.fixture(scope="module")
def dos_puertas(fuente: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """La misma exclusión con motivo, corrida por la puerta guiada y desde su YAML."""
    from conftest import FakeBinningProcess

    import bayesrisk.binning.transformer as transformer_module

    raiz = tmp_path_factory.mktemp("dos_puertas")
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        parche.setattr(transformer_module, "_import_binning_process", lambda: FakeBinningProcess)
        sc = _puerta(fuente, raiz, name="guiada")
        sc.exclude("segment", reason=MOTIVO)
        sc.run()
        assert sc.study.run_context.status == "done", sc.study.run_context.error
        texto = sc.to_yaml()
        desde_yaml = bayesrisk.run(loads_config(texto), run_dir=raiz / "desde_yaml")
        assert desde_yaml.run_context.status == "done", desde_yaml.run_context.error
    return {
        "guiada": sc,
        "trail_guiada": Path(sc.project_dir) / "run" / "audit_trail.jsonl",
        "yaml": desde_yaml,
        "trail_yaml": raiz / "desde_yaml" / "audit_trail.jsonl",
        "run_dir_yaml": raiz / "desde_yaml",
    }


def _eventos_del_trail(trail: Path) -> list[dict[str, Any]]:
    return [json.loads(linea) for linea in trail.read_text(encoding="utf-8").splitlines()]


def _decisiones_humanas_del_trail(trail: Path) -> list[tuple[str, dict[str, Any]]]:
    return [
        (e["step"], e["payload"])
        for e in _eventos_del_trail(trail)
        if e["kind"] == "decision" and e["payload"].get("regla") == "decision_del_usuario"
    ]


def test_las_dos_puertas_dan_las_mismas_decisiones_humanas(dos_puertas: dict[str, Any]) -> None:
    guiada = _decisiones_humanas_del_trail(dos_puertas["trail_guiada"])
    desde_yaml = _decisiones_humanas_del_trail(dos_puertas["trail_yaml"])
    assert len(guiada) == 1
    assert guiada == desde_yaml
    (paso, payload) = guiada[0]
    assert paso == _decisiones().DECISIONS_STEP
    assert payload["motivo"] == MOTIVO and payload["variables"] == ["segment"]
    # Lo mismo en el preámbulo persistido, que leen el informe y la pantalla.
    from bayesrisk.guided.summaries import decision_lines_from_preamble

    linea = f"exclude segment — «{MOTIVO}»"
    assert decision_lines_from_preamble(dos_puertas["guiada"].study.preamble) == (linea,)
    assert decision_lines_from_preamble(dos_puertas["yaml"].preamble) == (linea,)


def test_la_procedencia_de_la_puerta_solo_esta_en_la_corrida_guiada(
    dos_puertas: dict[str, Any],
) -> None:
    def reglas(trail: Path) -> set[str]:
        return {
            e["payload"].get("regla") for e in _eventos_del_trail(trail) if e["kind"] == "decision"
        }

    assert "puerta_de_entrada" in reglas(dos_puertas["trail_guiada"])
    assert "puerta_de_entrada" not in reglas(dos_puertas["trail_yaml"])


def test_la_ficha_y_el_excel_tienen_las_mismas_filas_humanas(dos_puertas: dict[str, Any]) -> None:
    from bayesrisk.governance.model_card import _decision_from_event
    from bayesrisk.guided.export import _hojas_de_decisiones

    def filas_humanas_ficha(trail: Path) -> list[tuple[Any, ...]]:
        from bayesrisk.core.audit import AuditEvent

        filas = []
        for e in _eventos_del_trail(trail):
            if e["kind"] != "decision" or e["payload"].get("autor") != "usuario":
                continue
            r = _decision_from_event(AuditEvent.model_validate(e))
            filas.append((r.step, r.regla, r.valor, r.accion, r.autor, r.motivo))
        return filas

    assert filas_humanas_ficha(dos_puertas["trail_guiada"]) == filas_humanas_ficha(
        dos_puertas["trail_yaml"]
    )

    def hoja_humana(trail: Path) -> Any:
        tabla = _hojas_de_decisiones(trail)["Decisiones humanas"]
        return tabla.drop(columns=["Momento"]).to_dict("records")

    assert hoja_humana(dos_puertas["trail_guiada"]) == hoja_humana(dos_puertas["trail_yaml"])


def test_la_pantalla_dice_las_decisiones_que_trae_el_yaml(dos_puertas: dict[str, Any]) -> None:
    from bayesrisk.ui.summaries import serialize_summaries

    resumen = serialize_summaries(
        dos_puertas["yaml"],
        source_label="cartera",
        run_dir=dos_puertas["run_dir_yaml"],
        trail_path=dos_puertas["trail_yaml"],
    )
    assert resumen["error"] is None
    assert resumen["final"]["decisions"] == [f"exclude segment — «{MOTIVO}»"]


def test_una_decision_sin_efecto_sale_como_alerta_en_el_resumen_final(
    fuente: Path, tmp_path: Path
) -> None:
    from conftest import FakeBinningProcess

    import bayesrisk.binning.transformer as transformer_module
    from bayesrisk.ui.summaries import serialize_summaries

    sc = _puerta(fuente, tmp_path)
    sc.keep("segment", reason=MOTIVO)
    editado = _con(sc.config, model__force_include=[], selection__force_include=[])
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        parche.setattr(transformer_module, "_import_binning_process", lambda: FakeBinningProcess)
        study = bayesrisk.run(editado, run_dir=tmp_path / "sin_efecto")
    assert study.run_context.status == "done", study.run_context.error
    reglas = [payload["regla"] for _paso, payload in study.preamble]
    assert reglas == ["decision_sin_efecto"]
    resumen = serialize_summaries(
        study,
        source_label="cartera",
        run_dir=tmp_path / "sin_efecto",
        trail_path=tmp_path / "sin_efecto" / "audit_trail.jsonl",
    )
    assert resumen["final"]["decisions"] == []
    alertas = [a for a in resumen["final"]["review"] if "ya no está aplicada" in a]
    assert alertas == [
        f"Decisiones con motivo: La decisión «keep segment — {MOTIVO}» ya no está aplicada: "
        "la variable ya no está forzada en el config."
    ]


# ───────────────────────── D-DEC-4: el formulario conserva la sección ─────────────────────────


def test_la_pantalla_conserva_las_decisiones_al_ir_y_volver_del_yaml(
    fuente: Path, tmp_path: Path
) -> None:
    """``from-yaml`` → editar otra sección → ``to-yaml``: el registro sigue ahí, intacto."""
    from bayesrisk.ui import routes

    sc = _puerta(fuente, tmp_path)
    sc.exclude("segment", reason=MOTIVO)
    desde = routes.config_from_yaml(sc.to_yaml())
    assert desde["config_hash"] == config_hash(sc.config)
    config = desde["config"]
    assert [r["reason"] for r in config["decisions"]] == [MOTIVO]
    config["name"] = "editado en la pantalla"
    texto = routes.config_to_yaml(config)["yaml"]
    assert loads_config(texto).decisions == sc.config.decisions
