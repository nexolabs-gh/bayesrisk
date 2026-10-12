"""D-ESC-7: una sección de dominio nacida después de la 2.10.0 sólo se serializa si está declarada.

SDD-32 §5.3 y §12-4 (Cami, 2026-10-11, regla general). Hasta la 2.10.0, ``config_hash`` y
``dump_config`` serializaban **todas** las secciones, también las vacías (``"markov": null``): una
sección nueva con ``None`` de fábrica habría movido la identidad de todo config existente —también
los de los usuarios, que la usan como identidad de su inventario— y el YAML de toda corrida.

Los literales son la identidad medida sobre ``77a873b`` (bayesrisk 2.10.0) el 2026-10-11, antes de
tocar el config (``privado/evidencia/s42/capturar_identidad_2100.py``): el ``config_hash``, el
sha256 del YAML completo y el del YAML de los campos provistos, con las capas de dominio cargadas,
y el del preset F1 también en un intérprete sin cargarlas (sección opaca).
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import textwrap
from typing import Any, Final

import pytest

from bayesrisk.core.config import BayesRiskConfig, config_hash, dump_config, loads_config
from bayesrisk.core.config.schema import (
    SECCIONES_NACIDAS_DESPUES_DE_2_10_0,
    cargar_configs_de_dominio,
)
from bayesrisk.ui.presets import _PRESETS

#: ``{caso: (config_hash, sha256 del YAML completo, sha256 del YAML con exclude_unset)}``.
IDENTIDAD_2_10_0: Final[dict[str, tuple[str, str, str]]] = {
    "vacio": (
        "cbc42cfc02993f6646a744d66d2e0e348285e07761f59f434469afe2e8801610",
        "7eb925a90a2c8a083b90dd3875e4e7c9e26916d2225e59e4d81c16f2d7e5f223",
        "ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356",
    ),
    "f1-estandar-consumo": (
        "1063d6cfef0448c502b5f63c7e1f9f5b7ef234b0663b2d02a7527c52652c8633",
        "a57ac0e3f0eeb69c1b1e4b0a458dee7eac7eff52fbc40125811231923208c61f",
        "68cf417691631182b9dc692f282b4a9a353072009f8dc0bd1bae53aa9750ffbd",
    ),
    "f3-provisiones-consumo": (
        "857b06eef5aff267c36076641ffbdbf2fb17836511c206ea04fc5c160983886d",
        "e3178a15ccaeb8a965c6718fc369b99ceea7745a18eb97cc5c1a0e454eff448c",
        "61345def24777188e4dfea573bf90f53a05427fc5437a155b950ab7deb533202",
    ),
    "f4-ifrs9-retail": (
        "7de7a6829e85107303df2cfb9f4d09a40513bc8ea855ed9e3214d5182e88870c",
        "0034b80c1609fe9f0760bfa8d9e3e3f69af1e52cebc3501c14bd599f2b54c0c5",
        "a8a617126847e760270b382b513aa897ed583c1e82ee1168fb9b123289971ff5",
    ),
    "f5-provision-interna-generica": (
        "a7476bf2e595a8a65afea164ff60c9c1c13db140c4311d79be4aa7d858bcb81d",
        "381d3fdac6c50df0bbc5230f92027468cced48f9545023e6fdd17e7630388321",
        "aea942f2e74f231f3f8b8daa1cb83043c5d6a67a214eb50ba5a5ae57eefc5b53",
    ),
}
#: El YAML completo del preset F1 en un intérprete que no cargó las capas (secciones opacas).
_YAML_F1_OPACO_2_10_0: Final = "1dccef61867f1308e07446378595eb04b1604d292edc0566c0f65b819d63fce0"
#: Las secciones de la raíz del config de la 2.10.0, en su orden de declaración.
SECCIONES_DE_LA_2_10_0: Final[tuple[str, ...]] = (
    "schema_version",
    "name",
    "repro",
    "run",
    "data",
    "markov",
    "eda",
    "binning",
    "selection",
    "model",
    "scorecard",
    "calibration",
    "tuning",
    "ml",
    "explain",
    "survival",
    "forward",
    "stress",
    "provisioning_cmf",
    "provisioning_internal",
    "provisioning_ifrs9",
    "provisioning",
    "performance",
    "stability",
    "validation",
    "report",
    "audit",
    "governance",
    "tracking",
    "decisions",
)


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _crudo(caso: str) -> dict[str, Any]:
    return {} if caso == "vacio" else _PRESETS[caso]()["config"]


@pytest.fixture(autouse=True)
def _capas_cargadas() -> None:
    cargar_configs_de_dominio()


@pytest.mark.parametrize("caso", sorted(IDENTIDAD_2_10_0))
def test_sin_la_seccion_el_hash_y_el_yaml_son_los_de_la_2_10_0(caso: str) -> None:
    """El hash y el YAML de los campos provistos no dependen de lo que el proceso importó antes."""
    cfg = BayesRiskConfig.model_validate(_crudo(caso))
    esperado_hash, _esperado_yaml, esperado_unset = IDENTIDAD_2_10_0[caso]
    assert config_hash(cfg) == esperado_hash
    assert _sha(dump_config(cfg, exclude_unset=True)) == esperado_unset


def test_el_yaml_completo_es_el_de_la_2_10_0_en_un_interprete_fresco() -> None:
    """El YAML **completo** materializa los defaults de las secciones cuya capa está importada
    (``dump_config`` lo documenta), así que se mide en un intérprete con las capas de dominio
    cargadas y nada más, como se capturó sobre la 2.10.0.
    """
    codigo = textwrap.dedent(
        """
        import hashlib
        from bayesrisk.core.config import BayesRiskConfig, dump_config
        from bayesrisk.core.config.schema import cargar_configs_de_dominio
        from bayesrisk.ui.presets import _PRESETS
        cargar_configs_de_dominio()
        casos = {"vacio": {}}
        casos.update({pid: f()["config"] for pid, f in _PRESETS.items()})
        for nombre, crudo in sorted(casos.items()):
            yaml = dump_config(BayesRiskConfig.model_validate(crudo))
            print(nombre, hashlib.sha256(yaml.encode("utf-8")).hexdigest())
        """
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    medidos = dict(zip(salida[0::2], salida[1::2], strict=True))
    assert medidos == {caso: valores[1] for caso, valores in IDENTIDAD_2_10_0.items()}


def test_la_identidad_no_depende_de_que_las_capas_esten_cargadas() -> None:
    """En un intérprete fresco la sección viaja opaca; tampoco ahí entra si no se declaró."""
    codigo = textwrap.dedent(
        """
        import hashlib
        from bayesrisk.core.config import BayesRiskConfig, config_hash, dump_config
        from bayesrisk.ui.presets import standard_preset
        cfg = BayesRiskConfig.model_validate(standard_preset()["config"])
        print(config_hash(cfg))
        print(hashlib.sha256(dump_config(cfg).encode("utf-8")).hexdigest())
        print("master_scale" in cfg.model_dump(mode="json"))
        """
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    assert salida == [IDENTIDAD_2_10_0["f1-estandar-consumo"][0], _YAML_F1_OPACO_2_10_0, "False"]


@pytest.mark.parametrize("seccion", sorted(SECCIONES_NACIDAS_DESPUES_DE_2_10_0))
def test_ausente_no_aparece_en_ninguna_serializacion(seccion: str) -> None:
    cfg = BayesRiskConfig()
    assert getattr(cfg, seccion) is None
    for volcado in (
        cfg.model_dump(),
        cfg.model_dump(mode="json", by_alias=True),
        cfg.model_dump(mode="json", by_alias=True, exclude_unset=True),
    ):
        assert seccion not in volcado
    assert seccion not in cfg.model_dump_json()
    assert f"{seccion}:" not in dump_config(cfg)
    # Declarada explícitamente en None es lo mismo que ausente: nada que identificar.
    explicita = BayesRiskConfig.model_validate({seccion: None})
    assert config_hash(explicita) == config_hash(cfg)
    assert dump_config(explicita) == dump_config(cfg)


def test_declarada_si_entra_a_la_identidad_y_vuelve_igual() -> None:
    base = BayesRiskConfig.model_validate(_crudo("f1-estandar-consumo"))
    crudo = {**_crudo("f1-estandar-consumo"), "master_scale": {}}
    declarada = BayesRiskConfig.model_validate(crudo)
    assert "master_scale" in declarada.model_dump(mode="json")
    yaml = dump_config(declarada)
    assert "\nmaster_scale:" in yaml
    assert config_hash(declarada) != config_hash(base)
    assert loads_config(yaml) == declarada
    assert config_hash(loads_config(yaml)) == config_hash(declarada)
    # Una hoja de la sección es una decisión que cambia resultados: mueve la identidad.
    con_corte = BayesRiskConfig.model_validate({**crudo, "master_scale": {"approval_cutoff": 541}})
    assert config_hash(con_corte) != config_hash(declarada)


def test_toda_seccion_nueva_de_la_raiz_esta_en_la_regla() -> None:
    """Completitud en los dos sentidos: lo nuevo está en la regla y la regla sólo nombra lo nuevo.

    Una sección que se agregue a la raíz sin entrar a la regla movería todos los hashes; una que
    se nombre en la regla sin ser nueva dejaría de serializarse vacía, y el YAML de la 2.10.0
    cambiaría.
    """
    nuevas = tuple(c for c in BayesRiskConfig.model_fields if c not in SECCIONES_DE_LA_2_10_0)
    assert set(nuevas) == set(SECCIONES_NACIDAS_DESPUES_DE_2_10_0)
    assert set(SECCIONES_DE_LA_2_10_0) <= set(BayesRiskConfig.model_fields)
    for seccion in SECCIONES_NACIDAS_DESPUES_DE_2_10_0:
        assert BayesRiskConfig.model_fields[seccion].default is None


def test_los_dos_schemas_del_config_siguen_siendo_el_mismo() -> None:
    """En la 2.10.0 el schema de validación y el de serialización eran idénticos (medido). La regla
    no puede costar el segundo: un serializador con retorno ``Any`` lo dejaba vacío (pasada 1 de
    Codex sobre la capa A)."""
    validacion = BayesRiskConfig.model_json_schema()
    serializacion = BayesRiskConfig.model_json_schema(mode="serialization")
    assert serializacion == validacion
    assert "master_scale" in serializacion["properties"]
    for seccion in SECCIONES_NACIDAS_DESPUES_DE_2_10_0:
        assert BayesRiskConfig.model_fields[seccion].exclude_if is not None, seccion
