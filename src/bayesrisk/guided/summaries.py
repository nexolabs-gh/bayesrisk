"""Resúmenes por etapa y resumen final de la puerta guiada (D-FLU-2, D-FLU-4; D-SIM-5).

Una sola fuente para texto, ``_repr_html_`` y —en la capa B— pantalla: cada resumen se arma
**sólo** con lo que su etapa o una anterior ya publicó en el ``ArtifactStore`` (las cards, las
tablas estables y los dos diagnósticos aditivos de §3.6), y todas las palabras que lee una
persona salen de los mapas de rótulos que ya existen —``report.prose``, ``validation.results``,
``stability.results``, ``selection.results``, ``binning.results``, ``eda``—. Aquí no hay una
segunda aritmética: se cuenta, se enumera y se formatea.

Los identificadores del motor (``low_iv``, ``dev_vs_oot``, ``hosmer_lemeshow``, los códigos de
aviso) no llegan a estas frases: lo gatea ``tests/unit/test_guided_summaries.py`` con el mismo
criterio que el informe (``test_report_codigos_internos``).
"""

from __future__ import annotations

import html
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal

import numpy as np
import pandas as pd

from bayesrisk.binning.results import IV_BAND_LABELS
from bayesrisk.core.decisions import REGLA_DECISION_HUMANA, REGLA_DECISION_SIN_EFECTO
from bayesrisk.core.time_units import year_fraction
from bayesrisk.core.tramos import (
    es_fila_de_totales,
    filas_que_casan,
    rotulo_de_no_vistas,
    rotulos_por_fila,
)
from bayesrisk.eda.card import FAILED_ANALYSIS_LABELS, failed_analysis_sentence
from bayesrisk.eda.default_rate import (
    AXIS_LABELS,
    DEFAULT_RATE_NOT_EVALUABLE_REASON_LABELS,
)
from bayesrisk.eda.quality import QUALITY_FLAG_LABELS
from bayesrisk.eda.stability import NOT_EVALUABLE_REASON_LABELS, STABILITY_INDICATOR_LABELS
from bayesrisk.report.cifras import (
    cifra,
    corte_porcentual,
    es_columna_de_conteo,
    frente_al_corte,
    pvalor,
)
from bayesrisk.report.document import RESULT_DOMAINS
from bayesrisk.report.prose import (
    _ANCHOR_KINDS,
    _ANCHOR_SOURCES,
    _CALIBRATION_METHODS,
    _COMPARISON_LABELS,
    _DECLARED_WARNING_PROSE,
    _DISCRIMINANT_BANDS,
    _IFRS9_PIT_MODE_LABELS,
    _MONOTONIC_LABELS,
    _PARTITION_LABELS,
    _STEPWISE_DIRECTIONS,
    _cifra,
    _cut,
    _declared_warning_descriptions,
    _enumerar,
    _miles,
    _pct,
    _plural,
)
from bayesrisk.selection.results import REASON_LABELS
from bayesrisk.stability.results import (
    BAND_LABELS,
    PSI_METRIC_LABELS,
    STABILITY_METRIC_LABELS,
    TEMPORAL_AXIS_LABELS,
)
from bayesrisk.validation.results import (
    CALIBRATION_TEST_LABELS,
    HL_NOT_EVALUABLE_REASON_LABELS,
    VALIDATION_DECISION_LABELS,
    VALIDATION_FAMILY_LABELS,
    VALIDATION_STATUS_LABELS,
)

if TYPE_CHECKING:
    from bayesrisk.core.study import Study

__all__ = [
    "RESUMEN_FINAL_ROTULOS",
    "SIN_ALERTAS",
    "SIN_DECISIONES",
    "STAGE_LABELS",
    "STAGE_LABELS_CARTERA",
    "STAGE_ORDER",
    "FinalSummary",
    "StageSummary",
    "SummaryContext",
    "TablaDeEtapa",
    "build_final_summary",
    "build_stage_summaries",
    "build_stage_summary",
    "decision_line",
    "decision_lines_from_preamble",
    "family_of",
    "partition_label",
    "partition_label_from_config",
    "source_label_from_config",
    "stage_labels",
    "time_unit_words",
]

#: Rótulo en español de cada etapa, en el orden del pipeline (D-FLU-2 §3.2). Los nombres son los
#: de las secciones del config y de los pasos; los rótulos, lo que lee una persona (D-SIM-9).
STAGE_LABELS: Final[dict[str, str]] = {
    "data": "Datos y muestras",
    "eda": "Análisis exploratorio",
    "binning": "Tramos y WoE",
    "selection": "Selección de variables",
    "model": "Modelo",
    "scorecard": "Tarjeta de puntuación",
    "calibration": "Calibración",
    "performance": "Desempeño",
    "stability": "Estabilidad",
    "validation": "Validación formal",
    "report": "Informe y ficha",
}
STAGE_ORDER: Final[tuple[str, ...]] = tuple(STAGE_LABELS)

#: Rótulos de la familia de cartera (FLUJO-GUIADO-IFRS9 D-ECL-7): una corrida que provisiona IFRS 9
#: sin dominios del scorecard habla con estas etapas, venga de ``bayesrisk.Ecl``, de un YAML o de la
#: pantalla —también la del preset F4, que conserva su target inerte—. Sin «malos» ni muestras: la
#: provisión no los usa.
STAGE_LABELS_CARTERA: Final[dict[str, str]] = {
    "data": "Cartera",
    "survival": "Curva de PD",
    "provisioning_ifrs9": "Provisión IFRS 9",
    "report": "Informe y ficha",
}
_FAMILIAS: Final[dict[str, dict[str, str]]] = {
    "scorecard": STAGE_LABELS,
    "cartera": STAGE_LABELS_CARTERA,
}
#: El título del resumen final de cada familia (deja de estar fijo en «Resumen del scorecard»).
_TITULOS: Final[dict[str, str]] = {
    "scorecard": "Resumen del scorecard",
    "cartera": "Resumen de la provisión IFRS 9",
}
#: Lo que dice el estado técnico de una provisión, que no tiene veredicto técnico: en su lugar, el
#: resumen final lista lo que la cifra supone («Supuestos»). Viaja en ``FinalSummary.validation``
#: para los consumidores que todavía leen ese campo (la pantalla, hasta la capa B).
SIN_VEREDICTO_TECNICO: Final = (
    "no aplica: una provisión no tiene veredicto técnico; lo que la cifra supone está en "
    "«Supuestos»"
)
#: Nombre de cada unidad temporal de :mod:`bayesrisk.core.time_units`, por su fracción de año:
#: singular y plural, para decir «5 años» o «12 meses» en vez del literal que trae el config.
_UNIDADES_EN_PALABRAS: Final[dict[float, tuple[str, str]]] = {
    1.0: ("año", "años"),
    0.5: ("semestre", "semestres"),
    0.25: ("trimestre", "trimestres"),
    1.0 / 12.0: ("mes", "meses"),
    1.0 / 52.0: ("semana", "semanas"),
    1.0 / 365.0: ("día", "días"),
}


def stage_labels(family: str) -> Mapping[str, str]:
    """Los rótulos de las etapas de una familia de resúmenes, en el orden del pipeline."""
    return _FAMILIAS.get(family, STAGE_LABELS)


def family_of(config: Any) -> str:
    """La familia de resúmenes que decide el pipeline de la corrida (D-ECL-7).

    ``"cartera"`` si provisiona IFRS 9 y no corre ningún dominio del scorecard
    (``RESULT_DOMAINS``); si no, ``"scorecard"``. No la decide un argumento: la misma corrida
    habla igual por la puerta guiada, por su YAML y por la pantalla.
    """
    if config is None or getattr(config, "provisioning_ifrs9", None) is None:
        return "scorecard"
    if any(getattr(config, dominio, None) is not None for dominio in RESULT_DOMAINS):
        return "scorecard"
    return "cartera"


def time_unit_words(unit: Any, count: int) -> str | None:
    """«año»/«años», «mes»/«meses»…: la unidad en palabras, o ``None`` si no es convertible."""
    fraccion = year_fraction(str(unit)) if unit is not None else None
    if fraccion is None:
        return None
    par = _UNIDADES_EN_PALABRAS.get(fraccion)
    if par is None:
        return None
    return par[0] if count == 1 else par[1]


#: Filas de una tabla de decisión que el texto de consola muestra antes de resumir el resto; el
#: HTML del notebook y ``sc.results[<etapa>]`` llevan la tabla entera.
_FILAS_EN_CONSOLA: Final = 40

#: Lo que dice el resumen final sin decisiones humanas registradas. No afirma «valores de
#: fábrica»: una corrida sin ``exclude``/``keep``/``merge_bins``/``set_bins`` puede llevar
#: argumentos distintos de los de fábrica, y en la pantalla el config se editó a mano (pasada 2
#: de Codex sobre la capa B). Lo que se decidió vive en el config de la corrida, que es la verdad.
SIN_DECISIONES: Final = (
    "Ninguna decisión humana registrada; lo que se decidió vive en el config de la corrida."
)
#: Lo que dice el resumen final cuando ninguna etapa levantó una alerta.
SIN_ALERTAS: Final = "Sin alertas en ninguna etapa."
#: Los rótulos de los bloques del resumen final: una sola fuente para la consola, el notebook y
#: la página ejecutiva del informe (D-FLU-4; capa C de FLUJO-GUIADO-SCORECARD).
RESUMEN_FINAL_ROTULOS: Final[dict[str, str]] = {
    "execution": "Ejecución",
    "validation": "Validación técnica",
    "figures": "Cifras clave",
    "review": "Qué revisar",
    "decisions": "Decisiones humanas registradas",
    "files": "Dónde quedó cada archivo",
}
#: La regla con que se firma una decisión humana en el trail (D-FLU-3), y la del registro que ya no
#: está aplicado (D-DEC-3): una sola fuente, la del módulo que las emite.
_REGLA_DECISION_HUMANA: Final = REGLA_DECISION_HUMANA
_REGLA_DECISION_SIN_EFECTO: Final = REGLA_DECISION_SIN_EFECTO
#: El rótulo de las alertas del registro de decisiones en «Qué revisar».
_ROTULO_DECISIONES: Final = "Decisiones con motivo"
#: El bloque que reemplaza a «Validación técnica» en el resumen final de una provisión (§3.8), y
#: la primera de sus cinco cifras, la que la consola repite al cerrar la corrida.
_ROTULO_SUPUESTOS: Final = "Supuestos"
_ROTULO_ECL_TOTAL: Final = "ECL total"

_Kind = Literal["text", "int", "num", "num2", "num3", "pct", "bool", "pvalor"]

#: Acciones del stepwise en palabras (``model.results.StepwiseDecision.action``).
_STEPWISE_ACTION_LABELS: Final[dict[str, str]] = {
    "enter": "entra",
    "remove": "sale",
    "keep": "se mantiene",
    "flag": "queda marcada",
    "exclude": "se excluye",
}
#: Criterios del stepwise y de las guardas de signo e IV en palabras.
_STEPWISE_CRITERION_LABELS: Final[dict[str, str]] = {
    "wald_pvalue": "p-valor de Wald",
    "lr_test": "test de razón de verosimilitud",
    "both": "p-valor de Wald y test de razón de verosimilitud",
    "sign": "signo del coeficiente",
    "iv_contribution": "contribución al IV",
    "force_include": "inclusión forzada",
    "force_exclude": "exclusión forzada",
}


@dataclass(frozen=True, slots=True)
class SummaryContext:
    """Lo que la puerta sabe y el ``Study`` no: rutas, inferencias y decisiones humanas.

    ``project_dir`` y ``run_dir`` admiten ``None`` desde la capa C: el informe se renderiza como
    último paso de la corrida, antes de que ``bayesrisk.run`` consolide su destino, así que no
    conoce la carpeta final de la evidencia y no la inventa. ``extra_files`` es lo que quien
    arma el contexto sabe de sus propios archivos y el ``Study`` todavía no publica (el informe,
    de sí mismo).
    """

    project_dir: Path | None
    run_dir: Path | None
    source_label: str
    partition_label: str
    inference_lines: tuple[str, ...] = ()
    decision_lines: tuple[str, ...] = ()
    report_dir: Path | None = None
    trail_path: Path | None = None
    card_path: Path | None = None
    config_path: Path | None = None
    until: str | None = None
    extra_files: tuple[tuple[str, str], ...] = ()
    #: Etapas del pipeline que todavía NO habían corrido al armar el resumen: el informe se
    #: renderiza en medio de la corrida y `run.steps` puede poner pasos después de él (pasada 1
    #: de Codex sobre C1). Con ellas el resumen no afirma que el informe cierra la corrida ni que
    #: una validación que viene después «no está en el config».
    pending_stages: tuple[str, ...] = ()
    #: La familia de resúmenes cuando todavía no hay ``Study`` del que leerla (un resumen pedido
    #: antes de correr). Con corrida, la decide su config (:func:`family_of`).
    family: str = "scorecard"


class TablaDeEtapa(pd.DataFrame):
    """Una tabla de decisión: números intactos para calcular, escritos como se leen al mostrarse.

    Es un ``DataFrame`` de verdad —filtrar, ordenar o exportar lo trata como a cualquier otro, y
    sus columnas numéricas siguen siendo números—, pero en el notebook y en la consola se ve con la
    misma regla del resumen de la etapa y de la pantalla (:func:`_formatear`): coma decimal, miles,
    porcentajes y «—» en las ausencias, sin el índice. Antes se veía cruda —``0.547746``, ``None``,
    ``NaN``— junto a un resumen que decía ``0,548`` (pedido de Cami, 2026-09-24).
    """

    _metadata: ClassVar[list[str]] = ["formats"]
    formats: dict[str, _Kind]

    @property
    def _constructor(self) -> type[TablaDeEtapa]:
        return TablaDeEtapa

    @classmethod
    def de(cls, tabla: pd.DataFrame, formats: Mapping[str, _Kind]) -> TablaDeEtapa:
        """La tabla, copiada, con la regla de formato de sus columnas."""
        salida = cls(tabla.copy())
        salida.formats = dict(formats)
        return salida

    def _vista(self) -> pd.DataFrame:
        return _formatear(pd.DataFrame(self), getattr(self, "formats", None) or {})

    def __repr__(self) -> str:
        """La tabla como se lee en la consola."""
        return self._vista().to_string(index=False, max_rows=pd.get_option("display.max_rows"))

    def _repr_html_(self) -> str:
        """La tabla como se lee en el notebook."""
        return self._vista().to_html(
            index=False, border=0, max_rows=pd.get_option("display.max_rows")
        )


@dataclass(frozen=True, slots=True)
class StageSummary:
    """El resumen de una etapa: de 3 a 8 líneas, sus alertas y su tabla de decisión (D-SIM-5)."""

    stage: str
    label: str
    lines: tuple[str, ...]
    alerts: tuple[str, ...] = ()
    table: pd.DataFrame | None = None
    formats: Mapping[str, _Kind] = field(default_factory=dict)
    #: Tablas que acompañan a la de decisión, cada una con su título y su regla de formato. Son
    #: aditivas (FLUJO-GUIADO-IFRS9 §3.8: la curva de PD se lee por cartera **y** por sus
    #: coeficientes); una etapa del scorecard no trae ninguna y se serializa exactamente igual,
    #: también en su ``repr`` (el cuaderno publicado lo muestra).
    extra_tables: tuple[tuple[str, pd.DataFrame, Mapping[str, _Kind]], ...] = field(
        default=(), repr=False
    )

    def text(self, *, with_table: bool = True) -> str:
        """El resumen como texto para la consola."""
        partes = [f"── {self.label} ──", *self.lines]
        partes.extend(f"⚠ {alerta}" for alerta in self.alerts)
        if with_table and self.table is not None and not self.table.empty:
            mostrada = _formatear(self.table, self.formats)
            partes.append(mostrada.head(_FILAS_EN_CONSOLA).to_string(index=False))
            resto = len(mostrada.index) - _FILAS_EN_CONSOLA
            if resto > 0:
                partes.append(
                    f"… y {_miles(resto)} {_plural(resto, 'fila más', 'filas más')} en "
                    f"sc.results[{self.stage!r}]"
                )
        if with_table:
            for titulo, tabla, formatos in self.extra_tables:
                if tabla.empty:
                    continue
                partes.append(f"{titulo}:")
                partes.append(_formatear(tabla, formatos).to_string(index=False))
        return "\n".join(partes)

    def __str__(self) -> str:
        """El texto del resumen."""
        return self.text()

    def _repr_html_(self) -> str:
        """El mismo resumen para el notebook."""
        partes = [f"<h3>{html.escape(self.label)}</h3>", "<ul>"]
        partes.extend(f"<li>{html.escape(linea)}</li>" for linea in self.lines)
        partes.append("</ul>")
        if self.alerts:
            partes.append("<ul>")
            partes.extend(f"<li>⚠ {html.escape(alerta)}</li>" for alerta in self.alerts)
            partes.append("</ul>")
        if self.table is not None and not self.table.empty:
            partes.append(_formatear(self.table, self.formats).to_html(index=False, border=0))
        for titulo, tabla, formatos in self.extra_tables:
            if tabla.empty:
                continue
            partes.append(f"<h4>{html.escape(titulo)}</h4>")
            partes.append(_formatear(tabla, formatos).to_html(index=False, border=0))
        return f'<div class="bayesrisk-summary">{"".join(partes)}</div>'

    def to_dict(self) -> dict[str, Any]:
        """El resumen como JSON transportable, con la tabla ya escrita como la lee una persona.

        Es lo que consume la pantalla (D-FLU-8: Resultados lee la misma fuente que
        ``summary()``): las celdas viajan formateadas por :func:`_formatear` —coma decimal,
        miles, «—» en las ausencias— para que el panel pinte exactamente lo que el notebook y la
        consola muestran, sin una segunda regla de formato en el front. Las tablas adicionales
        viajan en ``extra_tables`` sólo cuando la etapa las trae: un resumen sin ellas se
        serializa exactamente igual que antes de que existieran.
        """
        salida: dict[str, Any] = {
            "stage": self.stage,
            "label": self.label,
            "lines": list(self.lines),
            "alerts": list(self.alerts),
            "table": _tabla_transportable(self.table, self.formats),
        }
        extras = [
            {"title": titulo, **tabla_dict}
            for titulo, tabla, formatos in self.extra_tables
            if (tabla_dict := _tabla_transportable(tabla, formatos)) is not None
        ]
        if extras:
            salida["extra_tables"] = extras
        return salida


