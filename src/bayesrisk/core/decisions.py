"""Las decisiones humanas con motivo del config, como eventos del trail (D-DEC-2 y D-DEC-3).

La sección INFRA ``decisions`` (:class:`~bayesrisk.core.config.schema.DecisionEntry`) es el
registro, en orden y con su historia, de lo que una persona decidió con ``exclude``, ``keep``,
``merge_bins`` o ``set_bins`` —en el scorecard— o con ``exclude`` y ``rebut_backstops`` —en una
provisión IFRS 9 (FLUJO-GUIADO-IFRS9 D-ECL-8)—. :class:`~bayesrisk.core.study.Study` la declara
al trail en cada corrida, después del preámbulo que reciba (la entrada y las inferencias de la
puerta guiada): así la corrida guiada, ``bayesrisk.run(loads_config(yaml))`` y la pantalla dan
**las mismas** decisiones humanas, con el mismo payload que la puerta emitía antes de la 2.3.0.

Antes de emitir, cada registro se coteja con el config que va a correr, **variable por variable**
y sólo en el **último** registro de cada variable dentro de su familia (``exclude``/``keep``;
``merge_bins``/``set_bins``; las covariables de la curva; las presunciones de mora); los
anteriores son historia y se emiten tal cual. Tres estados:

- **aplicada** — la hoja del config refleja la decisión: la variable está en
  ``binning.exclude_columns`` (``exclude``); está en ``selection.force_include`` y en
  ``model.force_include`` y no está excluida (``keep``); su hoja de
  ``binning.variable_overrides`` tiene los mismos cortes fijados que la huella (tramos). En una
  provisión: la covariable ya no está en ``survival.input.covariate_cols`` (``exclude`` con esa
  hoja en su huella) y los días de mora de ``provisioning_ifrs9.staging`` son los de la huella
  (``rebut_backstops``, cuyo sujeto es la columna de mora).
- **en suspenso** — los cortes siguen ahí pero la variable se excluyó después: D-EXC-1 ya lo
  declara (``override_en_suspenso``) y la decisión se emite como hoy.
- **sin efecto** — la hoja no está o cambió (un YAML editado a mano, el formulario de la
  pantalla). No se atribuye a una persona: el motor declara ``decision_sin_efecto`` (D-DEC-3 (a),
  precedente ``point_override_sin_casar``) y el resumen final lo dice como alerta.

Un registro de varias variables puede quedar aplicado en parte: se emite como decisión humana
sólo para lo aplicado —``variables`` las nombra y ``valor`` es la huella **restringida a ellas**,
porque ``DecisionRecord`` guarda ``valor`` y descarta ``variables``—, con la huella completa en la
clave aditiva ``huella``; lo demás va como ``decision_sin_efecto``. Los dos eventos llevan la clave
aditiva ``registro`` (la posición en ``config.decisions``). La huella es acumulada: si la de un
registro aplicado nombra **otra** variable cuya decisión quedó sin efecto, el ``valor`` humano la
omite, con ``huella`` y ``registro``. Fuera de esos casos, un registro aplicado se emite
exactamente como hoy, sin ``registro`` ni ``huella``.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from bayesrisk.core.config.schema import BayesRiskConfig, DecisionEntry

__all__ = [
    "DECISIONS_STEP",
    "REGLA_DECISION_HUMANA",
    "REGLA_DECISION_SIN_EFECTO",
    "eventos_de_decisiones",
    "payload_de_decision",
]

#: El paso con que se declaran al trail: la sección del config que las registra. Es el mismo para
#: la corrida guiada y para la del YAML, así las dos puertas escriben eventos idénticos.
DECISIONS_STEP: Final = "decisions"
#: La regla de una decisión humana aplicada (D-FLU-3; el payload no cambia con la 2.3.0).
REGLA_DECISION_HUMANA: Final = "decision_del_usuario"
#: La regla con que el motor declara un registro cuyo efecto ya no está en el config (D-DEC-3).
REGLA_DECISION_SIN_EFECTO: Final = "decision_sin_efecto"

_HOJA_EXCLUIDAS: Final = "binning.exclude_columns"
_HOJA_CORTES: Final = "binning.variable_overrides"
#: La hoja que deja escrita ``exclude`` sobre la curva de PD: la lista de covariables que queda.
_HOJA_COVARIABLES: Final = "survival.input.covariate_cols"
#: Las dos hojas que deja escritas ``rebut_backstops`` y la columna de mora que es su sujeto.
_HOJAS_PRESUNCIONES: Final = (
    "provisioning_ifrs9.staging.dpd_sicr_backstop",
    "provisioning_ifrs9.staging.dpd_default_backstop",
)
_HOJA_COLUMNA_MORA: Final = "provisioning_ifrs9.staging.days_past_due_col"
_FAMILIA: Final[Mapping[str, str]] = {
    "exclude": "variables",
    "keep": "variables",
    "merge_bins": "tramos",
    "set_bins": "tramos",
    "rebut_backstops": "presunciones",
}


def _familia(registro: DecisionEntry) -> str:
    """La familia en que se coteja un registro: la última decisión de cada variable gana en ella.

    ``exclude`` sobre la curva de PD es su propia familia: retirar una covariable no compite con
    excluir una predictora del scorecard que se llame igual.
    """
    if registro.action == "exclude" and _HOJA_COVARIABLES in registro.value:
        return "covariables"
    return _FAMILIA[registro.action]


def payload_de_decision(entry: DecisionEntry) -> dict[str, Any]:
    """El payload del evento ``decision_del_usuario`` de un registro, el mismo de antes de la 2.3.0.

    ``valor`` es la huella guardada (las hojas acumuladas que la decisión dejó escritas) y
    ``variables``, el sujeto: lo que la línea «exclude score — «motivo»» necesita.
    """
    return {
        "regla": REGLA_DECISION_HUMANA,
        "umbral": None,
        "valor": copy.deepcopy(dict(entry.value)),
        "accion": entry.action,
        "autor": entry.author,
        "motivo": entry.reason,
        "variables": list(entry.columns),
    }


def eventos_de_decisiones(config: BayesRiskConfig) -> list[dict[str, Any]]:
    """Los payloads que la corrida declara por su registro de decisiones, en orden (D-DEC-2/3).

    Ver el módulo: un ``decision_del_usuario`` por registro aplicado (o en suspenso); lo que ya no
    está en el config, un ``decision_sin_efecto`` del motor; un registro aplicado en parte, los
    dos, con la clave ``registro``.
    """
    registros: tuple[DecisionEntry, ...] = tuple(getattr(config, "decisions", ()) or ())
    ultimo: dict[tuple[str, str], int] = {}
    for posicion, registro in enumerate(registros):
        for variable in registro.columns:
            ultimo[(_familia(registro), variable)] = posicion
    # Primera pasada: el estado de cada variable en el ÚLTIMO registro de su familia.
    cotejo: list[tuple[list[str], dict[str, tuple[str, ...]]]] = []
    for posicion, registro in enumerate(registros):
        aplicadas: list[str] = []
        sin_efecto: dict[str, tuple[str, ...]] = {}
        for variable in registro.columns:
            if ultimo[(_familia(registro), variable)] != posicion:
                # Historia: una decisión posterior sobre la misma variable la reemplazó.
                aplicadas.append(variable)
                continue
            hojas = _hojas_que_no_coinciden(config, registro, variable)
            if hojas:
                sin_efecto[variable] = hojas
            else:
                aplicadas.append(variable)
        cotejo.append((aplicadas, sin_efecto))
    eventos: list[dict[str, Any]] = []
    for posicion, registro in enumerate(registros):
        aplicadas, sin_efecto = cotejo[posicion]
        if not sin_efecto:
            # La huella es ACUMULADA (`exclude(x)` y luego `exclude(y)` guarda `[x, y]`): si nombra
            # otra variable cuyo efecto ya no está en el config y ninguna decisión posterior
            # aplicada lo explica, el evento humano no la atribuye —`DecisionRecord` y el Excel
            # conservan `valor`— y la huella completa queda como evidencia (pasadas 1 y 2 de Codex
            # sobre el código). Sin eso, exactamente el de hoy.
            ajenas = _ajenas_no_vigentes(config, registros, cotejo, ultimo, posicion)
            humana = payload_de_decision(registro)
            if ajenas:
                humana["valor"] = _huella_sin(registro.value, ajenas)
                humana["registro"] = posicion
                humana["huella"] = copy.deepcopy(dict(registro.value))
            eventos.append(humana)
            continue
        if aplicadas:
            humana = payload_de_decision(registro)
            humana["valor"] = _huella_restringida(registro.value, aplicadas)
            humana["variables"] = aplicadas
            humana["registro"] = posicion
            humana["huella"] = copy.deepcopy(dict(registro.value))
            eventos.append(humana)
        variables = [v for v in registro.columns if v in sin_efecto]
        hojas_rotas = sorted({hoja for v in variables for hoja in sin_efecto[v]})
        eventos.append(
            {
                "regla": REGLA_DECISION_SIN_EFECTO,
                "umbral": ", ".join(hojas_rotas),
                "valor": _huella_restringida(registro.value, variables),
                "accion": registro.action,
                "motivo": registro.reason,
                "variables": variables,
                "registro": posicion,
            }
        )
    return eventos


def _ajenas_no_vigentes(
    config: BayesRiskConfig,
    registros: Sequence[DecisionEntry],
    cotejo: Sequence[tuple[list[str], dict[str, tuple[str, ...]]]],
    ultimo: Mapping[tuple[str, str], int],
    posicion: int,
) -> set[str]:
    """Las variables ajenas al registro que su huella acumulada nombra y ya no se sostienen.

    Una variable ajena se conserva en el ``valor`` si su elemento sigue en la hoja vigente del
    config, o si una decisión **posterior** y aplicada sobre ella en la misma familia lo explica
    (historia: ``exclude(x)``, ``exclude(y)`` y luego ``keep(x)``). Si no —se retiró a mano, con o
    sin su registro, o la decisión posterior quedó sin efecto—, no se le atribuye.
    """
    registro = registros[posicion]
    familia = _familia(registro)
    propias = set(registro.columns)
    retiradas: set[str] = set()
    for hoja, contenido in registro.value.items():
        if not isinstance(contenido, Sequence) or isinstance(contenido, str | bytes):
            continue
        seccion, _, campo = hoja.partition(".")
        vigente = _lista(config, seccion, campo)
        for item in contenido:
            nombre = item.get("name") if isinstance(item, Mapping) else item
            if not isinstance(nombre, str) or nombre in propias or item in vigente:
                continue
            posterior = ultimo.get((familia, nombre), -1)
            if posterior > posicion and nombre not in cotejo[posterior][1]:
                continue
            retiradas.add(nombre)
    return retiradas


def _huella_sin(valor: Mapping[str, Any], variables: set[str]) -> dict[str, Any]:
    """La huella sin los elementos que nombran ``variables``."""
    salida: dict[str, Any] = {}
    for hoja, contenido in valor.items():
        if isinstance(contenido, Sequence) and not isinstance(contenido, str | bytes):
            salida[hoja] = [
                copy.deepcopy(item)
                for item in contenido
                if (item.get("name") if isinstance(item, Mapping) else item) not in variables
            ]
        else:
            salida[hoja] = copy.deepcopy(contenido)
    return salida


def _hojas_que_no_coinciden(
    config: BayesRiskConfig, registro: DecisionEntry, variable: str
) -> tuple[str, ...]:
    """Las hojas que ya no reflejan la decisión sobre ``variable``; vacío si la aplica."""
    if registro.action == "rebut_backstops":
        # Las presunciones de mora: las dos hojas tienen que estar en la huella y seguir con el
        # mismo número, y la columna de mora tiene que seguir siendo el sujeto registrado. Una
        # huella incompleta, una sección ausente o una columna cambiada no se atribuyen a quien
        # decidió (pasada 1 de Codex sobre la capa A de IFRS 9).
        faltan = [hoja for hoja in _HOJAS_PRESUNCIONES if hoja not in registro.value]
        distintas = [
            hoja for hoja, valor in registro.value.items() if _hoja_escalar(config, hoja) != valor
        ]
        if _hoja_escalar(config, _HOJA_COLUMNA_MORA) != variable:
            distintas.append(_HOJA_COLUMNA_MORA)
        return tuple(dict.fromkeys([*faltan, *distintas]))
    if registro.action == "exclude" and _HOJA_COVARIABLES in registro.value:
        # Una covariable retirada de la curva: aplicada mientras no vuelva a la lista, y sólo si
        # la curva sigue ahí (sin sección no hay efecto que atribuir).
        if _hoja_escalar(config, _HOJA_COVARIABLES) is None:
            return (_HOJA_COVARIABLES,)
        covariables = _lista(config, "survival", "input.covariate_cols")
        return () if variable not in covariables else (_HOJA_COVARIABLES,)
    excluidas = _lista(config, "binning", "exclude_columns")
    if registro.action == "exclude":
        return () if variable in excluidas else (_HOJA_EXCLUIDAS,)
    if registro.action == "keep":
        faltan = [
            f"{seccion}.force_include"
            for seccion in ("selection", "model")
            if variable not in _lista(config, seccion, "force_include")
        ]
        if variable in excluidas:
            faltan.append(_HOJA_EXCLUIDAS)
        return tuple(faltan)
    # merge_bins / set_bins: los mismos cortes fijados que la huella. Si la variable se excluyó
    # después, los cortes siguen escritos y quedan en suspenso (D-EXC-1): se emite como hoy.
    guardada = _hoja_de_cortes(registro.value.get(_HOJA_CORTES), variable)
    vigente = _hoja_de_cortes(_lista(config, "binning", "variable_overrides"), variable)
    if guardada is None or vigente is None or _cortes(guardada) != _cortes(vigente):
        return (_HOJA_CORTES,)
    return ()


def _lista(config: BayesRiskConfig, seccion: str, campo: str) -> tuple[Any, ...]:
    """Una hoja lista del config; vacía si la sección no está (la decisión no vive ahí).

    ``campo`` admite una ruta con puntos dentro de la sección (``input.covariate_cols``).
    """
    valor = _valor_en(getattr(config, seccion, None), campo)
    if valor is None or isinstance(valor, str | bytes):
        return ()
    return tuple(valor) if isinstance(valor, Iterable) else ()


def _hoja_escalar(config: BayesRiskConfig, hoja: str) -> Any:
    """El valor de una hoja escalar del config por su ruta completa (``seccion.campo.subcampo``)."""
    seccion, _, campo = hoja.partition(".")
    return _valor_en(getattr(config, seccion, None), campo)


def _valor_en(objeto: Any, ruta: str) -> Any:
    """Baja por ``ruta`` (con puntos) en un modelo o un ``dict`` opaco; ``None`` si no existe."""
    actual = objeto
    for parte in ruta.split("."):
        if actual is None:
            return None
        actual = actual.get(parte) if isinstance(actual, Mapping) else getattr(actual, parte, None)
    return actual


def _como_mapping(hoja: Any) -> Mapping[str, Any] | None:
    if isinstance(hoja, Mapping):
        return hoja
    dump = getattr(hoja, "model_dump", None)
    return dump(mode="python") if callable(dump) else None


def _hoja_de_cortes(hojas: Any, variable: str) -> Mapping[str, Any] | None:
    if not isinstance(hojas, Sequence) or isinstance(hojas, str | bytes):
        return None
    for hoja in hojas:
        datos = _como_mapping(hoja)
        if datos is not None and datos.get("name") == variable:
            return datos
    return None


def _cortes(hoja: Mapping[str, Any]) -> tuple[tuple[float, ...], tuple[bool, ...]]:
    """Los cortes fijados de una hoja, comparables: lo que decide la tramificación."""
    cortes = tuple(float(c) for c in (hoja.get("user_splits") or ()))
    fijados = tuple(bool(f) for f in (hoja.get("user_splits_fixed") or ()))
    return cortes, fijados


def _huella_restringida(valor: Mapping[str, Any], variables: Sequence[str]) -> dict[str, Any]:
    """La huella filtrada a ``variables``: cada hoja lista conserva sólo sus elementos."""
    nombres = set(variables)
    salida: dict[str, Any] = {}
    for hoja, contenido in valor.items():
        if isinstance(contenido, Sequence) and not isinstance(contenido, str | bytes):
            salida[hoja] = [
                copy.deepcopy(item)
                for item in contenido
                if (item.get("name") if isinstance(item, Mapping) else item) in nombres
            ]
        else:
            salida[hoja] = copy.deepcopy(contenido)
    return salida
