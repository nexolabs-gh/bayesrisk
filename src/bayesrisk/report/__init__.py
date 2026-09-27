"""Capa ``report`` de bayesrisk: reportes auditables de scorecard (SDD-26).

Al importarse, registra :class:`ReportConfig` en el hook diferido de
:mod:`bayesrisk.core.config.schema`. Así ``BayesRiskConfig.report`` se valida como sub-config real
sin que ``import bayesrisk.core`` arrastre ``bayesrisk.report`` ni dependencias de render/IA. El
paquete importa ``report.step`` al final para ejecutar ``@register("standard", domain="report")``
sin cargar Jinja2, WeasyPrint ni SDKs IA; los DTOs y componentes pesados se reexportan de forma
perezosa.

**Estable (SemVer 2.x).**
"""

from __future__ import annotations

import importlib
from typing import Any, Final

from bayesrisk.core.config import schema as _schema
from bayesrisk.report.config import (
    AiNarrationConfig,
    DocumentStructureConfig,
    HtmlRenderConfig,
    PdfRenderConfig,
    ReportConfig,
    SectionPolicyConfig,
)
from bayesrisk.report.exceptions import (
    ReportAIError,
    ReportDependencyError,
    ReportError,
    ReportExportError,
    ReportInputError,
    ReportRenderError,
)

# Registra la clase real del sub-config report en el hook de `core`.
_schema._REPORT_CONFIG_CLS = ReportConfig

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "AIClient": ("bayesrisk.report.ai", "AIClient"),
    "AINarrator": ("bayesrisk.report.ai", "AINarrator"),
    "AIRequest": ("bayesrisk.report.ai", "AIRequest"),
    "AIResponse": ("bayesrisk.report.ai", "AIResponse"),
    "AiNarrationBlock": ("bayesrisk.report.results", "AiNarrationBlock"),
    "ReportBuilder": ("bayesrisk.report.builder", "ReportBuilder"),
    "HtmlReportRenderer": ("bayesrisk.report.renderer", "HtmlReportRenderer"),
    "PdfReportRenderer": ("bayesrisk.report.renderer", "PdfReportRenderer"),
    "PlaceholderBlock": ("bayesrisk.report.results", "PlaceholderBlock"),
    "ReportInputBundle": ("bayesrisk.report.results", "ReportInputBundle"),
    "ReportManifest": ("bayesrisk.report.results", "ReportManifest"),
    "ReportResult": ("bayesrisk.report.results", "ReportResult"),
    "ReportSection": ("bayesrisk.report.results", "ReportSection"),
    "ReportStep": ("bayesrisk.report.step", "ReportStep"),
    "RuleBasedNarrator": ("bayesrisk.report.ai", "RuleBasedNarrator"),
    "render_pdf": ("bayesrisk.report.pdf", "render_pdf"),
}

__all__ = [
    "AIClient",
    "AINarrator",
    "AIRequest",
    "AIResponse",
    "AiNarrationBlock",
    "AiNarrationConfig",
    "DocumentStructureConfig",
    "HtmlRenderConfig",
    "HtmlReportRenderer",
    "PdfRenderConfig",
    "PdfReportRenderer",
    "PlaceholderBlock",
    "ReportAIError",
    "ReportBuilder",
    "ReportConfig",
    "ReportDependencyError",
    "ReportError",
    "ReportExportError",
    "ReportInputBundle",
    "ReportInputError",
    "ReportManifest",
    "ReportRenderError",
    "ReportResult",
    "ReportSection",
    "ReportStep",
    "RuleBasedNarrator",
    "SectionPolicyConfig",
    "render_pdf",
]

# Import perezoso a nivel paquete para ejecutar @register("standard", domain="report") al importar
# `bayesrisk.report`, sin contaminar `import bayesrisk.core` ni cargar Jinja2/WeasyPrint/SDKs IA.
importlib.import_module("bayesrisk.report.step")


def __getattr__(name: str) -> Any:
    """Carga DTOs de ``report`` bajo demanda para preservar el import liviano."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'bayesrisk.report' has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(importlib.import_module(module_name), attribute_name)
    globals()[name] = value
    return value