@dataclass(frozen=True, slots=True)
class FinalSummary:
    """El resumen final (D-FLU-4).

    Ejecución y validación técnica por separado, cinco cifras, qué revisar, decisiones y archivos.
    """

    execution: str
    validation: str
    figures: tuple[tuple[str, str], ...]
    review: tuple[str, ...]
    decisions: tuple[str, ...]
    files: tuple[tuple[str, str], ...]
    stages: tuple[StageSummary, ...] = ()
    #: El título del bloque, que depende de la familia (FLUJO-GUIADO-IFRS9 D-ECL-7). Los tres
    #: campos de la familia quedan fuera del ``repr``: el del scorecard es el de antes (el cuaderno
    #: publicado lo muestra), y el texto y el HTML ya los dicen.
    title: str = field(default=_TITULOS["scorecard"], repr=False)
    #: Lo que la cifra supone, leído del config y de los artefactos de la corrida: en la familia
    #: de cartera reemplaza a la validación técnica, que una provisión no tiene (§3.8).
    assumptions: tuple[str, ...] = field(default=(), repr=False)
    family: str = field(default="scorecard", repr=False)

    @property
    def _de_cartera(self) -> bool:
        return self.family == "cartera"

    def headline(self) -> tuple[str, ...]:
        """Las dos líneas con que la puerta cierra una corrida en la consola.

        El scorecard dice su ejecución y su validación técnica; una provisión, su ejecución y la
        cifra (la primera de sus cinco, la ECL total) con su cobertura.
        """
        r = RESUMEN_FINAL_ROTULOS
        if not self._de_cartera:
            return (f"{r['execution']}: {self.execution}", f"{r['validation']}: {self.validation}")
        cifras = dict(self.figures)
        segunda = tuple(
            f"{rotulo}: {cifras[rotulo]}" for rotulo in (_ROTULO_ECL_TOTAL,) if rotulo in cifras
        )
        return (f"{r['execution']}: {self.execution}", *segunda)

    def text(self) -> str:
        """El resumen final como texto para la consola."""
        r = RESUMEN_FINAL_ROTULOS
        partes = [f"══ {self.title} ══", f"{r['execution']}: {self.execution}"]
        if self._de_cartera:
            partes.append(f"{_ROTULO_SUPUESTOS}:")
            partes.extend(f"  • {supuesto}" for supuesto in self.assumptions)
        else:
            partes.append(f"{r['validation']}: {self.validation}")
        if self.figures:
            partes.append(f"{r['figures']}:")
            partes.extend(f"  {rotulo}: {valor}" for rotulo, valor in self.figures)
        partes.append(f"{r['review']}:")
        if self.review:
            partes.extend(f"  ⚠ {alerta}" for alerta in self.review)
        else:
            partes.append(f"  {SIN_ALERTAS}")
        partes.append(f"{r['decisions']}:")
        if self.decisions:
            partes.extend(f"  • {linea}" for linea in self.decisions)
        else:
            partes.append(f"  {SIN_DECISIONES}")
        partes.append(f"{r['files']}:")
        partes.extend(f"  {rotulo}: {ruta}" for rotulo, ruta in self.files)
        return "\n".join(partes)

    def __str__(self) -> str:
        """El texto del resumen final."""
        return self.text()

    def _repr_html_(self) -> str:
        """El mismo resumen final para el notebook."""
        r = RESUMEN_FINAL_ROTULOS
        partes = [f"<h2>{html.escape(self.title)}</h2>"]
        partes.append(f"<p><b>{r['execution']}:</b> {html.escape(self.execution)}</p>")
        if self._de_cartera:
            partes.append(f"<h4>{_ROTULO_SUPUESTOS}</h4><ul>")
            partes.extend(f"<li>{html.escape(supuesto)}</li>" for supuesto in self.assumptions)
            partes.append("</ul>")
        else:
            partes.append(f"<p><b>{r['validation']}:</b> {html.escape(self.validation)}</p>")
        if self.figures:
            partes.append("<table><tbody>")
            partes.extend(
                f"<tr><th>{html.escape(rotulo)}</th><td>{html.escape(valor)}</td></tr>"
                for rotulo, valor in self.figures
            )
            partes.append("</tbody></table>")
        partes.append(f"<h4>{r['review']}</h4><ul>")
        if self.review:
            partes.extend(f"<li>⚠ {html.escape(alerta)}</li>" for alerta in self.review)
        else:
            partes.append(f"<li>{SIN_ALERTAS}</li>")
        partes.append(f"</ul><h4>{r['decisions']}</h4><ul>")
        if self.decisions:
            partes.extend(f"<li>{html.escape(linea)}</li>" for linea in self.decisions)
        else:
            partes.append(f"<li>{html.escape(SIN_DECISIONES)}</li>")
        partes.append(f"</ul><h4>{r['files']}</h4><ul>")
        partes.extend(
            f"<li>{html.escape(rotulo)}: <code>{html.escape(ruta)}</code></li>"
            for rotulo, ruta in self.files
        )
        partes.append("</ul>")
        return f'<div class="bayesrisk-summary">{"".join(partes)}</div>'

    def to_dict(self) -> dict[str, Any]:
        """El resumen final como JSON transportable (los dos estados, cifras, alertas, archivos).

        Las etapas no viajan aquí: cada una se serializa con su propio :meth:`StageSummary.to_dict`.
        La familia de cartera agrega su título, su familia y sus supuestos; el scorecard se
        serializa exactamente igual que antes de que existieran.
        """
        salida: dict[str, Any] = {
            "execution": self.execution,
            "validation": self.validation,
            "figures": [[rotulo, valor] for rotulo, valor in self.figures],
            "review": list(self.review),
            "decisions": list(self.decisions),
            "files": [[rotulo, ruta] for rotulo, ruta in self.files],
        }
        if self._de_cartera:
            salida["title"] = self.title
            salida["family"] = self.family
            salida["assumptions"] = list(self.assumptions)
        return salida


def partition_label(strategy: Mapping[str, Any]) -> str:
    """Cómo se separa la muestra, en palabras, desde la estrategia de partición del config.

    Una sola fuente para la puerta guiada (que la construye con sus argumentos) y para la pantalla
    (que la lee del config de la corrida): el resumen de «Datos y muestras» dice lo mismo por las
    dos puertas.
    """
    tipo = str(strategy.get("type", ""))
    holdout = _float(strategy.get("holdout_fraction"))
    resto = f"; holdout {_pct(holdout, decimals=0)} del resto" if holdout is not None else ""
    if tipo == "temporal":
        crudo = strategy.get("oot_from")
        frontera = pd.to_datetime(str(crudo), errors="coerce") if crudo is not None else None
        desde = frontera.date().isoformat() if isinstance(frontera, pd.Timestamp) else str(crudo)
        return f"fuera de tiempo desde {desde} por «{strategy.get('date_col')}»{resto}"
    if tipo == "cohort":
        reservadas = ", ".join(str(c) for c in _sequence(strategy.get("oot_cohorts")))
        return (
            f"cohortes fuera de tiempo: {reservadas} (columna «{strategy.get('cohort_col')}»)"
            f"{resto}"
        )
    if tipo == "random":
        dev = _float(strategy.get("dev_fraction"))
        oot = _float(strategy.get("oot_fraction")) or 0.0
        fuera = (
            f"y {_pct(oot, decimals=0)} fuera de tiempo (pseudo-OOT)"
            if oot > 0
            else "sin muestra fuera de tiempo"
        )
        return (
            f"partición aleatoria: {_pct(dev, decimals=0)} desarrollo y "
            f"{_pct(holdout, decimals=0)} holdout, {fuera}"
        )
    if tipo == "columna":
        return f"división ya marcada en la columna «{strategy.get('partition_col')}»"
    return f"estrategia de partición «{tipo}»" if tipo else "estrategia de partición no declarada"


def partition_label_from_config(config: Any) -> str:
    """:func:`partition_label` leído del config de una corrida (``data.partition.strategy``).

    Es lo que arman la pantalla y el informe, que no conocen los argumentos de la puerta guiada:
    con ellos el resumen de «Datos y muestras» dice lo mismo por las tres puertas. Sin sección
    ``data`` o sin estrategia devuelve vacío: no afirma una partición que el config no declara.
    """
    data = getattr(config, "data", None)
    partition = getattr(data, "partition", None)
    strategy = getattr(partition, "strategy", None)
    if strategy is None:
        return ""
    dump = getattr(strategy, "model_dump", None)
    volcado = dump(mode="python") if callable(dump) else strategy
    return partition_label(volcado) if isinstance(volcado, Mapping) else ""


def source_label_from_config(config: Any) -> str:
    """Cómo nombrar los datos sin la puerta guiada: la fuente que el config declara.

    Misma fuente para la pantalla (sin ``dataset_id``) y para el informe; sin ``data.load.source``
    dice «datos de la corrida», no una ruta inventada.
    """
    load = getattr(getattr(config, "data", None), "load", None)
    source = getattr(load, "source", None)
    return str(source) if source else "datos de la corrida"


def decision_line(payload: Mapping[str, Any]) -> str:
    """Una decisión humana en una línea: ``<acción> <variables> — «<motivo>»``.

    Única fuente para el resumen final de la puerta guiada (que la arma con sus decisiones en
    memoria) y para la página ejecutiva del informe (que la lee del preámbulo que ``Study``
    conserva): las dos escriben la misma línea desde el mismo payload, el del evento
    ``decision`` del trail (D-FLU-3).
    """
    variables = ", ".join(str(v) for v in _sequence(payload.get("variables")))
    accion = str(payload.get("accion", ""))
    motivo = str(payload.get("motivo", ""))
    sujeto = f"{accion} {variables}" if variables else accion
    if accion == "rebut_backstops":
        # El sujeto es la columna de mora; lo que se decidió son los días (FLUJO-GUIADO-IFRS9 §3.9).
        dias = _dias_de_mora(payload.get("valor"))
        if dias:
            sujeto += f" ({dias})"
    return f"{sujeto} — «{motivo}»"


def _dias_de_mora(valor: Any) -> str:
    """«Stage 2 desde 60 días de mora y Stage 3 desde 90 días de mora», desde la huella."""
    huella = _mapping(valor)
    partes = [
        f"{etapa} desde {huella[hoja]} días de mora"
        for hoja, etapa in (
            ("provisioning_ifrs9.staging.dpd_sicr_backstop", "Stage 2"),
            ("provisioning_ifrs9.staging.dpd_default_backstop", "Stage 3"),
        )
        if hoja in huella
    ]
    return _enumerar(partes)


def decision_lines_from_preamble(
    preamble: Iterable[tuple[str | None, Mapping[str, Any]]],
) -> tuple[str, ...]:
    """Las decisiones humanas declaradas en el preámbulo de una corrida, en líneas.

    Sólo las que la puerta guiada firma como del usuario (``decision_del_usuario``); las
    inferencias de la puerta y las reglas del motor no son decisiones humanas.
    """
    return tuple(
        decision_line(payload)
        for _paso, payload in preamble
        if str(payload.get("regla", "")) == _REGLA_DECISION_HUMANA
    )


# ────────────────────────────── resúmenes por etapa ──────────────────────────────


def build_stage_summaries(study: Study, context: SummaryContext) -> tuple[StageSummary, ...]:
    """Los resúmenes de las etapas que dejaron artefactos, en el orden del pipeline.

    Una corrida parcial o fallida conserva los de lo que sí corrió; el informe, que se renderiza
    como último paso, no encuentra todavía el suyo. Una etapa que no se pueda armar levanta: quien
    llama decide si es un fallo de la corrida (la puerta guiada) o un hueco que se declara (la
    pantalla y el informe).
    """
    dominios = {dominio for dominio, _clave in study.artifacts.keys()}  # noqa: SIM118
    orden = tuple(stage_labels(family_of(getattr(study, "config", None))))
    return tuple(build_stage_summary(stage, study, context) for stage in orden if stage in dominios)


def build_stage_summary(stage: str, study: Study, context: SummaryContext) -> StageSummary:
    """Arma el resumen de ``stage`` con lo que el ``Study`` ya publicó, en la voz de su familia."""
    familia = family_of(getattr(study, "config", None))
    builder = (_BUILDERS_CARTERA if familia == "cartera" else _BUILDERS).get(stage)
    label = stage_labels(familia).get(stage, stage)
    if builder is None:
        return StageSummary(stage=stage, label=label, lines=("Etapa sin resumen propio.",))
    return builder(study, context)


