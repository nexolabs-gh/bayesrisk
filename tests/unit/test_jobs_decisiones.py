"""Gate de las DECISIONES OBLIGATORIAS de un trabajo (D-OBL-6/7, enmienda DECISIONES-OBLIGATORIAS).

Una decisión obligatoria es lo que el motor **no puede rellenar por nadie**: qué define un cliente
malo en esta cartera, cómo se separa la muestra. Son `DATO-INSTITUCIONAL`, y por eso el catálogo de
defaults efectivos las omite en vez de inventarlas (D-OBL-1/2) y el trabajo las pregunta en
idioma de negocio (D-OBL-6).

**Por qué el gate es bidireccional, y por qué eso es lo único que lo hace útil.** Los paths se
declaran a mano en ``bayesrisk/ui/jobs.py`` —tienen que ser literales, porque esa capa es
*domain-agnostic* por otro gate—, así que sin nada que los ate al motor se separarían en silencio en
las dos direcciones:

- **Falta una pregunta** ⇒ alguien añade un campo obligatorio al motor y un trabajo pasa a ser
  incompletable sin que la interfaz sepa decir qué falta. Es el modo de fallo caro.
- **Sobra una pregunta** ⇒ el copy pide algo que ya tiene default, y la interfaz reclama por un
  campo que el usuario no necesita tocar.

El oráculo se deriva de ``model_fields``, que es donde Pydantic guarda la obligatoriedad de verdad.

**Las decisiones de un trabajo** (FLUJO-GUIADO-IFRS9 §3.12, ``_DECISIONES_POR_TRABAJO``) son la
misma clase en un contexto: un campo con valor de fábrica que ESE trabajo deja sin responder —la
unidad y el horizonte de la curva que alimenta una provisión—. Su gate es el mismo par: la
pregunta existe sólo si el esqueleto del trabajo deja el campo sin responder, y el trabajo la
hace. Y lo que un trabajo declara «no aplica» (un override ``null``: la corrida de cartera no tiene
target ni partición, D-ECL-2) no se pregunta.
"""

from __future__ import annotations

import re
from typing import Any, get_args

import pytest
from pydantic import BaseModel

from bayesrisk.core.config.schema import (
    cargar_configs_de_dominio,
    cargar_configs_expandibles,
)
from bayesrisk.ui.jobs import _DECISIONES_POR_TRABAJO, decisiones_de, list_jobs

#: Las 16 secciones que el formulario ofrece. Espejo del catálogo del front; el gate de deriva de
#: esa lista vive en `test_column_roles.py`, y aquí sólo acota el barrido a lo navegable.
SECCIONES_DEL_FORMULARIO = (
    "data",
    "eda",
    "binning",
    "selection",
    "model",
    "scorecard",
    "calibration",
    "performance",
    "stability",
    "validation",
    "survival",
    # IFRS9-FIRMABLE capa C: los escenarios de la institución, entre la curva y las provisiones.
    "forward",
    "provisioning_cmf",
    "provisioning_internal",
    "provisioning_ifrs9",
    "provisioning",
    "report",
    "governance",
)


def test_el_espejo_de_secciones_es_el_mismo_que_el_del_gate_de_copy() -> None:
    """Mismo motivo que en `test_effective_defaults`: un espejo a mano sin comparar se queda
    viejo en silencio, y aquí acotaría el barrido de decisiones a menos secciones de las que hay."""
    from test_copy_del_formulario import SECCIONES_DEL_FORMULARIO as DEL_GATE_DE_COPY

    assert SECCIONES_DEL_FORMULARIO == DEL_GATE_DE_COPY


def _submodelo_declarado(anotacion: Any) -> type[BaseModel] | None:
    """La clase de un campo submodelo, también si es obligatorio y admite ``null`` (D-ECL-2).

    ``data.target`` y ``data.partition`` son ``X | None`` obligatorios: el ``null`` declara una
    corrida de cartera, y cuando se declaran sus hojas obligatorias siguen siendo decisiones.
    """
    if isinstance(anotacion, type) and issubclass(anotacion, BaseModel):
        return anotacion
    ramas = [rama for rama in get_args(anotacion) if rama is not type(None)]
    if len(ramas) == 1 and isinstance(ramas[0], type) and issubclass(ramas[0], BaseModel):
        return ramas[0]
    return None


