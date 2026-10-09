"""Constructor lógico del **documento** del informe (SDD-26 §4/§6/§7; mejora 1.1).

``ReportBuilder`` recolecta las cards y artefactos tabulares ya publicados por un ``Study`` y arma
un :class:`~bayesrisk.report.results.ReportInputBundle`. Lo que ensambla no es un volcado del
pipeline: es un documento —portada, índice, resumen ejecutivo, capítulos y anexos— cuya estructura
declara :mod:`bayesrisk.report.document`, la **única** fuente de orden y títulos.

Los ocho dominios del pipeline dejan de ser secciones de primer nivel y pasan a ser subsecciones:
las que sostienen el juicio de validación, en *Resultados*; el detalle completo (todas las tablas y
todos los payloads), en los *Anexos B y C*. **Nada de lo que antes se reportaba desaparece**: el
dump se degrada a anexo, que es lo que hace auditable al informe.

El módulo sigue siendo *pass-through*: no recalcula ni normaliza números de dominios aguas arriba.
Sólo toma snapshots defensivos de estructuras mutables, especialmente ``DataFrame``.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import copy
import importlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NoReturn, TypeAlias, cast

from pydantic import BaseModel

from bayesrisk.report import prose
from bayesrisk.report._manifest import REPORT_TEMPLATE_VERSION, REPORT_TITLE, html_report_id
from bayesrisk.report.config import ReportConfig
from bayesrisk.report.document import (
    APPENDIX_LINEAGE_ID,
    APPENDIX_PARAMETER_DOMAINS,
    APPENDIX_PARAMETERS_ID,
    APPENDIX_TABLES_ID,
    CANONICAL_SECTION_ORDER,
    CHAPTER_SPECS,
    CONTEXT_DOMAINS,
    EXECUTIVE_SUMMARY_ID,
    HL_GROUP_TABLE_PREFIX,
    IFRS9_DOMAINS,
    IFRS9_EXTRA_SECTIONS,
    METHODOLOGY_STEPS,
    PIPELINE_DOMAINS,
    PROVISION_DOMAINS,
    RESULT_DOMAINS,
    SURVIVAL_PD_BY_PERIOD_TABLE,
    VALIDATION_FAMILIES,
    ChapterSpec,
    domain_section_id,
    domain_title,
)
from bayesrisk.report.exceptions import ReportInputError
from bayesrisk.report.results import (
    GovernanceDeclaration,
    PlaceholderBlock,
    ReportInputBundle,
    ReportManifest,
    ReportOutputFormat,
    ReportSection,
    ReportSectionStatus,
)

if TYPE_CHECKING:
    import pandas as pd

    from bayesrisk.core.lineage import LineageBundle
    from bayesrisk.core.study import Study

    DataFrameLike: TypeAlias = pd.DataFrame
else:
    DataFrameLike: TypeAlias = Any
    LineageBundle: TypeAlias = Any
    Study: TypeAlias = Any

__all__ = ["CANONICAL_SECTION_ORDER", "OPTIONAL_REPORT_INPUTS", "ReportBuilder"]

_CARD_ARTIFACTS: Final[tuple[tuple[str, str], ...]] = (
    # Población real (SDD-02). Opcional: no entra en ``ReportStep.requires``.
    ("data", "data_card"),
    ("eda", "eda_card"),
    ("binning", "binning_card"),
    ("selection", "selection_card"),
    ("model", "model_card"),
    ("scorecard", "card"),
    ("calibration", "card"),
    ("performance", "card"),
    ("stability", "card"),
    # Provisiones. Se RECOLECTAN si el dominio corrió, pero NO se exigen: no están en el default
    # de `SectionPolicyConfig.required_sections`, así que una corrida de scorecard no las echa en
    # falta. Su presencia activa el capítulo condicional (`ChapterSpec.requires_domain`).
    ("provisioning_cmf", "card"),
    ("provisioning_internal", "card"),
    ("provisioning", "card"),
    # IFRS 9 / ECL (SDD-16). Se RECOLECTA si el dominio corrió; no se exige (no está en las
    # ``required_sections`` por defecto). Su presencia activa el capítulo condicional ``ifrs9``
    # (``ChapterSpec.requires_domain='provisioning_ifrs9'``), igual que provisiones.
    ("provisioning_ifrs9", "card"),
    # Survival (SDD-18): no genera capítulo propio; su card alimenta la prosa del capítulo IFRS 9
    # (el mecanismo PD→lifetime se describe desde lo que la corrida realmente ajustó, no desde
    # supuestos del preset). Opcional como las demás cards de negocio.
    ("survival", "card"),
    # Resumen de validación formal (SDD-22). El capítulo se gatea por el ``result`` atómico,
    # no por esta card aislada; ambos son opcionales para report.
    ("validation", "card"),
)
_CARD_KEY_BY_DOMAIN: Final[dict[str, str]] = dict(_CARD_ARTIFACTS)
_RESULT_ARTIFACTS: Final[tuple[tuple[str, str], ...]] = (("validation", "result"),)

#: Las **cards** que el builder adopta si existen, más el ``result`` atómico de validación. Es el
#: contrato de *consumo opcional* del dominio ``report`` (D-FX-3): ninguna de estas claves entra a
#: ``ReportStep.requires`` —eso lo decide la doble intersección—, pero todas se declaran en
#: ``ReportStep.optional_requires`` para que la puerta pública ``bayesrisk.run(..., artifacts=...)``
#: no llame INERTE a una clave que el informe sí lee.
#:
#: ⚠️ **Son las cards, no todo lo que el builder recolecta.** ``_TABLE_ARTIFACTS`` y
#: ``_FIGURE_ARTIFACTS`` también se adoptan si existen y **siguen declarándose inertes** al
#: inyectarlas. Es el alcance que fija D-FX-3, que habla de cards; ampliarlo movería el veredicto de
#: la puerta de artefactos y es decisión de producto, no un olvido de esta línea.
OPTIONAL_REPORT_INPUTS: Final[tuple[tuple[str, str], ...]] = _CARD_ARTIFACTS + _RESULT_ARTIFACTS
_TABLE_ARTIFACTS: Final[tuple[tuple[str, str], ...]] = (
    ("eda", "default_rate"),
    ("eda", "stability"),
    ("eda", "univariate"),
    ("eda", "quality"),
    ("binning", "tables"),
    ("binning", "summary"),
    ("binning", "woe_frame"),
    ("selection", "selected_woe_frame"),
    ("selection", "selection_table"),
    ("selection", "correlation_matrix"),
    ("selection", "vif_table"),
    ("selection", "stability_table"),
    ("model", "coefficients"),
    ("model", "stepwise_trace"),
    ("model", "fit_statistics"),
    ("model", "raw_pd_frame"),
    ("scorecard", "scorecard"),
    ("scorecard", "score"),
    ("scorecard", "out_of_model_score"),
    ("calibration", "parameters"),
    ("calibration", "calibrated_pd_frame"),
    ("calibration", "out_of_model_calibrated_pd_frame"),
    ("performance", "performance_table"),
    ("performance", "discriminant_metrics"),
    ("stability", "psi_table"),
    ("stability", "stability_metrics"),
    # Provisiones: solo los frames AGREGADOS (SDD-28 §6.4). NUNCA ``detail`` (6.000 filas por
    # operación): no cabe en el cuerpo de un informe ni en el anexo.
    ("provisioning", "comparison"),
    ("provisioning_cmf", "summary"),
    ("provisioning_internal", "groups"),
    # IFRS 9: solo el ``summary`` agregado por stage (3 filas). NUNCA ``detail``/``staging``
    # (una fila por operación): mismo criterio que provisiones.
    ("provisioning_ifrs9", "summary"),
    # La curva de PD (D-ECL-12): los coeficientes del ajuste, una fila por término. NUNCA
    # ``term_structure`` (una fila por operación y período); su PD por período y cartera la arma
    # :func:`_curva_de_pd_por_cartera` con la función del resumen.
    ("survival", "coefficients"),
)
#: Las claves de la puntuación fuera del ajuste (enmienda PUNTUAR-POBLACION-TTD, D-TTD-2) se
#: publican siempre, vacías cuando la corrida no tiene esas filas. Una tabla sin filas no es
#: evidencia ni dato: no llega al informe, ni a sus exports, ni al anexo. Así el informe de una
#: corrida sin filas fuera del ajuste queda idéntico al de antes.
_OMITIDAS_SI_VACIAS: Final[frozenset[tuple[str, str]]] = frozenset(
    {("scorecard", "out_of_model_score"), ("calibration", "out_of_model_calibrated_pd_frame")}
)
_FIGURE_ARTIFACTS: Final[tuple[tuple[str, str], ...]] = (("eda", "figures"),)
_VALID_OUTPUT_FORMATS: Final[frozenset[str]] = frozenset(
    {"html", "pdf", "md", "docx", "csv", "xlsx"}
)
# La fuente editable se escribe como ``.qmd`` (Quarto), pero su formato lógico es ``md``.
_SUFFIX_ALIASES: Final[dict[str, str]] = {"qmd": "md"}
# Secciones de config que la Metodología necesita para describir lo que realmente se ejecutó.
# F3/F4 requieren los parámetros regulatorios que realmente ejecutan; no se agregan a
# ``PIPELINE_DOMAINS`` porque esa constante conserva la semántica del pipeline scorecard F1.
_PARAM_DOMAINS: Final[tuple[str, ...]] = (
    "data",
    *PIPELINE_DOMAINS,
    "survival",
    "markov",
    "forward",
    *PROVISION_DOMAINS,
    "provisioning_ifrs9",
    "validation",
)


class ReportBuilder:
    """Ensambla el documento lógico desde cards/results; no renderiza."""

    def __init__(self, config: ReportConfig) -> None:
        """Construye el builder desde una ``ReportConfig`` validada."""
        self.config = config

    @classmethod
    def from_config(cls, cfg: ReportConfig) -> ReportBuilder:
        """Construye ``ReportBuilder`` desde ``BayesRiskConfig.report``."""
        return cls(cfg)

    def collect(self, study: Study) -> ReportInputBundle:
        """Recolecta cards, tablas, figuras, parámetros y lineage en un snapshot defensivo."""
        lineage = _lineage_from_study(study)
        results = self._collect_results(study)
        cards = self._collect_cards(study)
        _merge_atomic_result_cards(cards, results)
        tables = self._collect_tables(study)
        tables.update(_data_card_tables(cards))
        tables.update(_atomic_result_tables(results))
        tables.update(_hl_group_tables(study, results))
        tables.update(_curva_de_pd_por_cartera(study))
        ifrs9_extras, tablas_ifrs9 = _escenarios_y_pd_del_modelo(study)
        tables.update(tablas_ifrs9)
        tables.update(_extract_card_dataframes(cards))
        figures = self._collect_figures(study)
        pipeline_params = _collect_pipeline_params(study)
        missing_sections = self._missing_required_sections(cards)
        bundle = ReportInputBundle(
            lineage=lineage,
            cards=cards,
            results=results,
            tables=tables,
            figures=figures,
            sections=(),
            missing_sections=missing_sections,
            pipeline_params=pipeline_params,
            # D-MON-3: la moneda sale del config del propio informe, no de un dominio del pipeline.
            currency=(self.config.currency or ""),
            # D-SC-14: lo declarado en `governance`, que existe cuando corre `report`.
            governance=_governance_declaration(getattr(study.config, "governance", None)),
            # Capa C de FLUJO-GUIADO-SCORECARD: el resumen final de la corrida, desde los mismos
            # constructores que `Scorecard.summary()` y la pantalla, para la página ejecutiva.
            summary=_run_summary(study, self.config),
            # D-CPY-3: los tramos con su rótulo legible, desde los bordes efectivos.
            bin_labels=_rotulos_de_tramos(study),
            # D-NOV-1 §1.1: la fila de puntos que recibe una categoría no vista, por variable.
            unseen_reference_bins=_referencias_no_vistas(study),
            # D-PAN-4: la procedencia de los tramos del EDA, declarada por el perfilador.
            eda_numeric_profiles=_perfiles_numericos(study),
            # IFRS9-FIRMABLE capa C: los escenarios y la PD del modelo, desde los resúmenes.
            ifrs9_extras=ifrs9_extras,
        )
        return bundle.model_copy(update={"sections": self.build_sections(bundle)})

    def build_sections(self, bundle: ReportInputBundle) -> tuple[ReportSection, ...]:
        """Construye el documento: capítulos, subsecciones de dominio y anexos.

        El orden y los títulos salen de :data:`~bayesrisk.report.document.CHAPTER_SPECS`; la
        numeración (1-6 para capítulos, A/B/C para anexos) se deriva aquí, de modo que omitir un
        dominio no deja huecos en el índice.

        Un capítulo con ``requires_domain`` informado es **condicional**: se omite entero si ese
        dominio no publicó card. La numeración se reajusta sola, porque se deriva de los capítulos
        efectivamente emitidos y no de la posición en ``CHAPTER_SPECS``.
        """
        sections: list[ReportSection] = []
        chapter_number = 0
        appendix_index = 0
        for spec in CHAPTER_SPECS:
            if spec.requires_domain and spec.requires_domain not in bundle.cards:
                continue  # capítulo condicional: el dominio no corrió ⇒ no existe el capítulo
            if spec.requires_result and spec.requires_result not in bundle.results:
                continue  # capítulo condicional: falta el oracle agregado ⇒ no se emite
            if spec.requires_governance and bundle.governance is None:
                continue  # capítulo condicional: sin gobernanza declarada ⇒ no existe (D-SC-16)
            if spec.requires_any_domain and not any(
                domain in bundle.cards for domain in spec.requires_any_domain
            ):
                continue  # condicional any-of: ninguno de sus dominios corrió ⇒ sin capítulo
            if spec.kind == "summary" and not _hay_pagina_ejecutiva(bundle):
                continue  # sin corrida, o el resumen no es el de lo que corrió: no hay página
            if spec.numbered:
                chapter_number += 1
                number = str(chapter_number)
            elif spec.kind == "appendix":
                number = chr(ord("A") + appendix_index)
                appendix_index += 1
            else:
                number = ""
            sections.append(self._chapter_section(spec, bundle, number))
            sections.extend(self._subsections(spec, bundle, number))
        return tuple(sections)

    def _chapter_section(
        self,
        spec: ChapterSpec,
        bundle: ReportInputBundle,
        number: str,
    ) -> ReportSection:
        """Construye el capítulo de primer nivel con su prosa y su bloque por completar."""
        payload: dict[str, Any] = {}
        if spec.id == APPENDIX_LINEAGE_ID:
            payload = _copy_mapping(cast(Mapping[Any, Any], bundle.lineage.model_dump(mode="json")))
            if not payload.get("injected_artifacts"):
                # D-ART-12: sin puerta, el Anexo A conserva sus bytes y su forma previos.
                payload.pop("injected_artifacts", None)
        elif spec.id == "limitations":
            payload = {
                "determinism_caveats": tuple(bundle.lineage.determinism_caveats),
                "missing_sections": bundle.missing_sections,
            }
        elif spec.id == APPENDIX_TABLES_ID:
            payload = {
                "table_keys": tuple(bundle.tables),
                "figure_keys": tuple(bundle.figures),
            }
        elif spec.kind == "summary":
            payload = dict(bundle.summary or {})
        return ReportSection(
            id=spec.id,
            title=spec.title,
            status="included",
            source_domain="report",
            source_key=spec.id,
            payload=payload,
            metric_sections={},
            kind=spec.kind,
            level=1,
            number=number,
            body=_chapter_body(spec.id, bundle),
            placeholder=_placeholder(spec, self.config),
        )

    def _subsections(
        self,
        spec: ChapterSpec,
        bundle: ReportInputBundle,
        number: str,
    ) -> tuple[ReportSection, ...]:
        """Construye las subsecciones de dominio que cuelgan de un capítulo."""
        if spec.id == "context":
            return self._domain_subsections(spec.id, CONTEXT_DOMAINS, bundle, number, kind="data")
        if spec.id == "methodology":
            return self._methodology_subsections(bundle, number)
        if spec.id == "results":
            return self._domain_subsections(spec.id, RESULT_DOMAINS, bundle, number, kind="data")
        if spec.id == "validation":
            return self._validation_subsections(bundle, number)
        if spec.id == "provisions":
            return self._domain_subsections(spec.id, PROVISION_DOMAINS, bundle, number, kind="data")
        if spec.id == "ifrs9":
            return self._ifrs9_subsections(bundle, number)
        if spec.id == APPENDIX_PARAMETERS_ID:
            return self._domain_subsections(
                spec.id,
                APPENDIX_PARAMETER_DOMAINS,
                bundle,
                number,
                kind="appendix",
            )
        return ()

    def _validation_subsections(
        self,
        bundle: ReportInputBundle,
        number: str,
    ) -> tuple[ReportSection, ...]:
        """Proyecta una subsección por familia declarada por el ``ValidationResult`` atómico."""
        card = bundle.cards.get("validation")
        if not isinstance(card, Mapping):
            return ()
        raw_families = card.get("families_run", ())
        families = (
            tuple(str(item) for item in raw_families)
            if isinstance(raw_families, tuple | list)
            else ()
        )
        sections: list[ReportSection] = []
        for family, title in VALIDATION_FAMILIES:
            if family not in families:
                continue
            sections.append(
                ReportSection(
                    id=domain_section_id("validation", family),
                    title=title,
                    status="included",
                    source_domain="validation",
                    source_key="result",
                    payload={},
                    metric_sections={},
                    kind="data",
                    level=2,
                    number=f"{number}.{len(sections) + 1}",
                    body=prose.validation_family_body(bundle, family),
                )
            )
        return tuple(sections)

    def _ifrs9_subsections(
        self,
        bundle: ReportInputBundle,
        number: str,
    ) -> tuple[ReportSection, ...]:
        """La curva, los escenarios, la provisión y la PD del modelo, en el orden del pipeline.

        Entre la curva y la provisión va lo que la corrida hizo con sus escenarios, y tras la
        provisión lo que hizo con la PD del modelo (IFRS9-FIRMABLE capa C). Las dos subsecciones
        nuevas sólo existen cuando ``bundle.ifrs9_extras`` las trae: sin escenarios ni las dos PD,
        el capítulo es exactamente el de siempre.
        """
        de_dominio = {
            section.source_domain: section
            for section in self._domain_subsections(
                "ifrs9", IFRS9_DOMAINS, bundle, number, kind="data"
            )
        }
        orden: list[ReportSection] = []
        for hijo in ("survival", "forward", "provisioning_ifrs9", "pd_model"):
            if hijo in de_dominio:
                orden.append(de_dominio[hijo])
            elif hijo in bundle.ifrs9_extras:
                orden.append(
                    ReportSection(
                        id=domain_section_id("ifrs9", hijo),
                        title=IFRS9_EXTRA_SECTIONS[hijo],
                        status="included",
                        # `forward` publica sus tablas del cuerpo por `KEY_TABLES["forward"]`; la
                        # de la PD del modelo no trae tablas: sólo dice.
                        source_domain="forward" if hijo == "forward" else None,
                        source_key=None,
                        payload={},
                        metric_sections={},
                        kind="data" if hijo == "forward" else "prose",
                        level=2,
                        number=number,
                        body=bundle.ifrs9_extras[hijo],
                    )
                )
        return tuple(
            section.model_copy(update={"number": f"{number}.{i}"})
            for i, section in enumerate(orden, 1)
        )

    def _methodology_subsections(
        self,
        bundle: ReportInputBundle,
        number: str,
    ) -> tuple[ReportSection, ...]:
        """Una subsección por etapa realmente ejecutada, con su prosa de parámetros reales."""
        sections: list[ReportSection] = []
        for step, title in METHODOLOGY_STEPS:
            body = prose.methodology_body(bundle, step)
            if not body:
                continue
            sections.append(
                ReportSection(
                    id=domain_section_id("methodology", step),
                    title=title,
                    status="included",
                    source_domain=step,
                    source_key=_CARD_KEY_BY_DOMAIN.get(step),
                    payload={},
                    metric_sections={},
                    kind="prose",
                    level=2,
                    number=f"{number}.{len(sections) + 1}",
                    body=body,
                )
            )
        return tuple(sections)

    def _domain_subsections(
        self,
        parent_id: str,
        domains: tuple[str, ...],
        bundle: ReportInputBundle,
        number: str,
        *,
        kind: str,
    ) -> tuple[ReportSection, ...]:
        """Construye las subsecciones de dominio de un capítulo aplicando ``missing_policy``."""
        sections: list[ReportSection] = []
        for domain in domains:
            if kind == "appendix" and domain in bundle.pipeline_params:
                # Anexo C documenta todo config efectivo recolectado, incluso si el dominio no
                # publicó card en esta corrida (p. ej. un bloque experimental config-only).
                status: ReportSectionStatus | None = "included"
            else:
                status = self._domain_status(domain, bundle.cards)
            if status is None:
                continue
            # El Anexo C anexa los parámetros de lo que sí corrió; un dominio ausente no tiene
            # parámetros que anexar y ya queda declarado en Limitaciones.
            if status == "missing" and kind == "appendix":
                continue
            sections.append(
                self._domain_section(
                    parent_id=parent_id,
                    domain=domain,
                    status=status,
                    bundle=bundle,
                    number=f"{number}.{len(sections) + 1}",
                    kind=kind,
                )
            )
        return tuple(sections)

    def _domain_status(
        self,
        domain: str,
        cards: Mapping[str, Any],
    ) -> ReportSectionStatus | None:
        """Resuelve si un dominio se publica, se omite o falla, según ``missing_policy``."""
        if domain in cards:
            return "included"
        if domain not in set(self.config.sections.required_sections):
            return None
        if self.config.sections.missing_policy == "error":
            card_key = _CARD_KEY_BY_DOMAIN.get(domain, "<sin contrato de card>")
            raise ReportInputError(
                "Falta una card requerida para construir el reporte: "
                f"dominio='{domain}', clave='{card_key}'. "
                "Ejecute el step aguas arriba o use missing_policy='warn'/'skip' para un "
                "reporte parcial explícito."
            )
        if self.config.sections.missing_policy == "skip":
            return None
        return "missing"

    def _domain_section(
        self,
        *,
        parent_id: str,
        domain: str,
        status: ReportSectionStatus,
        bundle: ReportInputBundle,
        number: str,
        kind: str,
    ) -> ReportSection:
        """Construye una subsección de dominio: datos en el cuerpo, dump completo en el anexo."""
        card_key = _CARD_KEY_BY_DOMAIN.get(domain)
        artifact_name = f"{domain}.{card_key or 'effective_config'}"
        payload: dict[str, Any] = {}
        metric_sections: dict[str, Any] = {}
        if status == "missing":
            payload = {
                "warning": (
                    "Sección requerida ausente; el reporte parcial no inventa números ni "
                    "rellena métricas."
                )
            }
        elif kind == "appendix":
            # Sólo el Anexo C reproduce el payload crudo: el cuerpo lo referencia, no lo repite.
            if domain in bundle.cards:
                payload, metric_sections = _payload_and_metric_sections(
                    _card_to_mapping(bundle.cards[domain], artifact_name),
                    artifact=artifact_name,
                )
            # Cada dominio configurado publica su config efectivo completo junto con la card. No
            # hay dump del config raíz: solo la sección namespaced que realmente alimentó el step.
            effective_config = bundle.pipeline_params.get(domain)
            if isinstance(effective_config, Mapping):
                payload["effective_config"] = _copy_mapping(effective_config)
        return ReportSection(
            id=domain_section_id(parent_id, domain),
            title=domain_title(domain, _titulo_card(bundle, domain)),
            status=status,
            source_domain=domain,
            source_key=card_key or "effective_config",
            payload=payload,
            metric_sections=metric_sections,
            kind=cast(Any, kind),
            level=2,
            number=number,
            body=prose.results_body(bundle, domain) if kind == "data" else (),
        )

    def build_manifest(self, bundle: ReportInputBundle, *, path: str) -> ReportManifest:
        """Ensambla metadatos pre-render; el renderer completa el ``sha256`` real."""
        output_format = _output_format_from_path(path, self.config)
        return ReportManifest(
            report_id=html_report_id(bundle, self.config),
            title=REPORT_TITLE,
            created_from_lineage_at=bundle.lineage.created_at.isoformat(),
            template_id=self.config.html.template_id,
            template_version=REPORT_TEMPLATE_VERSION,
            output_format=output_format,
            path=path,
            sha256="",
            deterministic=self.config.html.deterministic_ids and not self.config.ai.enabled,
            ai_enabled=self.config.ai.enabled,
            ai_used=False,
            sections=bundle.sections,
        )

    def _collect_cards(self, study: Study) -> dict[str, dict[str, Any]]:
        """Lee las cards canónicas del ``ArtifactStore`` y valida ``metric_sections``."""
        cards: dict[str, dict[str, Any]] = {}
        for domain, key in _CARD_ARTIFACTS:
            if not study.artifacts.has(domain, key):
                continue
            artifact_name = f"{domain}.{key}"
            raw = _card_to_mapping(study.artifacts.get(domain, key), artifact_name)
            _payload_and_metric_sections(raw, artifact=artifact_name)
            cards[domain] = raw
        return cards

    def _collect_results(self, study: Study) -> dict[str, Any]:
        """Recolecta DTOs agregados opcionales usados como oracle atómico por el documento."""
        results: dict[str, Any] = {}
        for domain, key in _RESULT_ARTIFACTS:
            if not study.artifacts.has(domain, key):
                continue
            value = study.artifacts.get(domain, key)
            if not isinstance(value, BaseModel):
                raise ReportInputError(
                    f"El resultado atómico '{domain}.{key}' debe ser un BaseModel; "
                    f"tipo observado={type(value).__name__}."
                )
            results[domain] = _copy_value(value)
        return results

    def _collect_tables(self, study: Study) -> dict[str, DataFrameLike]:
        """Extrae ``DataFrame`` de artefactos tabulares conocidos sin alterar upstream."""
        tables: dict[str, DataFrameLike] = {}
        for domain, key in _TABLE_ARTIFACTS:
            if not study.artifacts.has(domain, key):
                continue
            artefacto = study.artifacts.get(domain, key)
            if (domain, key) in _OMITIDAS_SI_VACIAS and bool(getattr(artefacto, "empty", False)):
                continue
            # D-SC-17: la tasa que no se pudo agrupar llega con la tabla vacía y su causa
            # declarada. Una tabla de sólo encabezados no es evidencia —ni en el cuerpo ni en el
            # anexo—, y la prosa del capítulo ya dice por qué no está. La condición nombra la
            # clave: `("eda", "stability")` también publica `not_evaluable_reason` —con otro
            # significado, la SEÑAL temporal— y no aporta ninguna tabla que omitir.
            if (domain, key) == ("eda", "default_rate") and (
                getattr(artefacto, "not_evaluable_reason", None) is not None
            ):
                continue
            # D-SC-20: la calidad que no se pudo calcular llega con la tabla vacía y sus siete
            # columnas. Mismo trato: una tabla de sólo encabezados no es evidencia, y la prosa del
            # contexto ya dice qué no se calculó y por qué.
            if (domain, key) == ("eda", "quality") and (
                getattr(getattr(artefacto, "by_column", None), "empty", False) is True
            ):
                continue
            tables.update(_extract_dataframes(artefacto, f"{domain}.{key}"))
        return tables

    def _collect_figures(self, study: Study) -> dict[str, Any]:
        """Recolecta especificaciones declarativas de figuras publicadas por EDA."""
        figures: dict[str, Any] = {}
        for domain, key in _FIGURE_ARTIFACTS:
            if study.artifacts.has(domain, key):
                figures[f"{domain}.{key}"] = _copy_value(study.artifacts.get(domain, key))
        return figures

    def _missing_required_sections(self, cards: Mapping[str, Any]) -> tuple[str, ...]:
        """Lista los dominios obligatorios ausentes, en el orden del pipeline."""
        required = set(self.config.sections.required_sections)
        return tuple(
            domain for domain in PIPELINE_DOMAINS if domain in required and domain not in cards
        )


def _hay_pagina_ejecutiva(bundle: ReportInputBundle) -> bool:
    """Si la página ejecutiva se emite: hay resumen y es el de lo que corrió.

    Sin ``summary`` (un bundle armado a mano, sin corrida) no hay página. Con un dominio del
    scorecard en las cards, la página es la del scorecard, como siempre. Sin ninguno —la cadena
    ``data → survival → provisioning_ifrs9``—, la página sólo sale si el resumen es el de una
    provisión (``family`` = ``"cartera"``, D-ECL-12): una corrida IFRS 9 cuyo config arrastra
    secciones del scorecard que no corrieron tendría el resumen del molde del scorecard, y no lo
    recibe.
    """
    if bundle.summary is None:
        return False
    if any(domain in bundle.cards for domain in RESULT_DOMAINS):
        return True
    return bundle.summary.get("family") == _FAMILIA_CARTERA


#: La familia de resúmenes de una provisión (``bayesrisk.guided.summaries.family_of``).
_FAMILIA_CARTERA: Final = "cartera"


def _chapter_body(chapter_id: str, bundle: ReportInputBundle) -> tuple[str, ...]:
    """Prosa determinista del capítulo; los capítulos sin prosa propia devuelven vacío."""
    if chapter_id == EXECUTIVE_SUMMARY_ID and (bundle.summary or {}).get("family") == (
        _FAMILIA_CARTERA
    ):
        return (
            "Lo que cuenta la corrida al terminar, con la misma fuente que la puerta guiada y la "
            "pestaña Resultados: el estado de la ejecución, los supuestos de los que depende la "
            "provisión, sus cifras clave, qué revisar, las decisiones humanas con su motivo y "
            "dónde queda cada archivo. Una provisión no tiene veredicto técnico del motor: el "
            "juicio sobre ella lo firma el validador en el resumen ejecutivo.",
            "Las rutas son las que el informe escribió al generarse: si la corrida se copia o se "
            "archiva después —desde la interfaz, o al apartar una corrida anterior—, los archivos "
            "se buscan en su carpeta de destino, y el registro de auditoría deja constancia de "
            "cada uno que se escribió.",
        )
    if chapter_id == EXECUTIVE_SUMMARY_ID:
        return (
            "Lo que cuenta la corrida al terminar, con la misma fuente que la puerta guiada y la "
            "pestaña Resultados: el estado de la ejecución y de la validación técnica, las cifras "
            "clave, qué revisar, las decisiones humanas con su motivo y dónde queda cada archivo. "
            "El veredicto lo firma el validador en el resumen ejecutivo.",
            "Las rutas son las que el informe escribió al generarse: si la corrida se copia o se "
            "archiva después —desde la interfaz, o al apartar una corrida anterior—, los archivos "
            "se buscan en su carpeta de destino, y el registro de auditoría deja constancia de "
            "cada uno que se escribió.",
        )
    if chapter_id == "model_card":
        return prose.model_card_body(bundle)
    if chapter_id == "context":
        return prose.context_body(bundle)
    if chapter_id == "methodology":
        return prose.methodology_intro(bundle)
    if chapter_id == "results":
        return prose.results_intro(bundle)
    if chapter_id == "validation":
        return prose.validation_intro(bundle)
    if chapter_id == "provisions":
        return prose.provisions_intro(bundle)
    if chapter_id == "ifrs9":
        return prose.ifrs9_intro(bundle)
    if chapter_id == "conclusions":
        return prose.conclusions_body(bundle)
    if chapter_id == "limitations":
        return prose.limitations_body(bundle)
    if chapter_id == APPENDIX_TABLES_ID:
        return (
            "Este anexo reproduce íntegras todas las tablas que produjo la corrida, incluidas "
            "las que el cuerpo del informe ya mostró. Es la trazabilidad completa: nada de lo "
            "que el motor calculó queda fuera del documento.",
        )
    if chapter_id == APPENDIX_PARAMETERS_ID:
        return (
            "Este anexo reproduce el payload completo de cada etapa: los parámetros efectivos y "
            "las métricas estructuradas tal como las publicó cada step, sin resumir.",
        )
    if chapter_id == APPENDIX_LINEAGE_ID:
        return (
            "La corrida queda identificada por los hashes de configuración y de datos, el commit "
            "del código y la semilla raíz. Con estos cuatro valores el resultado es reproducible.",
        )
    return ()


def _run_summary(study: Study, config: ReportConfig) -> dict[str, Any]:
    """El resumen final de la corrida para la página ejecutiva, o el motivo de que no lo haya.

    Los mismos constructores que ``Scorecard.summary()`` y que la pestaña Resultados
    (:mod:`bayesrisk.guided.summaries`, import perezoso: arrastra los mapas de rótulos de los
    dominios y ``import bayesrisk.report`` tiene que seguir liviano). El informe se renderiza como
    último paso, antes de que ``bayesrisk.run`` consolide la evidencia, así que el contexto no
    conoce la carpeta de la corrida y no la inventa: de sus archivos dice lo que el config manda
    (:func:`_archivos_que_el_informe_conoce`). Un resumen que no se pueda armar no tumba el
    informe —el documento es lo que la persona pidió—: se publica el motivo y el capítulo lo
    dice, la misma política que la pantalla.
    """
    from bayesrisk.guided.summaries import (
        RESUMEN_FINAL_ROTULOS,
        ROTULO_SUPUESTOS,
        SIN_ALERTAS,
        SIN_DECISIONES,
        SummaryContext,
        build_final_summary,
        build_stage_summaries,
        decision_lines_from_preamble,
        family_of,
        partition_label_from_config,
        source_label_from_config,
    )

    payload: dict[str, Any] = {
        "final": None,
        "labels": dict(RESUMEN_FINAL_ROTULOS),
        "sin_alertas": SIN_ALERTAS,
        "sin_decisiones": SIN_DECISIONES,
        "error": None,
    }
    if family_of(study.config) == _FAMILIA_CARTERA:
        # Una provisión (D-ECL-12): la página dice sus «Supuestos» en lugar de la validación
        # técnica, que no tiene. Se declara aunque el resumen no se arme, para que el capítulo
        # diga por qué no hay resumen en vez de omitirse. El payload del scorecard no gana
        # claves: su informe queda byte a byte.
        payload["family"] = _FAMILIA_CARTERA
        payload["labels"]["assumptions"] = ROTULO_SUPUESTOS
    try:
        contexto = SummaryContext(
            project_dir=None,
            run_dir=None,
            source_label=source_label_from_config(study.config),
            partition_label=partition_label_from_config(study.config),
            decision_lines=decision_lines_from_preamble(getattr(study, "preamble", ())),
            extra_files=_archivos_que_el_informe_conoce(study, config),
            pending_stages=_etapas_despues_del_informe(study),
        )
        etapas = build_stage_summaries(study, contexto)
        final = build_final_summary(study, etapas, contexto)
    except Exception as exc:  # se publica el motivo; el informe no se pierde por una frase
        texto = str(exc).strip() or type(exc).__name__
        payload["error"] = f"El resumen de la corrida no se pudo armar: {texto}"
        return payload
    payload["final"] = final.to_dict()
    return payload


def _etapas_despues_del_informe(study: Study) -> tuple[str, ...]:
    """Los pasos que ``run.steps`` puso DESPUÉS de ``report`` y que no habrán corrido al renderizar.

    El motor corre los pasos en orden de declaración y la validación formal es un insumo
    opcional del informe, así que ``[…, "report", "validation"]`` es un pipeline válido en el que
    el informe se escribe antes de la validación (pasada 1 de Codex sobre C1). La página
    ejecutiva no puede reflejar lo que aún no corrió, y tiene que decirlo en vez de afirmar que
    cierra la corrida. ``check_pipeline`` devuelve la misma lista que ``run`` (``run.steps`` o el
    pipeline por defecto) sin correr nada; si no se puede resolver, no se afirma nada.
    """
    comprobar = getattr(study, "check_pipeline", None)
    if not callable(comprobar):
        return ()
    try:
        pasos = [str(paso) for paso in comprobar()]
    except Exception:  # un pipeline que no resuelve no cambia lo que el informe puede afirmar
        return ()
    if "report" not in pasos:
        return ()
    return tuple(pasos[pasos.index("report") + 1 :])


def _archivos_que_el_informe_conoce(
    study: Study, config: ReportConfig
) -> tuple[tuple[str, str], ...]:
    """Dónde queda cada archivo, dicho sólo con lo que el config manda al renderizar.

    El HTML se nombra por su ruta (``output_dir`` + ``basename``, la misma que publica
    ``ReportResult.html_path``); los formatos pedidos, por la suya, con la salvedad de que un
    extra ausente los degrada; el registro de auditoría y la ficha, por su nombre en la carpeta
    de evidencia, que el informe no conoce porque se escribe antes de consolidarla.
    """
    archivos: list[tuple[str, str]] = []
    output_dir = config.output_dir.strip()
    if output_dir:
        base = Path(output_dir)
        archivos.append(("Informe HTML", str(base / f"{config.basename}.html")))
        derivados = (
            ("pdf", "Informe PDF", ".pdf", " (se escribe si el extra pdf está instalado)"),
            ("docx", "Informe Word", ".docx", " (se escribe si el extra docx está instalado)"),
            ("md", "Fuente editable (Quarto)", ".qmd", ""),
        )
        for formato, rotulo, sufijo, salvedad in derivados:
            if formato in config.formats:
                archivos.append((rotulo, f"{base / f'{config.basename}{sufijo}'}{salvedad}"))
    else:
        archivos.append(("Informe HTML", "no se escribió en disco: el informe se pidió en memoria"))
    audit = getattr(study.config, "audit", None)
    if audit is not None and _campo(audit, "enabled", True):
        # Con un nombre RELATIVO (la puerta guiada y el default por código) el archivo vive en la
        # carpeta de evidencia y se nombra. Con una ruta ABSOLUTA no se imprime ni la ruta ni el
        # nombre: la interfaz reserva el trail en una ruta provisional con un token por corrida
        # (`.trail-<token>.jsonl`) y lo renombra al persistir, así que imprimirla rompía el
        # determinismo del HTML entre dos corridas del mismo config (la suite completa lo acusó)
        # y apuntaba a un archivo que ya no existe. `audit` es INFRA: lo que varía con ella no
        # puede entrar al documento.
        trail = Path(str(_campo(audit, "trail_filename", "audit_trail.jsonl")))
        archivos.append(
            (
                "Registro de auditoría",
                "en la ruta que fija la sección audit del config"
                if trail.is_absolute()
                else f"{trail.name}, en la carpeta de evidencia de la corrida",
            )
        )
    if getattr(study.config, "governance", None) is not None:
        # La ficha se escribe sólo cuando la corrida tiene carpeta de evidencia (`run_dir`,
        # D-GOB-6); el informe no sabe si la hay, y no afirma un archivo que puede no existir.
        archivos.append(
            (
                "Ficha del modelo",
                "model_card.json y model_card.md, en la carpeta de evidencia de la corrida si se "
                "pidió una (run_dir)",
            )
        )
    return tuple(archivos)


def _campo(seccion: Any, nombre: str, default: Any) -> Any:
    """Un campo de una sección del config que puede llegar validada o como el dict crudo."""
    if isinstance(seccion, Mapping):
        return seccion.get(nombre, default)
    return getattr(seccion, nombre, default)


def _governance_declaration(value: Any) -> GovernanceDeclaration | None:
    """Proyecta ``config.governance`` al DTO del informe; ``None`` si no se declaró.

    El campo del config raíz es ``Any`` en runtime para no arrastrar ``bayesrisk.governance`` al
    importar el núcleo, así que puede llegar ya validado (``GovernanceConfig``) o como el ``dict``
    crudo del YAML si nadie importó el paquete antes. 🔴 Un ``dict`` se VALIDA con
    ``GovernanceConfig`` y de ahí se proyecta: la primera versión lo leía con defaults propios y,
    según el orden de imports, podía atribuir a la institución un propósito vacío o un nombre que
    nunca declaró (hallazgo de la revisión adversarial de la 1.14.0). Sólo se copian las
    declaraciones que el capítulo publica.
    """
    if value is None:
        return None
    from pydantic import ValidationError

    from bayesrisk.governance.config import GovernanceConfig

    if isinstance(value, GovernanceConfig):
        declared = value
    elif isinstance(value, BaseModel):
        try:
            declared = GovernanceConfig.model_validate(value.model_dump(mode="json"))
        except ValidationError as error:
            raise ReportInputError(f"governance no es un config válido: {error}") from error
    elif isinstance(value, Mapping):
        try:
            declared = GovernanceConfig.model_validate(dict(value))
        except ValidationError as error:
            raise ReportInputError(f"governance no es un config válido: {error}") from error
    else:
        raise ReportInputError(f"governance no es un config ni un mapping: {type(value).__name__}")
    return GovernanceDeclaration(
        model_name=declared.model_name,
        purpose=declared.purpose,
        assumptions=tuple(declared.assumptions),
        limitations=tuple(declared.limitations),
        review_period_months=declared.review_period_months,
        cartera=_optional_text(declared.cartera),
        motor=declared.motor,
        fase=declared.fase,
        estado_validacion=declared.estado_validacion,
        author=_optional_text(declared.author),
    )


def _optional_text(value: Any) -> str | None:
    return None if value is None or str(value).strip() == "" else str(value)


def _placeholder(spec: ChapterSpec, config: ReportConfig) -> PlaceholderBlock | None:
    """Adjunta el bloque POR COMPLETAR salvo que el config pida el entregable final."""
    if not spec.placeholder_title or config.document.placeholders == "hide":
        return None
    return PlaceholderBlock(
        title=spec.placeholder_title,
        guidance=spec.placeholder_guidance,
    )


def _merge_atomic_result_cards(
    cards: dict[str, dict[str, Any]],
    results: Mapping[str, Any],
) -> None:
    """Usa la card incluida en el DTO atómico y rechaza un snapshot independiente incoherente."""
    result = results.get("validation")
    if result is None:
        return
    atomic_card = getattr(result, "card", None)
    if atomic_card is None:
        raise ReportInputError("validation.result no contiene su card resumen atómica.")
    mapped = _card_to_mapping(atomic_card, "validation.result.card")
    standalone = cards.get("validation")
    if standalone is not None and standalone != mapped:
        raise ReportInputError(
            "validation.card no coincide con validation.result.card; el reporte rechaza una "
            "lectura no atómica de la validación."
        )
    cards["validation"] = mapped


def _data_card_tables(cards: Mapping[str, Mapping[str, Any]]) -> dict[str, DataFrameLike]:
    """Proyecta estados, particiones y exclusiones copiando literales de ``DataCardSection``."""
    card = cards.get("data")
    if card is None:
        return {}
    if card.get("target_col") is None:
        # D-ECL-2: una corrida de cartera no etiqueta ni particiona. Tablas vacías dirían «cero
        # malos» donde lo cierto es «no aplica»; la prosa de contexto lo declara.
        return {}
    class_counts = _required_mapping(card, "class_counts", artifact="data.data_card")
    partition_sizes = _required_mapping(card, "partition_sizes", artifact="data.data_card")
    partition_rates = _required_mapping(card, "partition_bad_rates", artifact="data.data_card")
    exclusions = _required_mapping(card, "exclusions_by_reason", artifact="data.data_card")

    states = [
        {"Estado": str(state), "Observaciones": _copy_value(count)}
        for state, count in class_counts.items()
    ]
    partitions = [
        {
            "Partición": str(partition),
            "Observaciones": _copy_value(size),
            "Tasa de incumplimiento": _copy_value(partition_rates.get(partition)),
        }
        for partition, size in partition_sizes.items()
    ]
    exclusion_rows = [
        {"Motivo": str(reason), "Exclusiones": _copy_value(count)}
        for reason, count in exclusions.items()
    ]
    return {
        "data.states": _frame_from_records(states, ("Estado", "Observaciones")),
        "data.partitions": _frame_from_records(
            partitions,
            ("Partición", "Observaciones", "Tasa de incumplimiento"),
        ),
        "data.exclusions": _frame_from_records(exclusion_rows, ("Motivo", "Exclusiones")),
    }


def _atomic_result_tables(results: Mapping[str, Any]) -> dict[str, DataFrameLike]:
    """Copia los frames de las familias corridas desde un único ``ValidationResult``."""
    result = results.get("validation")
    if result is None:
        return {}
    card = getattr(result, "card", None)
    raw_families = getattr(card, "families_run", ())
    families = {str(item) for item in raw_families}
    tables: dict[str, DataFrameLike] = {}
    for family, _ in VALIDATION_FAMILIES:
        if family not in families:
            continue
        frame = getattr(result, family, None)
        if not _is_dataframe_like(frame):
            raise ReportInputError(
                f"validation.result.{family} debe ser un DataFrame del DTO atómico."
            )
        tables[f"validation.{family}"] = cast(DataFrameLike, _copy_value(frame))
    return tables


#: Los encabezados de la tabla por grupo del Hosmer-Lemeshow en el informe (D-HLG-2). Las tasas van
#: en porcentaje, como la frase del resumen que las cita («45,56 % observado frente a 42,14 %
#: predicho»), y la diferencia en puntos porcentuales.
_HL_GROUP_REPORT_COLUMNS: Final[tuple[str, ...]] = (
    "Grupo",
    "Observaciones",
    "Malos observados",
    "Malos esperados",
    "Tasa observada (%)",
    "PD media (%)",
    "Diferencia (pp)",
    "O/E",
    "Contribución al estadístico",
)


def _hl_group_tables(study: Study, results: Mapping[str, Any]) -> dict[str, DataFrameLike]:
    """Una tabla por muestra con los grupos del Hosmer-Lemeshow, para la subsección de calibración.

    D-HLG-2: lee ``("validation", "hosmer_lemeshow_groups")`` —la publica el mismo paso que
    ``validation.result``, fuera del DTO para que éste no cambie— y la coteja con el resultado
    atómico: cada muestra tiene que tener su Hosmer-Lemeshow con estadístico en
    ``validation.result.calibration`` y la suma de sus contribuciones tiene que reproducirlo. Si no,
    el informe rechaza la lectura, como rechaza una card que no casa con su resultado. Una corrida
    guardada antes de la clave, o sin ninguna muestra con veredicto, no suma tablas.
    """
    if not study.artifacts.has("validation", "hosmer_lemeshow_groups"):
        return {}
    grupos = study.artifacts.get("validation", "hosmer_lemeshow_groups")
    if not _is_dataframe_like(grupos) or bool(getattr(grupos, "empty", True)):
        return {}
    result = results.get("validation")
    calibracion = getattr(result, "calibration", None)
    if not _is_dataframe_like(calibracion):
        raise ReportInputError(
            "validation.hosmer_lemeshow_groups exige su validation.result; el reporte rechaza una "
            "lectura no atómica de la validación."
        )
    estadisticos: dict[str, float] = {}
    for fila in cast(Any, calibracion).to_dict("records"):
        valor = fila.get("statistic")
        if (
            fila.get("test") == "hosmer_lemeshow"
            and isinstance(valor, int | float)
            and math.isfinite(float(valor))
        ):
            estadisticos[str(fila.get("partition"))] = float(valor)
    tablas: dict[str, DataFrameLike] = {}
    for muestra, filas in grupos.groupby("partition", sort=False):
        nombre = str(muestra)
        suma = float(filas["contribution"].sum())
        estadistico = estadisticos.get(nombre)
        if estadistico is None or not math.isclose(suma, estadistico, rel_tol=1e-9, abs_tol=1e-12):
            raise ReportInputError(
                f"validation.hosmer_lemeshow_groups de «{nombre}» no reproduce el Hosmer-Lemeshow "
                "de validation.result; el reporte rechaza una lectura no atómica de la validación."
            )
        registros = [
            {
                "Grupo": int(fila["group"]),
                "Observaciones": int(fila["n"]),
                "Malos observados": int(fila["observed_defaults"]),
                "Malos esperados": round(float(fila["expected_defaults"]), 1),
                "Tasa observada (%)": round(100.0 * float(fila["observed_dr"]), 2),
                "PD media (%)": round(100.0 * float(fila["mean_pd"]), 2),
                "Diferencia (pp)": round(float(fila["gap_pp"]), 2),
                "O/E": round(float(fila["oe_ratio"]), 3),
                "Contribución al estadístico": round(float(fila["contribution"]), 2),
            }
            for fila in filas.sort_values("group", kind="stable").to_dict("records")
        ]
        tablas[f"{HL_GROUP_TABLE_PREFIX}{nombre}"] = _frame_from_records(
            registros, _HL_GROUP_REPORT_COLUMNS
        )
    return tablas


def _escenarios_y_pd_del_modelo(
    study: Study,
) -> tuple[dict[str, tuple[str, ...]], dict[str, DataFrameLike]]:
    """El cuerpo y las tablas de «Escenarios y ajuste por ciclo» y de «La PD de tu modelo…».

    Los arma :func:`bayesrisk.guided.summaries.ifrs9_report_extras` (import perezoso: arrastra los
    mapas de rótulos de los dominios): las mismas líneas, alertas y tablas que los resúmenes de
    etapa, ya escritas. El informe no recalcula nada. Las alertas se dicen como «Qué revisar». Sin
    escenarios ni las dos PD, nada: el capítulo es el de siempre.
    """
    if not study.artifacts.has("provisioning_ifrs9", "card"):
        return {}, {}
    from bayesrisk.guided.summaries import ifrs9_report_extras

    pd = importlib.import_module("pandas")
    cuerpos: dict[str, tuple[str, ...]] = {}
    tablas: dict[str, DataFrameLike] = {}
    for seccion, contenido in ifrs9_report_extras(study).items():
        cuerpos[seccion] = (
            *(f"{linea}." for linea in contenido["lines"]),
            *(f"Qué revisar: {alerta}." for alerta in contenido["alerts"]),
        )
        for clave, columnas, filas in contenido["tables"]:
            tablas[clave] = cast(DataFrameLike, pd.DataFrame(filas, columns=columnas))
    return cuerpos, tablas


def _curva_de_pd_por_cartera(study: Study) -> dict[str, DataFrameLike]:
    """La PD acumulada por período y cartera de la curva, para el capítulo IFRS 9 (D-ECL-12).

    La arma la MISMA función que la tabla adicional de la etapa «Curva de PD» del resumen
    (:func:`bayesrisk.guided.summaries.pd_curve_by_portfolio`, import perezoso: arrastra los
    mapas de rótulos de los dominios): el informe no recalcula la curva, la publica como la lee la
    persona en la puerta, la pantalla y el Excel. Sin curva —survival no corrió, o publicó otra
    forma—, no hay tabla y la subsección no la anuncia.
    """
    if not study.artifacts.has("survival", "term_structure"):
        return {}
    from bayesrisk.guided.summaries import pd_curve_by_portfolio

    tabla = pd_curve_by_portfolio(study)
    if tabla is None or tabla.empty:
        return {}
    return {SURVIVAL_PD_BY_PERIOD_TABLE: tabla}


def _required_mapping(
    card: Mapping[str, Any],
    key: str,
    *,
    artifact: str,
) -> Mapping[Any, Any]:
    value = card.get(key)
    if not isinstance(value, Mapping):
        raise ReportInputError(f"{artifact}.{key} debe ser un mapping literal.")
    return value


def _frame_from_records(
    records: list[dict[str, Any]],
    columns: tuple[str, ...],
) -> DataFrameLike:
    """Construye una tabla de presentación sin importar pandas al cargar ``bayesrisk.report``."""
    pd = importlib.import_module("pandas")
    return cast(DataFrameLike, pd.DataFrame.from_records(records, columns=columns))


def _collect_pipeline_params(study: Study) -> dict[str, Any]:
    """Snapshot JSON de las secciones de config de cada dominio realmente configurado.

    Es lo que permite a la Metodología describir el binning, la selección o la calibración con sus
    parámetros reales. Un dominio sin config no aparece: la prosa omite lo que no puede afirmar.
    """
    config = getattr(study, "config", None)
    if config is None:
        return {}
    params: dict[str, Any] = {}
    for domain in _PARAM_DOMAINS:
        section = getattr(config, domain, None)
        if section is None:
            continue
        if isinstance(section, BaseModel):
            params[domain] = _copy_mapping(cast(Mapping[Any, Any], section.model_dump(mode="json")))
        elif isinstance(section, Mapping):
            params[domain] = _copy_mapping(section)
    return params


def _lineage_from_study(study: Study) -> LineageBundle:
    lineage = getattr(getattr(study, "run_context", None), "lineage", None)
    if lineage is None:
        try:
            lineage = study.lineage_bundle()
        except Exception as exc:
            raise ReportInputError(
                "El reporte requiere LineageBundle disponible en el Study; ejecute la corrida "
                "o inyecte run_context.lineage antes de construir el bundle."
            ) from exc
    return cast(LineageBundle, _copy_value(lineage))


def _titulo_card(bundle: ReportInputBundle, domain: str) -> Mapping[str, Any] | None:
    """La card del dominio, si está, para que el título pueda depender de lo configurado (D-MAX-2).

    Devuelve ``None`` cuando el dominio no publicó card —sección ausente o pipeline parcial—, y eso
    es lo correcto: sin el dato, el título no afirma nada que no pueda sostener.
    """
    card = bundle.cards.get(domain)
    if card is None:
        return None
    return _card_to_mapping(card, f"{domain}.card")


def _card_to_mapping(value: Any, artifact: str) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return _copy_mapping(cast(Mapping[Any, Any], value.model_dump(mode="python")))
    if isinstance(value, Mapping):
        return _copy_mapping(value)
    raise ReportInputError(
        f"La card '{artifact}' debe ser un BaseModel o mapping serializable; "
        f"tipo observado={type(value).__name__}."
    )


def _payload_and_metric_sections(
    raw_card: Mapping[str, Any],
    *,
    artifact: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_metric_sections = raw_card.get("metric_sections", {})
    if raw_metric_sections is None:
        metric_sections: dict[str, Any] = {}
    elif isinstance(raw_metric_sections, Mapping):
        metric_sections = _copy_mapping(raw_metric_sections)
    else:
        raise ReportInputError(
            f"metric_sections de '{artifact}' debe ser un mapping JSON-serializable."
        )
    _validate_metric_sections(metric_sections, artifact=artifact)
    payload = {
        key: _payload_value(value, prefix=f"{artifact}.{key}")
        for key, value in raw_card.items()
        if key != "metric_sections"
    }
    return payload, metric_sections


def _validate_metric_sections(metric_sections: Mapping[str, Any], *, artifact: str) -> None:
    try:
        json.dumps(
            metric_sections,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=_raise_not_json_serializable,
        )
    except (TypeError, ValueError) as exc:
        raise ReportInputError(
            f"metric_sections de '{artifact}' no es JSON-serializable; "
            "publique métricas estructuradas sin objetos Python opacos ni floats no finitos."
        ) from exc


def _raise_not_json_serializable(value: object) -> NoReturn:
    raise TypeError(f"{type(value).__name__} no es JSON-serializable")


def _perfiles_numericos(study: Study) -> tuple[str, ...]:
    """Las columnas que el EDA perfiló como numéricas; vacío sin perfiles (D-PAN-4)."""
    if not study.artifacts.has("eda", "univariate"):
        return ()
    univariate = study.artifacts.get("eda", "univariate")
    return tuple(str(columna) for columna in getattr(univariate, "numeric_profiles", ()))


def _rotulos_de_tramos(study: Study) -> dict[str, list[str]]:
    """El rótulo legible de cada tramo de cada variable tramificada (D-CPY-3)."""
    if not study.artifacts.has("binning", "tables"):
        return {}
    from bayesrisk.core.tramos import rotulos_por_fila

    tablas = study.artifacts.get("binning", "tables")
    bordes = (
        study.artifacts.get("binning", "bin_edges")
        if study.artifacts.has("binning", "bin_edges")
        else None
    )
    if not isinstance(tablas, Mapping):
        return {}
    return {
        str(variable): rotulos_por_fila(tabla, bordes, str(variable))
        for variable, tabla in tablas.items()
        if _is_dataframe_like(tabla)
    }


def _referencias_no_vistas(study: Study) -> dict[str, int]:
    """Por categórica del modelo, el ``bin_index`` de la fila de puntos de su tramo de referencia.

    La misma búsqueda del escalador con que el bundle congela la referencia (D-NOV-1 §1.1). Vacío
    sin tabla de puntos o con un binning ajustado antes de D-NOV.
    """
    if not (
        study.artifacts.has("scorecard", "scorecard") and study.artifacts.has("binning", "process")
    ):
        return {}
    referencias = getattr(study.artifacts.get("binning", "process"), "unseen_reference_", None)
    tarjeta = study.artifacts.get("scorecard", "scorecard")
    if not referencias or not _is_dataframe_like(tarjeta):
        return {}
    from bayesrisk.scorecard.scaler import filas_de_referencia_no_vista

    return {
        variable: int(cast(int, fila["bin_index"]))
        for variable, fila in filas_de_referencia_no_vista(tarjeta, referencias).items()
    }


def _extract_dataframes(value: Any, prefix: str) -> dict[str, DataFrameLike]:
    if _is_dataframe_like(value):
        return {prefix: cast(DataFrameLike, _copy_value(value))}
    if isinstance(value, BaseModel):
        return _extract_dataframes(value.model_dump(mode="python"), prefix)
    if isinstance(value, Mapping):
        frames: dict[str, DataFrameLike] = {}
        for raw_key in sorted(value, key=str):
            frames.update(_extract_dataframes(value[raw_key], f"{prefix}.{raw_key}"))
        return frames
    return {}


def _extract_card_dataframes(cards: Mapping[str, Mapping[str, Any]]) -> dict[str, DataFrameLike]:
    frames: dict[str, DataFrameLike] = {}
    for domain, raw_card in cards.items():
        frames.update(_extract_dataframes(raw_card, f"{domain}.{_CARD_KEY_BY_DOMAIN[domain]}"))
    return frames


def _copy_mapping(value: Mapping[Any, Any]) -> dict[str, Any]:
    return {str(key): _copy_value(item) for key, item in value.items()}


def _payload_value(value: Any, *, prefix: str) -> Any:
    if _is_dataframe_like(value):
        return {"table_ref": prefix}
    if isinstance(value, BaseModel):
        return _payload_value(value.model_dump(mode="python"), prefix=prefix)
    if isinstance(value, Mapping):
        return {
            str(key): _payload_value(item, prefix=f"{prefix}.{key}") for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _payload_value(item, prefix=f"{prefix}.{index}") for index, item in enumerate(value)
        ]
    if isinstance(value, tuple):
        return tuple(
            _payload_value(item, prefix=f"{prefix}.{index}") for index, item in enumerate(value)
        )
    return _copy_value(value)


def _copy_value(value: Any) -> Any:
    if _is_dataframe_like(value):
        return value.copy(deep=True)
    if isinstance(value, BaseModel):
        return value.model_copy(deep=True)
    if isinstance(value, Mapping):
        return {copy.deepcopy(key): _copy_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_copy_value(item) for item in value)
    return copy.deepcopy(value)


def _is_dataframe_like(value: object) -> bool:
    return all(hasattr(value, attribute) for attribute in ("columns", "copy", "select_dtypes"))


def _output_format_from_path(path: str, config: ReportConfig) -> ReportOutputFormat:
    """Deriva el formato del manifest desde la extensión del archivo, con respaldo en el config.

    ``.qmd`` es la extensión de Quarto, pero el formato lógico del manifiesto es ``md``: el archivo
    es Markdown, la extensión sólo dice qué herramienta lo compila.
    """
    suffix = _SUFFIX_ALIASES.get(
        Path(path).suffix.lower().lstrip("."), Path(path).suffix.lower().lstrip(".")
    )
    if suffix in _VALID_OUTPUT_FORMATS:
        return cast(ReportOutputFormat, suffix)
    return config.formats[0] if config.formats else "html"
