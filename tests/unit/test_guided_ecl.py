"""La puerta guiada de IFRS 9, ``bayesrisk.Ecl`` (FLUJO-GUIADO-IFRS9, capa A; D-ECL-1…D-ECL-9).

Los gates de la capa (§3.15 y §6-3…9 de la enmienda):

- la entrada mínima, las inferencias declaradas y las paradas **antes de correr** (sin horizonte,
  unidad no reconocida), sin dejar nada escrito;
- las constantes de la puerta tomadas del preset F4 (§3.5) y ``data`` en «no aplica» (D-ECL-2);
- ``config_hash(ecl.config)`` igual al del YAML exportado, con y sin decisiones;
- la ECL de ``Ecl`` sobre el dataset del paquete, con la marca, **igual a la de F4** salvo la
  etiqueta ``partition`` de la curva (§4: 3.423.116);
- paridad ``run()`` frente a ``run(until="survival") + resume()``;
- una decisión de cada tipo —``exclude`` y ``rebut_backstops``— en ``config.decisions``, en el
  trail y en el resumen final, y el cotejo que reconoce su efecto (D-DEC-3);
- el artefacto aditivo ``("survival", "coefficients")`` con su golden.

Los resúmenes de la familia (sin códigos internos ni palabras del scorecard) están en
``test_guided_summaries_cartera.py``; las cinco cifras, en ``test_simplicidad_ifrs9.py``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from _proyeccion_canonica import canonizar

import bayesrisk
from bayesrisk.audit.replay import read_trail
from bayesrisk.core.config import BayesRiskConfig, config_hash, loads_config
from bayesrisk.guided import Ecl, EclInputError
from bayesrisk.ui import datasets
from bayesrisk.ui.presets import ifrs9_preset

_GOLDEN_COEFICIENTES = (
    Path(__file__).resolve().parents[1] / "fixtures" / ("survival_coefficients_f4.json")
)
#: La ECL del preset F4 sobre el dataset del paquete (S28 §1; enmienda §4).
_ECL_F4 = 3_423_116.118598177
_COVARIABLES = ["days_past_due", "utilizacion_linea", "deuda_ingreso", "antiguedad_meses"]
#: Los dominios cuyo resultado es cálculo en una provisión: lo que se compara bit a bit.
_DOMINIOS = ("survival", "provisioning_ifrs9")


def _argumentos(datos: Path | pd.DataFrame, run_dir: Path, **cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "data": datos,
        "id": "loan_id",
        "as_of": "as_of_date",
        "portfolio": "portfolio",
        "exposure": "ead",
        "lgd": "lgd",
        "rate": "eir",
        "days_past_due": "days_past_due",
        "default": "is_default",
        "duration": "duration",
        "event": "event",
        "period": "year",
        "horizon": 5,
        "covariates": list(_COVARIABLES),
        "run_dir": run_dir,
        "formats": [],
    }
    base.update(cambios)
    return base


def _ecl(datos: Path | pd.DataFrame, run_dir: Path, **cambios: Any) -> Ecl:
    ecl = Ecl(**_argumentos(datos, run_dir, **cambios))
    ecl._echo = lambda _texto: None
    return ecl


@pytest.fixture(scope="module")
def _semilla() -> Iterator[None]:
    """La semilla de hash del ``conftest``, para los fixtures de módulo (que corren antes)."""
    with pytest.MonkeyPatch.context() as parche:
        parche.setenv("PYTHONHASHSEED", "0")
        yield


@pytest.fixture(scope="module")
def datos(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return datasets.materialize(
        "ifrs9_retail_latam", workdir=tmp_path_factory.mktemp("ifrs9_datos")
    )


@pytest.fixture(scope="module")
def corrida(datos: Path, tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Ecl:
    """La corrida completa de la puerta sobre el dataset del paquete, con la marca."""
    ecl = _ecl(datos, tmp_path_factory.mktemp("ecl"), name="completa")
    ecl.run()
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return ecl


@pytest.fixture(scope="module")
def f4(datos: Path, tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Any:
    """La corrida del preset F4 por la puerta completa, sin informe."""
    cfg = deepcopy(ifrs9_preset()["config"])
    cfg["data"]["load"]["source"] = str(datos)
    cfg["report"] = None
    study = bayesrisk.run(
        BayesRiskConfig.model_validate(cfg), run_dir=tmp_path_factory.mktemp("f4") / "run"
    )
    assert study.run_context.status == "done", study.run_context.error
    return study


def _proyeccion(study: Any, *, sin_particion: bool = False) -> dict[str, Any]:
    """Los artefactos de cálculo de la provisión, bit a bit (la proyección canónica del molde)."""
    salida: dict[str, Any] = {}
    for dominio, clave in sorted(study.artifacts.keys()):
        if dominio not in _DOMINIOS or clave in {"estimator", "result"}:
            continue
        valor = study.artifacts.get(dominio, clave)
        if sin_particion and isinstance(valor, pd.DataFrame) and "partition" in valor.columns:
            valor = valor.drop(columns=["partition"])
        salida[f"{dominio}.{clave}"] = canonizar(valor)
    return salida


# ─────────────────────────── entrada mínima e inferencias (§3.2) ───────────────────────────


def test_las_inferencias_se_declaran_y_lo_institucional_no_se_infiere(corrida: Ecl) -> None:
    reglas = [i.regla for i in corrida.inferences]
    assert reglas == [
        "inferencia_horizonte_12m",
        "inferencia_esquema",
        "inferencia_corrida_de_cartera",
    ]
    horizonte = corrida.inferences[0]
    assert horizonte.valor == {"unidad": "year", "periodos": 1}
    trail = read_trail(corrida.project_dir / "run" / "audit_trail.jsonl")
    eventos = [(e.step, e.payload.get("regla")) for e in trail if e.kind == "decision"]
    assert eventos[0] == ("ecl_guided", "puerta_de_entrada")
    assert [r for paso, r in eventos if paso == "ecl_guided"][1:] == reglas


def test_sin_id_ni_marca_se_infiere_el_identificador_y_se_declara_la_ausencia(
    datos: Path, tmp_path: Path
) -> None:
    ecl = _ecl(datos, tmp_path, id=None, default=None)
    reglas = [i.regla for i in ecl.inferences]
    assert "inferencia_identificador" in reglas
    assert "inferencia_sin_marca" in reglas
    assert ecl.config.provisioning_ifrs9.staging.is_default_col is None


@pytest.mark.parametrize(
    ("period", "periodos"),
    [
        ("year", 1),
        ("Años", 1),
        ("semestre", 2),
        ("quarter", 4),
        ("trimestres", 4),
        ("mes", 12),
        ("months", 12),
        ("semana", 52),
        ("día", 365),
    ],
)
def test_el_horizonte_de_12_meses_se_infiere_de_la_unidad(
    datos: Path, tmp_path: Path, period: str, periodos: int
) -> None:
    ecl = _ecl(datos, tmp_path, period=period)
    assert ecl.config.provisioning_ifrs9.pd.horizon_12m_periods == periodos
    assert ecl.config.survival.time_grid.time_unit == period


@pytest.mark.parametrize("period", ["quincena", "bimestre", "period", ""])
def test_una_unidad_no_reconocida_detiene_la_puerta_antes_de_correr(
    datos: Path, tmp_path: Path, period: str
) -> None:
    with pytest.raises(EclInputError, match="Unidades aceptadas: año, semestre"):
        _ecl(datos, tmp_path, period=period, name="unidad")
    assert not (tmp_path / "unidad").exists(), "una puerta que no valida no deja nada escrito"


def test_sin_horizonte_se_detiene_con_el_maximo_observado_y_el_valor_que_usaria(
    datos: Path, tmp_path: Path
) -> None:
    with pytest.raises(EclInputError) as error:
        _ecl(datos, tmp_path, horizon=None, name="sin_horizonte")
    mensaje = str(error.value)
    assert "Tus datos observan hasta 5 años" in mensaje
    assert "horizon=5" in mensaje
    assert not (tmp_path / "sin_horizonte").exists()


@pytest.mark.parametrize("horizonte", [0, -1, 2.5, True])
def test_un_horizonte_que_no_es_un_entero_positivo_se_rechaza(
    datos: Path, tmp_path: Path, horizonte: Any
) -> None:
    with pytest.raises(EclInputError, match="horizon="):
        _ecl(datos, tmp_path, horizon=horizonte)


def test_una_columna_que_el_archivo_no_trae_se_nombra(datos: Path, tmp_path: Path) -> None:
    with pytest.raises(EclInputError, match="no trae la columna tasa"):
        _ecl(datos, tmp_path, rate="tasa")


def test_la_historia_de_la_curva_no_entra_como_covariable(datos: Path, tmp_path: Path) -> None:
    with pytest.raises(EclInputError, match="historia de la curva"):
        _ecl(datos, tmp_path, covariates=["event", "deuda_ingreso"])


def test_un_id_como_columna_alimenta_la_curva_y_la_provision(datos: Path, tmp_path: Path) -> None:
    frame = pd.read_parquet(datos).reset_index()
    ecl = _ecl(frame, tmp_path, name="id_columna")
    assert ecl.config.data.schema_.unique_keys == ("loan_id",)
    assert ecl.config.survival.input.id_col == "loan_id"
    assert ecl.config.provisioning_ifrs9.row_id_col == "loan_id"


# ─────────────────────────── constantes de la puerta (§3.5) y D-ECL-2 ───────────────────────────


def test_las_constantes_de_la_puerta_son_las_del_preset_f4(corrida: Ecl) -> None:
    cfg = corrida.config
    preset = ifrs9_preset()["config"]
    assert cfg.data.target is None and cfg.data.partition is None
    assert cfg.survival.input.pd_source == "none"
    assert cfg.survival.method == "discrete_hazard"
    assert cfg.survival.discrete_hazard.pd_role == "none"
    ifrs = cfg.provisioning_ifrs9
    assert ifrs.pd.pit_mode == "ttc_only"
    assert ifrs.scenarios.source == "single"
    assert ifrs.ead.method == "provided"
    assert ifrs.lgd.method == "provided"
    assert (ifrs.staging.dpd_sicr_backstop, ifrs.staging.dpd_default_backstop) == (30, 90)
    assert (
        ifrs.ecl.discount_convention == preset["provisioning_ifrs9"]["ecl"]["discount_convention"]
    )
    assert cfg.survival.fail_on_falta_dato is True and ifrs.fail_on_falta_dato is True


# ─────────────────────────── identidad (§6-5) ───────────────────────────


def test_el_config_hash_es_el_del_yaml_exportado(corrida: Ecl) -> None:
    assert config_hash(corrida.config) == config_hash(loads_config(corrida.to_yaml()))


# ─────────────────────────── la cifra (§4) ───────────────────────────


def test_la_ecl_de_la_puerta_es_la_de_f4_salvo_la_etiqueta_de_particion(
    corrida: Ecl, f4: Any
) -> None:
    card = corrida.study.artifacts.get("provisioning_ifrs9", "card")
    assert card.total_ecl_reported == pytest.approx(_ECL_F4, abs=1e-6)
    assert (card.n_stage1, card.n_stage2, card.n_stage3) == (5235, 477, 288)
    assert _proyeccion(corrida.study, sin_particion=True) == _proyeccion(f4, sin_particion=True)
    # Lo único que difiere: la etiqueta de partición que arrastra la curva por fila.
    ts_puerta = corrida.study.artifacts.get("survival", "term_structure")
    ts_f4 = f4.artifacts.get("survival", "term_structure")
    assert set(ts_f4["partition"].dropna()) and ts_puerta["partition"].isna().all()


# ─────────────────────────── parar y seguir (§6-6) ───────────────────────────


def test_run_completo_y_run_until_mas_resume_calculan_lo_mismo(
    datos: Path, tmp_path: Path, corrida: Ecl
) -> None:
    ecl = _ecl(datos, tmp_path, name="por_partes")
    ecl.run(until="survival")
    assert ecl.study.run_context.status == "done"
    assert not ecl.study.artifacts.has("provisioning_ifrs9", "card")
    assert ecl.summary().execution == "completada hasta «Curva de PD» (corrida parcial)"
    ecl.resume()
    assert ecl.study.run_context.status == "done"
    assert _proyeccion(ecl.study) == _proyeccion(corrida.study)


def test_until_rechaza_una_etapa_que_no_es_del_pipeline(corrida: Ecl) -> None:
    with pytest.raises(EclInputError, match="no es una etapa"):
        corrida.run(until="binning")


# ─────────────────────────── decisiones humanas (§3.9, §6-9) ───────────────────────────


@pytest.fixture(scope="module")
def decidida(datos: Path, tmp_path_factory: pytest.TempPathFactory, _semilla: None) -> Ecl:
    """Una corrida con una decisión de cada tipo, aplicada con ``resume()``."""
    ecl = _ecl(datos, tmp_path_factory.mktemp("decidida"), name="decidida")
    ecl.exclude("antiguedad_meses", reason="no viene en el archivo de los próximos cierres")
    ecl.rebut_backstops(stage2_days=60, reason="evidencia de cura en 31-60 días, informe 2025-03")
    ecl.resume()
    assert ecl.study.run_context.status == "done", ecl.study.run_context.error
    return ecl


def test_cada_decision_escribe_el_config_y_su_registro(decidida: Ecl) -> None:
    cfg = decidida.config
    assert "antiguedad_meses" not in cfg.survival.input.covariate_cols
    assert cfg.provisioning_ifrs9.staging.dpd_sicr_backstop == 60
    registros = [(d.action, d.columns, d.author) for d in cfg.decisions]
    assert registros == [
        ("exclude", ("antiguedad_meses",), "usuario"),
        ("rebut_backstops", ("days_past_due",), "usuario"),
    ]
    assert cfg.decisions[0].value == {
        "survival.input.covariate_cols": ["days_past_due", "utilizacion_linea", "deuda_ingreso"]
    }
    assert cfg.decisions[1].value == {
        "provisioning_ifrs9.staging.dpd_sicr_backstop": 60,
        "provisioning_ifrs9.staging.dpd_default_backstop": 90,
    }


def test_cada_decision_llega_al_trail_y_al_resumen_final_con_su_motivo(decidida: Ecl) -> None:
    trail = read_trail(decidida.project_dir / "run" / "audit_trail.jsonl")
    humanas = [
        e.payload
        for e in trail
        if e.kind == "decision" and e.payload.get("regla") == "decision_del_usuario"
    ]
    assert [(p["accion"], p["motivo"]) for p in humanas] == [
        ("exclude", "no viene en el archivo de los próximos cierres"),
        ("rebut_backstops", "evidencia de cura en 31-60 días, informe 2025-03"),
    ]
    assert not [e for e in trail if e.payload.get("regla") == "decision_sin_efecto"]
    final = decidida.summary()
    assert final.decisions == (
        "exclude antiguedad_meses — «no viene en el archivo de los próximos cierres»",
        "rebut_backstops days_past_due (Stage 2 desde 60 días de mora y Stage 3 desde 90 días "
        "de mora) — «evidencia de cura en 31-60 días, informe 2025-03»",
    )
    assert any("Stage 2 desde 60 días de mora y Stage 3 desde 90" in s for s in final.assumptions)


def test_la_decision_cambia_la_cifra_y_el_staging(decidida: Ecl, corrida: Ecl) -> None:
    antes = corrida.study.artifacts.get("provisioning_ifrs9", "card")
    despues = decidida.study.artifacts.get("provisioning_ifrs9", "card")
    assert despues.n_stage2 < antes.n_stage2, "con 60 días hay menos operaciones en Stage 2"
    assert despues.total_ecl_reported != antes.total_ecl_reported


def test_el_yaml_con_decisiones_conserva_la_identidad_y_las_trae(decidida: Ecl) -> None:
    yaml = decidida.to_yaml()
    recargado = loads_config(yaml)
    assert config_hash(recargado) == config_hash(decidida.config)
    assert [d.action for d in recargado.decisions] == ["exclude", "rebut_backstops"]


def test_una_decision_deshecha_a_mano_se_declara_sin_efecto(decidida: Ecl, tmp_path: Path) -> None:
    """El cotejo de D-DEC-3 reconoce el efecto sobre la curva y sobre la mora (§3.9)."""
    from bayesrisk.core.decisions import eventos_de_decisiones

    cfg = loads_config(decidida.to_yaml())
    survival = cfg.survival.model_copy(
        update={
            "input": cfg.survival.input.model_copy(
                update={"covariate_cols": (*cfg.survival.input.covariate_cols, "antiguedad_meses")}
            )
        }
    )
    ifrs = cfg.provisioning_ifrs9
    ifrs = ifrs.model_copy(
        update={"staging": ifrs.staging.model_copy(update={"dpd_sicr_backstop": 30})}
    )
    editado = cfg.model_copy(update={"survival": survival, "provisioning_ifrs9": ifrs})
    eventos = eventos_de_decisiones(editado)
    assert [(e["regla"], e["accion"]) for e in eventos] == [
        ("decision_sin_efecto", "exclude"),
        ("decision_sin_efecto", "rebut_backstops"),
    ]
    assert eventos[0]["umbral"] == "survival.input.covariate_cols"
    assert eventos[1]["umbral"] == "provisioning_ifrs9.staging.dpd_sicr_backstop"
    # Y sin tocar nada, las dos siguen aplicadas.
    assert {e["regla"] for e in eventos_de_decisiones(cfg)} == {"decision_del_usuario"}


@pytest.mark.parametrize(
    ("llamada", "mensaje"),
    [
        (lambda e: e.exclude("ingreso_mensual", reason="x"), "no es una covariable"),
        (lambda e: e.exclude("deuda_ingreso", reason="  "), "exige reason="),
        (lambda e: e.rebut_backstops(reason="x"), "stage2_days=, stage3_days="),
        (lambda e: e.rebut_backstops(stage2_days=-1, reason="x"), "número entero de días"),
        (lambda e: e.rebut_backstops(stage3_days=20, reason="x"), "empezaría antes que el Stage 2"),
    ],
)
def test_una_decision_que_no_cabe_se_rechaza_con_su_causa(
    datos: Path, tmp_path: Path, llamada: Any, mensaje: str
) -> None:
    ecl = _ecl(datos, tmp_path)
    with pytest.raises(EclInputError, match=mensaje):
        llamada(ecl)
    assert ecl.config.decisions == ()


# ─────────────────────────── coeficientes de la curva (§3.8, §6-8) ───────────────────────────


def test_los_coeficientes_de_la_curva_son_su_golden(corrida: Ecl) -> None:
    tabla = corrida.study.artifacts.get("survival", "coefficients")
    assert list(tabla.columns) == ["term", "coef", "std_error", "p_value"]
    golden = json.loads(_GOLDEN_COEFICIENTES.read_text(encoding="utf-8"))
    assert tabla["term"].tolist() == [fila["term"] for fila in golden["filas"]]
    for (_, fila), esperado in zip(tabla.iterrows(), golden["filas"], strict=True):
        for columna in ("coef", "std_error"):
            assert math.isclose(fila[columna], esperado[columna], rel_tol=1e-6), (fila, esperado)
        # El p-valor llega a 1e-266: se compara su orden de magnitud.
        assert math.isclose(
            math.log10(fila["p_value"]), math.log10(esperado["p_value"]), rel_tol=1e-4
        ), (fila, esperado)


def test_los_artefactos_existentes_de_survival_no_se_mueven(corrida: Ecl, f4: Any) -> None:
    """La clave nueva es aditiva: los siete artefactos de siempre siguen ahí y F4 la gana sola."""
    from bayesrisk.survival.step import SURVIVAL_ARTIFACTS

    claves_f4 = [k for d, k in f4.artifacts.keys() if d == "survival"]  # noqa: SIM118
    assert claves_f4 == [*SURVIVAL_ARTIFACTS, "coefficients"]