def _hojas_obligatorias(cls: type[BaseModel], prefijo: tuple[str, ...]) -> list[str]:
    """Paths de las HOJAS obligatorias sin default, bajando por los submodelos obligatorios.

    Baja sólo por lo obligatorio a propósito: dentro de un submodelo **opcional** los campos
    requeridos no son decisiones pendientes —el submodelo entero se puede omitir—, así que
    preguntarlos sería reclamar por algo que el usuario no tiene que contestar.
    """
    encontradas: list[str] = []
    for nombre, campo in cls.model_fields.items():
        if not campo.is_required():
            continue
        clave = campo.alias or nombre
        submodelo = _submodelo_declarado(campo.annotation)
        if submodelo is not None:
            hijas = _hojas_obligatorias(submodelo, (*prefijo, clave))
            # Un submodelo obligatorio cuyos hijos tienen todos default es él mismo la decisión.
            encontradas.extend(hijas or [".".join((*prefijo, clave))])
        else:
            encontradas.append(".".join((*prefijo, clave)))
    return encontradas


def _obligatorias_del_formulario() -> dict[str, list[str]]:
    """``{sección: [paths obligatorios]}`` para las secciones que el formulario ofrece.

    Se pregunta a las secciones **expandibles** (D-GOB-10), no sólo a los dominios: ``governance``
    está en el formulario desde D-GOB-11 y su ``purpose`` es la decisión de D-GOB-12. Con el loader
    de dominios el gate la saltaba en silencio y la pregunta podía desaparecer sin ponerse rojo.
    """
    disponibles = cargar_configs_expandibles()
    salida: dict[str, list[str]] = {}
    for seccion in SECCIONES_DEL_FORMULARIO:
        cls = disponibles.get(seccion)
        if cls is None:
            continue  # extra ausente: su sección no se expande, y no hay nada que preguntar
        paths = _hojas_obligatorias(cls, (seccion,))
        if paths:
            salida[seccion] = paths
    return salida


def _decisiones_declaradas() -> dict[str, dict[str, Any]]:
    """``{path: decisión}`` de todo lo que el catálogo declara, sin repetir.

    Catálogo COMPLETO (D-JUR-9.2): las decisiones obligatorias son una propiedad de las
    secciones, y las de referencia siguen en el formulario.
    """
    declaradas: dict[str, dict[str, Any]] = {}
    for job in list_jobs(incluir_referencia=True):
        for decision in job["required_decisions"]:
            declaradas[decision["path"]] = decision
    return declaradas


def test_el_barrido_no_es_vacuo() -> None:
    """Sin esto, un oráculo roto daría verde con cero campos — ya pasó en este repo."""
    obligatorias = _obligatorias_del_formulario()
    assert obligatorias, "el barrido no encontró ni una sección con campos obligatorios"
    assert "data" in obligatorias, "`data.target.bad_rule` existe: el oráculo está roto"
    assert _decisiones_declaradas(), "el catálogo no declara ninguna decisión"


def _paths_de_trabajo() -> set[str]:
    return {d["path"] for decisiones in _DECISIONES_POR_TRABAJO.values() for d in decisiones}


def _nulos(job: dict[str, Any]) -> list[str]:
    """Los caminos que el trabajo declara «no aplica» (override ``null``)."""
    return [ruta for ruta, valor in job["overrides"] if valor is None]


def _bajo(ruta: str, raices: list[str]) -> bool:
    return any(ruta == raiz or ruta.startswith(f"{raiz}.") for raiz in raices)


def test_toda_decision_declarada_es_de_verdad_obligatoria() -> None:
    """Dirección 1: no se reclama por un campo que ya tiene default (salvo en su trabajo)."""
    todas = {p for paths in _obligatorias_del_formulario().values() for p in paths}
    sobrantes = sorted(set(_decisiones_declaradas()) - todas - _paths_de_trabajo())
    assert sobrantes == [], (
        f"el catálogo pregunta por campos que no son obligatorios: {sobrantes}. "
        "Si el motor les dio un default, quita su pregunta del catálogo."
    )


def test_todo_campo_obligatorio_del_formulario_tiene_su_pregunta() -> None:
    """Dirección 2: la que de verdad importa.

    Sin ella, añadir un campo obligatorio al motor deja un trabajo incompletable y la interfaz
    callada — el usuario ve «este campo es obligatorio» y ningún sitio le dice cuál ni por qué.
    """
    declaradas = set(_decisiones_declaradas())
    faltan = sorted(
        f"{seccion}: {path}"
        for seccion, paths in _obligatorias_del_formulario().items()
        for path in paths
        if path not in declaradas
    )
    assert faltan == [], (
        f"campos obligatorios sin pregunta declarada: {faltan}. Añádeles su entrada en "
        "`_DECISIONES_POR_SECCION` de `bayesrisk/ui/jobs.py`, con la pregunta en idioma de negocio."
    )