def _resumen_data(study: Study, context: SummaryContext) -> StageSummary:
    card = _card(study, "data", "data_card")
    lines: list[str] = [f"Archivo: {context.source_label}"]
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    if card is not None and card.get("target_col") is None:
        # D-ECL-2: corrida de cartera. Sin target ni partición no hay malos ni muestras que contar,
        # y «0 malos» sería falso: no aplica.
        lines.append(
            f"{_miles(_int(card.get('n_rows')) or 0)} filas · "
            f"{_miles(_int(card.get('n_features')) or 0)} columnas"
        )
    elif card is not None:
        n_rows = _int(card.get("n_rows")) or 0
        class_counts = _mapping(card.get("class_counts"))
        n_bad = _int(class_counts.get("malo")) or 0
        lines.append(
            f"{_miles(n_rows)} filas · {_miles(n_bad)} malos "
            f"({_pct(card.get('bad_rate'))}) · {_miles(_int(card.get('n_features')) or 0)} columnas"
        )
        sizes = _mapping(card.get("partition_sizes"))
        rates = _mapping(card.get("partition_bad_rates"))
        muestras = tuple(
            f"{_partition_label(str(p))} {_miles(_int(n) or 0)} ({_pct(rates.get(p))})"
            for p, n in sizes.items()
            if str(p) != "fuera_de_modelo" and (_int(n) or 0) > 0
        )
        if muestras:
            lines.append(f"Muestras: {' · '.join(muestras)} — {context.partition_label}")
        fuera = _int(sizes.get("fuera_de_modelo")) or 0
        indeterminados = _int(class_counts.get("indeterminado")) or 0
        excluidos = _int(class_counts.get("excluido")) or 0
        if fuera or indeterminados or excluidos:
            lines.append(_linea_fuera_del_ajuste(study, fuera, indeterminados, excluidos))
        table = _tabla_muestras(study)
    lines.extend(context.inference_lines)
    if context.run_dir is not None:
        lines.append(f"Evidencia de la corrida: {context.run_dir}")
    return StageSummary(
        stage="data",
        label=STAGE_LABELS["data"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={"Filas": "int", "Malos": "int", "Tasa de malos": "pct"},
    )


def _linea_fuera_del_ajuste(study: Study, fuera: int, indeterminadas: int, excluidas: int) -> str:
    """Qué quedó fuera del ajuste y qué le pasa (D-TTD-3 y D-CPY-1).

    La composición en sus tres grupos —el tercero son las filas con desenlace que una división por
    columna no asignó a ninguna muestra— y si la tarjeta las puntuará: sólo las que la TTD
    declarada incluye. Lo dice en futuro porque esta etapa no sabe si la corrida llegará a la
    tarjeta (``run(until=…)``).
    """
    con_desenlace = max(fuera - indeterminadas - excluidas, 0)
    total = max(fuera, indeterminadas + excluidas)
    linea = (
        f"Fuera del ajuste: {_miles(total)} {_plural(total, 'operación', 'operaciones')} "
        f"({_composicion(indeterminadas, excluidas, con_desenlace)})"
    )
    if _filas_fuera_en_ttd(study) > 0:
        linea += "; no entran al ajuste, y la tarjeta las puntúa aparte como parte de la " + (
            "población total (TTD)"
        )
    else:
        linea += "; no entran al ajuste ni a la población total (TTD), así que no se puntúan"
    if con_desenlace:
        linea += f"; su tasa de malos se mide sobre las {_miles(con_desenlace)} con desenlace"
    return linea


def _composicion(indeterminadas: int, excluidas: int, con_desenlace: int) -> str:
    """«6.225 indeterminadas», «3 indeterminadas y 2 excluidas», … (sólo los grupos con filas)."""
    partes = [
        f"{_miles(n)} {_plural(n, singular, plural)}"
        for n, singular, plural in (
            (indeterminadas, "indeterminada", "indeterminadas"),
            (excluidas, "excluida", "excluidas"),
            (
                con_desenlace,
                "con desenlace fuera de las muestras declaradas",
                ("con desenlace fuera de las muestras declaradas"),
            ),
        )
        if n
    ]
    return _enumerar(tuple(partes)) if partes else "ninguna"


def _filas_fuera_en_ttd(study: Study) -> int:
    """Cuántas filas fuera del ajuste incluye la TTD declarada (las que se puntúan, D-TTD-1)."""
    frame = _artifact(study, "data", "frame")
    splits = _artifact(study, "data", "splits")
    if not isinstance(frame, pd.DataFrame) or splits is None:
        return 0
    particion = getattr(splits, "partition_col", "partition")
    ttd = getattr(splits, "ttd_col", "ttd")
    if particion not in frame.columns or ttd not in frame.columns:
        return 0
    mascara = frame[particion].astype("string").eq("fuera_de_modelo").fillna(False) & frame[
        ttd
    ].astype("boolean").fillna(False)
    return int(mascara.astype(bool).sum())


def _filas(study: Study, domain: str, key: str) -> int | None:
    """Filas de un frame publicado, o ``None`` si la clave no está (un paso que no corrió)."""
    valor = _artifact(study, domain, key)
    return len(valor.index) if isinstance(valor, pd.DataFrame) else None


def _alerta_fuera_del_ajuste(previas: int | None, actuales: int | None) -> tuple[str, ...]:
    """La alerta de la etapa que no pudo puntuar lo que la anterior le entregó (D-TTD-1 §1.6).

    Sólo en la etapa donde la cadena pasa de tener filas a quedar vacía: las siguientes publican
    vacío sin volver a alertar (D-TTD-2). La causa exacta queda en el registro de auditoría.
    """
    if previas and actuales == 0:
        return (
            f"No se pudo puntuar a las {_miles(previas)} operaciones fuera del ajuste en esta "
            "etapa; la causa quedó en el registro de auditoría",
        )
    return ()


def _composicion_de(study: Study, indice: pd.Index) -> str:
    """La composición de unas filas fuera del ajuste, leída del estado que publicó ``data``."""
    frame = _artifact(study, "data", "frame")
    labels = _artifact(study, "data", "labels")
    estado = getattr(labels, "status_col", "label_status")
    if not isinstance(frame, pd.DataFrame) or estado not in frame.columns:
        return f"{_miles(len(indice))} {_plural(len(indice), 'operación', 'operaciones')}"
    valores = frame.loc[frame.index.intersection(indice), estado].astype("string")
    indeterminadas = int(valores.eq("indeterminado").fillna(False).sum())
    excluidas = int(valores.eq("excluido").fillna(False).sum())
    return _composicion(indeterminadas, excluidas, len(indice) - indeterminadas - excluidas)


#: Cómo se lee la banda del PSI de representatividad (D-TTD-4): no es deriva, así que no dice
#: «Redesarrollar»; los cortes son los de estabilidad de la corrida.
_REPRESENTATIVIDAD_LABELS: Final[dict[str, str]] = {
    "stable": "se parecen",
    "review": "difieren moderadamente",
    "redevelop": "difieren",
}

#: Dónde se contó una categoría no vista (D-TTD-5), dicho dentro de una frase.
_MUESTRA_NO_VISTA_LABELS: Final[dict[str, str]] = {
    "holdout": "en Holdout",
    "oot": "en Fuera de tiempo (OOT)",
    "fuera_de_modelo": "fuera del ajuste",
}


def _alertas_categorias_no_vistas(study: Study) -> tuple[str, ...]:
    """Una alerta por variable con categorías que no existían en Desarrollo (D-TTD-5).

    Dice el tratamiento **efectivo**: el riesgo de su peor tramo, nombrado (D-NOV-4). Una tabla
    publicada antes de D-NOV no trae ``tramo_asignado``: esas filas recibieron WoE 0.
    """
    tabla = _artifact(study, "binning", "unseen_categories")
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return ()
    alertas: list[str] = []
    for variable, filas in tabla.groupby("variable", sort=False):
        total = int(filas["filas"].sum())
        detalle = _enumerar(
            tuple(
                f"{_miles(int(fila['filas']))} "
                f"{_MUESTRA_NO_VISTA_LABELS.get(str(fila['muestra']), str(fila['muestra']))}"
                for _, fila in filas.iterrows()
            )
        )
        tramo = filas["tramo_asignado"].iloc[0] if "tramo_asignado" in filas.columns else None
        tratamiento = (
            "WoE 0, el riesgo promedio"
            if tramo is None or pd.isna(tramo)
            else f"el riesgo de su peor tramo («{_tramo_legible(study, str(variable), tramo)}»)"
        )
        alertas.append(
            f"«{variable}»: {_miles(total)} {_plural(total, 'operación', 'operaciones')} con una "
            f"categoría que no existía en Desarrollo ({detalle}); en esa variable "
            f"{_plural(total, 'recibe', 'reciben')} {tratamiento}"
        )
    return tuple(alertas)


def _tramo_legible(study: Study, variable: str, etiqueta_del_motor: Any) -> str:
    """El rótulo legible del tramo con esa etiqueta del motor, desde la tabla de la variable."""
    etiqueta = str(etiqueta_del_motor)
    tablas = _artifact(study, "binning", "tables")
    tabla = tablas.get(variable) if isinstance(tablas, Mapping) else None
    if not isinstance(tabla, pd.DataFrame) or "Bin" not in tabla.columns:
        return etiqueta
    regulares = [
        not es_fila_de_totales(indice, valor)
        for indice, valor in zip(tabla.index, tabla["Bin"], strict=True)
    ]
    filas = tabla.loc[regulares]
    for posicion, valor in enumerate(filas["Bin"].tolist()):
        if str(valor) == etiqueta:
            rotulos = rotulos_por_fila(filas, _artifact(study, "binning", "bin_edges"), variable)
            return str(rotulos[posicion])
    return etiqueta


#: Desde qué fracción de una muestra una variable categórica con valores que no existían en
#: Desarrollo recibe además la alerta de cambio de dominio (D-NOV-3). Constante aprobada: medido,
#: una categoría nueva de verdad queda muy por debajo (``programa`` 1,0 % de OOT en el SBA) y una
#: predictora derivada de la fecha, muy por encima (``anio_fiscal`` 45,8 %).
_UMBRAL_CAMBIO_DE_DOMINIO: Final = 0.10

#: La muestra de una alerta de cambio de dominio, dicha tras «de las operaciones».
_MUESTRA_DOMINIO_LABELS: Final[dict[str, str]] = {
    "holdout": "de Holdout",
    "oot": "fuera de tiempo (OOT)",
    "fuera_de_modelo": "fuera del ajuste",
}


def _alertas_cambio_de_dominio(
    study: Study, variables: Iterable[str] | None = None
) -> tuple[str, ...]:
    """Una alerta por (variable, muestra) con valores no vistos desde el 10 % de esa muestra.

    Se suma a la de D-TTD-5, que sigue para toda variable con una sola fila no vista (D-NOV-3).
    No excluye nada: excluir es una decisión humana con motivo. ``variables`` limita las alertas a
    esas variables —la selección las repite sólo para las que entran—.
    """
    tabla = _artifact(study, "binning", "unseen_categories")
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return ()
    tamanos = _tamanos_de_muestra(study)
    permitidas = None if variables is None else set(variables)
    alertas: list[str] = []
    for _, fila in tabla.iterrows():
        variable, muestra = str(fila["variable"]), str(fila["muestra"])
        tamano = tamanos.get(muestra, 0)
        if (permitidas is not None and variable not in permitidas) or tamano <= 0:
            continue
        fraccion = int(fila["filas"]) / tamano
        if fraccion < _UMBRAL_CAMBIO_DE_DOMINIO:
            continue
        alertas.append(
            f"«{variable}»: el {_pct(fraccion, decimals=1)} de las operaciones "
            f"{_MUESTRA_DOMINIO_LABELS.get(muestra, muestra)} trae un valor que no existía en "
            "Desarrollo. Si la variable se deriva de la fecha, no sirve para predecir fuera de "
            "tiempo: considera excluirla (`exclude`)."
        )
    return tuple(alertas)


def _tamanos_de_muestra(study: Study) -> dict[str, int]:
    """Filas de Holdout, OOT y fuera del ajuste: las muestras en que se cuentan las no vistas."""
    tamanos = {"fuera_de_modelo": _filas_fuera_en_ttd(study)}
    frame = _artifact(study, "data", "frame")
    splits = _artifact(study, "data", "splits")
    particion = getattr(splits, "partition_col", "partition")
    if isinstance(frame, pd.DataFrame) and particion in frame.columns:
        conteos = frame[particion].astype("string").value_counts()
        for muestra in ("holdout", "oot"):
            tamanos[muestra] = int(conteos.get(muestra, 0))
    return tamanos


def _tabla_muestras(study: Study) -> pd.DataFrame | None:
    frame = _artifact(study, "data", "frame")
    labels = _artifact(study, "data", "labels")
    splits = _artifact(study, "data", "splits")
    if not isinstance(frame, pd.DataFrame) or labels is None or splits is None:
        return None
    target_col = getattr(labels, "target_col", "target")
    partition_col = getattr(splits, "partition_col", "partition")
    if target_col not in frame.columns or partition_col not in frame.columns:
        return None
    filas: list[dict[str, Any]] = []
    particiones = frame[partition_col].astype("string")
    for particion in ("desarrollo", "holdout", "oot", "fuera_de_modelo"):
        mascara = particiones.eq(particion).fillna(False).astype(bool)
        n = int(mascara.sum())
        if n == 0:
            continue
        objetivo = frame.loc[mascara, target_col]
        con_target = objetivo.notna()
        # D-CPY-1: sin ningún desenlace conocido los malos son desconocidos, no cero; con alguno se
        # conservan, y la tasa se mide sobre esos.
        malos = int(objetivo[con_target].astype(float).sum()) if con_target.any() else None
        tasa = (malos or 0) / int(con_target.sum()) if con_target.any() else float("nan")
        filas.append(
            {
                "Muestra": _partition_label(particion),
                "Filas": n,
                "Malos": malos,
                "Tasa de malos": tasa,
            }
        )
    return pd.DataFrame(filas)


def _resumen_eda(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "eda", "eda_card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    formats: dict[str, _Kind] = {}
    if card is not None:
        eje = AXIS_LABELS.get(str(card.get("axis")), str(card.get("axis")))
        n_periods = _int(card.get("n_periods")) or 0
        sin_eje = card.get("default_rate_not_evaluable_reason")
        fallos = _mapping(card.get("failed_analyses"))
        # D-SC-19/20: un sub-análisis caído es algo que revisar —una ALERTA, que el resumen final
        # recoge en «Qué revisar»— y su línea de cifras se calla: publicar «ninguna marca» o «0
        # columnas» sobre un cálculo que no se hizo sería afirmar un resultado negativo.
        for clave in FAILED_ANALYSIS_LABELS:
            if clave in fallos:
                alerts.append(failed_analysis_sentence(clave, str(fallos[clave])))
        if sin_eje == "no_calculable":
            # La agrupación falló, no el archivo: la tasa global se conserva si hubo población.
            # Sin población no hay cifra, y «sin operaciones elegibles» afirmaría algo que nadie
            # midió; la línea «en el tiempo» la dice la alerta de arriba, con su causa.
            media = card.get("overall_default_rate")
            lines.append(
                "Tasa de malos: no disponible"
                if media is None or media != media
                else f"Tasa de malos: {_pct(media)}"
            )
        elif sin_eje:
            # D-SC-17: no hubo eje con que agrupar. Decir «por fecha de observación: 0 períodos»
            # sería absurdo, y la tasa global sí existe y es la cifra que el modelador quiere. No
            # lleva denominador: el único que `eda` publica vive en las filas de `by_period`, que
            # aquí no hay, y el resumen NO calcula (D-FLU-2); el tamaño lo dio la etapa de datos.
            media = card.get("overall_default_rate")
            lines.append(
                "Tasa de malos: sin operaciones elegibles"
                if media is None or media != media
                else f"Tasa de malos: {_pct(media)}"
            )
            lines.append(
                "Tasa de malos en el tiempo: no evaluable "
                f"({DEFAULT_RATE_NOT_EVALUABLE_REASON_LABELS.get(str(sin_eje), str(sin_eje))})"
            )
        else:
            lines.append(
                f"Tasa de malos {eje}: {_miles(n_periods)} "
                f"{_plural(n_periods, 'período', 'períodos')}, media "
                f"{_pct(card.get('overall_default_rate'))}"
            )
        causa = card.get("stability_not_evaluable_reason")
        indicador = STABILITY_INDICATOR_LABELS.get(
            str(card.get("stability_metric_used")), str(card.get("stability_metric_used"))
        )
        if sin_eje or causa in ("no_calculable", "tasa_no_calculable"):
            # La línea de arriba —o la alerta— ya dijo que la tasa en el tiempo no es evaluable y
            # por qué; repetirlo con las palabras de la señal sería decir dos veces lo mismo.
            pass
        elif causa:
            lines.append(
                "Deterioro de la tasa en el tiempo: no evaluable "
                f"({NOT_EVALUABLE_REASON_LABELS.get(str(causa), str(causa))})"
            )
        elif card.get("stability_flagged"):
            alerts.append(
                f"La tasa de malos se deteriora en el tiempo: {indicador} "
                f"{_frente(card.get('stability_value'), card.get('stability_threshold'))} "
                f"supera el umbral {_cut(card.get('stability_threshold'))}"
            )
        else:
            lines.append(
                f"Deterioro de la tasa en el tiempo: sin señal ({indicador} "
                f"{_frente(card.get('stability_value'), card.get('stability_threshold'))}, "
                f"umbral {_cut(card.get('stability_threshold'))})"
            )
        if "univariate" not in fallos:
            lines.append(
                f"{_miles(_int(card.get('n_columns_profiled')) or 0)} columnas descritas frente "
                "al incumplimiento"
            )
        marcas = _marcas_de_calidad(study)
        if "quality" in fallos:
            pass
        elif marcas:
            lines.append(f"Marcas de calidad del archivo: {_enumerar(marcas)}")
        else:
            lines.append("Marcas de calidad del archivo: ninguna")
        tasa = _artifact(study, "eda", "default_rate")
        by_period = getattr(tasa, "by_period", None)
        if isinstance(by_period, pd.DataFrame) and not by_period.empty:
            columnas = {
                "period": eje.capitalize(),
                "n_eligible": "Filas",
                "n_bad": "Malos",
                "default_rate": "Tasa de malos",
                "low_confidence": "Poca confianza",
            }
            table = by_period[[c for c in columnas if c in by_period.columns]].rename(
                columns=columnas
            )
            formats = {"Filas": "int", "Malos": "int", "Tasa de malos": "pct"}
    if not lines:
        lines.append("El análisis exploratorio no publicó su resumen.")
    return StageSummary(
        stage="eda",
        label=STAGE_LABELS["eda"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats=formats,
    )


def _marcas_de_calidad(study: Study) -> tuple[str, ...]:
    quality = _artifact(study, "eda", "quality")
    by_column = getattr(quality, "by_column", None)
    if not isinstance(by_column, pd.DataFrame) or by_column.empty:
        return ()
    marcas: list[str] = []
    for flag, rotulo in QUALITY_FLAG_LABELS.items():
        if flag not in by_column.columns:
            continue
        columnas = [str(c) for c in by_column.loc[by_column[flag].astype(bool), "col"]]
        if columnas:
            marcas.append(f"{rotulo}: {', '.join(columnas)}")
    return tuple(marcas)


def _categorias_reagrupadas(reagrupadas: Mapping[str, Any]) -> tuple[str, ...]:
    """«proposito» (nivel A48: 5 operaciones, ninguna incumplida), una por variable (D-RAR-2)."""
    partes: list[str] = []
    for variable, datos in reagrupadas.items():
        registro = _mapping(datos)
        niveles = tuple(str(nivel) for nivel in _sequence(registro.get("levels")))
        filas = _int(registro.get("n_obs")) or 0
        malos = _int(registro.get("n_events")) or 0
        nivel = f"nivel {niveles[0]}" if len(niveles) == 1 else f"niveles {_enumerar(niveles)}"
        partes.append(f"«{variable}» ({nivel}: {_operaciones_y_clase(filas, malos)})")
    return tuple(partes)


def _operaciones_y_clase(filas: int, malos: int) -> str:
    """«4 operaciones, ninguna incumplida», «5 operaciones, todas incumplidas» o cuántas."""
    clase = (
        "ninguna incumplida"
        if malos == 0
        else "todas incumplidas"
        if malos == filas
        else f"{_miles(malos)} {_plural(malos, 'incumplida', 'incumplidas')}"
    )
    return f"{_miles(filas)} {_plural(filas, 'operación', 'operaciones')}, {clase}"


#: El bin auxiliar de OptBinning, dicho para quien lee (D-FAL-2).
_BIN_ASIGNADO_LABELS: Final[dict[str, str]] = {
    "Missing": "Faltantes",
    "Special": "Valores especiales",
}


def _bins_asignados(asignados: Sequence[Any]) -> tuple[str, ...]:
    """Una línea por bin de faltantes o especiales cuyo WoE se asignó (D-FAL-2)."""
    lineas: list[str] = []
    for datos in asignados:
        registro = _mapping(datos)
        tipo = str(registro.get("bin"))
        filas = _int(registro.get("n_obs")) or 0
        malos = _int(registro.get("n_events")) or 0
        lineas.append(
            f"{_BIN_ASIGNADO_LABELS.get(tipo, tipo)} de «{registro.get('variable')}» "
            f"({_operaciones_y_clase(filas, malos)}): se les asignó el riesgo de su peor tramo"
        )
    return tuple(lineas)


def _resumen_binning(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "binning", "binning_card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    if card is not None:
        n_binned = _int(card.get("n_variables_binned")) or 0
        n_requested = _int(card.get("n_variables_requested")) or 0
        n_skipped = _int(card.get("n_variables_skipped")) or 0
        lines.append(
            f"{_miles(n_binned)} de {_miles(n_requested)} variables tramificadas"
            + (f"; {_miles(n_skipped)} no tramificables" if n_skipped else "")
        )
        excluded = tuple(str(c) for c in _sequence(card.get("excluded_by_target_rule")))
        if excluded:
            lines.append(
                f"Fuera por definir el incumplimiento (fuga de información): {', '.join(excluded)}"
            )
        reagrupadas = _categorias_reagrupadas(_mapping(card.get("rare_category_regroupings")))
        if reagrupadas:
            # D-RAR-2: sólo en el camino exitoso. Si el reajuste no alcanza, el paso levanta y
            # este resumen no llega a construirse: el diagnóstico lo da el mensaje del error.
            lines.append(
                "Categorías con muy pocas operaciones agrupadas para poder calcular su WoE: "
                + "; ".join(reagrupadas)
            )
        lines.extend(_bins_asignados(_sequence(card.get("assigned_bins"))))
        summary = _artifact(study, "binning", "summary")
        if isinstance(summary, pd.DataFrame) and not summary.empty:
            bandas: dict[str, list[str]] = {}
            for _, fila in summary.iterrows():
                if fila.get("skipped_reason"):
                    continue
                banda = IV_BAND_LABELS.get(str(fila.get("iv_band")), str(fila.get("iv_band")))
                bandas.setdefault(banda, []).append(str(fila.get("name")))
            if bandas:
                lines.append(
                    "Poder predictivo (IV): "
                    + " · ".join(f"{banda}: {', '.join(vs)}" for banda, vs in bandas.items())
                )
            sospechosas = [
                str(fila.get("name"))
                for _, fila in summary.iterrows()
                if bool(fila.get("is_suspicious_iv"))
            ]
            if sospechosas:
                alerts.append(
                    "IV sospechosamente alto (posible fuga de información): "
                    f"{', '.join(sospechosas)}"
                )
            omitidas = [
                f"{fila.get('name')} ({fila.get('skipped_reason')})"
                for _, fila in summary.iterrows()
                if fila.get("skipped_reason")
            ]
            if omitidas:
                lines.append(f"No tramificables: {', '.join(omitidas)}")
            columnas = {
                "name": "Variable",
                "dtype": "Tipo",
                "n_bins": "Tramos",
                "iv": "IV",
                "iv_band": "Banda de IV",
                "monotonic_trend": "Tendencia",
            }
            table = summary[[c for c in columnas if c in summary.columns]].rename(columns=columnas)
            table["Banda de IV"] = table["Banda de IV"].map(lambda v: IV_BAND_LABELS.get(str(v), v))
            table["Tendencia"] = table["Tendencia"].map(
                lambda v: _MONOTONIC_LABELS.get(str(v), v) if v is not None else "—"
            )
            table["Tipo"] = table["Tipo"].map(
                lambda v: {"numerical": "numérica", "categorical": "categórica"}.get(str(v), v)
            )
        alerts.extend(_alertas_de_inversion(study))
        alerts.extend(_alertas_categorias_no_vistas(study))
        alerts.extend(_alertas_cambio_de_dominio(study))
        alerts.extend(
            _alerta_fuera_del_ajuste(
                _filas_fuera_en_ttd(study), _filas(study, "binning", "out_of_model_woe_frame")
            )
        )
    if not lines:
        lines.append("El binning no publicó su resumen.")
    return StageSummary(
        stage="binning",
        label=STAGE_LABELS["binning"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={"Tramos": "int", "IV": "num3"},
    )


def _alertas_de_inversion(study: Study) -> tuple[str, ...]:
    """«Invierte en <muestra>» por variable, desde ``("binning", "event_rate_by_partition")``."""
    tasas = _artifact(study, "binning", "event_rate_by_partition")
    if not isinstance(tasas, pd.DataFrame) or tasas.empty or "inverts" not in tasas.columns:
        return ()
    invierte = tasas[tasas["inverts"].fillna(False).astype(bool)]
    if invierte.empty:
        return ()
    alertas: list[str] = []
    for variable, filas in invierte.groupby("feature", sort=True):
        muestras = sorted({str(p) for p in filas["partition"]}, key=_orden_particion)
        alertas.append(
            f"{variable}: la tasa de malos invierte la tendencia en "
            f"{_enumerar(tuple(_partition_label(p) for p in muestras))}"
        )
    return tuple(alertas)


def _resumen_selection(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "selection", "selection_card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    formats: dict[str, _Kind] = {}
    if card is not None:
        n_sel = _int(card.get("n_selected")) or 0
        n_cand = _int(card.get("n_candidates")) or 0
        lines.append(f"Entran {_miles(n_sel)} de {_miles(n_cand)} variables candidatas")
        tabla = _artifact(study, "selection", "selection_table")
        if isinstance(tabla, pd.DataFrame) and not tabla.empty:
            salen = [
                f"{fila.get('feature')} ({_rotulo(REASON_LABELS, fila.get('reason'))})"
                for _, fila in tabla.iterrows()
                if not bool(fila.get("included"))
            ]
            if salen:
                lines.append(f"Salen: {', '.join(salen)}")
            columnas = {
                "feature": "Variable",
                "included": "Entra",
                "reason": "Motivo",
                "iv": "IV",
                "auc": "AUC",
                "ks": "KS",
                "max_abs_corr": "Correlación máxima",
                "vif": "VIF",
            }
            table = tabla[[c for c in columnas if c in tabla.columns]].rename(columns=columnas)
            table["Motivo"] = table["Motivo"].map(lambda v: REASON_LABELS.get(str(v), v))
            table["Entra"] = table["Entra"].map(lambda v: "sí" if bool(v) else "no")
            formats = {
                "IV": "num3",
                "AUC": "num3",
                "KS": "num3",
                "Correlación máxima": "num3",
                "VIF": "num2",
            }
            table = _anexar_iv_por_muestra(study, table)
            for muestra in ("Desarrollo", "Holdout", "Fuera de tiempo (OOT)"):
                if f"IV {muestra}" in table.columns:
                    formats[f"IV {muestra}"] = "num3"
        corr = card.get("max_abs_correlation_after_selection")
        vif = card.get("max_vif_after_selection")
        frases: list[str] = []
        if corr is not None:
            frases.append(f"correlación máxima entre las finales {_cifra(corr, decimales=3)}")
        if vif is not None:
            frases.append(f"VIF máximo {_cifra(vif, decimales=2)}")
        if frases:
            lines.append(_capitalizar(_enumerar(tuple(frases))))
        high_iv = tuple(str(c) for c in _sequence(card.get("high_iv_flags")))
        if high_iv:
            alerts.append(
                f"IV excesivo (posible fuga de información), explicar antes de aprobar: "
                f"{', '.join(high_iv)}"
            )
        inestables = tuple(str(c) for c in _sequence(card.get("stability_flags")))
        if inestables:
            alerts.append(f"Inestabilidad temporal: {', '.join(inestables)}")
        alerts.extend(_alertas_iv_por_muestra(study))
        if isinstance(tabla, pd.DataFrame) and "included" in tabla.columns:
            entran = tabla.loc[tabla["included"].astype(bool), "feature"].astype(str)
            alerts.extend(_alertas_cambio_de_dominio(study, entran))
    if not lines:
        lines.append("La selección no publicó su resumen.")
    return StageSummary(
        stage="selection",
        label=STAGE_LABELS["selection"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats=formats,
    )


def _anexar_iv_por_muestra(study: Study, table: pd.DataFrame) -> pd.DataFrame:
    """Suma a la tabla de decisión el IV por muestra de ``("selection", "iv_by_partition")``."""
    iv = _artifact(study, "selection", "iv_by_partition")
    if not isinstance(iv, pd.DataFrame) or iv.empty or "Variable" not in table.columns:
        return table
    ancho = iv.pivot_table(index="feature", columns="partition", values="iv", aggfunc="first")
    salida = table.copy()
    for particion in ("desarrollo", "holdout", "oot"):
        if particion in ancho.columns:
            salida[f"IV {_partition_label(particion)}"] = salida["Variable"].map(ancho[particion])
    return salida


def _alertas_iv_por_muestra(study: Study) -> tuple[str, ...]:
    iv = _artifact(study, "selection", "iv_by_partition")
    if not isinstance(iv, pd.DataFrame) or iv.empty or "not_evaluable_reason" not in iv.columns:
        return ()
    sin_evaluar = iv[iv["not_evaluable_reason"].notna()]
    if sin_evaluar.empty:
        return ()
    muestras = sorted({str(p) for p in sin_evaluar["partition"]}, key=_orden_particion)
    return (
        "IV por muestra no evaluable en "
        f"{_enumerar(tuple(_partition_label(p) for p in muestras))}: la muestra tiene una sola "
        "clase",
    )


def _resumen_model(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "model", "model_card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    if card is not None:
        finales = tuple(str(c) for c in _sequence(card.get("final_features")))
        lines.append(
            f"Variables finales ({_miles(len(finales))}): {', '.join(finales) or 'ninguna'}"
        )
        umbrales = _mapping(card.get("thresholds"))
        direccion = str(umbrales.get("stepwise.direction", "none"))
        lines.extend(_traza_del_stepwise(study, direccion))
        fit = _mapping(card.get("fit_statistics"))
        if fit:
            partes = [
                f"pseudo-R² de McFadden {_cifra(fit.get('pseudo_r2_mcfadden'), decimales=3)}",
                f"AIC {_cifra(fit.get('aic'), decimales=1)}",
            ]
            if fit.get("llr_p_value") is not None:
                partes.append(
                    f"p-valor del test de razón de verosimilitud {_pvalor(fit.get('llr_p_value'))}"
                )
            partes.append("convergió" if fit.get("converged") else "NO convergió")
            lines.append(f"Ajuste en Desarrollo: {' · '.join(partes)}")
            if fit.get("converged") is False:
                alerts.append(
                    "El ajuste no convergió: la inferencia sobre los coeficientes no es válida"
                )
        signos = tuple(str(c) for c in _sequence(card.get("sign_flags")))
        if signos:
            alerts.append(
                "Coeficiente con el signo invertido respecto del riesgo esperado: "
                f"{', '.join(signos)}"
            )
        concentran = tuple(str(c) for c in _sequence(card.get("iv_contribution_flags")))
        if concentran:
            umbral = umbrales.get("iv_contribution.threshold")
            alerts.append(
                f"Concentra más del {_corte_pct(umbral)} del IV del modelo: {', '.join(concentran)}"
            )
        coeficientes = _artifact(study, "model", "coefficients")
        if isinstance(coeficientes, pd.DataFrame) and not coeficientes.empty:
            columnas = {
                "feature": "Variable",
                "beta": "Coeficiente",
                "standard_error": "Error estándar",
                "p_value": "p-valor",
                "sign_ok": "Signo esperado",
                "iv": "IV",
                "iv_contribution": "Contribución al IV",
            }
            table = coeficientes[[c for c in columnas if c in coeficientes.columns]].rename(
                columns=columnas
            )
            table["Variable"] = table["Variable"].map(
                lambda v: "intercepto" if str(v) == "intercept" else v
            )
            table["Signo esperado"] = table["Signo esperado"].map(
                lambda v: (
                    "—"
                    if v is None or (isinstance(v, float) and pd.isna(v))
                    else ("sí" if bool(v) else "no")
                )
            )
    alerts.extend(
        _alerta_fuera_del_ajuste(
            _filas(study, "binning", "out_of_model_woe_frame"),
            _filas(study, "model", "out_of_model_pd_frame"),
        )
    )
    if not lines:
        lines.append("El modelo no publicó su resumen.")
    return StageSummary(
        stage="model",
        label=STAGE_LABELS["model"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={
            "Coeficiente": "num",
            "Error estándar": "num",
            "p-valor": "pvalor",
            "IV": "num3",
            "Contribución al IV": "pct",
        },
    )


def _traza_del_stepwise(study: Study, direccion: str) -> tuple[str, ...]:
    """Qué salió, qué entró y por qué, en palabras, desde ``("model", "stepwise_trace")``."""
    traza = _artifact(study, "model", "stepwise_trace")
    decisiones = list(traza) if isinstance(traza, list | tuple) else []
    if not decisiones:
        return (f"Ajuste {_STEPWISE_DIRECTIONS.get(direccion, direccion)}",)
    iteraciones = max((_int(getattr(d, "iteration", 0)) or 0) for d in decisiones)
    entradas = [d for d in decisiones if getattr(d, "action", "") == "enter"]
    salidas = [d for d in decisiones if getattr(d, "action", "") in {"remove", "exclude"}]
    lineas = [
        f"{_capitalizar(_STEPWISE_DIRECTIONS.get(direccion, direccion))}: "
        f"{_miles(iteraciones)} {_plural(iteraciones, 'iteración', 'iteraciones')}, "
        f"{_miles(len(entradas))} {_plural(len(entradas), 'entrada', 'entradas')} y "
        f"{_miles(len(salidas))} {_plural(len(salidas), 'salida', 'salidas')}"
    ]
    for d in salidas:
        criterio = _STEPWISE_CRITERION_LABELS.get(str(getattr(d, "criterion", "")), "")
        detalle = _detalle_stepwise(d)
        lineas.append(
            f"  Sale {getattr(d, 'feature', '')} en la iteración "
            f"{_miles(_int(getattr(d, 'iteration', 0)) or 0)} por {criterio}{detalle}"
        )
    return tuple(lineas)


def _detalle_stepwise(decision: Any) -> str:
    p_value = getattr(decision, "p_value", None)
    threshold = getattr(decision, "threshold", None)
    if p_value is not None and threshold is not None:
        return f" (p-valor {_pvalor_frente(p_value, threshold)}, umbral {_cut(threshold)})"
    beta = getattr(decision, "beta", None)
    if beta is not None:
        return f" (coeficiente {_cifra(beta, decimales=3)})"
    return ""


def _resumen_scorecard(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "scorecard", "card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    if card is not None:
        lines.append(
            f"Escala: {_cut(card.get('pdo'), minimo=0)} puntos por duplicar las odds, "
            f"{_cut(card.get('target_score'), minimo=0)} puntos a odds "
            f"{_cut(card.get('target_odds'), minimo=0)}:1 "
            f"(factor {_cifra(card.get('factor'), decimales=2)}, "
            f"desplazamiento {_cifra(card.get('offset'), decimales=2)})"
        )
        score = _artifact(study, "scorecard", "score")
        columna = str(card.get("score_column", "score"))
        if isinstance(score, pd.DataFrame) and columna in score.columns and not score.empty:
            valores = pd.to_numeric(score[columna], errors="coerce").dropna()
            if not valores.empty:
                lines.append(
                    f"Puntajes observados: de {_cifra(valores.min(), decimales=0)} a "
                    f"{_cifra(valores.max(), decimales=0)} "
                    f"(media {_cifra(valores.mean(), decimales=1)})"
                )
        n_var = _int(card.get("n_variables")) or 0
        lines.append(
            f"{_miles(n_var)} {_plural(n_var, 'variable con puntos', 'variables con puntos')}; "
            + (
                "un puntaje más alto indica menor riesgo"
                if card.get("score_direction") == "higher_is_lower_risk"
                else "un puntaje más alto indica mayor riesgo"
            )
        )
        overrides = _int(card.get("overrides_count")) or 0
        if overrides:
            lines.append(f"Puntos fijados a mano en {_miles(overrides)} tramos")
        fuera = _artifact(study, "scorecard", "out_of_model_score")
        if (
            isinstance(fuera, pd.DataFrame)
            and not fuera.empty
            and columna in fuera.columns
            and isinstance(score, pd.DataFrame)
        ):
            dev = pd.to_numeric(
                score.loc[score["partition"].astype("string").eq("desarrollo").fillna(False)][
                    columna
                ],
                errors="coerce",
            )
            n = len(fuera.index)
            lines.append(
                f"Fuera del ajuste (TTD): {_miles(n)} "
                f"{_plural(n, 'operación puntuada', 'operaciones puntuadas')} "
                f"({_composicion_de(study, fuera.index)}), puntaje medio "
                f"{_cifra(pd.to_numeric(fuera[columna], errors='coerce').mean(), decimales=0)}"
                + (f" (Desarrollo {_cifra(dev.mean(), decimales=0)})" if not dev.empty else "")
            )
        alerts.extend(
            _alerta_fuera_del_ajuste(
                _filas(study, "model", "out_of_model_pd_frame"),
                _filas(study, "scorecard", "out_of_model_score"),
            )
        )
        tarjeta = _artifact(study, "scorecard", "scorecard")
        if isinstance(tarjeta, pd.DataFrame) and not tarjeta.empty:
            columnas = {
                "feature": "Variable",
                "bin_label": "Tramo",
                "woe": "WoE",
                "points": "Puntos",
            }
            table = tarjeta[[c for c in columnas if c in tarjeta.columns]].rename(columns=columnas)
            if "Tramo" in table.columns and "Variable" in table.columns:
                # D-CPY-3: el rótulo legible; `bin_label` del artefacto no cambia.
                legibles = _legibles(study)
                posiciones = (
                    tarjeta["bin_index"]
                    if "bin_index" in tarjeta.columns
                    else pd.Series([None] * len(tarjeta.index), index=tarjeta.index)
                )
                table["Tramo"] = [
                    _legible_en(legibles.get(str(variable), []), posicion, str(tramo))
                    for variable, tramo, posicion in zip(
                        table["Variable"], table["Tramo"], posiciones, strict=True
                    )
                ]
                table = _con_lineas_no_vistas(study, tarjeta, table)
        alerts.extend(_overrides_sin_casar(study))
    if not lines:
        lines.append("La tarjeta no publicó su resumen.")
    return StageSummary(
        stage="scorecard",
        label=STAGE_LABELS["scorecard"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={"WoE": "num3", "Puntos": "int"},
    )


def _resumen_calibration(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "calibration", "card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    if card is not None:
        metodo = _CALIBRATION_METHODS.get(str(card.get("method")), str(card.get("method")))
        fuente = _ANCHOR_SOURCES.get(str(card.get("anchor_source")), str(card.get("anchor_source")))
        tipo = _ANCHOR_KINDS.get(str(card.get("anchor_kind")), str(card.get("anchor_kind")))
        lines.append(f"Método: {metodo}; ancla {tipo}: {fuente} = {_pct(card.get('target_pd'))}")
        lines.append(
            f"PD media en Desarrollo: cruda {_pct(card.get('raw_mean_pd_dev'))} → calibrada "
            f"{_pct(card.get('calibrated_mean_pd_dev'))}"
            + (
                " (desplazamiento del intercepto "
                f"{_cifra(_sin_ruido(card.get('offset')), decimales=4)})"
                if card.get("offset") is not None
                else ""
            )
        )
        empates = _int(card.get("ties_created")) or 0
        lines.append(
            "Orden de riesgo preservado"
            if card.get("ranking_preserved")
            else "El orden de riesgo NO se preservó"
        )
        if not card.get("ranking_preserved"):
            alerts.append("La calibración alteró el orden de riesgo entre operaciones")
        if empates:
            alerts.append(f"La calibración creó {_miles(empates)} empates de PD")
        table = _tabla_pd_por_muestra(study, card)
        linea_ttd = _linea_pd_ttd(study, card)
        if linea_ttd is not None:
            lines.append(linea_ttd)
        alerts.extend(
            _alerta_fuera_del_ajuste(
                _filas(study, "scorecard", "out_of_model_score"),
                _filas(study, "calibration", "out_of_model_calibrated_pd_frame"),
            )
        )
    if not lines:
        lines.append("La calibración no publicó su resumen.")
    return StageSummary(
        stage="calibration",
        label=STAGE_LABELS["calibration"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={
            "Filas": "int",
            "PD media cruda": "pct",
            "PD media calibrada": "pct",
            "Tasa de malos observada": "pct",
        },
    )


def _legibles(study: Study) -> dict[str, list[str]]:
    """El rótulo legible de cada tramo, por variable y en el orden de sus filas (D-CPY-3)."""
    tablas = _artifact(study, "binning", "tables")
    bordes = _artifact(study, "binning", "bin_edges")
    if not isinstance(tablas, Mapping):
        return {}
    return {
        str(variable): rotulos_por_fila(
            tabla, bordes if isinstance(bordes, pd.DataFrame) else None, str(variable)
        )
        for variable, tabla in tablas.items()
        if isinstance(tabla, pd.DataFrame)
    }


def _con_lineas_no_vistas(study: Study, tarjeta: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """Tras los tramos de cada categórica del modelo, la línea de sus categorías no vistas.

    «Categorías no vistas → como «<tramo>»», con el WoE y los puntos de la fila que les da la
    búsqueda del escalador (D-NOV-1 §1.1). ``table`` es ``tarjeta`` con sus columnas públicas y el
    mismo índice; es la tabla del resumen, del Excel y de la pantalla.
    """
    from bayesrisk.scorecard.scaler import filas_de_referencia_no_vista

    proceso = _artifact(study, "binning", "process")
    referencias = getattr(proceso, "unseen_reference_", None)
    if not referencias or "bin_index" not in tarjeta.columns:
        return table
    filas = filas_de_referencia_no_vista(tarjeta, referencias)
    if not filas:
        return table
    variables = [str(valor) for valor in tarjeta["feature"].tolist()]
    posiciones = tarjeta["bin_index"].tolist()
    publicas = [
        {str(clave): valor for clave, valor in registro.items()}
        for registro in table.to_dict(orient="records")
    ]
    registros: list[dict[str, Any]] = []
    for posicion, registro in enumerate(publicas):
        registros.append(registro)
        variable = variables[posicion]
        fila = filas.get(variable)
        ultima = posicion + 1 == len(variables) or variables[posicion + 1] != variable
        if fila is None or not ultima:
            continue
        propia = next(
            i
            for i, (v, b) in enumerate(zip(variables, posiciones, strict=True))
            if v == variable and b == fila["bin_index"]
        )
        referencia = dict(publicas[propia])
        referencia["Tramo"] = rotulo_de_no_vistas(str(referencia["Tramo"]))
        registros.append(referencia)
    return pd.DataFrame(registros, columns=table.columns)


def _legible_en(legibles: list[str], posicion: Any, respaldo: str) -> str:
    """El rótulo de la fila ``posicion``, o la etiqueta del motor si no hay rótulo para ella."""
    n = _int(posicion)
    return legibles[n] if n is not None and 0 <= n < len(legibles) else respaldo


def _overrides_sin_casar(study: Study) -> tuple[str, ...]:
    """Una alerta por ajuste manual de puntos que no calzó con ningún tramo (D-CPY-3).

    Casa con la etiqueta del motor o con el rótulo legible, la misma regla del escalador. Antes un
    ajuste así se ignoraba en silencio.
    """
    seccion = getattr(study.config, "scorecard", None)
    ajustes = (
        seccion.get("point_overrides", ())
        if isinstance(seccion, Mapping)
        else getattr(seccion, "point_overrides", ())
    )
    tarjeta = _artifact(study, "scorecard", "scorecard")
    if not ajustes or not isinstance(tarjeta, pd.DataFrame):
        return ()
    legibles = _legibles(study)
    tablas = _artifact(study, "binning", "tables")
    alertas: list[str] = []
    for ajuste in ajustes:
        feature = str(
            _mapping(ajuste).get("feature") if isinstance(ajuste, Mapping) else ajuste.feature
        )
        etiqueta = str(
            _mapping(ajuste).get("bin_label") if isinstance(ajuste, Mapping) else ajuste.bin_label
        )
        tabla = tablas.get(feature) if isinstance(tablas, Mapping) else None
        crudas = (
            [
                str(fila.get("Bin"))
                for indice, fila in tabla.iterrows()
                if not es_fila_de_totales(indice, fila.get("Bin"))
            ]
            if isinstance(tabla, pd.DataFrame)
            else [str(v) for v in tarjeta.loc[tarjeta["feature"].eq(feature), "bin_label"]]
        )
        if filas_que_casan(etiqueta, crudas, legibles.get(feature, [])):
            continue
        alertas.append(
            f"El ajuste manual de puntos de «{feature}» para el tramo «{etiqueta}» no calzó con "
            "ningún tramo y no se aplicó"
        )
    return tuple(alertas)


def _linea_pd_ttd(study: Study, card: Mapping[str, Any]) -> str | None:
    """La PD calibrada media de toda la población que pidió crédito (D-TTD-3).

    Sólo con operaciones fuera del ajuste puntuadas: sin ellas, la TTD son las muestras que la
    tabla ya muestra.
    """
    modelables = _artifact(study, "calibration", "calibrated_pd_frame")
    fuera = _artifact(study, "calibration", "out_of_model_calibrated_pd_frame")
    columna = str(card.get("pd_calibrated_column", "pd_calibrated"))
    if (
        not isinstance(modelables, pd.DataFrame)
        or not isinstance(fuera, pd.DataFrame)
        or fuera.empty
        or columna not in modelables.columns
        or columna not in fuera.columns
    ):
        return None
    todas = pd.concat(
        [
            pd.to_numeric(modelables[columna], errors="coerce"),
            pd.to_numeric(fuera[columna], errors="coerce"),
        ]
    )
    n = len(todas.index)
    return (
        "PD calibrada media de toda la población que pidió crédito "
        f"(TTD, {_miles(n)} {_plural(n, 'operación', 'operaciones')}): {_pct(todas.mean())}"
    )


def _tabla_pd_por_muestra(study: Study, card: Mapping[str, Any]) -> pd.DataFrame | None:
    frame = _artifact(study, "calibration", "calibrated_pd_frame")
    if not isinstance(frame, pd.DataFrame) or frame.empty or "partition" not in frame.columns:
        return None
    cruda = str(card.get("pd_raw_column", "pd_raw"))
    calibrada = str(card.get("pd_calibrated_column", "pd_calibrated"))
    if cruda not in frame.columns or calibrada not in frame.columns:
        return None
    filas: list[dict[str, Any]] = []
    particiones = frame["partition"].astype("string")
    for particion in ("desarrollo", "holdout", "oot"):
        mascara = particiones.eq(particion).fillna(False).astype(bool)
        if not mascara.any():
            continue
        sub = frame.loc[mascara]
        fila: dict[str, Any] = {
            "Muestra": _partition_label(particion),
            "Filas": int(mascara.sum()),
            "PD media cruda": float(pd.to_numeric(sub[cruda], errors="coerce").mean()),
            "PD media calibrada": float(pd.to_numeric(sub[calibrada], errors="coerce").mean()),
        }
        if "target" in sub.columns:
            objetivo = pd.to_numeric(sub["target"], errors="coerce").dropna()
            fila["Tasa de malos observada"] = (
                float(objetivo.mean()) if not objetivo.empty else float("nan")
            )
        filas.append(fila)
    fuera = _artifact(study, "calibration", "out_of_model_calibrated_pd_frame")
    if (
        isinstance(fuera, pd.DataFrame)
        and not fuera.empty
        and cruda in fuera.columns
        and calibrada in fuera.columns
    ):
        # D-TTD-3: la fila de lo que quedó fuera del ajuste; la tasa observada sólo sobre las
        # filas con desenlace, si las hay.
        objetivo = (
            pd.to_numeric(fuera["target"], errors="coerce").dropna()
            if "target" in fuera.columns
            else pd.Series(dtype="float64")
        )
        filas.append(
            {
                "Muestra": f"{_partition_label('fuera_de_modelo')} (TTD)",
                "Filas": len(fuera.index),
                "PD media cruda": float(pd.to_numeric(fuera[cruda], errors="coerce").mean()),
                "PD media calibrada": float(
                    pd.to_numeric(fuera[calibrada], errors="coerce").mean()
                ),
                "Tasa de malos observada": (
                    float(objetivo.mean()) if not objetivo.empty else float("nan")
                ),
            }
        )
    return pd.DataFrame(filas)


def _resumen_performance(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "performance", "card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    if card is not None:
        maximos = _mapping(card.get("max_metrics_by_partition"))
        bandas = _mapping(card.get("bands_by_partition"))
        for particion in _sequence(card.get("partitions")):
            pid = str(particion)
            valores = _mapping(maximos.get(pid))
            banda = str(bandas.get(pid, ""))
            if banda == "not_evaluable":
                alerts.append(
                    f"Discriminación no evaluable en {_partition_label(pid)}"
                    + _causa_no_evaluable(card, pid)
                )
                continue
            lines.append(
                f"{_partition_label(pid)}: AUC {_cifra(valores.get('auc'), decimales=3)} · "
                f"Gini {_cifra(valores.get('gini'), decimales=3)} · "
                f"KS {_cifra(valores.get('ks'), decimales=3)}"
            )
            if banda == "threshold_flag":
                alerts.append(
                    f"{_partition_label(pid)}: {_DISCRIMINANT_BANDS['threshold_flag'].lower()}"
                )
        caida = _caida_dev_oot(maximos)
        if caida is not None:
            lines.append(caida)
        tabla = _artifact(study, "performance", "performance_table")
        if isinstance(tabla, pd.DataFrame) and not tabla.empty:
            columnas = {
                "partition": "Muestra",
                "decile": "Decil",
                "n_total": "Filas",
                "n_bad": "Malos",
                "bad_rate": "Tasa de malos",
                "mean_pd": "PD media",
                "mean_score": "Puntaje medio",
                "cum_bad_capture_rate": "Captura acumulada de malos",
                "ks_at_decile": "KS en el decil",
            }
            table = tabla[[c for c in columnas if c in tabla.columns]].rename(columns=columnas)
            table["Muestra"] = table["Muestra"].map(lambda v: _partition_label(str(v)))
            table = table.reset_index(drop=True)
    if not lines and not alerts:
        lines.append("El desempeño no publicó su resumen.")
    return StageSummary(
        stage="performance",
        label=STAGE_LABELS["performance"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={
            "Decil": "int",
            "Filas": "int",
            "Malos": "int",
            "Tasa de malos": "pct",
            "PD media": "pct",
            "Puntaje medio": "num2",
            "Captura acumulada de malos": "pct",
            "KS en el decil": "num3",
        },
    )


def _caida_dev_oot(maximos: Mapping[str, Any]) -> str | None:
    """La caída Desarrollo → OOT (o → Holdout sin OOT) de AUC y KS, en palabras."""
    dev = _mapping(maximos.get("desarrollo"))
    destino = "oot" if "oot" in maximos else ("holdout" if "holdout" in maximos else None)
    if destino is None or not dev:
        return None
    fuera = _mapping(maximos.get(destino))
    frases: list[str] = []
    for clave, rotulo in (("auc", "AUC"), ("ks", "KS")):
        a = _float(dev.get(clave))
        b = _float(fuera.get(clave))
        if a is None or b is None:
            continue
        delta = b - a
        relativo = f" ({_pct(delta / a, decimals=1)})" if a else ""
        signo = "+" if delta > 0 else ""
        frases.append(f"{rotulo} {signo}{_cifra(delta, decimales=3)}{relativo}")
    if not frases:
        return None
    return f"Caída Desarrollo → {_partition_label(destino)}: {' · '.join(frases)}"


def _causa_no_evaluable(card: Mapping[str, Any], particion: str) -> str:
    secciones = _mapping(card.get("metric_sections"))
    causas = _mapping(
        _mapping(secciones.get("discrimination")).get("not_evaluable_reasons_by_partition")
    )
    causa = causas.get(particion)
    return f" ({causa})" if causa else ""


def _resumen_stability(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "stability", "card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    if card is not None:
        maximos = _mapping(card.get("max_psi_by_comparison"))
        metricas = _mapping(card.get("psi_metric_by_comparison"))
        bandas = _mapping(card.get("bands_by_comparison"))
        for comparacion in _sequence(card.get("comparisons")):
            cid = str(comparacion)
            banda = str(bandas.get(cid, ""))
            rotulo_banda = BAND_LABELS.get(banda, banda)
            valor = maximos.get(cid)
            magnitud = PSI_METRIC_LABELS.get(str(metricas.get(cid)), "")
            if banda == "not_evaluable" or valor is None:
                lines.append(f"{_COMPARISON_LABELS.get(cid, cid)}: PSI no evaluable")
                continue
            frase = (
                f"{_COMPARISON_LABELS.get(cid, cid)}: peor PSI {_cifra(valor)} "
                f"({magnitud}) → {rotulo_banda}"
            )
            lines.append(frase)
            if banda in {"review", "redevelop"}:
                alerts.append(
                    f"Estabilidad {_COMPARISON_LABELS.get(cid, cid)}: banda «{rotulo_banda}»"
                )
        peor = card.get("worst_csi_feature")
        if peor is not None:
            lines.append(
                f"CSI más alto: {str(peor).removesuffix('__points').removesuffix('__bin')} "
                f"({_cifra(card.get('worst_csi_value'))})"
            )
        representatividad = _linea_representatividad(study)
        if representatividad is not None:
            linea, alerta = representatividad
            lines.append(linea)
            if alerta is not None:
                alerts.append(alerta)
        alerts.extend(
            _alerta_fuera_del_ajuste(
                _filas(study, "calibration", "out_of_model_calibrated_pd_frame"),
                _filas(study, "stability", "out_of_model_psi"),
            )
        )
        secciones = _mapping(_mapping(card.get("metric_sections")).get("stability"))
        eje = str(secciones.get("temporal_axis", "none"))
        if eje != "none":
            n = _int(secciones.get("n_periods")) or 0
            lines.append(
                f"Estabilidad temporal del score por {TEMPORAL_AXIS_LABELS.get(eje, eje).lower()}: "
                f"{_miles(n)} {_plural(n, 'período', 'períodos')}"
            )
        metricas_tabla = _artifact(study, "stability", "stability_metrics")
        if isinstance(metricas_tabla, pd.DataFrame) and not metricas_tabla.empty:
            columnas = {
                "metric": "Métrica",
                "comparison": "Comparación",
                "feature": "Variable",
                "value": "Valor",
                "band": "Banda",
            }
            table = metricas_tabla[[c for c in columnas if c in metricas_tabla.columns]].rename(
                columns=columnas
            )
            table["Métrica"] = table["Métrica"].map(
                lambda v: STABILITY_METRIC_LABELS.get(str(v), v)
            )
            table["Comparación"] = table["Comparación"].map(
                lambda v: {**_COMPARISON_LABELS, **TEMPORAL_AXIS_LABELS}.get(str(v), v)
            )
            table["Banda"] = table["Banda"].map(lambda v: BAND_LABELS.get(str(v), v))
            table = table.reset_index(drop=True)
    if not lines:
        lines.append("La estabilidad no publicó su resumen.")
    return StageSummary(
        stage="stability",
        label=STAGE_LABELS["stability"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={"Valor": "num"},
    )


def _linea_representatividad(study: Study) -> tuple[str, str | None] | None:
    """Lo que quedó fuera del ajuste frente a Desarrollo (D-TTD-4): la línea y su alerta."""
    psi = _artifact(study, "stability", "out_of_model_psi")
    if not isinstance(psi, pd.DataFrame) or psi.empty:
        return None
    total = _float(psi["total_value"].iloc[0])
    banda = str(psi["band"].iloc[0])
    lectura = _REPRESENTATIVIDAD_LABELS.get(banda, banda)
    linea = f"Fuera del ajuste frente a Desarrollo: PSI {_cifra(total)} — {lectura}"
    modelables = _artifact(study, "calibration", "calibrated_pd_frame")
    fuera = _artifact(study, "calibration", "out_of_model_calibrated_pd_frame")
    if (
        isinstance(modelables, pd.DataFrame)
        and isinstance(fuera, pd.DataFrame)
        and not fuera.empty
        and "pd_calibrated" in modelables.columns
        and "pd_calibrated" in fuera.columns
    ):
        dev = pd.to_numeric(
            modelables.loc[
                modelables["partition"].astype("string").eq("desarrollo").fillna(False),
                "pd_calibrated",
            ],
            errors="coerce",
        ).mean()
        media = pd.to_numeric(fuera["pd_calibrated"], errors="coerce").mean()
        if pd.notna(dev) and pd.notna(media):
            sentido = "menor" if media < dev else "mayor" if media > dev else "el mismo"
            linea += (
                f": el modelo las ve con {sentido} riesgo (PD calibrada media {_pct(media)} "
                f"frente a {_pct(dev)})"
            )
    alerta = (
        f"Las operaciones fuera del ajuste difieren de Desarrollo (PSI {_cifra(total)}): la "
        "muestra de ajuste no las representa"
        if banda == "redevelop"
        else None
    )
    return linea, alerta


def _resumen_validation(study: Study, context: SummaryContext) -> StageSummary:
    del context
    card = _card(study, "validation", "card")
    lines: list[str] = []
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    if card is not None:
        estado = str(card.get("overall_status", ""))
        rotulo = VALIDATION_STATUS_LABELS.get(estado, estado)
        decisivas = _pruebas_decisivas(study)
        detalle = f" — lo decide {_enumerar(decisivas)}" if decisivas else ""
        lines.append(f"Estado técnico: {rotulo}{detalle}")
        n_tests = _int(card.get("n_tests")) or 0
        n_failed = _int(card.get("n_failed")) or 0
        familias = tuple(
            VALIDATION_FAMILY_LABELS.get(str(f), str(f)).lower()
            for f in _sequence(card.get("families_run"))
        )
        lines.append(
            f"{_miles(n_tests)} "
            f"{_plural(n_tests, 'prueba con veredicto', 'pruebas con veredicto')}, "
            f"{_miles(n_failed)} {_plural(n_failed, 'fallida', 'fallidas')}; familias: "
            f"{_enumerar(familias) if familias else 'ninguna'}"
        )
        if estado in {"fail", "warn"}:
            alerts.append(
                f"Estado técnico «{rotulo}»"
                + (f": revisar {_enumerar(decisivas)}" if decisivas else "")
            )
        avisos = _declared_warning_descriptions(
            tuple(str(a) for a in _sequence(card.get("falta_dato")))
        )
        alerts.extend(_capitalizar(a) for a in avisos)
        lines.append(
            "El estado técnico es una síntesis del motor; el veredicto lo firma un validador"
        )
        table = _tabla_de_pruebas(study)
    if not lines:
        lines.append("La validación formal no publicó su resumen.")
    return StageSummary(
        stage="validation",
        label=STAGE_LABELS["validation"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={"Valor": "num", "p-valor": "pvalor"},
    )


def _pruebas_decisivas(study: Study) -> tuple[str, ...]:
    """Las pruebas que fallaron o quedaron en revisión, en palabras, con su muestra."""
    decisivas: list[str] = []
    calibracion = _artifact(study, "validation", "calibration")
    grupos_hl = _artifact(study, "validation", "hosmer_lemeshow_groups")
    if isinstance(calibracion, pd.DataFrame) and not calibracion.empty:
        for _, fila in calibracion.iterrows():
            if str(fila.get("decision")) == "fail":
                prueba = CALIBRATION_TEST_LABELS.get(str(fila.get("test")), str(fila.get("test")))
                esperada, observada = (
                    _float(fila.get("expected_pd")),
                    _float(fila.get("observed_dr")),
                )
                es_hl = str(fila.get("test")) == "hosmer_lemeshow"
                # D-CPY-6: la brecha MEDIA agregada, sin atribuirle una causa; Hosmer-Lemeshow mide
                # por grupo y esta media no lo reemplaza. El veredicto no cambia.
                brecha = (
                    f"; PD media agregada {_pct(esperada)} frente a {_pct(observada)} observada"
                    if es_hl and esperada is not None and observada is not None
                    else ""
                )
                if es_hl:
                    brecha += _mayor_diferencia_hl(grupos_hl, str(fila.get("partition")))
                decisivas.append(
                    f"{prueba} en {_partition_label(str(fila.get('partition')))} "
                    f"(p-valor {_pvalor(fila.get('p_value'))}{brecha})"
                )
    estabilidad = _artifact(study, "validation", "stability")
    if isinstance(estabilidad, pd.DataFrame) and not estabilidad.empty:
        for _, fila in estabilidad.iterrows():
            if str(fila.get("decision")) in {"fail", "warn"}:
                decisivas.append(_prueba_de_estabilidad(fila))
    discriminacion = _artifact(study, "validation", "discrimination")
    if isinstance(discriminacion, pd.DataFrame) and not discriminacion.empty:
        for _, fila in discriminacion.iterrows():
            if str(fila.get("status")) == "not_evaluable":
                decisivas.append(
                    f"discriminación no evaluable en {_partition_label(str(fila.get('partition')))}"
                )
    return tuple(decisivas)


def _mayor_diferencia_hl(grupos: Any, partition: str) -> str:
    """«; la mayor diferencia, en el grupo 8 de 10: 45,56 % observado frente a 42,14 % predicho».

    D-HLG-2: el grupo de **mayor diferencia absoluta** entre la tasa observada y la PD media —a
    igual diferencia, el de menor número—, no el de mayor contribución al estadístico (en el SBA,
    el 3, con 1,7 pp y O/E 0,64): la frase dice magnitud absoluta y la tabla por grupo trae la
    razón O/E y la contribución para que la diferencia relativa no se esconda. Sin la clave
    —una corrida guardada con una versión anterior— o sin filas de esa muestra, no suma nada.
    """
    if not isinstance(grupos, pd.DataFrame) or grupos.empty:
        return ""
    muestra = grupos[grupos["partition"].astype(str) == partition]
    if muestra.empty:
        return ""
    muestra = muestra.sort_values("group", kind="stable").reset_index(drop=True)
    diferencia = muestra["gap_pp"].astype(float).abs()
    # `idxmax` devuelve la primera aparición del máximo: con las filas en orden de grupo, el de
    # menor número.
    fila = muestra.loc[diferencia.idxmax()].to_dict()
    return (
        f"; la mayor diferencia, en el grupo {int(fila['group'])} de {len(muestra)}: "
        f"{_pct(_float(fila['observed_dr']))} observado frente a "
        f"{_pct(_float(fila['mean_pd']))} predicho"
    )


def _prueba_de_estabilidad(fila: Any) -> str:
    """«CSI de anio_fiscal Desarrollo vs. OOT (Redesarrollar)», «PSI temporal por período (…)».

    Los mismos mapas que la tabla de la etapa (D-CPY-2): el eje temporal en palabras y la variable
    de cada CSI, para que tres CSI no se lean iguales.
    """
    metrica = _rotulo(STABILITY_METRIC_LABELS, fila.get("metric"))
    banda = _rotulo(BAND_LABELS, fila.get("band"))
    comparacion = str(fila.get("comparison"))
    if comparacion in TEMPORAL_AXIS_LABELS:
        return f"{metrica} por {TEMPORAL_AXIS_LABELS[comparacion].lower()} ({banda})"
    texto = _rotulo(_COMPARISON_LABELS, comparacion)
    if str(fila.get("metric")) == "csi" and fila.get("feature") is not None:
        return f"{metrica} de {_sin_sufijo(fila.get('feature'))} {texto} ({banda})"
    return f"{metrica} {texto} ({banda})"


def _tabla_de_pruebas(study: Study) -> pd.DataFrame | None:
    """Una fila por prueba y muestra, con su veredicto en palabras."""
    filas: list[dict[str, Any]] = []
    discriminacion = _artifact(study, "validation", "discrimination")
    if isinstance(discriminacion, pd.DataFrame):
        for _, fila in discriminacion.iterrows():
            filas.append(
                {
                    "Familia": VALIDATION_FAMILY_LABELS["discrimination"],
                    "Prueba": "AUC",
                    "Muestra": _partition_label(str(fila.get("partition"))),
                    "Valor": _float(fila.get("auc")),
                    "p-valor": None,
                    "Veredicto": (
                        "Evaluada" if str(fila.get("status")) == "ok" else "No evaluable"
                    ),
                }
            )
    calibracion = _artifact(study, "validation", "calibration")
    if isinstance(calibracion, pd.DataFrame):
        for _, fila in calibracion.iterrows():
            decision = str(fila.get("decision"))
            veredicto = VALIDATION_DECISION_LABELS.get(decision, decision)
            causa = fila.get("not_evaluable_reason")
            if causa is not None and not (isinstance(causa, float) and pd.isna(causa)):
                veredicto += f" ({HL_NOT_EVALUABLE_REASON_LABELS.get(str(causa), str(causa))})"
            filas.append(
                {
                    "Familia": VALIDATION_FAMILY_LABELS["calibration"],
                    "Prueba": _rotulo(CALIBRATION_TEST_LABELS, fila.get("test")),
                    "Muestra": _partition_label(str(fila.get("partition"))),
                    "Valor": _float(fila.get("statistic")),
                    "p-valor": _float(fila.get("p_value")),
                    "Veredicto": veredicto,
                }
            )
    estabilidad = _artifact(study, "validation", "stability")
    if isinstance(estabilidad, pd.DataFrame):
        for _, fila in estabilidad.iterrows():
            decision = str(fila.get("decision"))
            veredicto = {
                **VALIDATION_DECISION_LABELS,
                "warn": VALIDATION_STATUS_LABELS["warn"],
            }.get(decision, decision)
            filas.append(
                {
                    "Familia": VALIDATION_FAMILY_LABELS["stability"],
                    "Prueba": (
                        f"{_rotulo(STABILITY_METRIC_LABELS, fila.get('metric'))} · "
                        f"{_sin_sufijo(fila.get('feature'))}"
                    ),
                    "Muestra": {**_COMPARISON_LABELS, **TEMPORAL_AXIS_LABELS}.get(
                        str(fila.get("comparison")), str(fila.get("comparison"))
                    ),
                    "Valor": _float(fila.get("value")),
                    "p-valor": None,
                    "Veredicto": f"{veredicto} ({_rotulo(BAND_LABELS, fila.get('band'))})",
                }
            )
    if not filas:
        return None
    return pd.DataFrame(filas)


def _resumen_report(study: Study, context: SummaryContext) -> StageSummary:
    lines: list[str] = []
    resultado = _artifact(study, "report", "result")
    for atributo, rotulo in (
        ("html_path", "Informe HTML"),
        ("docx_path", "Informe Word"),
        ("pdf_path", "Informe PDF"),
        ("md_path", "Fuente editable (Quarto)"),
    ):
        ruta = getattr(resultado, atributo, None) if resultado is not None else None
        if ruta:
            lines.append(f"{rotulo}: {_ruta_absoluta(ruta, context)}")
        elif atributo == "pdf_path" and resultado is not None:
            lines.append(f"{rotulo}: no se generó (falta el extra de PDF o su motor nativo)")
    if context.card_path is not None:
        lines.append(f"Ficha del modelo: {context.card_path}")
    if context.trail_path is not None:
        lines.append(f"Registro de auditoría: {context.trail_path}")
    if not lines:
        lines.append("El informe no publicó sus rutas.")
    return StageSummary(stage="report", label=STAGE_LABELS["report"], lines=tuple(lines))


# ─────────────────── familia de cartera: IFRS 9 (FLUJO-GUIADO-IFRS9 D-ECL-7) ───────────────────
#
# Una corrida que provisiona IFRS 9 sin dominios del scorecard habla en palabras de provisiones:
# «Cartera», «Curva de PD», «Provisión IFRS 9». Cada resumen lee sólo lo que publicó su etapa o una
# anterior y el config de ESA corrida —nunca el preset F4 ni la puerta guiada—: la familia la eligen
# también un YAML y la pantalla, que admiten Vasicek, escenarios de `forward` y PD de originación.

#: La duración, en años, que se acepta como «un año» al leer la curva (la del motor, D-HOR-0).
_TOL_ANIO: Final = 1e-9
#: El p-valor sobre el que un coeficiente de la curva se describe «sin efecto distinguible de
#: cero». Es la lectura del resumen, no una regla del motor: no excluye nada por sí sola.
_P_SIN_EFECTO: Final = 0.05
#: Los gatillos de staging en palabras (``provisioning/ifrs9/staging.py``, los siete nombres
#: canónicos de ``sicr_triggers``). Los de mora llevan el umbral de ESA corrida.
_GATILLOS_STAGE_2: Final[tuple[str, ...]] = (
    "sicr_pd_ratio",
    "sicr_pd_pit_backstop",
    "notch_downgrade",
    "stage_override",
    "dpd_sicr_backstop",
)
_GATILLOS_STAGE_3: Final[tuple[str, ...]] = (
    "dpd_default_backstop",
    "is_default",
    "stage_override",
)
_ROTULO_GATILLO: Final[dict[str, str]] = {
    "sicr_pd_ratio": "aumento de la PD de por vida frente a la de origen",
    "sicr_pd_pit_backstop": "aumento de la PD point-in-time frente a la de origen",
    "notch_downgrade": "bajada de rating",
    "stage_override": "decisión cualitativa (override por operación)",
    "is_default": "la marca de incumplimiento",
}
#: La columna de nombre fijo con la PD PIT en origen que habilita el backstop PIT (``staging.py``).
_COLUMNA_PD_PIT_ORIGEN: Final = "pd_pit_origination"
#: Las presunciones de mora de IFRS 9 (5.5.11 y B5.5.37): lo que se rebate con motivo (§3.9).
_PRESUNCION_STAGE_2: Final = 30
_PRESUNCION_STAGE_3: Final = 90


def _resumen_cartera(study: Study, context: SummaryContext) -> StageSummary:
    """«Cartera»: operaciones, fecha de corte, exposición y carteras; sin malos ni muestras."""
    frame = _artifact(study, "data", "frame")
    card = _card(study, "data", "data_card")
    ifrs = _seccion(study, "provisioning_ifrs9")
    as_of_col = _hoja(ifrs, "as_of_date_col")
    cartera_col = _hoja(ifrs, "portfolio_col")
    ead_col = _hoja(ifrs, "ead", "ead_col") if _hoja(ifrs, "ead", "method") == "provided" else None
    lines: list[str] = [f"Archivo: {context.source_label}"]
    alerts: list[str] = []
    table: pd.DataFrame | None = None
    n_filas = (
        len(frame.index)
        if isinstance(frame, pd.DataFrame)
        else (_int(card.get("n_rows")) if card is not None else None) or 0
    )
    partes = [f"{_miles(n_filas)} {_plural(n_filas, 'operación', 'operaciones')}"]
    if isinstance(frame, pd.DataFrame):
        if isinstance(as_of_col, str) and as_of_col in frame.columns:
            fechas = sorted({_fecha_legible(v) for v in frame[as_of_col].dropna().unique()})
            if len(fechas) == 1:
                partes.append(f"fecha de corte {fechas[0]}")
            elif fechas:
                alerts.append(
                    f"El archivo trae {_miles(len(fechas))} fechas de corte distintas en "
                    f"«{as_of_col}» ({_enumerar(fechas[:3])}{'…' if len(fechas) > 3 else ''}): "
                    "la provisión se calcula a una sola fecha de corte"
                )
        if isinstance(cartera_col, str) and cartera_col in frame.columns:
            n_carteras = int(frame[cartera_col].nunique(dropna=True))
            partes.append(f"{_miles(n_carteras)} {_plural(n_carteras, 'cartera', 'carteras')}")
            table = _tabla_por_cartera(frame, cartera_col, ead_col)
        if isinstance(ead_col, str) and ead_col in frame.columns:
            total = _float(pd.to_numeric(frame[ead_col], errors="coerce").sum())
            if total is not None:
                partes.append(f"exposición total {_monto(total)}")
    lines.append(" · ".join(partes))
    lines.extend(context.inference_lines)
    if context.run_dir is not None:
        lines.append(f"Evidencia de la corrida: {context.run_dir}")
    return StageSummary(
        stage="data",
        label=STAGE_LABELS_CARTERA["data"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=table,
        formats={
            "Operaciones": "int",
            "Exposición": "int",
            "Participación en la exposición": "pct",
        },
    )


def _tabla_por_cartera(frame: pd.DataFrame, cartera_col: str, ead_col: str | None) -> pd.DataFrame:
    """Operaciones y exposición por cartera (la tabla de decisión de «Cartera»)."""
    grupos = frame.groupby(frame[cartera_col].astype("string"), dropna=False, sort=True)
    filas: list[dict[str, Any]] = []
    tiene_ead = isinstance(ead_col, str) and ead_col in frame.columns
    total = float(pd.to_numeric(frame[ead_col], errors="coerce").sum()) if tiene_ead else 0.0
    for cartera, grupo in grupos:
        fila: dict[str, Any] = {
            "Cartera": "—" if pd.isna(cartera) else str(cartera),
            "Operaciones": len(grupo.index),
        }
        if tiene_ead:
            exposicion = float(pd.to_numeric(grupo[ead_col], errors="coerce").sum())
            fila["Exposición"] = round(exposicion)
            fila["Participación en la exposición"] = exposicion / total if total else None
        filas.append(fila)
    return pd.DataFrame(filas)


def _resumen_curva(study: Study, context: SummaryContext) -> StageSummary:
    """«Curva de PD»: la historia observada, la forma de la curva y el efecto de las covariables."""
    card = _card(study, "survival", "card") or {}
    terminos = _artifact(study, "survival", "coefficients")
    curva = _artifact(study, "survival", "term_structure")
    survival = _seccion(study, "survival")
    unidad = card.get("time_unit") or _hoja(survival, "time_grid", "time_unit")
    n_filas = _int(card.get("n_rows")) or 0
    n_eventos = _int(card.get("n_events")) or 0
    n_censuradas = _int(_mapping(card.get("diagnostics")).get("n_censored"))
    n_periodos = _int(card.get("n_periods")) or 0
    lines: list[str] = []
    alerts: list[str] = []
    historia = (
        f"{_miles(n_filas)} {_plural(n_filas, 'operación observada', 'operaciones observadas')} · "
        f"{_miles(n_eventos)} {_plural(n_eventos, 'incumplimiento', 'incumplimientos')}"
    )
    if n_censuradas is not None:
        historia += (
            f" · {_miles(n_censuradas)} sin incumplir al cierre de su observación (censuradas)"
        )
    lines.append(historia)
    palabras = time_unit_words(unidad, n_periodos)
    if palabras is not None:
        lines.append(
            f"La curva llega a {_miles(n_periodos)} {palabras}, un período por {_singular(unidad)}"
        )
    else:
        lines.append(f"La curva tiene {_miles(n_periodos)} períodos (unidad «{unidad}»)")
    covariables = tuple(str(c) for c in _sequence(_hoja(survival, "input", "covariate_cols")))
    if covariables:
        efectos = _efectos_en_palabras(terminos, covariables)
        lines.append(
            f"Covariables: {efectos}" if efectos else f"Covariables: {', '.join(covariables)}"
        )
    else:
        lines.append("Sin covariables: una sola curva para toda la cartera")
        alerts.append(
            "La curva no usa covariables: todas las operaciones comparten la misma PD por "
            "período, y el orden de riesgo entre ellas sólo lo dan la mora y la marca en el staging"
        )
    medias = _pd_medias(curva)
    if medias is not None:
        un_anio, de_por_vida = medias
        partes = []
        if un_anio is not None:
            partes.append(f"a 12 meses {_pct(un_anio)}")
        partes.append(f"de por vida {_pct(de_por_vida)}")
        lines.append(f"PD media de las operaciones: {_enumerar(partes)}")
    if _hoja(_seccion(study, "provisioning_ifrs9"), "pd", "pit_mode") == "ttc_only":
        lines.append(
            "Es una curva a lo largo del ciclo (TTC): resume la historia observada, sin ajuste a "
            "las condiciones actuales ni escenarios"
        )
    tabla = _tabla_de_coeficientes(terminos)
    extra: list[tuple[str, pd.DataFrame, Mapping[str, _Kind]]] = []
    por_cartera = _pd_por_periodo_y_cartera(study, curva, unidad)
    if por_cartera is not None:
        formatos: dict[str, _Kind] = {"Período": "int"}
        formatos.update({str(c): "pct" for c in por_cartera.columns[2:]})
        extra.append(
            (
                "PD acumulada por período y cartera (promedio de las operaciones)",
                por_cartera,
                formatos,
            )
        )
    return StageSummary(
        stage="survival",
        label=STAGE_LABELS_CARTERA["survival"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=tabla,
        formats={"Coeficiente": "num", "Error estándar": "num", "p-valor": "pvalor"},
        extra_tables=tuple(extra),
    )


def _efectos_en_palabras(terminos: Any, covariables: Sequence[str]) -> str:
    """«más days_past_due, más riesgo; …» desde el signo y el p-valor de cada coeficiente."""
    if not isinstance(terminos, pd.DataFrame) or "term" not in terminos.columns:
        return ""
    por_termino = terminos.set_index("term")
    frases: list[str] = []
    for columna in covariables:
        if columna not in por_termino.index:
            continue
        frases.append(f"{columna}: {_efecto(por_termino.loc[columna])}")
    return "; ".join(frases)


def _efecto(fila: Any) -> str:
    coef = _float(fila.get("coef"))
    p_valor = _float(fila.get("p_value"))
    if coef is None:
        return "sin coeficiente"
    if p_valor is not None and p_valor > _P_SIN_EFECTO:
        return f"sin efecto distinguible de cero (p-valor {_pvalor(p_valor)})"
    return "más alto, más riesgo" if coef > 0 else "más alto, menos riesgo"


def _tabla_de_coeficientes(terminos: Any) -> pd.DataFrame | None:
    """Los coeficientes de la curva con signo, error estándar, p-valor y su efecto en palabras."""
    if not isinstance(terminos, pd.DataFrame) or terminos.empty:
        return None
    filas: list[dict[str, Any]] = []
    for _, fila in terminos.iterrows():
        termino = str(fila.get("term"))
        periodo = termino.removeprefix("period_")
        if termino.startswith("period_") and periodo.isdigit():
            nombre, efecto = f"Período {periodo}", "nivel base del período"
        else:
            nombre, efecto = termino, _efecto(fila)
        filas.append(
            {
                "Término": nombre,
                "Coeficiente": _float(fila.get("coef")),
                "Error estándar": _float(fila.get("std_error")),
                "p-valor": _float(fila.get("p_value")),
                "Efecto": efecto,
            }
        )
    return pd.DataFrame(filas)


def _pd_medias(curva: Any) -> tuple[float | None, float] | None:
    """PD acumulada media a un año y al final de la curva, sobre las operaciones (promedio simple).

    La de un año es la del último período que no supera un año de duración (``time_value`` en la
    unidad de la curva, convertida con :func:`year_fraction`); sin unidad convertible no se dice.
    """
    if not isinstance(curva, pd.DataFrame) or curva.empty:
        return None
    ordenada = curva.sort_values(["row_id", "period"], kind="mergesort")
    de_por_vida = _float(ordenada.groupby("row_id", sort=False)["pd_cumulative"].last().mean())
    if de_por_vida is None:
        return None
    anios = _en_anios(ordenada)
    un_anio: float | None = None
    if anios is not None:
        dentro = ordenada.loc[anios.le(1.0 + _TOL_ANIO).fillna(False)]
        if not dentro.empty:
            un_anio = _float(dentro.groupby("row_id", sort=False)["pd_cumulative"].last().mean())
    return un_anio, de_por_vida


def _en_anios(curva: pd.DataFrame) -> pd.Series | None:
    """``time_value`` en años, fila a fila; ``None`` si la curva no trae su unidad."""
    if "time_value" not in curva.columns or "time_unit" not in curva.columns:
        return None
    fracciones = curva["time_unit"].map(
        lambda u: year_fraction(str(u)) if u is not None and not pd.isna(u) else None
    )
    return pd.to_numeric(curva["time_value"], errors="coerce") * pd.to_numeric(
        fracciones, errors="coerce"
    )


def _pd_por_periodo_y_cartera(study: Study, curva: Any, unidad: Any) -> pd.DataFrame | None:
    """La PD acumulada media por período, por cartera y para toda la cartera.

    La cartera de cada operación se lee del frame que publicó ``data`` con la columna de cartera
    que declara la provisión de ESA corrida; sin ella, sólo «Toda la cartera».
    """
    if not isinstance(curva, pd.DataFrame) or curva.empty:
        return None
    base = curva[["row_id", "period", "pd_cumulative"]].copy()
    if "time_value" in curva.columns:
        base["time_value"] = curva["time_value"]
    carteras = _cartera_por_operacion(study)
    columnas: list[str] = []
    if carteras is not None:
        base["cartera"] = base["row_id"].astype(str).map(carteras)
        columnas = sorted(str(c) for c in base["cartera"].dropna().unique())
    filas: list[dict[str, Any]] = []
    for periodo, grupo in base.groupby("period", sort=True):
        tiempo = _float(grupo["time_value"].iloc[0]) if "time_value" in grupo.columns else None
        fila: dict[str, Any] = {"Período": _int(periodo), "Plazo": _plazo(tiempo, unidad)}
        for cartera in columnas:
            fila[cartera] = _float(grupo.loc[grupo["cartera"] == cartera, "pd_cumulative"].mean())
        fila["Toda la cartera"] = _float(grupo["pd_cumulative"].mean())
        filas.append(fila)
    return pd.DataFrame(filas)


def _cartera_por_operacion(study: Study) -> dict[str, str] | None:
    """``row_id`` → cartera, con el mismo identificador que usan la curva y la provisión."""
    frame = _artifact(study, "data", "frame")
    cartera_col = _hoja(_seccion(study, "provisioning_ifrs9"), "portfolio_col")
    if not isinstance(frame, pd.DataFrame) or not isinstance(cartera_col, str):
        return None
    if cartera_col not in frame.columns:
        return None
    id_col = _hoja(_seccion(study, "survival"), "input", "id_col")
    ids = (
        frame[id_col].astype(str)
        if isinstance(id_col, str) and id_col in frame.columns
        else pd.Series(frame.index.astype(str), index=frame.index)
    )
    return dict(zip(ids.tolist(), frame[cartera_col].astype(str).tolist(), strict=True))


def _plazo(tiempo: float | None, unidad: Any) -> str:
    """«1 año», «18 meses», «0,25 años»: el plazo de un período en la unidad de la curva."""
    if tiempo is None:
        return "—"
    entero = float(tiempo).is_integer()
    cantidad = int(tiempo) if entero else 2
    palabras = time_unit_words(unidad, cantidad)
    numero = _miles(int(tiempo)) if entero else _cifra(tiempo, decimales=2)
    return f"{numero} {palabras}" if palabras else f"{numero} ({unidad})"


def _singular(unidad: Any) -> str:
    return time_unit_words(unidad, 1) or str(unidad)


def _resumen_provision(study: Study, context: SummaryContext) -> StageSummary:
    """«Provisión IFRS 9»: etapas, ECL y cobertura, qué gatilló cada etapa y la EAD declarada."""
    card = _card(study, "provisioning_ifrs9", "card") or {}
    detalle = _artifact(study, "provisioning_ifrs9", "detail")
    staging = _artifact(study, "provisioning_ifrs9", "staging")
    resumen = _artifact(study, "provisioning_ifrs9", "summary")
    ifrs = _seccion(study, "provisioning_ifrs9")
    lines: list[str] = []
    alerts: list[str] = []
    ecl = _float(card.get("total_ecl_reported"))
    ead = _float(card.get("total_ead"))
    n_filas = _int(card.get("n_rows")) or 0
    cabecera = [f"{_miles(n_filas)} {_plural(n_filas, 'operación', 'operaciones')}"]
    if card.get("as_of_date"):
        cabecera.insert(0, f"Fecha de corte {card.get('as_of_date')}")
    if ead is not None:
        cabecera.append(f"exposición {_monto(ead)}")
    lines.append(" · ".join(cabecera))
    if ecl is not None:
        cobertura = f" · cobertura {_pct(ecl / ead)}" if ead else ""
        lines.append(f"ECL total {_monto(ecl)}{cobertura}")
    por_etapa = _por_etapa(detalle)
    if por_etapa:
        partes = [
            f"Stage {etapa}: {_miles(n)} ({_pct(exp / ead if ead else None)} de la exposición)"
            for etapa, (n, exp, _ecl) in sorted(por_etapa.items())
        ]
        lines.append(" · ".join(partes))
    lines.extend(_lineas_de_gatillos(staging, ifrs))
    if _hoja(ifrs, "staging", "is_default_col") is None:
        lines.append(
            "Sin marca de incumplimiento: el Stage 3 se asigna sólo por mora de "
            f"{_hoja(ifrs, 'staging', 'dpd_default_backstop')} días o más"
        )
    falta = tuple(str(c) for c in _sequence(card.get("falta_dato")))
    if "FALTA-DATO-IFRS-4" in falta:
        lines.append(_ead_constante())
    if str(card.get("pit_mode") or "") == "ttc_only":
        alerts.append(
            "La provisión usa la PD a lo largo del ciclo (TTC), sin ajuste a las condiciones "
            "actuales ni a escenarios macroeconómicos: IFRS 9 (5.5.17) pide considerar "
            "información razonable sobre el presente y el futuro"
        )
    if _staging_solo_por_mora(study, ifrs):
        con_marca = _hoja(ifrs, "staging", "is_default_col") is not None
        alerts.append(
            "El aumento significativo del riesgo se detecta sólo por la mora"
            + (" y la marca de incumplimiento" if con_marca else "")
            + ": la corrida no trae PD de origen, rating ni decisión cualitativa con que "
            "compararlo"
        )
    otras = [c for c in falta if c != "FALTA-DATO-IFRS-4"]
    alerts.extend(_capitalizar(d) for d in _declared_warning_descriptions(otras))
    extra: list[tuple[str, pd.DataFrame, Mapping[str, _Kind]]] = []
    gatillos = _tabla_de_gatillos(staging, ifrs)
    if gatillos is not None:
        extra.append(("Operaciones por etapa y gatillo", gatillos, {"Operaciones": "int"}))
    return StageSummary(
        stage="provisioning_ifrs9",
        label=STAGE_LABELS_CARTERA["provisioning_ifrs9"],
        lines=tuple(lines),
        alerts=tuple(alerts),
        table=_tabla_de_provision(resumen),
        formats={
            "Etapa": "int",
            "Operaciones": "int",
            "Exposición": "int",
            "ECL": "int",
            "Cobertura": "pct",
        },
        extra_tables=tuple(extra),
    )


def _por_etapa(detalle: Any) -> dict[int, tuple[int, float, float]]:
    """Operaciones, exposición y ECL por etapa, leídas del detalle por operación."""
    if not isinstance(detalle, pd.DataFrame) or "stage" not in detalle.columns:
        return {}
    salida: dict[int, tuple[int, float, float]] = {}
    for etapa, grupo in detalle.groupby("stage", sort=True):
        numero = _int(etapa)
        if numero is None:
            continue
        salida[numero] = (
            len(grupo.index),
            _suma(grupo, "ead"),
            _suma(grupo, "ecl_reported"),
        )
    return salida


def _suma(frame: pd.DataFrame, columna: str) -> float:
    """La suma numérica de una columna; cero si la columna no está."""
    if columna not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[columna], errors="coerce").sum())


def _rotulo_gatillo(gatillo: str, ifrs: Any) -> str:
    if gatillo == "dpd_sicr_backstop":
        return f"mora de {_hoja(ifrs, 'staging', 'dpd_sicr_backstop')} días o más"
    if gatillo == "dpd_default_backstop":
        return f"mora de {_hoja(ifrs, 'staging', 'dpd_default_backstop')} días o más"
    return _ROTULO_GATILLO.get(gatillo, gatillo)


def _conteo_de_gatillos(staging: Any) -> dict[int, dict[str, int]]:
    """Por etapa, cuántas operaciones dispararon cada gatillo de esa etapa (``sicr_triggers``)."""
    if not isinstance(staging, pd.DataFrame) or "sicr_triggers" not in staging.columns:
        return {}
    conteo: dict[int, dict[str, int]] = {}
    propios = {2: _GATILLOS_STAGE_2, 3: _GATILLOS_STAGE_3}
    for etapa, gatillos in zip(staging["stage"], staging["sicr_triggers"], strict=True):
        etapa_int = int(etapa)
        if etapa_int not in propios:
            continue
        for gatillo in _sequence(gatillos):
            if str(gatillo) in propios[etapa_int]:
                por_gatillo = conteo.setdefault(etapa_int, {})
                por_gatillo[str(gatillo)] = por_gatillo.get(str(gatillo), 0) + 1
    return conteo


def _lineas_de_gatillos(staging: Any, ifrs: Any) -> list[str]:
    """Las líneas «Qué llevó a Stage 2/3: …» con los gatillos que dispararon en ESTA corrida."""
    lineas: list[str] = []
    conteo = _conteo_de_gatillos(staging)
    for etapa in (2, 3):
        por_gatillo = conteo.get(etapa)
        if not por_gatillo:
            continue
        orden = _GATILLOS_STAGE_2 if etapa == 2 else _GATILLOS_STAGE_3
        partes = [
            f"{_rotulo_gatillo(g, ifrs)} ({_miles(por_gatillo[g])})"
            for g in orden
            if g in por_gatillo
        ]
        lineas.append(f"Qué llevó a Stage {etapa}: {_enumerar(partes)}")
    if isinstance(staging, pd.DataFrame) and "low_credit_risk_exempt" in staging.columns:
        exentas = int(staging["low_credit_risk_exempt"].astype("boolean").fillna(False).sum())
        if exentas:
            lineas.append(
                f"{_miles(exentas)} {_plural(exentas, 'operación quedó', 'operaciones quedaron')} "
                "en Stage 1 por la exención de bajo riesgo crediticio"
            )
    return lineas


def _tabla_de_gatillos(staging: Any, ifrs: Any) -> pd.DataFrame | None:
    """Operaciones por etapa y gatillo; una operación cuenta en cada gatillo que disparó."""
    if not isinstance(staging, pd.DataFrame) or "stage" not in staging.columns:
        return None
    filas: list[dict[str, Any]] = []
    sin_gatillo = 0
    if "sicr_triggers" in staging.columns:
        sin_gatillo = int(
            sum(
                1
                for etapa, gatillos in zip(staging["stage"], staging["sicr_triggers"], strict=True)
                if int(etapa) == 1 and not _sequence(gatillos)
            )
        )
    if sin_gatillo:
        filas.append({"Etapa": 1, "Gatillo": "ninguno", "Operaciones": sin_gatillo})
    conteo = _conteo_de_gatillos(staging)
    for etapa in (2, 3):
        orden = _GATILLOS_STAGE_2 if etapa == 2 else _GATILLOS_STAGE_3
        for gatillo in orden:
            n = conteo.get(etapa, {}).get(gatillo)
            if n:
                filas.append(
                    {"Etapa": etapa, "Gatillo": _rotulo_gatillo(gatillo, ifrs), "Operaciones": n}
                )
    return pd.DataFrame(filas) if filas else None


def _tabla_de_provision(resumen: Any) -> pd.DataFrame | None:
    """ECL por cartera y etapa (filas, exposición, ECL y cobertura), de la tabla de la provisión."""
    if not isinstance(resumen, pd.DataFrame) or resumen.empty:
        return None
    tabla = resumen
    if "scenario" in tabla.columns and tabla["scenario"].astype(str).eq("all").any():
        tabla = tabla.loc[tabla["scenario"].astype(str).eq("all")]
    return pd.DataFrame(
        {
            "Cartera": tabla["portfolio"].astype(str).to_numpy(),
            "Etapa": pd.to_numeric(tabla["stage"], errors="coerce").to_numpy(),
            "Operaciones": pd.to_numeric(tabla["n_rows"], errors="coerce").to_numpy(),
            "Exposición": pd.to_numeric(tabla["total_ead"], errors="coerce").round().to_numpy(),
            "ECL": pd.to_numeric(tabla["total_ecl_reported"], errors="coerce").round().to_numpy(),
            "Cobertura": pd.to_numeric(tabla["coverage_ratio"], errors="coerce").to_numpy(),
        }
    )


def _staging_solo_por_mora(study: Study, ifrs: Any) -> bool:
    """Si ningún gatillo alternativo a la mora y la marca estaba disponible en ESTA corrida."""
    if ifrs is None:
        return False
    frame = _artifact(study, "data", "frame")
    columnas = set(frame.columns) if isinstance(frame, pd.DataFrame) else set()
    return (
        _hoja(ifrs, "staging", "origination_pd_life_col") is None
        and _COLUMNA_PD_PIT_ORIGEN not in columnas
        and _hoja(ifrs, "staging", "notch_downgrade_threshold") is None
        and _hoja(ifrs, "staging", "stage_override_col") is None
    )


def _ead_constante() -> str:
    """La EAD constante declarada (IFRS-4), en palabras y con su consecuencia (§3.14)."""
    return (
        f"{_capitalizar(_DECLARED_WARNING_PROSE['FALTA-DATO-IFRS-4'])}: si la cartera amortiza, la "
        "ECL de por vida queda sobrestimada"
    )


_BUILDERS: Final[dict[str, Callable[[Study, SummaryContext], StageSummary]]] = {
    "data": _resumen_data,
    "eda": _resumen_eda,
    "binning": _resumen_binning,
    "selection": _resumen_selection,
    "model": _resumen_model,
    "scorecard": _resumen_scorecard,
    "calibration": _resumen_calibration,
    "performance": _resumen_performance,
    "stability": _resumen_stability,
    "validation": _resumen_validation,
    "report": _resumen_report,
}
_BUILDERS_CARTERA: Final[dict[str, Callable[[Study, SummaryContext], StageSummary]]] = {
    "data": _resumen_cartera,
    "survival": _resumen_curva,
    "provisioning_ifrs9": _resumen_provision,
    "report": _resumen_report,
}


# ────────────────────────────── resumen final ──────────────────────────────


def build_final_summary(
    study: Study | None,
    stages: Sequence[StageSummary],
    context: SummaryContext,
) -> FinalSummary:
    """Ejecución y validación técnica por separado, cinco cifras, alertas, decisiones y archivos.

    Una provisión (familia de cartera) no tiene veredicto técnico: en su lugar dice sus
    «Supuestos», y sus cinco cifras son las de la provisión (:func:`_resumen_final_cartera`).
    """
    familia = family_of(getattr(study, "config", None)) if study is not None else context.family
    if familia == "cartera":
        return _resumen_final_cartera(study, stages, context)
    execution = _estado_de_ejecucion(study, stages, context)
    validation = _estado_de_validacion(study, context)
    figures = _cinco_cifras(study) if study is not None else ()
    review = (
        *(f"{s.label}: {a}" for s in stages for a in s.alerts),
        *(f"{_ROTULO_DECISIONES}: {a}" for a in _decisiones_sin_efecto(study)),
    )
    files = _archivos(study, context)
    return FinalSummary(
        execution=execution,
        validation=validation,
        figures=figures,
        review=review,
        decisions=tuple(context.decision_lines),
        files=files,
        stages=tuple(stages),
    )


def _decisiones_sin_efecto(study: Study | None) -> tuple[str, ...]:
    """Las decisiones del registro que ya no están aplicadas en el config, como alertas (D-DEC-3).

    Se leen del preámbulo que la corrida persistió (``decision_sin_efecto``, que el motor declara
    en vez de atribuírselas a una persona): «La decisión «set_bins monto — motivo» ya no está
    aplicada: sus cortes cambiaron en el config». Precedente: ``point_override_sin_casar``.
    """
    if study is None:
        return ()
    alertas: list[str] = []
    for _paso, payload in getattr(study, "preamble", ()) or ():
        if str(payload.get("regla", "")) != _REGLA_DECISION_SIN_EFECTO:
            continue
        variables = [str(v) for v in _sequence(payload.get("variables"))]
        accion = str(payload.get("accion", ""))
        motivo = str(payload.get("motivo", ""))
        varias = len(variables) > 1
        if accion in {"merge_bins", "set_bins"}:
            razon = "sus cortes cambiaron en el config"
        elif accion == "rebut_backstops":
            razon = "los días de mora de Stage 2 o Stage 3 cambiaron en el config"
        elif accion == "exclude":
            razon = (
                "las variables ya no están excluidas en el config"
                if varias
                else "la variable ya no está excluida en el config"
            )
        else:
            razon = (
                "las variables ya no están forzadas en el config"
                if varias
                else "la variable ya no está forzada en el config"
            )
        sujeto = f"{accion} {', '.join(variables)}" if variables else accion
        alertas.append(f"La decisión «{sujeto} — {motivo}» ya no está aplicada: {razon}.")
    return tuple(alertas)


def _estado_de_ejecucion(
    study: Study | None,
    stages: Sequence[StageSummary],
    context: SummaryContext,
    rotulos: Mapping[str, str] = STAGE_LABELS,
) -> str:
    if study is None:
        return "sin correr todavía"
    estado = study.run_context.status
    caidos = _analisis_exploratorios_caidos(study)
    if estado == "running":
        # El informe se renderiza con la corrida todavía en curso: no afirma «completada» —eso lo
        # dice summary() al terminar— sino qué corrió sin fallos hasta aquí y, si `run.steps`
        # puso pasos después del informe, cuáles quedan y que este documento no los refleja.
        corrieron = _enumerar([s.label for s in stages]) if stages else "ninguna etapa"
        if caidos:
            # D-SC-20: con un análisis exploratorio parcial, «sin fallos» sería falso. Una corrida
            # sana no entra aquí y conserva byte a byte las dos frases de abajo.
            parcial = (
                "el análisis exploratorio, de forma parcial: "
                f"{_miles(caidos)} de sus análisis no se "
                f"{_plural(caidos, 'pudo', 'pudieron')} calcular (ver «Qué revisar»)"
            )
            if context.pending_stages:
                quedan = _enumerar([rotulos.get(s, s) for s in context.pending_stages])
                return (
                    f"corrieron {corrieron} antes de este informe; {parcial}; después del informe "
                    f"quedan por correr {quedan}, y este documento no puede reflejarlas"
                )
            return (
                f"corrieron {corrieron}; {parcial}; este informe es la última etapa de la corrida"
            )
        if context.pending_stages:
            quedan = _enumerar([rotulos.get(s, s) for s in context.pending_stages])
            return (
                f"corrieron sin fallos {corrieron} antes de este informe; después de él quedan "
                f"por correr {quedan}, y este documento no puede reflejarlas"
            )
        return f"corrieron sin fallos {corrieron}; este informe es la última etapa de la corrida"
    if estado == "done":
        cola = " — con el análisis exploratorio parcial" if caidos else ""
        if context.until is not None:
            hasta = rotulos.get(context.until, context.until)
            return f"completada hasta «{hasta}» (corrida parcial){cola}"
        return f"completada{cola}"
    if estado == "failed":
        error = study.run_context.error
        etapa = rotulos.get(str(getattr(error, "step", None)), str(getattr(error, "step", None)))
        mensaje = getattr(error, "message", "") if error is not None else ""
        donde = f" en «{etapa}»" if getattr(error, "step", None) else " antes del primer paso"
        return f"fallida{donde}: {mensaje}"
    return estado


def _analisis_exploratorios_caidos(study: Study) -> int:
    """Cuántos sub-análisis de `eda` no se pudieron calcular (D-SC-19); 0 si no corrió."""
    card = _card(study, "eda", "eda_card")
    return len(_mapping(card.get("failed_analyses"))) if card is not None else 0


def _estado_de_validacion(study: Study | None, context: SummaryContext) -> str:
    if study is None:
        return "sin correr todavía"
    card = _card(study, "validation", "card")
    if card is None:
        if "validation" in context.pending_stages:
            return "no había corrido al emitir este informe: viene después en el pipeline"
        if context.until is not None:
            return "no corrió: la corrida se detuvo antes de la validación formal"
        if study.run_context.status == "failed":
            return "no corrió: la corrida falló antes"
        return "no corrió: la validación formal no está en el config"
    estado = str(card.get("overall_status", ""))
    rotulo = VALIDATION_STATUS_LABELS.get(estado, estado)
    decisivas = _pruebas_decisivas(study)
    return f"{rotulo}" + (f" — lo decide {_enumerar(decisivas)}" if decisivas else "")


def _cinco_cifras(study: Study) -> tuple[tuple[str, str], ...]:
    """Las cinco cifras del resumen final.

    AUC, Gini y KS en la muestra fuera de tiempo (o la última disponible), caída del AUC de
    Desarrollo a esa muestra y peor PSI con su banda.
    """
    cifras: list[tuple[str, str]] = []
    performance = _card(study, "performance", "card")
    if performance is not None:
        maximos = _mapping(performance.get("max_metrics_by_partition"))
        destino = "oot" if "oot" in maximos else ("holdout" if "holdout" in maximos else None)
        if destino is not None:
            valores = _mapping(maximos.get(destino))
            rotulo = _partition_label(destino)
            cifras.append((f"AUC en {rotulo}", _cifra(valores.get("auc"), decimales=3)))
            cifras.append((f"Gini en {rotulo}", _cifra(valores.get("gini"), decimales=3)))
            cifras.append((f"KS en {rotulo}", _cifra(valores.get("ks"), decimales=3)))
            dev = _float(_mapping(maximos.get("desarrollo")).get("auc"))
            fuera = _float(valores.get("auc"))
            if dev is not None and fuera is not None:
                delta = fuera - dev
                relativo = f" ({_pct(delta / dev, decimals=1)})" if dev else ""
                cifras.append(
                    (
                        f"Caída del AUC Desarrollo → {rotulo}",
                        f"{_cifra(delta, decimales=3)}{relativo}",
                    )
                )
    stability = _card(study, "stability", "card")
    if stability is not None:
        maximos_psi = _mapping(stability.get("max_psi_by_comparison"))
        bandas = _mapping(stability.get("bands_by_comparison"))
        peor: tuple[str, float] | None = None
        for cid, valor in maximos_psi.items():
            v = _float(valor)
            if v is not None and (peor is None or v > peor[1]):
                peor = (str(cid), v)
        if peor is not None:
            banda = BAND_LABELS.get(str(bandas.get(peor[0], "")), str(bandas.get(peor[0], "")))
            cifras.append(
                (
                    "Peor PSI entre score y PD",
                    f"{_cifra(peor[1])} ({_COMPARISON_LABELS.get(peor[0], peor[0])}) → {banda}",
                )
            )
    return tuple(cifras)


def _resumen_final_cartera(
    study: Study | None, stages: Sequence[StageSummary], context: SummaryContext
) -> FinalSummary:
    """El resumen final de una provisión: ejecución, supuestos, cinco cifras, alertas y archivos."""
    return FinalSummary(
        execution=_estado_de_ejecucion(study, stages, context, STAGE_LABELS_CARTERA),
        validation=SIN_VEREDICTO_TECNICO,
        figures=_cinco_cifras_cartera(study) if study is not None else (),
        review=(
            *(f"{s.label}: {a}" for s in stages for a in s.alerts),
            *(f"{_ROTULO_DECISIONES}: {a}" for a in _decisiones_sin_efecto(study)),
        ),
        decisions=tuple(context.decision_lines),
        files=_archivos(study, context),
        stages=tuple(stages),
        title=_TITULOS["cartera"],
        assumptions=_supuestos(study) if study is not None else (),
        family="cartera",
    )


def _cinco_cifras_cartera(study: Study) -> tuple[tuple[str, str], ...]:
    """ECL total, cobertura, exposición y ECL en Stage 2 y 3, y PD a 12 meses ponderada (§3.8)."""
    card = _card(study, "provisioning_ifrs9", "card")
    detalle = _artifact(study, "provisioning_ifrs9", "detail")
    if card is None:
        return ()
    ecl = _float(card.get("total_ecl_reported"))
    ead = _float(card.get("total_ead"))
    cifras: list[tuple[str, str]] = []
    if ecl is not None:
        cifras.append((_ROTULO_ECL_TOTAL, _monto(ecl)))
    if ecl is not None and ead:
        cifras.append(("Cobertura (ECL sobre la exposición)", _pct(ecl / ead)))
    por_etapa = _por_etapa(detalle)
    if por_etapa:
        exp_total = sum(exp for _n, exp, _e in por_etapa.values())
        ecl_total = sum(e for _n, _exp, e in por_etapa.values())
        exp_23 = sum(exp for etapa, (_n, exp, _e) in por_etapa.items() if etapa in (2, 3))
        ecl_23 = sum(e for etapa, (_n, _exp, e) in por_etapa.items() if etapa in (2, 3))
        cifras.append(
            ("Exposición en Stage 2 y 3", _pct(exp_23 / exp_total if exp_total else None))
        )
        cifras.append(("ECL de Stage 2 y 3", _pct(ecl_23 / ecl_total if ecl_total else None)))
    if isinstance(detalle, pd.DataFrame) and {"pd_12m", "ead"} <= set(detalle.columns):
        pesos = pd.to_numeric(detalle["ead"], errors="coerce")
        pds = pd.to_numeric(detalle["pd_12m"], errors="coerce")
        suma = float(pesos.sum())
        if suma:
            cifras.append(
                (
                    "PD a 12 meses media, ponderada por la exposición",
                    _pct(float((pds * pesos).sum()) / suma),
                )
            )
    return tuple(cifras)


def _supuestos(study: Study) -> tuple[str, ...]:
    """Lo que la cifra supone, leído del config y de los artefactos de ESA corrida (§3.8).

    Nunca del preset F4 ni de la puerta guiada: un YAML o la pantalla pueden correr Vasicek,
    escenarios ponderados o PD de originación, y el resumen tiene que decir lo que corrió.
    """
    card = _card(study, "provisioning_ifrs9", "card") or {}
    ifrs = _seccion(study, "provisioning_ifrs9")
    survival = _seccion(study, "survival")
    supuestos: list[str] = []
    pit_mode = str(card.get("pit_mode") or _hoja(ifrs, "pd", "pit_mode") or "")
    if pit_mode == "ttc_only":
        supuestos.append(
            "La PD es a lo largo del ciclo (TTC): no se ajusta a las condiciones actuales ni a "
            "escenarios macroeconómicos"
        )
    elif pit_mode:
        supuestos.append(f"La PD es {_IFRS9_PIT_MODE_LABELS.get(pit_mode, pit_mode)}")
    escenarios = tuple(str(s) for s in _sequence(card.get("scenarios")))
    pesos = _mapping(card.get("scenario_weights"))
    if len(escenarios) > 1:
        detalle = ", ".join(f"{s} ({_pct(pesos.get(s), decimals=0)})" for s in escenarios)
        supuestos.append(f"Escenarios ponderados: {detalle}")
    elif escenarios:
        supuestos.append("Un escenario único, sin ponderación macroeconómica")
    if str(card.get("term_structure_source") or "") == "survival" and survival is not None:
        covariables = tuple(_sequence(_hoja(survival, "input", "covariate_cols")))
        if covariables:
            supuestos.append(
                "La curva de PD se ajusta a la historia de incumplimientos de la propia cartera, "
                f"con {_miles(len(covariables))} "
                f"{_plural(len(covariables), 'covariable', 'covariables')}"
            )
        else:
            supuestos.append("Una sola curva de PD para toda la cartera, sin covariables")
    horizonte = _int(_hoja(ifrs, "pd", "horizon_12m_periods"))
    unidad = _hoja(survival, "time_grid", "time_unit") if survival is not None else None
    if horizonte is not None:
        palabras = time_unit_words(unidad, horizonte) if unidad is not None else None
        supuestos.append(
            f"Los 12 meses del Stage 1 son {_miles(horizonte)} "
            + (palabras if palabras else _plural(horizonte, "período", "períodos"))
            + " de la curva"
        )
    s2 = _int(_hoja(ifrs, "staging", "dpd_sicr_backstop"))
    s3 = _int(_hoja(ifrs, "staging", "dpd_default_backstop"))
    if s2 is not None and s3 is not None:
        if (s2, s3) == (_PRESUNCION_STAGE_2, _PRESUNCION_STAGE_3):
            supuestos.append(
                f"Stage 2 desde {s2} días de mora y Stage 3 desde {s3}: las presunciones de "
                "IFRS 9 (5.5.11 y B5.5.37)"
            )
        else:
            supuestos.append(
                f"Stage 2 desde {s2} días de mora y Stage 3 desde {s3}, frente a las presunciones "
                f"de IFRS 9 de {_PRESUNCION_STAGE_2} y {_PRESUNCION_STAGE_3}"
            )
    if "FALTA-DATO-IFRS-4" in tuple(str(c) for c in _sequence(card.get("falta_dato"))):
        supuestos.append(_ead_constante())
    if _hoja(ifrs, "lgd", "method") == "provided":
        supuestos.append("La LGD es la del archivo de cartera, la misma en cada período")
    return tuple(supuestos)


def _archivos(study: Study | None, context: SummaryContext) -> tuple[tuple[str, str], ...]:
    archivos: list[tuple[str, str]] = []
    if context.project_dir is not None:
        archivos.append(("Carpeta del proyecto", str(context.project_dir)))
    if context.config_path is not None:
        archivos.append(("Config vigente", str(context.config_path)))
    if context.run_dir is not None:
        archivos.append(("Evidencia de la corrida", str(context.run_dir)))
    if context.trail_path is not None:
        archivos.append(("Registro de auditoría", str(context.trail_path)))
    if context.card_path is not None:
        archivos.append(("Ficha del modelo", str(context.card_path)))
    resultado = _artifact(study, "report", "result") if study is not None else None
    for atributo, rotulo in (
        ("html_path", "Informe HTML"),
        ("docx_path", "Informe Word"),
        ("pdf_path", "Informe PDF"),
        ("md_path", "Fuente editable (Quarto)"),
    ):
        ruta = getattr(resultado, atributo, None) if resultado is not None else None
        if ruta:
            archivos.append((rotulo, _ruta_absoluta(ruta, context)))
    archivos.extend(context.extra_files)
    # Un rótulo, una ruta, y gana la ÚLTIMA: `extra_files` es lo que sabe quien arma el contexto
    # —el informe que se está generando ahora— y el artefacto `report.result` que un `Study`
    # recargado conserva es el del informe ANTERIOR. Sin esto, regenerar un informe con otro
    # `output_dir` o `basename` publicaba dos «Informe HTML» con destinos incompatibles, y con el
    # mismo config, la misma ruta dos veces (pasada 6 de Codex sobre la capa C).
    ultimas: dict[str, str] = {}
    for rotulo, ruta in archivos:
        ultimas[rotulo] = ruta
    return tuple(ultimas.items())


# ────────────────────────────── utilidades ──────────────────────────────


def _formatear(table: pd.DataFrame, formats: Mapping[str, _Kind]) -> pd.DataFrame:
    """La tabla con cada celda ya escrita como la lee una persona (coma decimal, miles)."""
    salida = table.copy()
    for columna in salida.columns:
        tipo = formats.get(str(columna))
        if tipo is None:
            if pd.api.types.is_float_dtype(salida[columna].dtype):
                tipo = "num"
            elif pd.api.types.is_integer_dtype(salida[columna].dtype) and es_columna_de_conteo(
                str(columna)
            ):
                tipo = "int"
            else:
                salida[columna] = salida[columna].map(_celda_texto)
                continue
        salida[columna] = salida[columna].map(lambda v, t=tipo: _celda(v, t))
    return salida


def _celda(valor: Any, tipo: _Kind) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or valor is pd.NA:
        return "—"
    if tipo == "int":
        return _miles(int(valor))
    if tipo == "pct":
        return _pct(valor)
    if tipo == "num2":
        return _cifra(valor, decimales=2)
    if tipo == "num3":
        return _cifra(valor, decimales=3)
    if tipo == "num":
        return _cifra(valor)
    if tipo == "bool":
        return "sí" if bool(valor) else "no"
    if tipo == "pvalor":
        # D-CPY-4: la regla de las frases —«< 0,001» y tres decimales— también en las tablas.
        return _pvalor(valor)
    return _celda_texto(valor)


def _celda_texto(valor: Any) -> str:
    if valor is None or valor is pd.NA or (isinstance(valor, float) and pd.isna(valor)):
        return "—"
    if isinstance(valor, bool | np.bool_):
        return "sí" if bool(valor) else "no"
    return str(valor)


#: Bajo este valor absoluto, un desplazamiento del intercepto es ruido de coma flotante.
_RUIDO_DEL_INTERCEPTO: Final = 1e-12


def _sin_ruido(valor: Any) -> Any:
    """El desplazamiento del intercepto, con el ruido de coma flotante escrito como cero.

    Cuando la calibración ancla a la tasa observada, el desplazamiento es cero salvo el residuo del
    solver (``-1,01e-16`` en Windows, ``-2,7e-16`` en Linux): la regla del informe lo escribiría en
    notación científica, distinto en cada plataforma, y el cuaderno publicado dejaría de ser
    reproducible (CI de ``be3130e``). Es presentación: el número del artefacto no cambia.
    """
    numero = _float(valor)
    if numero is not None and abs(numero) < _RUIDO_DEL_INTERCEPTO:
        return 0.0
    return valor


def _frente(valor: Any, umbral: Any, *, decimales: int = 4) -> str:
    """Una observación junto a su corte, con los decimales que la dejan de su lado (D-PAN-3).

    Pasada 1 de Codex sobre el código: con 0.249962 frente a 0,24996, la alerta decía «0,24996
    supera el umbral 0,24996».
    """
    numero, corte_ = _float(valor), _float(umbral)
    if numero is None or corte_ is None:
        return _cifra(valor, decimales=decimales)
    return frente_al_corte(cifra(numero, decimales=decimales), numero, corte_)


def _pvalor_frente(valor: Any, umbral: Any) -> str:
    """Un p-valor junto a su corte: «< 0,001» no dice el lado de un corte menor que 0,001."""
    numero, corte_ = _float(valor), _float(umbral)
    if numero is None or corte_ is None:
        return _pvalor(valor)
    escrito = pvalor(numero)
    if escrito.startswith("<") and corte_ < 0.001:
        escrito = cifra(numero)
    return frente_al_corte(escrito, numero, corte_)


def _corte_pct(valor: Any) -> str:
    """Un corte que es una proporción, como porcentaje exacto; «No disponible» si falta."""
    numero = _float(valor)
    return corte_porcentual(numero) if numero is not None else _cifra(valor)


def _pvalor(valor: Any) -> str:
    numero = _float(valor)
    if numero is None:
        return "—"
    return pvalor(numero)


def _ruta_absoluta(ruta: Any, context: SummaryContext) -> str:
    camino = Path(str(ruta))
    if camino.is_absolute():
        return str(camino)
    return str((Path.cwd() / camino).resolve())


def _rotulo(mapa: Mapping[str, str], valor: Any) -> str:
    """La palabra pública de un identificador, o el identificador si el mapa no lo trae."""
    return mapa.get(str(valor), str(valor))


def _sin_sufijo(valor: Any) -> str:
    return str(valor).removesuffix("__points").removesuffix("__bin")


def _orden_particion(particion: str) -> int:
    return {"desarrollo": 0, "holdout": 1, "oot": 2}.get(particion, 3)


def _partition_label(partition: str) -> str:
    return _PARTITION_LABELS.get(partition, partition)


def _capitalizar(texto: str) -> str:
    return texto[:1].upper() + texto[1:] if texto else texto


def _seccion(study: Study | None, nombre: str) -> Any:
    """La sección ``nombre`` del config de la corrida, o ``None``."""
    return getattr(getattr(study, "config", None), nombre, None)


def _hoja(objeto: Any, *ruta: str) -> Any:
    """Una hoja del config por su ruta, sea la sección un modelo o un ``dict`` opaco."""
    actual = objeto
    for parte in ruta:
        if actual is None:
            return None
        actual = actual.get(parte) if isinstance(actual, Mapping) else getattr(actual, parte, None)
    return actual


def _monto(valor: float) -> str:
    """Un monto redondeado a la unidad, con punto de miles y sin moneda (D-MON-5)."""
    return _miles(round(valor))


def _fecha_legible(valor: Any) -> str:
    """Una fecha de corte como ``2025-06-30``, venga como texto, fecha o marca de tiempo."""
    if isinstance(valor, str):
        return valor
    marca = pd.to_datetime(valor, errors="coerce")
    if isinstance(marca, pd.Timestamp) and not pd.isna(marca):
        return marca.date().isoformat()
    return str(valor)


def _tabla_transportable(
    tabla: pd.DataFrame | None, formatos: Mapping[str, _Kind]
) -> dict[str, Any] | None:
    """Una tabla con las celdas ya escritas como las lee una persona (el JSON de la pantalla)."""
    if tabla is None or tabla.empty:
        return None
    mostrada = _formatear(tabla, formatos)
    return {
        "columns": [str(c) for c in mostrada.columns],
        "rows": [[str(v) for v in fila] for fila in mostrada.itertuples(index=False)],
    }


def _artifact(study: Study | None, domain: str, key: str) -> Any:
    if study is None or not study.artifacts.has(domain, key):
        return None
    return study.artifacts.get(domain, key)


def _card(study: Study, domain: str, key: str) -> Mapping[str, Any] | None:
    valor = _artifact(study, domain, key)
    if valor is None:
        return None
    if isinstance(valor, Mapping):
        return valor
    dump = getattr(valor, "model_dump", None)
    if callable(dump):
        volcado = dump(mode="python")
        return volcado if isinstance(volcado, Mapping) else None
    return None


def _mapping(valor: Any) -> Mapping[str, Any]:
    return valor if isinstance(valor, Mapping) else {}


def _sequence(valor: Any) -> tuple[Any, ...]:
    if isinstance(valor, str | bytes) or valor is None:
        return ()
    if isinstance(valor, Iterable):
        return tuple(valor)
    return ()


def _int(valor: Any) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        if isinstance(valor, float) and pd.isna(valor):
            return None
        return int(valor)
    except (TypeError, ValueError):
        return None


def _float(valor: Any) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(numero) else numero
