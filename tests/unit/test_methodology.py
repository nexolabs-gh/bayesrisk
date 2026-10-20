"""Tests de la ficha metodológica compartida por UI e informe."""

from __future__ import annotations

import pytest

from bayesrisk.methodology import build_ifrs9_methodology_card, methodology_paragraphs


def test_vista_contextual_delega_en_dominio_y_conserva_fallback_defensivo() -> None:
    import numpy as np
    from test_validation_step import _scorecard_study

    from bayesrisk.methodology import build_validation_context_view
    from bayesrisk.ui.exceptions import UiSerializationError
    from bayesrisk.ui.serializers import serialize_study
    from bayesrisk.validation.config import ValidationConfig
    from bayesrisk.validation.exceptions import ValidationDataError
    from bayesrisk.validation.interpretation import interpretation_details, interpretation_lines
    from bayesrisk.validation.step import ValidationStep

    cfg = ValidationConfig(families=("calibration",), calibration={"binomial_by_grade": False})
    study = _scorecard_study(config=cfg)
    assert build_validation_context_view(study) == {
        "interpretation": None,
        "interpretation_lines": None,
    }
    ValidationStep(cfg).execute(study, np.random.default_rng(0))
    value = study.artifacts.get("validation", "interpretation")
    view = build_validation_context_view(study)
    assert view["interpretation"] == value.model_dump(mode="json")
    assert view["interpretation_lines"] == [
        *interpretation_lines(value),
        *interpretation_details(value),
    ]
    frame = study.artifacts.get("validation", "calibration_tie_groups").copy()
    frame.loc[0, "n"] += 1
    study.artifacts.set("validation", "calibration_tie_groups", frame, overwrite=True)
    with pytest.raises(ValidationDataError, match="grupos"):
        build_validation_context_view(study)
    future = {"policy_id": "future", "unrecognized": ["original"]}
    study.artifacts.set("validation", "interpretation", future, overwrite=True)
    view = build_validation_context_view(study)
    assert view["interpretation_lines"] is None
    view["interpretation"]["unrecognized"].append("mutación")
    assert future["unrecognized"] == ["original"]
    payload = serialize_study(study, governance=None)["validation"]
    assert payload["interpretation"] == future
    assert payload["interpretation_lines"] is None
    future["unrecognized"].append(float("inf"))
    with pytest.raises(UiSerializationError):
        serialize_study(study, governance=None)


def test_ficha_ifrs9_deriva_activos_y_capacidades_de_config_y_cards() -> None:
    """La ficha narra la corrida F4 sin números literales independientes de sus fuentes."""
    card = build_ifrs9_methodology_card(
        config=_config(),
        survival_card=_survival_card(),
        ifrs9_card=_ifrs9_card(),
    )

    assert card is not None
    active = {fact.id: fact for fact in card.active}
    assert active["lifetime_pd"].value == "Discrete-time hazard"
    assert active["lifetime_pd"].detail == "6.000 filas · 1.502 eventos · horizonte 5 años"
    assert active["pd_basis"].value == "TTC (through-the-cycle)"
    assert active["loss_inputs"].value == "LGD provided · EAD provided"
    assert "EAD se mantiene constante" in active["loss_inputs"].detail
    assert active["staging"].value == "30/90 días + is_default"
    assert active["scenario"].value == "Base 100 %"
    assert active["discount"].value == "EIR anual"

    inactive = {fact.id: fact for fact in card.not_exercised}
    assert set(inactive) == {"forward", "macro_scenarios", "markov"}
    assert all(fact.value == "Capacidad no ejercida" for fact in inactive.values())
    assert inactive["markov"].detail == (
        "La term-structure activa proviene de survival, no de Markov."
    )
    assert card.source_refs == (
        "config.survival",
        "survival.card",
        "config.provisioning_ifrs9",
        "provisioning_ifrs9.card",
    )

    paragraphs = methodology_paragraphs(card)
    assert "Activo en esta corrida:" in paragraphs
    assert "Capacidad no ejercida en esta corrida:" in paragraphs
    assert any("6.000 filas · 1.502 eventos · horizonte 5 años" in text for text in paragraphs)


