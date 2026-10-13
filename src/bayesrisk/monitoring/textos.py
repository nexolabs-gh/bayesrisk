"""Lo que el monitoreo dice en español (SDD-31 D-SIM-9).

Una sola fuente para el veredicto que publica el paso y para el resumen «Monitoreo».

Los identificadores del motor (``watch``, ``few_bads``…) nunca llegan al texto: cada uno tiene aquí
su frase. Un gate (``test_monitoring_textos``) exige una frase por cada código que el motor emite.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

__all__ = [
    "ACCIONES",
    "CAUSAS",
    "DIRECCIONES",
    "DIRECCIONES_CORTAS",
    "INDICADORES",
    "VEREDICTOS",
    "razon",
]

#: El veredicto de §3.5 en una palabra.
VEREDICTOS: Final[dict[str, str]] = {
    "no_outcome_yet": "Sin desenlace aún",
    "no_action": "Sin acción",
    "watch": "Vigilar",
    "recalibrate": "Recalibrar",
    "redevelop": "Redesarrollar",
}

#: Qué hacer con cada veredicto, en una línea.
ACCIONES: Final[dict[str, str]] = {
    "no_outcome_yet": (
        "Esperar el desenlace: la población no se movió y el desempeño todavía no se puede medir."
    ),
    "no_action": (
        "Seguir usando el modelo: la población, el orden y la PD de los tramos están en línea."
    ),
    "watch": (
        "Seguir de cerca el próximo periodo: cambió algo que todavía no es una falla del modelo."
    ),
    "recalibrate": (
        "Recalibrar la PD de los tramos: el modelo sigue ordenando, pero su nivel ya no acierta."
    ),
    "redevelop": (
        "Redesarrollar el modelo: los tramos separan menos de lo que promete y el AUC cayó contra "
        "la validación inicial; recalibrar el nivel no lo arregla."
    ),
}

#: Los indicadores, como los lee un comité.
INDICADORES: Final[dict[str, str]] = {
    "psi_score": "el PSI del puntaje",
    "psi_grades": "el PSI de la participación por tramo",
    "portfolio": "la calibración de la cartera",
    "grade": "la calibración del tramo",
    "auc_test": "la prueba del BCE contra el AUC inicial",
    "slope": "la pendiente de calibración",
}

#: Por qué un indicador no se pudo evaluar.
CAUSAS: Final[dict[str, str]] = {
    "few_bads": "menos de 2 malos con desenlace",
    "few_goods": "menos de 2 buenos con desenlace",
    "zero_variance": "todas las operaciones con desenlace en un solo tramo (varianza nula)",
    "one_pd": "los tramos con desenlace tienen una sola PD",
    "separation": "los malos y los buenos quedan en tramos separados (separación perfecta)",
    "singular_information": "la matriz de información no es invertible",
    "not_converged": "el ajuste no converge",
    "pd_out_of_range": "una PD de tramo fuera de (0, 1)",
    "few_outcomes": "menos de 30 operaciones con desenlace",
    "no_scored_rows": "ninguna operación puntuada",
    "initial_not_evaluable": "el AUC inicial de la tarjeta no es evaluable",
}

#: La dirección de un rojo de calibración (D-MNT-10), en una frase y en una palabra (tablas).
DIRECCIONES: Final[dict[str, str]] = {
    "under": "la PD subestima el riesgo",
    "over": "la PD sobrestima el riesgo",
}
DIRECCIONES_CORTAS: Final[dict[str, str]] = {"under": "subestima", "over": "sobrestima"}


def _tramos(tramos: Sequence[int]) -> str:
    lista = [str(t) for t in tramos]
    if len(lista) == 1:
        return f"el tramo {lista[0]}"
    return f"los tramos {', '.join(lista[:-1])} y {lista[-1]}"


def razon(
    regla: str,
    *,
    tramos_rojos: Sequence[int] = (),
    repetidos: Sequence[int] = (),
    direccion: str | None = None,
    pruebas_rojas: Sequence[str] = (),
    ambar: Sequence[str] = (),
    poblacion: str | None = None,
) -> str:
    """La razón del veredicto en una línea, desde la regla de §3.5 que lo decidió."""
    if regla == "discrimination_red":
        return (
            "la prueba del BCE contra el AUC inicial y la pendiente de calibración están en rojo: "
            "los tramos separan menos de lo que el modelo promete"
        )
    if regla == "portfolio_red":
        detalle = f" ({DIRECCIONES[direccion]})" if direccion in DIRECCIONES else ""
        return f"la tasa de malos de la cartera no acierta su PD{detalle}"
    if regla == "two_red_grades":
        return f"{_tramos(tramos_rojos)} en rojo: la PD de varios tramos ya no acierta"
    if regla == "repeated_red_grade":
        return f"{_tramos(repetidos)} en rojo dos periodos seguidos"
    if regla == "population_red":
        return "la población cambió (PSI en rojo); el orden y la PD de los tramos aguantan"
    if regla == "one_discrimination_test_red":
        return (
            f"{' y '.join(pruebas_rojas)} en rojo, pero no las dos pruebas de discriminación: "
            "todavía no es una pérdida de orden"
        )
    if regla == "isolated_red_grade":
        return (
            f"{_tramos(tramos_rojos)} en rojo, aislado: con varios tramos y periodos, un rojo "
            "suelto aparece por azar"
        )
    if regla == "amber":
        return f"{' y '.join(ambar)} en ámbar"
    if regla == "all_green":
        return "todo lo evaluable en verde"
    if regla == "no_outcome_population_moved":
        color = "rojo" if poblacion == "red" else "ámbar"
        return f"todavía sin desenlace, y la población se movió (PSI en {color})"
    if regla == "no_outcome":
        return "todavía sin desenlace; la población no se movió"
    raise ValueError(f"Regla de veredicto sin frase: {regla!r}")
