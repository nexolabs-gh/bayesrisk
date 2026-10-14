"""La lectura de la comparación en palabras (SDD-34 §3.6): reglas constantes, en orden.

Una sola fuente para el resumen, la pantalla y el informe (capa B). Cada línea aparece sólo si
aplica: la comparabilidad y los modelos repetidos; la discriminación contra la referencia; la
estabilidad; la concentración; la frontera; la validación técnica; las variables; y la elección
de la institución. En IFRS 9: la comparabilidad, cuánto provisiona cada una contra la referencia y
dónde, y la elección (§3.7).

**Experimental (fuera de la garantía SemVer 2.x).** Sale en la 2.15.0 (capa A del SDD-34).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from bayesrisk.report.cifras import cifra, conteo, porcentaje, pvalor
from bayesrisk.report.prose import _enumerar

__all__ = [
    "MUESTRAS",
    "NIVELES",
    "lectura_ifrs9",
    "lectura_scorecard",
    "numero_en_palabras",
]

#: Cómo se nombra cada muestra dentro de una frase.
MUESTRAS: Final[dict[str, str]] = {"desarrollo": "Desarrollo", "holdout": "Holdout", "oot": "OOT"}
#: Lo que dice cada nivel de comparabilidad contra la referencia (§3.3).
NIVELES: Final[dict[str, str]] = {
    "referencia": "referencia",
    "misma_muestra": "misma muestra evaluada",
    "misma_cartera": "misma cartera, otra muestra evaluada",
    "otra_cartera": "otra cartera",
}
_PALABRAS: Final[dict[int, str]] = {
    0: "cero",
    1: "una",
    2: "dos",
    3: "tres",
    4: "cuatro",
    5: "cinco",
    6: "seis",
    7: "siete",
    8: "ocho",
    9: "nueve",
    10: "diez",
}
_ESTADOS_VALIDACION: Final[dict[str, tuple[str, str]]] = {
    "pass": ("pasa", "pasan"),
    "warn": ("queda en revisión", "quedan en revisión"),
    "fail": ("falla", "fallan"),
    "not_evaluable": ("no es evaluable", "no son evaluables"),
}


def numero_en_palabras(n: int) -> str:
    """«seis» hasta diez; un número más grande, en cifras."""
    return _PALABRAS.get(n, conteo(n))


def _verbo(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _oracion(partes: Sequence[str], nombres: Sequence[str]) -> str:
    """Las partes unidas por «; », con mayúscula inicial.

    Salvo que empiece con el nombre de una corrida: un nombre se escribe tal cual.
    """
    texto = "; ".join(p for p in partes if p)
    if not texto or any(texto.startswith(nombre) for nombre in nombres):
        return texto
    return texto[0].upper() + texto[1:]


def _gini(modelo: Mapping[str, Any]) -> str:
    return cifra(modelo.get("gini"), decimales=3)


def _p(valor: float | None) -> str:
    escrito = pvalor(valor)
    return f"p {escrito}" if escrito.startswith("<") else f"p = {escrito}"


# ── scorecard ────────────────────────────────────────────────────────────────────────────────


def _linea_de_comparabilidad(
    nombres: Sequence[str], niveles: Sequence[str], copias: Mapping[str, str], sustantivo: str
) -> str:
    partes: list[str] = []
    otros = list(zip(nombres[1:], niveles[1:], strict=True))
    if all(nivel == "misma_muestra" for _, nivel in otros):
        partes.append(
            f"Las {numero_en_palabras(len(nombres))} {sustantivo} usan las mismas operaciones"
        )
    for nombre, nivel in otros:
        if nivel == "misma_cartera":
            partes.append(f"{nombre} se evaluó sobre otras operaciones de la misma cartera")
        elif nivel == "otra_cartera":
            partes.append(f"{nombre} se midió sobre otros datos: la comparación es orientativa")
    originales: dict[str, list[str]] = {}
    for copia, original in copias.items():
        originales.setdefault(original, []).append(copia)
    for original, iguales in originales.items():
        verbo = _verbo(len(iguales), "es el mismo modelo", "son el mismo modelo")
        partes.append(f"{_enumerar(iguales)} {verbo} que {original}")
    return "; ".join(partes)


def _linea_de_discriminacion(
    modelos: Sequence[Mapping[str, Any]], contra_ref: Sequence[Mapping[str, Any] | None]
) -> str:
    """Contra la referencia: quién empata, quién discrimina menos o más de verdad, y sin prueba."""
    ref = modelos[0]
    empatan = [ref["name"]]
    partes: list[str] = []
    for modelo, prueba in zip(modelos[1:], contra_ref[1:], strict=True):
        if modelo.get("same_as") is not None:
            continue
        nombre = modelo["name"]
        if modelo.get("auc") is None:
            muestra = MUESTRAS.get(str(modelo.get("evaluation_sample")), "su muestra")
            partes.append(f"la discriminación de {nombre} no es evaluable en {muestra}")
            continue
        if prueba is None or prueba["result"] in {"no_test", "not_evaluable"}:
            if prueba is not None and prueba["result"] == "not_evaluable":
                motivo = "prueba no evaluable"
            elif prueba is not None and prueba.get("reason") == "otra_cartera":
                motivo = "otros datos"
            else:
                motivo = "otras operaciones"
            partes.append(
                f"{nombre}: Gini {_gini(modelo)} frente a {_gini(ref)}, sin prueba ({motivo})"
            )
        elif prueba["result"] == "tie":
            empatan.append(nombre)
        else:
            mas = prueba["result"] == "better"
            partes.append(
                f"{nombre} discrimina {'más' if mas else 'menos'} (Gini {_gini(modelo)} frente "
                f"a {_gini(ref)}; {_p(prueba.get('p_value'))})"
            )
    cabeza = [f"en discriminación empatan {_enumerar(empatan)}"] if len(empatan) > 1 else []
    return _oracion([*cabeza, *partes], [m["name"] for m in modelos])


def _linea_de_estabilidad(modelos: Sequence[Mapping[str, Any]]) -> str:
    propios = [m for m in modelos if m.get("same_as") is None]
    bandas = {"stable", "review", "redevelop"}
    con_banda = [m for m in propios if m.get("psi_common_band") in bandas]
    partes: list[str] = []
    if con_banda and all(m["psi_common_band"] == "stable" for m in con_banda):
        partes.append(
            "Todas son estables" if len(con_banda) == len(propios) else "Las demás son estables"
        )
    elif con_banda:
        for banda, palabra in (
            ("stable", "estables"),
            ("review", "en revisión"),
            ("redevelop", "para redesarrollar"),
        ):
            de_la_banda = [m["name"] for m in con_banda if m["psi_common_band"] == banda]
            if de_la_banda:
                partes.append(f"PSI {palabra}: {_enumerar(de_la_banda)}")
    sin_psi = [m["name"] for m in propios if m not in con_banda]
    if sin_psi:
        partes.insert(0, f"sin PSI común: {_enumerar(sin_psi)}")
    otra_receta = [m["name"] for m in propios if m.get("own_recipe")]
    if otra_receta:
        partes.append(
            f"{_enumerar(otra_receta)} midió su PSI con otra receta; la frontera usa la de "
            "fábrica para todas"
        )
    holdout = [m["name"] for m in propios if m.get("evaluation_sample") == "holdout"]
    if holdout:
        partes.append(
            f"{_enumerar(holdout)} se evaluó en Holdout: si la muestra se separó al azar, su PSI "
            "no mide deriva en el tiempo"
        )
    return _oracion(partes, [m["name"] for m in modelos])


def _linea_de_concentracion(modelos: Sequence[Mapping[str, Any]]) -> str:
    propios = [m for m in modelos if m.get("same_as") is None]
    con_indice = [m for m in propios if m.get("concentration_index") is not None]
    sin_indice = [m["name"] for m in propios if m.get("concentration_index") is None]
    partes: list[str] = []
    ref = modelos[0]
    if con_indice:
        mejor = min(con_indice, key=lambda m: m["concentration_index"])
        if ref.get("concentration_index") is None:
            partes.append(
                f"Reparte mejor sus tramos: {mejor['name']} (índice "
                f"{cifra(mejor['concentration_index'], decimales=2)})"
            )
        elif mejor is not ref and mejor["concentration_index"] < ref["concentration_index"]:
            partes.append(
                f"Reparte mejor sus tramos: {mejor['name']} (índice "
                f"{cifra(mejor['concentration_index'], decimales=2)} frente a "
                f"{cifra(ref['concentration_index'], decimales=2)})"
            )
        else:
            partes.append(
                f"La referencia reparte mejor sus tramos (índice "
                f"{cifra(ref['concentration_index'], decimales=2)})"
            )
    if sin_indice:
        partes.append(f"sin índice de concentración (sin escala maestra): {_enumerar(sin_indice)}")
    return _oracion(partes, [m["name"] for m in modelos])


def _linea_de_frontera(modelos: Sequence[Mapping[str, Any]]) -> str:
    partes: list[str] = []
    for clave, rotulo in (
        ("concentration", "discriminación y concentración"),
        ("stability", "discriminación y estabilidad"),
    ):
        dentro = [m["name"] for m in modelos if m.get(f"frontier_{clave}") is True]
        fuera = [
            m["name"]
            for m in modelos
            if m.get(f"frontier_{clave}") is False and m.get("same_as") is None
        ]
        propios_dentro = [
            m["name"]
            for m in modelos
            if m.get(f"frontier_{clave}") is True and m.get("same_as") is None
        ]
        if not dentro:
            continue
        if len(propios_dentro) == 1 and fuera:
            partes.append(f"ninguna otra supera a {propios_dentro[0]} en {rotulo}")
        elif fuera:
            verbo = _verbo(len(fuera), "queda superada", "quedan superadas")
            partes.append(f"en {rotulo} {verbo} {_enumerar(fuera)}")
    return _oracion(partes, [m["name"] for m in modelos])


def _linea_de_validacion(modelos: Sequence[Mapping[str, Any]]) -> str:
    propios = [m for m in modelos if m.get("same_as") is None]
    partes: list[str] = []
    for estado, (singular, plural) in _ESTADOS_VALIDACION.items():
        del_estado = [m for m in propios if m.get("validation_status") == estado]
        if not del_estado:
            continue
        nombres = [
            f"{m['name']} ({m['validation_reason']})" if m.get("validation_reason") else m["name"]
            for m in del_estado
        ]
        verbo = _verbo(len(del_estado), singular, plural)
        if estado == "pass":
            partes.append(f"{verbo.capitalize()} la validación técnica {_enumerar(nombres)}")
        else:
            partes.append(f"{verbo} {_enumerar(nombres)}")
    sin = [m["name"] for m in propios if m.get("validation_status") is None]
    if sin:
        partes.append(f"sin validación formal: {_enumerar(sin)}")
    return _oracion(partes, [m["name"] for m in modelos])


def _linea_de_variables(
    modelos: Sequence[Mapping[str, Any]], variables: Mapping[str, Sequence[str] | None]
) -> str:
    propios = [m for m in modelos if m.get("same_as") is None]
    conjuntos = {m["name"]: variables.get(m["name"]) for m in propios}
    con_variables = {k: list(v) for k, v in conjuntos.items() if v is not None}
    if len(con_variables) < 2:
        return ""
    comunes = set.intersection(*(set(v) for v in con_variables.values()))
    partes = [
        f"Comparten {numero_en_palabras(len(comunes))} "
        f"{_verbo(len(comunes), 'variable', 'variables')}"
    ]
    ref = modelos[0]["name"]
    base = con_variables.get(ref)
    if base is not None:
        for nombre, propias in con_variables.items():
            if nombre == ref:
                continue
            quita = [v for v in base if v not in propias]
            agrega = [v for v in propias if v not in base]
            cambios = []
            if quita:
                cambios.append(f"quita {_enumerar(quita)}")
            if agrega:
                cambios.append(f"agrega {_enumerar(agrega)}")
            if cambios:
                partes.append(f"{nombre} {' y '.join(cambios)}")
    return "; ".join(partes)


def _linea_de_eleccion(eleccion: Mapping[str, Any] | None) -> str:
    if eleccion is None:
        return ""
    return f"La institución eligió {eleccion['name']}: «{eleccion['reason']}»"


def lectura_scorecard(
    *,
    nombres: Sequence[str],
    niveles: Sequence[str],
    copias: Mapping[str, str],
    modelos: Sequence[Mapping[str, Any]],
    contra_ref: Sequence[Mapping[str, Any] | None],
    variables: Mapping[str, Sequence[str] | None],
    eleccion: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Las líneas de §3.6 para scorecards, cada una sólo si aplica, en el orden fijo."""
    lineas = (
        _linea_de_comparabilidad(nombres, niveles, copias, "corridas"),
        _linea_de_discriminacion(modelos, contra_ref),
        _linea_de_estabilidad(modelos),
        _linea_de_concentracion(modelos),
        _linea_de_frontera(modelos),
        _linea_de_validacion(modelos),
        _linea_de_variables(modelos, variables),
        _linea_de_eleccion(eleccion),
    )
    return tuple(f"{linea}." for linea in lineas if linea)