def test_ficha_cambia_con_sus_fuentes_y_exige_card_de_ejecucion() -> None:
    """Variar config/cards cambia la ficha; config IFRS 9 sin card no se rotula como activo."""
    config = _config()
    config["survival"]["time_grid"]["horizon_periods"] = 7
    config["provisioning_ifrs9"]["staging"]["dpd_sicr_backstop"] = 45
    survival = _survival_card()
    survival["n_events"] = 777

    card = build_ifrs9_methodology_card(
        config=config,
        survival_card=survival,
        ifrs9_card=_ifrs9_card(),
    )
    assert card is not None
    active = {fact.id: fact for fact in card.active}
    assert active["lifetime_pd"].detail == "6.000 filas · 777 eventos · horizonte 7 años"
    assert active["staging"].value == "45/90 días + is_default"

    assert (
        build_ifrs9_methodology_card(
            config=config,
            survival_card=survival,
            ifrs9_card=None,
        )
        is None
    )


@pytest.mark.parametrize("term_source", ["forward", "markov"])
def test_ficha_ifrs9_respalda_fuente_no_survival_sin_inventar_cards(
    term_source: str,
) -> None:
    """Forward/Markov son fuentes válidas sin survival y sólo citan evidencia disponible."""
    config = _config()
    config["survival"] = None
    config[term_source] = {"type": "standard"}
    config["provisioning_ifrs9"]["pd"]["term_structure_source"] = term_source
    ifrs9_card = _ifrs9_card()
    ifrs9_card["term_structure_source"] = term_source

    card = build_ifrs9_methodology_card(
        config=config,
        survival_card=None,
        ifrs9_card=ifrs9_card,
    )

    assert card is not None
    active = {fact.id: fact for fact in card.active}
    assert "lifetime_pd" not in active
    assert active["pd_basis"].detail == (f"La term-structure activa proviene de {term_source}.")
    assert card.source_refs == (
        f"config.{term_source}",
        "config.provisioning_ifrs9",
        "provisioning_ifrs9.card",
    )
    assert "config.survival" not in card.source_refs
    assert "survival.card" not in card.source_refs

    inactive = {fact.id: fact for fact in card.not_exercised}
    if term_source == "forward":
        assert inactive["markov"].detail == (
            "La term-structure activa proviene de forward, no de Markov."
        )
    else:
        assert "markov" not in inactive


def _config() -> dict:
    return {
        "survival": {
            "method": "discrete_hazard",
            "time_grid": {"time_unit": "year", "horizon_periods": 5},
        },
        "forward": None,
        "markov": None,
        "provisioning_ifrs9": {
            "pd": {"term_structure_source": "survival", "pit_mode": "ttc_only"},
            "lgd": {"method": "provided"},
            "ead": {"method": "provided", "exposure_profile_col": None},
            "staging": {
                "dpd_sicr_backstop": 30,
                "dpd_default_backstop": 90,
                "is_default_col": "is_default",
            },
            "scenarios": {"source": "single"},
            "ecl": {
                "eir_col": "eir",
                "discount_convention": "annual_eir_year_fraction",
            },
        },
    }


def _survival_card() -> dict:
    return {
        "method": "discrete_hazard",
        "n_rows": 6_000,
        "n_events": 1_502,
        "n_periods": 5,
        "time_unit": "year",
    }


def _ifrs9_card() -> dict:
    return {
        "term_structure_source": "survival",
        "pit_mode": "ttc_only",
        "scenarios": ["base"],
        "scenario_weights": {"base": 1.0},
        "falta_dato": ["FALTA-DATO-IFRS-4"],
    }