def test_un_trabajo_hereda_exactamente_las_decisiones_de_sus_secciones() -> None:
    """El reparto por sección no puede dejar a un trabajo con preguntas de una sección que no ve.

    Hereda las de sus secciones, menos las que caen bajo un camino que declara «no aplica», más las
    suyas propias.
    """
    obligatorias = _obligatorias_del_formulario()
    for job in list_jobs(incluir_referencia=True):
        suyas = set(job["sections"])
        for decision in job["required_decisions"]:
            seccion = decision["path"].split(".", 1)[0]
            assert seccion in suyas, (
                f"«{job['id']}» pregunta por {decision['path']}, de una sección que no muestra"
            )
        esperadas = {
            p
            for s, paths in obligatorias.items()
            if s in suyas
            for p in paths
            if not _bajo(p, _nulos(job))
        } | {d["path"] for d in _DECISIONES_POR_TRABAJO.get(job["id"], ())}
        assert {d["path"] for d in job["required_decisions"]} == esperadas, job["id"]


def test_una_decision_bajo_un_camino_que_el_trabajo_declara_nulo_no_se_pregunta() -> None:
    """FLUJO-GUIADO-IFRS9 §3.12: la corrida de cartera no pregunta qué es un cliente malo."""
    por_id = {job["id"]: job for job in list_jobs(incluir_referencia=True)}
    ifrs9 = por_id["provisiones_ifrs9"]
    assert {"data.target", "data.partition"} <= set(_nulos(ifrs9))
    preguntadas = [d["path"] for d in ifrs9["required_decisions"]]
    assert not [p for p in preguntadas if _bajo(p, ["data.target", "data.partition"])]
    # Y el mismo filtro, por la función que arma el catálogo.
    assert [d["path"] for d in decisiones_de(["data"], no_aplican=["data.target"])] == [
        "data.partition.strategy"
    ]


def _valor_sembrado(job: dict[str, Any], ruta: str) -> tuple[bool, Any]:
    """``(tiene_valor, valor)`` del camino en el esqueleto: el override, o el de fábrica."""
    from bayesrisk.core.config.effective_defaults import DISCRIMINADOR, build_effective_defaults

    for override, valor in job["overrides"]:
        if override == ruta:
            return True, valor
    nodo: Any = build_effective_defaults()["sections"]
    for tramo in ruta.split("."):
        hijos = nodo.get("children") if isinstance(nodo.get(DISCRIMINADOR), bool) else nodo
        assert isinstance(hijos, dict) and tramo in hijos, ruta
        nodo = hijos[tramo]
    if not nodo[DISCRIMINADOR]:
        return False, None
    return True, nodo.get("value")


def test_una_decision_de_trabajo_llega_sin_responder_al_esqueleto() -> None:
    """Dos sentidos: el trabajo existe y la hace, y su esqueleto deja el campo SIN respuesta.

    Una decisión de trabajo sobre un campo que el esqueleto trae con valor saldría ya contestada
    por el motor —«period» como unidad—, que es el falso «ya está» de D-OBL-5: el trabajo lo siembra
    en blanco o su default es nulo.
    """
    por_id = {job["id"]: job for job in list_jobs(incluir_referencia=True)}
    assert _DECISIONES_POR_TRABAJO, "el gate no puede ser vacuo"
    for job_id, decisiones in _DECISIONES_POR_TRABAJO.items():
        assert job_id in por_id, job_id
        preguntadas = [d["path"] for d in por_id[job_id]["required_decisions"]]
        for decision in decisiones:
            assert decision["path"] in preguntadas, (job_id, decision["path"])
            _tiene, valor = _valor_sembrado(por_id[job_id], decision["path"])
            assert valor in (None, ""), (job_id, decision["path"], valor)