# ── IFRS 9 ───────────────────────────────────────────────────────────────────────────────────


def _monto(valor: float, moneda: str | None) -> str:
    texto = conteo(round(abs(valor)))
    return f"{texto} {moneda}" if moneda else texto


def lectura_ifrs9(
    *,
    nombres: Sequence[str],
    niveles: Sequence[str],
    copias: Mapping[str, str],
    provisiones: Sequence[Mapping[str, Any]],
    eleccion: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Las líneas de §3.7: comparabilidad, cuánto provisiona cada una y dónde, y la elección."""
    partes: list[str] = []
    otros = list(zip(nombres[1:], niveles[1:], strict=True))
    if all(nivel == "misma_cartera" for _, nivel in otros):
        partes.append(
            f"Las {numero_en_palabras(len(nombres))} provisiones son de la misma cartera y la "
            "misma fecha de corte"
        )
    for nombre, nivel in otros:
        if nivel == "otra_cartera":
            partes.append(
                f"{nombre} se calculó sobre otra cartera, otra fecha de corte u otra moneda: la "
                "comparación es orientativa"
            )
    for copia, original in copias.items():
        partes.append(f"{copia} da la misma provisión que {original}")
    lineas = ["; ".join(partes)] if partes else []
    ref = provisiones[0]
    for prov in provisiones[1:]:
        nombre = prov["name"]
        if prov["name"] in copias:
            continue
        if not prov["same_unit"]:
            lineas.append(
                f"Los montos de {nombre} no se restan a los de {ref['name']} "
                f"({prov['unit_reason']}): "
                f"su cobertura es {porcentaje(prov['coverage'], decimales=2)} frente a "
                f"{porcentaje(ref['coverage'], decimales=2)}"
            )
            continue
        diferencia = prov["ecl"] - ref["ecl"]
        if round(diferencia) == 0:
            lineas.append(f"{nombre} provisiona lo mismo que {ref['name']}")
            continue
        relativa = diferencia / ref["ecl"] if ref["ecl"] else None
        por_etapa = [(e, d) for e, d in prov["stage_differences"] if round(d) != 0]
        if len(por_etapa) == 1:
            donde = f"todo en Stage {por_etapa[0][0]}"
        else:
            etapa, monto = max(por_etapa, key=lambda par: abs(par[1]))
            signo = "más" if monto > 0 else "menos"
            donde = (
                f"la mayor diferencia en Stage {etapa} ({_monto(monto, prov['currency'])} {signo})"
            )
        cuanto = f" ({porcentaje(relativa, decimales=1)})" if relativa is not None else ""
        lineas.append(
            f"{nombre} provisiona {_monto(diferencia, prov['currency'])} "
            f"{'más' if diferencia > 0 else 'menos'} que {ref['name']}{cuanto}, {donde}"
        )
    eleccion_texto = _linea_de_eleccion(eleccion)
    if eleccion_texto:
        lineas.append(eleccion_texto)
    return tuple(f"{linea}." for linea in lineas if linea)
