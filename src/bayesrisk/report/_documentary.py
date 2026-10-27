"""Lectura editorial del scorecard por snapshot (D-DOC-SC), sin cálculos de riesgo.

Los hechos conservan valor, fuente y momento. Las frases son una vista interna compartida;
el DTO opcional sólo transporta escalares y destinos. No modifica las cards históricas.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from bayesrisk.report.cifras import (
    cifra,
    conteo,
    corte,
    corte_porcentual,
    frente_al_corte,
    porcentaje,
)

Scope = Literal["stage", "report", "run_end"]
Availability = Literal["available", "not_applicable", "unavailable"]


def _mapping(value: Any) -> Mapping[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _records(value: Any) -> list[dict[str, Any]]:
    if hasattr(value, "to_dict") and hasattr(value, "columns"):
        return list(value.to_dict("records"))
    return []


def _partition(value: str) -> str:
    from bayesrisk.report.prose import _PARTITION_LABELS

    return _PARTITION_LABELS.get(value, value)


def _order(value: str) -> tuple[int, str]:
    return ({"desarrollo": 0, "dev": 0, "holdout": 1, "oot": 2}.get(value, 3), value)


@dataclass(frozen=True)
class EditorialFact:
    """Un hecho original y su lectura; ``text`` nunca sustituye la fuente numérica."""

    id: str
    domain: str
    key: str
    selector: str
    value: str | float | int | bool | None
    text: str
    moment: str = "snapshot"
    population: str | None = None
    unit: str | None = None
    availability: Availability = "available"
    reason: str | None = None
    highlight: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": {"domain": self.domain, "key": self.key, "selector": self.selector},
            "moment": self.moment,
            "population": self.population,
            "value": self.value,
            "unit": self.unit,
            "availability": self.availability,
            "reason": self.reason,
        }


@dataclass
class EditorialSnapshot:
    """Entrada interna defensiva de una lectura; nunca contiene resultados del futuro."""

    cards: Mapping[str, Any] = field(default_factory=dict)
    tables: Mapping[str, Any] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)
    events: Sequence[Mapping[str, Any]] = ()
    interpretation: Any = None
    pending_stages: tuple[str, ...] = ()
    scope: Scope = "run_end"


@dataclass(frozen=True)
class DocumentaryReading:
    facts: tuple[EditorialFact, ...]
    scope: Scope
    pending_stages: tuple[str, ...]

    @property
    def review(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(f.text for f in self.facts if f.highlight and f.text))

    def lines(self, domain: str) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                f.text
                for f in self.facts
                if (f.domain == domain or (domain == "model" and f.id.startswith("iv."))) and f.text
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "emission_scope": self.scope,
            "pending_stages": list(self.pending_stages),
            "facts": [f.to_dict() for f in self.facts],
            "evidence_index": [
                {
                    "fact_id": f.id,
                    "artifact_key": f"{f.domain}.{f.key}",
                    # El builder resuelve el destino contra las secciones efectivamente emitidas.
                    "section_id": None,
                    "local_path": None,
                }
                for f in self.facts
            ],
        }


def iv_reading(
    card: Mapping[str, Any], coefficients: Any, events: Sequence[Mapping[str, Any]] = ()
) -> tuple[EditorialFact, ...]:
    """Distingue historia, final y ausencia; concentración usa >, nunca ≥."""
    threshold = _number(_mapping(card.get("thresholds")).get("iv_contribution.threshold"))
    finals = {
        str(r["feature"]): r.get("iv_contribution")
        for r in _records(coefficients)
        if "feature" in r
    }
    final_features = set(card.get("final_features", finals))
    flags = {str(v) for v in card.get("iv_contribution_flags", ())}
    history: dict[str, dict[int, float]] = {}
    history_runs: dict[tuple[str, int], str | None] = {}
    for event in events:
        if event.get("regla") != "model_iv_contribution":
            continue
        payload = _mapping(event.get("valor"))
        feature = payload.get("feature")
        iteration = _number(payload.get("iteration"))
        contribution = _number(payload.get("iv_contribution"))
        if (
            isinstance(feature, str)
            and iteration is not None
            and iteration.is_integer()
            and contribution is not None
        ):
            history.setdefault(feature, {})[int(iteration)] = contribution
            history_runs[(feature, int(iteration))] = event.get("run_id")
    variables = (
        flags
        | set(history)
        | {
            f
            for f, v in finals.items()
            if f != "intercept"
            and threshold is not None
            and (number := _number(v)) is not None
            and number > threshold
        }
    )
    facts: list[EditorialFact] = []
    for feature in sorted(variables):
        historic = history.get(feature, {})
        for iteration, value in sorted(historic.items()):
            text = (
                f"{feature}: alerta durante la construcción: {porcentaje(value)} "
                f"en la iteración {iteration}."
            )
            if feature not in final_features:
                text += " La variable no quedó en el modelo final."
            facts.append(
                EditorialFact(
                    f"iv.{feature}.history.{iteration}",
                    "audit",
                    "trail",
                    json.dumps(
                        {
                            "regla": "model_iv_contribution",
                            "feature": feature,
                            "iteration": iteration,
                            "field": "valor.iv_contribution",
                            "run_id": history_runs.get((feature, iteration)),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    value,
                    text,
                    moment=f"iteration:{iteration}",
                    population="Desarrollo",
                    unit="proportion",
                    highlight=True,
                )
            )
        if feature not in final_features:
            if feature in flags and not historic:
                facts.append(
                    EditorialFact(
                        f"iv.{feature}.historical_flag",
                        "model",
                        "model_card",
                        f"iv_contribution_flags:{feature}",
                        None,
                        f"{feature}: alerta registrada; momento no identificado en la evidencia "
                        "disponible. La variable no quedó en el modelo final.",
                        moment="historical",
                        availability="unavailable",
                        reason="momento de la alerta no identificado",
                        highlight=True,
                    )
                )
            continue
        final = _number(finals.get(feature))
        unknown = (
            "Alerta registrada; momento no identificado en la evidencia disponible. "
            if feature in flags and not historic
            else ""
        )
        reason = None
        if final is None or threshold is None:
            reason = (
                "umbral no disponible"
                if threshold is None
                else "contribución final no finita o ausente"
            )
            comparison = f"Comparación final no disponible: {reason}."
            if final is not None:
                comparison += f" Contribución final: {porcentaje(final)}."
        elif final > threshold:
            observed = frente_al_corte(porcentaje(final)[:-2], final * 100, threshold * 100)
            comparison = (
                f"Contribución final al IV superior al umbral: {observed} % > "
                f"{corte_porcentual(threshold)}."
            )
        else:
            observed = frente_al_corte(porcentaje(final)[:-2], final * 100, threshold * 100)
            comparison = (
                f"Contribución final: {observed} %; no supera el umbral "
                f"{corte_porcentual(threshold)}."
            )
        facts.append(
            EditorialFact(
                f"iv.{feature}.final",
                "model",
                "coefficients",
                f"feature={feature};iv_contribution",
                final,
                f"{feature}: {unknown}{comparison}",
                moment="final_model",
                population="Desarrollo",
                unit="proportion",
                availability="unavailable" if reason else "available",
                reason=reason,
                highlight=True,
            )
        )
        if threshold is not None:
            facts.append(
                EditorialFact(
                    f"iv.{feature}.threshold",
                    "model",
                    "model_card",
                    "thresholds.iv_contribution.threshold",
                    threshold,
                    "",
                    moment="final_model",
                    unit="proportion",
                )
            )
    return tuple(facts)


def trend_label(value: Any, dtype: Any) -> str:
    from bayesrisk.report.prose import _MONOTONIC_LABELS

    if dtype == "categorical":
        return "No aplica el diagnóstico de tendencia numérica"
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "No disponible"
    return _MONOTONIC_LABELS.get(str(value), "No disponible")


def _population(snapshot: EditorialSnapshot) -> list[EditorialFact]:
    facts: list[EditorialFact] = []
    data = _mapping(snapshot.cards.get("data"))
    counts = _mapping(data.get("class_counts"))
    bad, good = _number(counts.get("malo")), _number(counts.get("bueno"))
    n, rate = _number(data.get("n_rows")), _number(data.get("bad_rate"))
    if n is not None:
        text = f"Universo global: {conteo(int(n))} filas"
        if bad is not None and good is not None:
            text += f"; {conteo(int(bad + good))} elegibles y {conteo(int(bad))} malos"
        if rate is not None:
            text += f"; tasa de malos {porcentaje(rate)} sobre elegibles"
        facts.append(
            EditorialFact(
                "population.global",
                "data",
                "data_card",
                "n_rows;class_counts;bad_rate",
                n,
                text + ".",
                population="Global",
            )
        )
    for sample, size in sorted(
        _mapping(data.get("partition_sizes")).items(), key=lambda x: _order(str(x[0]))
    ):
        value = _number(size)
        if value is None:
            continue
        rate = _number(_mapping(data.get("partition_bad_rates")).get(sample))
        text = f"{_partition(str(sample))}: {conteo(int(value))} filas"
        if value == 0:
            text += "; tasa no aplicable (población vacía)"
        elif rate is not None:
            text += f"; tasa de malos {porcentaje(rate)} sobre las filas de la muestra"
        facts.append(
            EditorialFact(
                f"population.{sample}",
                "data",
                "data_card",
                f"partition_sizes.{sample};partition_bad_rates.{sample}",
                value,
                text + ".",
                population=_partition(str(sample)),
            )
        )
    eda = _mapping(snapshot.cards.get("eda"))
    if eda:
        params = _mapping(snapshot.params.get("eda"))
        analysis_sample = params.get("analysis_partition")
        population = (
            _partition(str(analysis_sample))
            if analysis_sample is not None
            else "población no acreditada"
        )
        rows = _records(snapshot.tables.get("eda.default_rate.by_period"))
        eligible = [_number(r.get("n_eligible")) for r in rows]
        bads = [_number(r.get("n_bad")) for r in rows]
        text = f"Tasa del análisis exploratorio: {population}, antes del muestreo de perfiles"
        complete = bool(rows) and all(v is not None for v in eligible + bads)
        if complete:
            eligible_count = int(sum(v for v in eligible if v is not None))
            bad_count = int(sum(v for v in bads if v is not None))
            text += f"; {conteo(eligible_count)} elegibles y {conteo(bad_count)} malos"
            periods = [str(r["period"]) for r in rows if "period" in r]
            if periods:
                text += (
                    f"; {len(periods)} períodos/cohortes, desde {periods[0]} "
                    f"hasta {periods[-1]}; detalle en la tabla temporal"
                )
        else:
            text += "; denominador temporal no disponible"
        facts.append(
            EditorialFact(
                "population.eda",
                "eda",
                "default_rate",
                "by_period.n_eligible;n_bad;period",
                len(rows) if complete else None,
                text + ".",
                population=population,
                availability="available" if complete else "unavailable",
                reason=None if complete else "denominador temporal no disponible",
            )
        )
    return facts


def _trends(snapshot: EditorialSnapshot) -> list[EditorialFact]:
    facts: list[EditorialFact] = []
    for row in _records(snapshot.tables.get("binning.summary")):
        name = str(row.get("name", ""))
        label = trend_label(row.get("monotonic_trend"), row.get("dtype"))
        facts.append(
            EditorialFact(
                f"trend.{name}",
                "binning",
                "summary",
                f"name={name};dtype;monotonic_trend",
                str(row["monotonic_trend"])
                if label != "No disponible" and row.get("monotonic_trend") is not None
                else None,
                f"{name}: tendencia de la tasa de malos en Desarrollo (tramos regulares): {label}. "
                "El WoE es otra magnitud.",
                population="Desarrollo",
                availability="not_applicable"
                if row.get("dtype") == "categorical"
                else "unavailable"
                if label == "No disponible"
                else "available",
            )
        )
    seen: set[tuple[str, str]] = set()
    rows = _records(snapshot.tables.get("binning.event_rate_by_partition"))
    for row in sorted(
        rows, key=lambda r: (*_order(str(r.get("partition"))), str(r.get("feature")))
    ):
        feature, sample = str(row.get("feature", "")), str(row.get("partition", ""))
        if row.get("inverts") is not True or (feature, sample) in seen:
            continue
        seen.add((feature, sample))
        facts.append(
            EditorialFact(
                f"inversion.{sample}.{feature}",
                "binning",
                "event_rate_by_partition",
                f"feature={feature};partition={sample};inverts",
                True,
                f"{feature}: la tasa de malos invierte la tendencia en {_partition(sample)}.",
                population=_partition(sample),
                highlight=True,
            )
        )
    return facts


def _performance(snapshot: EditorialSnapshot) -> list[EditorialFact]:
    card = _mapping(snapshot.cards.get("performance"))
    facts: list[EditorialFact] = []
    thresholds = _mapping(card.get("thresholds"))
    for sample, metrics in sorted(
        _mapping(card.get("max_metrics_by_partition")).items(), key=lambda x: _order(str(x[0]))
    ):
        pieces: list[str] = []
        start = len(facts)
        for metric in ("auc", "gini", "ks"):
            value = _number(_mapping(metrics).get(metric))
            if value is None:
                continue
            threshold = _number(thresholds.get(f"{metric}_min"))
            piece = f"{metric.upper()} {cifra(value, decimales=3)}"
            if threshold is not None:
                observed = frente_al_corte(cifra(value, decimales=3), value, threshold)
                piece = f"{metric.upper()} {observed}"
                piece += f"; mínimo configurado {corte(threshold)}"
            pieces.append(piece)
            facts.append(
                EditorialFact(
                    f"performance.{sample}.{metric}",
                    "performance",
                    "card",
                    f"max_metrics_by_partition.{sample}.{metric}",
                    value,
                    "",
                    population=_partition(str(sample)),
                )
            )
        if pieces:
            from dataclasses import replace

            text = f"{_partition(str(sample))}: {' · '.join(pieces)}."
            if not any(
                _number(thresholds.get(f"{m}_min")) is not None for m in ("auc", "gini", "ks")
            ):
                text += " Sin umbrales de alerta configurados."
            facts[start] = replace(facts[start], text=text, highlight=True)
    return facts


def psi_number(card: Mapping[str, Any], comparison: str) -> str:
    """Cifra del PSI que conserva el lado de ambas fronteras efectivas."""
    value = _number(_mapping(card.get("max_psi_by_comparison")).get(comparison))
    if value is None:
        return "No evaluable"
    number = cifra(value, decimales=4)
    thresholds = tuple(_number(card.get(key)) for key in ("stable_threshold", "review_threshold"))
    # Un refinamiento puede cambiar el lado del otro corte. Se acepta sólo el punto fijo:
    # cada cambio añade decimales, hasta la representación exacta que satisface ambos.
    while True:
        previous = number
        for threshold in thresholds:
            if threshold is not None:
                number = frente_al_corte(number, value, threshold)
        if number == previous:
            return number


def psi_reading(card: Mapping[str, Any]) -> list[EditorialFact]:
    """Una lectura del PSI para la cifra final y todos sus consumidores."""
    from bayesrisk.report.prose import _COMPARISON_LABELS
    from bayesrisk.stability.results import BAND_LABELS, PSI_METRIC_LABELS

    facts: list[EditorialFact] = []
    for comparison, raw in sorted(_mapping(card.get("max_psi_by_comparison")).items()):
        value = _number(raw)
        magnitude = PSI_METRIC_LABELS.get(
            str(_mapping(card.get("psi_metric_by_comparison")).get(comparison))
        )
        band = str(_mapping(card.get("bands_by_comparison")).get(comparison, "not_evaluable"))
        samples = _COMPARISON_LABELS.get(str(comparison), str(comparison))
        number = psi_number(card, str(comparison))
        cuts = [
            (name, _number(card.get(key)))
            for name, key in (("Estable", "stable_threshold"), ("Revisar", "review_threshold"))
        ]
        stable, review = cuts[0][1], cuts[1][1]
        reason = None
        if magnitude is None:
            reason = "la identidad de la magnitud y su relación con la banda no están acreditadas"
            text = (
                f"Lectura histórica: máximo PSI registrado {number}, {samples}; "
                "magnitud no acreditada. La banda histórica no se atribuye a este máximo"
            )
        else:
            text = (
                f"Peor PSI entre score y PD: {number}, {magnitude}, {samples}. "
                f"Banda {BAND_LABELS.get(band, 'No evaluable')}"
            )
        if value is None:
            reason = "el PSI no tiene un valor finito disponible"
        if stable is not None and review is not None:
            text += f"; cortes efectivos {corte(stable)} y {corte(review)}"
        else:
            text += "; cortes efectivos no disponibles"
        text += (
            ". Su alcance no acredita igualdad de distribuciones, calibración "
            "ni ausencia de todo desplazamiento."
        )
        facts.append(
            EditorialFact(
                f"psi.{comparison}",
                "stability",
                "card",
                f"max_psi_by_comparison.{comparison};psi_metric_by_comparison;bands_by_comparison",
                value,
                text,
                population=samples,
                availability="unavailable" if reason is not None else "available",
                reason=reason,
                highlight=True,
            )
        )
    return facts


def model_warnings(card: Mapping[str, Any]) -> tuple[EditorialFact, ...]:
    """Bloqueos del ajuste conservados también sin resumen serializado."""
    facts: list[EditorialFact] = []
    if _mapping(card.get("fit_statistics")).get("converged") is False:
        facts.append(
            EditorialFact(
                "model.not_converged",
                "model",
                "model_card",
                "fit_statistics.converged",
                False,
                "El ajuste no convergió: la inferencia sobre los coeficientes no es válida",
                highlight=True,
            )
        )
    for feature in sorted(str(f) for f in card.get("sign_flags", ())):
        facts.append(
            EditorialFact(
                f"model.sign.{feature}",
                "model",
                "model_card",
                f"sign_flags.{feature}",
                feature,
                f"Coeficiente con el signo invertido respecto del riesgo esperado: {feature}",
                highlight=True,
            )
        )
    return tuple(facts)


def _validation(snapshot: EditorialSnapshot) -> list[EditorialFact]:
    from bayesrisk.validation.interpretation import (
        HISTORICAL_READING_TEXT,
        UNSUPPORTED_POLICY_TEXT,
        interpretation_lines,
        read_interpretation,
    )
    from bayesrisk.validation.results import VALIDATION_STATUS_LABELS

    card = _mapping(snapshot.cards.get("validation"))
    if "validation" in snapshot.pending_stages:
        text = (
            "Validación pendiente de ejecución al emitir este informe."
            if snapshot.scope == "report"
            else "Validación pendiente de ejecución en este snapshot."
        )
        return [
            EditorialFact(
                "validation.pending",
                "run",
                "steps",
                "pending:validation",
                None,
                text,
                availability="unavailable",
                reason="etapa pendiente",
                highlight=True,
            )
        ]
    interpretation = read_interpretation(snapshot.interpretation)
    if interpretation is not None:
        return [
            EditorialFact(
                "validation.context",
                "validation",
                "interpretation",
                "overall_status;n_tests;n_failed;coverage_gap",
                interpretation.overall_status,
                " ".join(interpretation_lines(interpretation)),
                highlight=True,
            )
        ]
    if card:
        notice = (
            HISTORICAL_READING_TEXT if snapshot.interpretation is None else UNSUPPORTED_POLICY_TEXT
        )
        status = VALIDATION_STATUS_LABELS.get(str(card.get("overall_status")), "No disponible")
        text = f"{notice}. Estado histórico: {status}."
        return [
            EditorialFact(
                "validation.historical",
                "validation",
                "card",
                "overall_status",
                str(card.get("overall_status")),
                text,
                moment="historical",
                highlight=True,
            )
        ]
    return []


def _scale(snapshot: EditorialSnapshot) -> list[EditorialFact]:
    if "master_scale" in snapshot.pending_stages:
        return []
    facts: list[EditorialFact] = []
    rows = _records(snapshot.tables.get("master_scale.grade_table"))
    for row in sorted(rows, key=lambda r: (*_order(str(r.get("sample"))), str(r.get("grade")))):
        band = str(row.get("traffic_light"))
        if band not in {"red", "amber"}:
            continue
        sample, grade = str(row.get("sample")), str(row.get("grade"))
        pd, observed = _number(row.get("pd")), _number(row.get("bad_rate"))
        label = {"red": "Rojo", "amber": "Ámbar"}[band]
        text = (
            f"Escala maestra: tramo {grade}, {_partition(sample)}, {label}. "
            f"PD {porcentaje(pd)}; tasa observada {porcentaje(observed)} "
            "sobre operaciones con desenlace. Los tramos de escala no son grupos HL "
            "y no cambian el estado contextual."
        )
        facts.append(
            EditorialFact(
                f"scale.{sample}.{grade}",
                "master_scale",
                "grade_table",
                f"sample={sample};grade={grade};traffic_light;pd;bad_rate",
                pd,
                text,
                population=_partition(sample),
                unit="proportion",
                highlight=True,
            )
        )
    return facts


def build_reading(snapshot: EditorialSnapshot) -> DocumentaryReading:
    """Orden fijo de familias, sin top N ni decisiones humanas implícitas."""
    # El filtro es previo a construir frases: ni una card inyectada permite adoptar resultados
    # de un paso que la propia emisión declara pendiente.
    current = EditorialSnapshot(
        cards={d: c for d, c in snapshot.cards.items() if d not in snapshot.pending_stages},
        tables={
            k: v
            for k, v in snapshot.tables.items()
            if k.split(".", 1)[0] not in snapshot.pending_stages
        },
        params=snapshot.params,
        events=() if "model" in snapshot.pending_stages else snapshot.events,
        interpretation=snapshot.interpretation,
        pending_stages=snapshot.pending_stages,
        scope=snapshot.scope,
    )
    facts = (
        *_population(current),
        *_validation(current),
        *_scale(current),
        *_trends(current),
        *_performance(current),
        *psi_reading(_mapping(current.cards.get("stability"))),
        *model_warnings(_mapping(current.cards.get("model"))),
        *iv_reading(
            _mapping(current.cards.get("model")),
            current.tables.get("model.coefficients"),
            current.events,
        ),
    )
    return DocumentaryReading(tuple(facts), snapshot.scope, snapshot.pending_stages)


def study_events(study: Any, trail_path: Path | None = None) -> tuple[Mapping[str, Any], ...]:
    """Lee sólo eventos de ESTA corrida de un sink conocido; no interpreta ``detail``."""
    from bayesrisk.audit import JsonlAuditSink, read_trail
    from bayesrisk.core.audit import FanOutSink, InMemoryAuditSink

    candidates = [getattr(study, "_audit", None)]
    run_id = getattr(getattr(study, "run_context", None), "run_id", None)
    # Durante resume el trail canónico todavía pertenece a la corrida anterior. Se busca
    # primero el sink vivo y se acepta una fuente sólo si contiene el run_id actual.
    while candidates:
        sink = candidates.pop(0)
        if isinstance(sink, FanOutSink):
            candidates.extend(sink.sinks)
            continue
        elif isinstance(sink, InMemoryAuditSink):
            events = list(sink.events)
        elif isinstance(sink, JsonlAuditSink) and sink.path.is_file():
            events = list(read_trail(sink.path))
        else:
            continue
        if any(e.kind == "run_start" and e.payload.get("run_id") == run_id for e in events):
            return _decisions_for_run(events, run_id)
    if trail_path is not None and trail_path.is_file():
        return _decisions_for_run(read_trail(trail_path), run_id)
    return ()


def _decisions_for_run(events: Any, run_id: str | None) -> tuple[Mapping[str, Any], ...]:
    selected: list[Mapping[str, Any]] = []
    belongs = False
    for event in events:
        if event.kind == "run_start":
            belongs = run_id is not None and event.payload.get("run_id") == run_id
            if belongs:
                selected = []
        elif belongs and event.kind == "decision":
            selected.append({**event.payload, "run_id": run_id})
        elif event.kind == "run_end":
            belongs = False
    return tuple(selected)


def snapshot_from_study(
    study: Any,
    *,
    scope: Scope = "run_end",
    pending_stages: tuple[str, ...] = (),
    trail_path: Path | None = None,
) -> EditorialSnapshot:
    """Adapta artefactos existentes; no llama al builder ni ejecuta un paso."""
    from bayesrisk.report.builder import (
        _CARD_ARTIFACTS,
        _collect_pipeline_params,
        _extract_dataframes,
    )

    cards = {
        domain: dict(_mapping(study.artifacts.get(domain, key)))
        for domain, key in _CARD_ARTIFACTS
        if study.artifacts.has(domain, key)
    }
    tables: dict[str, Any] = {}
    for domain, key in (
        ("model", "coefficients"),
        ("binning", "summary"),
        ("binning", "event_rate_by_partition"),
        ("master_scale", "grade_table"),
        ("eda", "default_rate"),
    ):
        if study.artifacts.has(domain, key):
            tables.update(_extract_dataframes(study.artifacts.get(domain, key), f"{domain}.{key}"))
    interpretation = (
        study.artifacts.get("validation", "interpretation")
        if study.artifacts.has("validation", "interpretation")
        else None
    )
    return EditorialSnapshot(
        cards=cards,
        tables=tables,
        params=_collect_pipeline_params(study),
        events=study_events(study, trail_path),
        interpretation=interpretation,
        scope=scope,
        pending_stages=pending_stages,
    )


def reading_from_bundle(bundle: Any) -> DocumentaryReading:
    """Reusa la proyección del momento del informe; históricos sólo con sus propias fuentes."""
    final = _mapping(_mapping(getattr(bundle, "summary", None)).get("final"))
    raw = final.get("documentary_reading")
    events: list[Mapping[str, Any]] = []
    pending: tuple[str, ...] = ()
    if isinstance(raw, Mapping) and raw.get("schema_version") == 1:
        pending = tuple(str(s) for s in raw.get("pending_stages", ()))
        # Se recupera el valor estructurado del evento, nunca el texto de una decisión.
        for fact in raw.get("facts", ()):
            source = _mapping(_mapping(fact).get("source"))
            if source.get("domain") != "audit" or source.get("key") != "trail":
                continue
            try:
                selector = json.loads(str(source.get("selector", "")))
            except (TypeError, ValueError):
                continue
            if not isinstance(selector, dict) or selector.get("regla") != "model_iv_contribution":
                continue
            events.append(
                {
                    "regla": selector["regla"],
                    "valor": {
                        "feature": selector.get("feature"),
                        "iteration": selector.get("iteration"),
                        "iv_contribution": fact.get("value"),
                    },
                    "run_id": selector.get("run_id"),
                }
            )
    return build_reading(
        EditorialSnapshot(
            cards=bundle.cards,
            tables=getattr(bundle, "tables", {}),
            params=getattr(bundle, "pipeline_params", {}),
            interpretation=getattr(bundle, "validation_interpretation", None),
            scope="report",
            events=events,
            pending_stages=pending,
        )
    )