def test_los_dos_trabajos_con_survival_preguntan_cinco_cosas() -> None:
    """Ancla nominal: escrita a mano, no derivada, para que el gate no sea una tautología.

    La quinta es el propósito de la ficha del modelo (D-GOB-12), que heredan los diez trabajos
    porque los diez ofrecen ``governance`` (D-GOB-11). Que sea la última no es casual: el orden es
    el de ``_DECISIONES_POR_SECCION`` y la sección va al final del formulario, como ``report``.
    «Provisiones IFRS 9» no pregunta por target ni partición (corrida de cartera, D-ECL-2) y sí por
    la unidad y el horizonte de la curva (FLUJO-GUIADO-IFRS9 §3.12).
    """
    por_id = {job["id"]: job for job in list_jobs(incluir_referencia=True)}
    if "survival" not in cargar_configs_de_dominio():
        pytest.skip("el extra de survival no está instalado")
    assert [d["path"] for d in por_id["pd_lifetime"]["required_decisions"]] == [
        "data.target.bad_rule",
        "data.partition.strategy",
        "survival.input.duration_col",
        "survival.input.event_col",
        "governance.purpose",
    ]
    # Desde la capa C de IFRS9-FIRMABLE, también las dos de `forward` —las variables macro, que la
    # pantalla lee de las dos tablas—, que duermen mientras la sección esté apagada (latente).
    assert [d["path"] for d in por_id["provisiones_ifrs9"]["required_decisions"]] == [
        "survival.input.duration_col",
        "survival.input.event_col",
        "survival.time_grid.time_unit",
        "survival.time_grid.horizon_periods",
        "forward.input.macro_source.variable_cols",
        "forward.satellite.factor_cols",
        "governance.purpose",
    ]
    assert [d["path"] for d in por_id["scorecard_pd"]["required_decisions"]] == [
        "data.target.bad_rule",
        "data.partition.strategy",
        "governance.purpose",
    ]


#: Lo que una pregunta NO puede contener: el path, el nombre de una clase o cualquier literal que
#: sólo signifique algo dentro del código (D-OBL-9). El usuario lee negocio, no coordenadas.
_JERGA = re.compile(
    r"\b(None|True|False|null|bad_rule|good_rule|target_col|duration_col|event_col|strategy|"
    r"partition|BaseModel|BayesRiskConfig|config_hash|DataFrame|dataframe)\b"
)


def test_el_copy_de_una_decision_no_filtra_jerga_interna() -> None:
    """El path es la coordenada interna; lo que se lee es la pregunta.

    Mismo criterio que el gate de copy del catálogo de trabajos: una superficie que un humano lee no
    puede nombrar un campo del config. Aquí importa el doble, porque la decisión es justo el sitio
    donde la tentación de «pon el nombre del campo y se entiende» es más fuerte.
    """
    ofensores: list[str] = []
    for path, decision in _decisiones_declaradas().items():
        for campo in ("question", "help"):
            encontrado = _JERGA.search(decision[campo])
            if encontrado:
                ofensores.append(f"{path}.{campo}: «{encontrado.group(0)}»")
    assert ofensores == [], ofensores


def test_una_decision_declara_sus_cuatro_piezas_y_se_lee_como_pregunta() -> None:
    """Forma mínima: sin `question` no hay nada que enseñar, y sin `help` la pregunta queda sola.

    `answer_forms` entró con D-COL-6 y va en la igualdad, no en un superset: la clave tiene que
    estar SIEMPRE —vacía si la decisión no admite formas— para que una decisión nueva no pueda
    olvidarse de declarar si las tiene. Lo que hay dentro lo gobierna
    `test_jobs_formas_de_respuesta.py`.
    """
    for path, decision in _decisiones_declaradas().items():
        assert set(decision) == {"path", "question", "help", "answer_forms"}, path
        assert decision["question"].endswith("?"), f"{path}: la pregunta no pregunta"
        assert len(decision["help"]) > 40, f"{path}: la ayuda no ayuda"


def test_el_catalogo_devuelve_copias() -> None:
    """Mutar lo que devuelve el catálogo no puede contaminar el proceso."""
    primero = list_jobs(incluir_referencia=True)[0]["required_decisions"]
    primero[0]["question"] = "MUTADO"
    assert list_jobs(incluir_referencia=True)[0]["required_decisions"][0]["question"] != "MUTADO"


def test_decisiones_de_no_repite_ni_depende_del_orden() -> None:
    """Dos trabajos con las mismas secciones preguntan lo mismo, en el mismo orden."""
    assert decisiones_de(["data", "survival"]) == decisiones_de(["survival", "data"])
    assert decisiones_de(["data", "data"]) == decisiones_de(["data"])
    assert decisiones_de([]) == []
    assert decisiones_de(["binning", "report"]) == [], "esas secciones no imponen decisiones"
