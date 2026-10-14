"""Paso orquestable de la capa ``comparison`` (SDD-34 §2, §6.2, §7; CT-1).

``ComparisonStep`` corre en una corrida propia sin ``data`` (D-CMP-1): no requiere ningún
artefacto; lee el **resumen comparable** de cada corrida de ``comparison.runs`` (§6.1), los pone
lado a lado y publica ``("comparison", clave)``. Nunca vuelve a correr ni a puntuar un modelo, no
elige un ganador y no abre una carpeta con ``Study.load``. La huella de cada resumen, en orden,
queda en el lineage (``comparison_hashes``); las rutas, fuera del ``config_hash`` (§5.3).

La función pura :func:`comparar` hace todo el cálculo sobre los resúmenes ya leídos; el paso sólo
los lee, la llama, declara al registro de auditoría lo que comparó y publica.

**Experimental (fuera de la garantía SemVer 2.x).** Sale en la 2.15.0 (capa A del SDD-34).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

from bayesrisk.comparison.comparable import RECETA_PSI_DE_FABRICA, huella, leer
from bayesrisk.comparison.config import MAX_RUNS, MIN_RUNS, ComparisonConfig
from bayesrisk.comparison.exceptions import ComparisonDataError
from bayesrisk.core.mixins import AuditableMixin
from bayesrisk.core.registry import register
from bayesrisk.core.steps import ArtifactKey

if TYPE_CHECKING:
    import numpy as np

    from bayesrisk.comparison.results import ComparisonResult
    from bayesrisk.core.audit import AuditEvent
    from bayesrisk.core.study import Study

__all__ = [
    "COMPARISON_ARTIFACTS",
    "ComparisonStep",
    "comparar",
    "eleccion_registrada",
    "nombres_visibles",
]

COMPARISON_ARTIFACTS: Final[tuple[str, ...]] = (
    "runs",
    "models",
    "tests",
    "samples",
    "variables",
    "provision",
    "reading",
    "result",
    "card",
)
#: La hoja con que ``choose`` registra la huella del resumen elegido (D-CMP-6, extensión de D-DEC).
HOJA_DE_LA_ELECCION: Final = "comparison.choice"
_FUERA_DE_EVALUACION: Final = frozenset({"desarrollo"})


@register("standard", domain="comparison")
class ComparisonStep(AuditableMixin):
    """Pone lado a lado los resúmenes comparables de entre 2 y 10 corridas terminadas."""

    name: str = "comparison"
    requires: tuple[ArtifactKey, ...] = ()
    provides: tuple[ArtifactKey, ...] = tuple(("comparison", key) for key in COMPARISON_ARTIFACTS)

    def __init__(self, config: ComparisonConfig) -> None:
        """Construye el paso desde la sección ``ComparisonConfig`` ya validada."""
        self.config = config

    @classmethod
    def from_config(cls, cfg: ComparisonConfig) -> ComparisonStep:
        """Construye ``ComparisonStep`` desde ``BayesRiskConfig.comparison``."""
        return cls(cfg)

    def emit(self, event: AuditEvent) -> None:
        """Permite pasar el paso como ``AuditSink``."""
        self._audit.emit(event)

    def execute(self, study: Study, rng: np.random.Generator) -> ComparisonResult:
        """Lee los resúmenes, compara, declara al registro y publica los artefactos de §6.2."""
        del rng
        resumenes = [leer(ruta)[0] for ruta in self.config.runs]
        resultado = comparar(resumenes, eleccion=eleccion_registrada(study.config))
        self._declarar(resultado)
        self._publicar(study, resultado)
        return resultado

    def _declarar(self, resultado: ComparisonResult) -> None:
        """Cada corrida comparada con su huella y su nivel; los modelos repetidos (§9)."""
        runs = resultado.runs
        for _, fila in runs.iterrows():
            self.log_decision(
                regla="corrida_comparada",
                umbral=None,
                valor={
                    "posicion": int(fila["position"]),
                    "nombre": str(fila["name"]),
                    "config_hash": fila["config_hash"],
                    "bayesrisk": fila["bayesrisk"],
                    "huella": str(fila["summary_hash"]),
                    "nivel": str(fila["level"]),
                },
                accion="comparar",
                step=self.name,
            )
        for copia, original in resultado.card.same_as.items():
            self.log_decision(
                regla="mismo_modelo",
                umbral=None,
                valor={"nombre": copia, "igual_a": original},
                accion="declarar",
                step=self.name,
            )

    def _publicar(self, study: Study, resultado: ComparisonResult) -> None:
        """Publica los artefactos y ancla al lineage la huella de cada resumen (§9).

        La huella se escribe si y sólo si ESTE intento dejó guardado algún artefacto, como la
        tarjeta del monitoreo (D-MNT-1): un paso repetido sobre una corrida terminada choca con su
        evidencia y no le cambia las huellas.
        """
        objetos: tuple[tuple[str, Any], ...] = (
            ("runs", resultado.runs.copy(deep=True)),
            ("models", resultado.models.copy(deep=True)),
            ("tests", resultado.tests.copy(deep=True)),
            ("samples", resultado.samples.copy(deep=True)),
            ("variables", resultado.variables.copy(deep=True)),
            ("provision", resultado.provision.copy(deep=True)),
            ("reading", tuple(resultado.reading)),
            ("result", resultado),
            ("card", resultado.card.model_copy(deep=True)),
        )
        try:
            for clave, objeto in objetos:
                study.artifacts.set("comparison", clave, objeto)
        finally:
            propios = any(
                study.artifacts.has("comparison", clave)
                and study.artifacts.get("comparison", clave) is objeto
                for clave, objeto in objetos
            )
            lineage = study.run_context.lineage
            if propios and lineage is not None:
                lineage.comparison_hashes = tuple(resultado.card.summary_hashes)


# ── la elección registrada (D-CMP-6) ─────────────────────────────────────────────────────────


def eleccion_registrada(config: Any) -> dict[str, str] | None:
    """La última elección de ``config.decisions``: ``{huella, name, reason}``, o ``None``.

    La decisión se ata a la **huella** del resumen elegido, no al nombre ni a la posición: si esa
    huella ya no está entre las comparadas, no hay elección vigente (D-DEC la declara sin efecto).
    """
    registros = tuple(getattr(config, "decisions", ()) or ())
    for registro in reversed(registros):
        if getattr(registro, "action", None) == "choose":
            valor = dict(getattr(registro, "value", {}) or {})
            return {
                "huella": str(valor.get(HOJA_DE_LA_ELECCION, "")),
                "name": str(registro.columns[0]),
                "reason": str(registro.reason),
            }
    return None


# ── comparar ─────────────────────────────────────────────────────────────────────────────────


def nombres_visibles(nombres: Sequence[str]) -> tuple[str, ...]:
    """Los nombres de las corridas; uno repetido se distingue con su posición («consumo (2)»)."""
    conteo: dict[str, int] = {}
    for nombre in nombres:
        conteo[nombre] = conteo.get(nombre, 0) + 1
    return tuple(
        f"{nombre} ({posicion})" if conteo[nombre] > 1 else nombre
        for posicion, nombre in enumerate(nombres, start=1)
    )


def _validar_entrada(resumenes: Sequence[Mapping[str, Any]], huellas: Sequence[str]) -> str:
    """Entre 2 y 10, de una sola familia, sin repetidas (§7-2). Devuelve la familia."""
    if not MIN_RUNS <= len(resumenes) <= MAX_RUNS:
        raise ComparisonDataError(
            f"Se comparan entre {MIN_RUNS} y {MAX_RUNS} corridas; llegaron {len(resumenes)}."
        )
    familias = [str(r["family"]) for r in resumenes]
    if len(set(familias)) > 1:
        raise ComparisonDataError(
            "Las corridas son de familias distintas —un scorecard y una provisión IFRS 9 no se "
            f"comparan entre sí—: {', '.join(familias)}."
        )
    vistas: dict[str, int] = {}
    for posicion, valor in enumerate(huellas, start=1):
        if valor in vistas:
            raise ComparisonDataError(
                f"Las corridas {vistas[valor]} y {posicion} son la misma (el mismo resumen "
                "comparable): quita una."
            )
        vistas[valor] = posicion
    return familias[0]


def comparar(
    resumenes: Sequence[Mapping[str, Any]], *, eleccion: Mapping[str, str] | None = None
) -> ComparisonResult:
    """Compara los resúmenes, en orden (el primero es la referencia), y arma §6.2.

    Raises
    ------
    ComparisonDataError
        Fuera de 2 a 10 corridas, familias mezcladas o una corrida repetida.
    """
    from bayesrisk.comparison.engine import nivel_de_comparabilidad

    huellas = [huella(r) for r in resumenes]
    familia = _validar_entrada(resumenes, huellas)
    nombres = nombres_visibles([str(r["name"]) for r in resumenes])
    ref = resumenes[0]
    niveles = ("referencia", *(nivel_de_comparabilidad(ref, r) for r in resumenes[1:]))
    elegida: dict[str, str] | None = None
    if eleccion is not None and eleccion.get("huella") in huellas:
        posicion = huellas.index(str(eleccion["huella"]))
        elegida = {"name": nombres[posicion], "reason": str(eleccion["reason"])}
    if familia == "scorecard":
        return _comparar_scorecards(resumenes, huellas, nombres, niveles, elegida)
    return _comparar_provisiones(resumenes, huellas, nombres, niveles, elegida)


def _tabla_de_corridas(
    resumenes: Sequence[Mapping[str, Any]],
    huellas: Sequence[str],
    nombres: Sequence[str],
    niveles: Sequence[str],
    copias: Mapping[str, str],
) -> Any:
    import pandas as pd

    return pd.DataFrame(
        [
            {
                "position": i + 1,
                "name": nombres[i],
                "family": r["family"],
                "bayesrisk": r.get("bayesrisk"),
                "config_hash": r.get("config_hash"),
                "summary_hash": huellas[i],
                "created_at": r.get("created_at"),
                "level": niveles[i],
                "same_as": copias.get(nombres[i]),
            }
            for i, r in enumerate(resumenes)
        ]
    )


def _signo(x: float) -> int:
    return (x > 0) - (x < 0)


def _comparar_scorecards(
    resumenes: Sequence[Mapping[str, Any]],
    huellas: Sequence[str],
    nombres: Sequence[str],
    niveles: Sequence[str],
    elegida: Mapping[str, str] | None,
) -> ComparisonResult:
    import pandas as pd

    from bayesrisk.comparison.engine import (
        ALFA_DELONG,
        ORDEN_DE_BANDA,
        componentes_de_delong,
        delong_pareada,
        frontera,
        indice_bce,
        misma_muestra_evaluada,
    )
    from bayesrisk.comparison.results import ComparisonCardSection, ComparisonResult
    from bayesrisk.comparison.textos import lectura_scorecard

    n = len(resumenes)
    # El mismo modelo: la misma huella computacional que una corrida anterior (§3.3). Una corrida
    # sin tarjeta no tiene huella y no se declara igual a ninguna.
    copias: dict[str, str] = {}
    primera: dict[str, int] = {}
    for i, r in enumerate(resumenes):
        hash_modelo = r.get("model_hash")
        if hash_modelo is None:
            continue
        if hash_modelo in primera:
            copias[nombres[i]] = nombres[primera[hash_modelo]]
        else:
            primera[hash_modelo] = i

    modelos: list[dict[str, Any]] = []
    for i, r in enumerate(resumenes):
        evaluacion = str(r["evaluation_sample"])
        fila: Mapping[str, Any] = next((s for s in r["samples"] if s["sample"] == evaluacion), {})
        comun = r.get("score_psi_common") or {}
        propio = next(
            (p for p in r.get("score_psi") or [] if p["comparison"] == f"dev_vs_{evaluacion}"),
            None,
        )
        receta = r.get("psi_recipe")
        tramos = r.get("grades")
        participacion = (tramos or {}).get("share_by_sample", {}).get(evaluacion)
        indice = indice_bce(participacion) if participacion is not None else None
        validacion = r.get("validation") or {}
        modelos.append(
            {
                "name": nombres[i],
                "evaluation_sample": evaluacion,
                "optimistic": evaluacion in _FUERA_DE_EVALUACION,
                "n": fila.get("n"),
                "n_bad": fila.get("n_bad"),
                "auc": fila.get("auc"),
                "gini": fila.get("gini"),
                "ks": fila.get("ks"),
                "sample_status": fila.get("status"),
                "psi_common": comun.get("psi"),
                "psi_common_band": comun.get("band"),
                "psi_own": None if propio is None else propio.get("psi"),
                "psi_own_band": None if propio is None else propio.get("band"),
                "own_recipe": receta is not None and receta != RECETA_PSI_DE_FABRICA,
                "concentration_index": None if indice is None else indice.indice,
                "hhi": None if indice is None else indice.hhi,
                "k": None if indice is None else indice.k,
                "concentration_reason": ("sin escala maestra" if indice is None else indice.causa),
                "n_variables": None if r.get("variables") is None else len(r["variables"]),
                "validation_status": validacion.get("status"),
                "validation_reason": validacion.get("reason"),
                "model_hash": r.get("model_hash"),
                "same_as": copias.get(nombres[i]),
                "chosen": elegida is not None and elegida["name"] == nombres[i],
            }
        )

    # La prueba de DeLong pareada, sólo con la misma muestra evaluada (§3.3, §3.5).
    componentes: dict[int, Any] = {}
    for i, r in enumerate(resumenes):
        puntajes = r.get("evaluation_scores")
        if puntajes is not None and modelos[i]["auc"] is not None:
            componentes[i] = componentes_de_delong(puntajes["risk"], puntajes["default"])
    #: ``relacion[i][j]``: +1 si i discrimina más que j, 0 si empatan, -1 si menos; None sin AUC.
    relacion: list[list[int | None]] = [[None] * n for _ in range(n)]
    pruebas: list[dict[str, Any]] = []
    for i in range(n):
        for j in range(i + 1, n):
            auc_i, auc_j = modelos[i]["auc"], modelos[j]["auc"]
            fila_prueba: dict[str, Any] = {
                "model_a": nombres[i],
                "model_b": nombres[j],
                "auc_a": auc_i,
                "auc_b": auc_j,
                "difference": None if auc_i is None or auc_j is None else auc_i - auc_j,
                "paired": False,
                "statistic": None,
                "p_value": None,
                "result": "no_test",
                "reason": None,
            }
            if misma_muestra_evaluada(resumenes[i], resumenes[j]):
                if i in componentes and j in componentes:
                    prueba = delong_pareada(componentes[i], componentes[j])
                    fila_prueba.update(
                        paired=True,
                        statistic=prueba.estadistico,
                        p_value=prueba.p_valor,
                        reason=prueba.causa,
                    )
                    if prueba.estado == "ok" and prueba.p_valor is not None:
                        if prueba.p_valor >= ALFA_DELONG:
                            fila_prueba["result"] = "tie"
                        else:
                            fila_prueba["result"] = (
                                "a_better" if (prueba.diferencia or 0) > 0 else "b_better"
                            )
                    elif prueba.estado == "empate_sin_varianza":
                        fila_prueba["result"] = "tie"
                    else:
                        fila_prueba["result"] = "not_evaluable"
                else:
                    fila_prueba.update(result="not_evaluable", reason="muestra_no_evaluable")
            else:
                fila_prueba["reason"] = (
                    "otra_cartera"
                    if resumenes[i].get("portfolio_hash") != resumenes[j].get("portfolio_hash")
                    or resumenes[i].get("portfolio_hash") is None
                    else "otras_operaciones"
                )
            pruebas.append(fila_prueba)
            resultado = fila_prueba["result"]
            if resultado == "tie":
                valor: int | None = 0
            elif resultado == "a_better":
                valor = 1
            elif resultado == "b_better":
                valor = -1
            elif auc_i is not None and auc_j is not None:
                # Sin prueba (otras operaciones o no evaluable): se comparan las cifras, declarado.
                valor = _signo(auc_i - auc_j)
            else:
                valor = None
            relacion[i][j] = valor
            relacion[j][i] = None if valor is None else -valor

    # Las dos fronteras, como núcleo de la relación (§3.5), entre los modelos de cada gráfico.
    def _elegibles(segunda: str) -> list[int]:
        return [
            i
            for i, m in enumerate(modelos)
            if not m["optimistic"]
            and m["auc"] is not None
            and (
                m["psi_common_band"] in ORDEN_DE_BANDA
                if segunda == "stability"
                else m["concentration_index"] is not None
            )
        ]

    def _segunda(segunda: str, y: int, x: int) -> int:
        if segunda == "stability":
            return _signo(
                ORDEN_DE_BANDA[modelos[x]["psi_common_band"]]
                - ORDEN_DE_BANDA[modelos[y]["psi_common_band"]]
            )
        return _signo(modelos[x]["concentration_index"] - modelos[y]["concentration_index"])

    for segunda in ("stability", "concentration"):
        indices = _elegibles(segunda)

        def supera(a: int, b: int, *, _idx: list[int] = indices, _seg: str = segunda) -> bool:
            y, x = _idx[a], _idx[b]
            d = relacion[y][x]
            if d is None:
                return False
            s = _segunda(_seg, y, x)
            return d >= 0 and s >= 0 and (d > 0 or s > 0)

        dentro, por = frontera(len(indices), supera)
        for m in modelos:
            m[f"frontier_{segunda}"] = None
            m[f"superated_by_{segunda}"] = None
        for posicion, i in enumerate(indices):
            modelos[i][f"frontier_{segunda}"] = dentro[posicion]
            modelos[i][f"superated_by_{segunda}"] = tuple(
                nombres[indices[y]] for y in por[posicion]
            )

    # Las variables: la unión, en el orden de la referencia y luego por primera aparición.
    variables: list[dict[str, Any]] = []
    por_modelo: dict[str, list[str] | None] = {}
    orden: list[str] = []
    for i, r in enumerate(resumenes):
        lista = r.get("variables")
        por_modelo[nombres[i]] = None if lista is None else [str(v["feature"]) for v in lista]
        for v in lista or []:
            if v["feature"] not in orden:
                orden.append(str(v["feature"]))
    for variable in orden:
        for i, r in enumerate(resumenes):
            datos = next((v for v in r.get("variables") or [] if v["feature"] == variable), None)
            evaluacion = modelos[i]["evaluation_sample"]
            csi = (
                None
                if datos is None
                else next(
                    (c for c in datos["csi"] if c["comparison"] == f"dev_vs_{evaluacion}"), None
                )
            )
            beta = None if datos is None else datos.get("beta")
            variables.append(
                {
                    "feature": variable,
                    "model": nombres[i],
                    "included": datos is not None,
                    "beta": beta,
                    "sign": None if beta is None else ("+" if beta > 0 else "-"),
                    "sign_ok": None if datos is None else datos.get("sign_ok"),
                    "iv_development": None if datos is None else datos.get("iv_development"),
                    "iv_evaluation": None
                    if datos is None
                    else (datos.get("iv_by_sample") or {}).get(evaluacion),
                    "csi": None if csi is None else csi.get("csi"),
                    "csi_band": None if csi is None else csi.get("band"),
                }
            )

    muestras = [
        {"model": nombres[i], **{k: s.get(k) for k in _COLUMNAS_DE_MUESTRAS[1:]}}
        for i, r in enumerate(resumenes)
        for s in r["samples"]
    ]
    contra_ref: list[dict[str, Any] | None] = [None]
    for j in range(1, n):
        prueba_ref = pruebas[j - 1]  # los pares (0, j) son los primeros n-1
        resultado = prueba_ref["result"]
        contra_ref.append(
            {
                "result": {"a_better": "worse", "b_better": "better"}.get(resultado, resultado),
                "p_value": prueba_ref["p_value"],
                "reason": prueba_ref["reason"],
            }
        )
    lectura = lectura_scorecard(
        nombres=nombres,
        niveles=niveles,
        copias=copias,
        modelos=modelos,
        contra_ref=contra_ref,
        variables=por_modelo,
        eleccion=elegida,
    )
    card = ComparisonCardSection(
        family="scorecard",
        names=tuple(nombres),
        summary_hashes=tuple(huellas),
        levels=tuple(niveles),
        same_as=dict(copias),
        frontier_stability=tuple(m["name"] for m in modelos if m["frontier_stability"] is True),
        frontier_concentration=tuple(
            m["name"] for m in modelos if m["frontier_concentration"] is True
        ),
        n_tests=len(pruebas),
        n_paired_tests=sum(1 for p in pruebas if p["paired"]),
        chosen=None if elegida is None else elegida["name"],
        chosen_reason=None if elegida is None else elegida["reason"],
        constants={"delong_alpha": ALFA_DELONG, "psi_recipe": dict(RECETA_PSI_DE_FABRICA)},
        reading=lectura,
    )
    return ComparisonResult(
        runs=_tabla_de_corridas(resumenes, huellas, nombres, niveles, copias),
        models=pd.DataFrame(modelos),
        tests=pd.DataFrame(pruebas, columns=_COLUMNAS_DE_PRUEBAS),
        samples=pd.DataFrame(muestras),
        variables=pd.DataFrame(variables, columns=_COLUMNAS_DE_VARIABLES),
        provision=pd.DataFrame(columns=_COLUMNAS_DE_PROVISION),
        reading=lectura,
        card=card,
    )


_COLUMNAS_DE_MUESTRAS: Final[tuple[str, ...]] = (
    "model",
    "sample",
    "n",
    "n_bad",
    "auc",
    "gini",
    "ks",
    "status",
)
_COLUMNAS_DE_PRUEBAS: Final[tuple[str, ...]] = (
    "model_a",
    "model_b",
    "auc_a",
    "auc_b",
    "difference",
    "paired",
    "statistic",
    "p_value",
    "result",
    "reason",
)
_COLUMNAS_DE_VARIABLES: Final[tuple[str, ...]] = (
    "feature",
    "model",
    "included",
    "beta",
    "sign",
    "sign_ok",
    "iv_development",
    "iv_evaluation",
    "csi",
    "csi_band",
)
_COLUMNAS_DE_PROVISION: Final[tuple[str, ...]] = (
    "model",
    "stage",
    "n",
    "exposure",
    "ecl",
    "coverage",
    "ecl_difference",
    "ecl_difference_pct",
    "coverage_difference_pp",
    "same_unit",
    "unit_reason",
    "currency",
)


def _comparar_provisiones(
    resumenes: Sequence[Mapping[str, Any]],
    huellas: Sequence[str],
    nombres: Sequence[str],
    niveles: Sequence[str],
    elegida: Mapping[str, str] | None,
) -> ComparisonResult:
    """IFRS 9 (§3.7, D-CMP-8): por etapa, contra la referencia; sin gráficos ni frontera."""
    import pandas as pd

    from bayesrisk.comparison.engine import misma_unidad
    from bayesrisk.comparison.results import ComparisonCardSection, ComparisonResult
    from bayesrisk.comparison.textos import lectura_ifrs9

    def _ecl_por_etapa(r: Mapping[str, Any]) -> tuple[float, ...]:
        return tuple(float(e["ecl"]) for e in r["by_stage"])

    copias: dict[str, str] = {}
    vistos: dict[tuple[float, ...], int] = {}
    for i, r in enumerate(resumenes):
        clave = _ecl_por_etapa(r)
        if clave in vistos:
            copias[nombres[i]] = nombres[vistos[clave]]
        else:
            vistos[clave] = i

    ref = resumenes[0]
    filas: list[dict[str, Any]] = []
    provisiones: list[dict[str, Any]] = []
    modelos: list[dict[str, Any]] = []
    for i, r in enumerate(resumenes):
        unidad, razon = (True, "referencia") if i == 0 else misma_unidad(ref, r)
        etapas_ref = {e["stage"]: e for e in ref["by_stage"]}
        diferencias: list[tuple[int, float]] = []
        for etapa in (*r["by_stage"], {"stage": "total", **r["total"]}):
            base = ref["total"] if etapa["stage"] == "total" else etapas_ref.get(etapa["stage"], {})
            dif = float(etapa["ecl"]) - float(base.get("ecl", 0.0)) if unidad else None
            if dif is not None and etapa["stage"] != "total":
                diferencias.append((int(etapa["stage"]), dif))
            cobertura, cobertura_ref = etapa.get("coverage"), base.get("coverage")
            filas.append(
                {
                    "model": nombres[i],
                    "stage": str(etapa["stage"]),
                    "n": etapa["n"],
                    "exposure": etapa["exposure"],
                    "ecl": etapa["ecl"],
                    "coverage": cobertura,
                    "ecl_difference": dif,
                    "ecl_difference_pct": (
                        dif / float(base["ecl"]) if dif is not None and base.get("ecl") else None
                    ),
                    "coverage_difference_pp": (
                        (cobertura - cobertura_ref) * 100.0
                        if cobertura is not None and cobertura_ref is not None
                        else None
                    ),
                    "same_unit": unidad,
                    "unit_reason": razon,
                    "currency": r.get("currency"),
                }
            )
        provisiones.append(
            {
                "name": nombres[i],
                "ecl": float(r["total"]["ecl"]),
                "coverage": r["total"].get("coverage"),
                "same_unit": unidad,
                "unit_reason": _RAZONES_DE_UNIDAD.get(razon, razon),
                "currency": r.get("currency"),
                "stage_differences": diferencias,
            }
        )
        modelos.append(
            {
                "name": nombres[i],
                "as_of": r.get("as_of"),
                "currency": r.get("currency"),
                "scenarios": ", ".join(
                    f"{s['name']} ({_peso(s.get('weight'))})" for s in r.get("scenarios") or []
                ),
                "n": r["total"]["n"],
                "exposure": r["total"]["exposure"],
                "ecl": r["total"]["ecl"],
                "coverage": r["total"].get("coverage"),
                "same_unit": unidad,
                "unit_reason": razon,
                "same_as": copias.get(nombres[i]),
                "chosen": elegida is not None and elegida["name"] == nombres[i],
            }
        )
    lectura = lectura_ifrs9(
        nombres=nombres, niveles=niveles, copias=copias, provisiones=provisiones, eleccion=elegida
    )
    card = ComparisonCardSection(
        family="ifrs9",
        names=tuple(nombres),
        summary_hashes=tuple(huellas),
        levels=tuple(niveles),
        same_as=dict(copias),
        frontier_stability=(),
        frontier_concentration=(),
        n_tests=0,
        n_paired_tests=0,
        chosen=None if elegida is None else elegida["name"],
        chosen_reason=None if elegida is None else elegida["reason"],
        constants={},
        reading=lectura,
    )
    return ComparisonResult(
        runs=_tabla_de_corridas(resumenes, huellas, nombres, niveles, copias),
        models=pd.DataFrame(modelos),
        tests=pd.DataFrame(columns=_COLUMNAS_DE_PRUEBAS),
        samples=pd.DataFrame(columns=_COLUMNAS_DE_MUESTRAS),
        variables=pd.DataFrame(columns=_COLUMNAS_DE_VARIABLES),
        provision=pd.DataFrame(filas, columns=_COLUMNAS_DE_PROVISION),
        reading=lectura,
        card=card,
    )


#: Por qué no se restan dos montos, en palabras (§3.7).
_RAZONES_DE_UNIDAD: Final[dict[str, str]] = {
    "monedas_distintas": "las monedas declaradas son distintas",
    "unidad_no_probada": (
        "otra cartera u otras columnas de monto, sin la misma moneda declarada en las dos"
    ),
}


def _peso(valor: Any) -> str:
    from bayesrisk.report.cifras import porcentaje

    if valor is None or (isinstance(valor, float) and not math.isfinite(valor)):
        return "—"
    return porcentaje(float(valor), decimales=0)
