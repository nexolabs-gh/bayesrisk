"""La maquinaria común de las puertas guiadas (SDD-31 D-SIM-1/D-SIM-6; FLUJO-GUIADO-IFRS9 §2).

``bayesrisk.Scorecard`` y ``bayesrisk.Ecl`` son dos clientes de :func:`bayesrisk.run` que arman su
``BayesRiskConfig`` con argumentos distintos y cuentan etapas distintas, pero comparten **todo** lo
que no es de su dominio: la copia de los datos con su huella, el candado por carpeta, el informe
asociado a su corrida por identidad de intento, ``run(until=)``/``resume()``, el registro de las
decisiones humanas en ``config.decisions`` y el empaquetado. Vive aquí una sola vez —se movió tal
cual desde ``guided/scorecard.py`` cuando nació la segunda puerta— para que una corrección de
integridad (las pasadas de Codex sobre la capa B del scorecard encontraron seis) no tenga que
repetirse en dos copias.

Cada puerta declara su nombre, su paso en el trail, sus errores y su familia de resúmenes como
atributos de clase; lo que infiere y lo que decide sigue en su propio módulo.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import IO, Any, ClassVar, Final, Self

import pandas as pd
from pydantic import ValidationError

from bayesrisk.core.config import BayesRiskConfig, RunConfig, config_hash, dump_config
from bayesrisk.core.exceptions import BayesRiskError, ConfigError
from bayesrisk.guided.inference import AUTOR_PUERTA, Inferencia
from bayesrisk.guided.summaries import (
    FinalSummary,
    StageSummary,
    SummaryContext,
    build_final_summary,
    build_stage_summary,
    decision_line,
    stage_labels,
)
from bayesrisk.report.prose import _plural

__all__: list[str] = []

#: Nombre del subdirectorio de la corrida dentro de la carpeta del proyecto. ``bayesrisk.run``
#: sustituye **entero** su destino al consolidar una corrida y aparta el anterior a un respaldo
#: lateral; por eso la corrida vive en un subdirectorio y el snapshot de datos, el config vigente
#: y el informe viven al lado, donde ninguna consolidación se los lleva.
_RUN_SUBDIR: Final = "run"
_REPORTS_SUBDIR: Final = "reports"
_INPUT_SUBDIR: Final = "input"
_CONFIG_NAME: Final = "config.yaml"
_MODEL_CARD_NAME: Final = "model_card.json"
_LOCK_NAME: Final = ".lock"


class _PuertaGuiada:
    """Lo común de una puerta guiada: proyecto en disco, corrida, resúmenes y decisiones.

    Las subclases fijan los atributos de clase y, en su ``__init__``, llaman a :meth:`_iniciar`,
    cargan con :meth:`_cargar`, arman el config y terminan con :meth:`_resolver_pipeline` y
    :meth:`_publicar_snapshot` (o :meth:`_descartar_snapshot` si algo falla).
    """

    #: El nombre público de la puerta, el que leen los mensajes («Construye un Scorecard nuevo»).
    _PUERTA: ClassVar[str]
    #: El paso con que la puerta firma sus eventos en el trail.
    _GUIDED_STEP: ClassVar[str]
    #: Lo que la puerta rechaza antes de correr, y la corrida fallida con ``raise_on_error``.
    _InputError: ClassVar[type[ConfigError]]
    _RunError: ClassVar[type[BayesRiskError]]
    #: La familia de resúmenes con que habla (``guided.summaries``): rótulos, orden y resumen final.
    _FAMILIA: ClassVar[str]

    _name: str
    _project_dir: Path
    _run_dir: Path
    _reports_dir: Path
    _config_path: Path
    _config: BayesRiskConfig
    _steps: tuple[str, ...]
    _inferences: tuple[Inferencia, ...]
    _source_label: str
    _partition_label: str
    _inference_lines: tuple[str, ...]

    def _iniciar(self, name: str, run_dir: str | Path) -> None:
        """La carpeta del proyecto y el estado vacío de la puerta, antes de leer los datos."""
        self._name = _nombre_de_proyecto(name, self._InputError)
        raiz = Path(run_dir).resolve()
        self._project_dir = (raiz / self._name).resolve()
        if self._project_dir.parent != raiz:
            # Defensa en profundidad tras `_nombre_de_proyecto`: la carpeta del proyecto vive
            # SIEMPRE un nivel bajo `run_dir` (pasada 1 de Codex sobre la capa B).
            raise self._InputError(
                f"name={name!r} sacaría la carpeta del proyecto de run_dir={str(run_dir)!r}."
            )
        self._run_dir = self._project_dir / _RUN_SUBDIR
        self._reports_dir = self._project_dir / _REPORTS_SUBDIR
        self._config_path = self._project_dir / _CONFIG_NAME
        self._until: str | None = None
        self._study: Any = None
        self._stage_summaries: dict[str, StageSummary] = {}
        self._final: FinalSummary | None = None
        self._pending_decisions = False
        self._echo: Callable[[str], None] = print
        # El snapshot de los datos, escrito en un temporal al cargar y publicado con su nombre
        # definitivo sólo después de validar todo (pasada 1 de Codex sobre A: nada se pisa ni se
        # deja escrito si la puerta no valida).
        self._snapshot_pendiente: tuple[Path, Path] | None = None
        # Huella de los bytes sobre los que se infirió: `run()` la vuelve a medir antes de correr
        # (pasadas 1 y 2 de Codex sobre la capa B: el motor relee el archivo en cada corrida).
        self._source_digest: tuple[Path, str] | None = None

    # ── construcción ────────────────────────────────────────────────────────────────────

    def _publicar_snapshot(self) -> None:
        """Da su nombre definitivo al snapshot ya validado todo, sin pisar uno existente."""
        if self._snapshot_pendiente is None:
            return
        snapshot, temporal = self._snapshot_pendiente
        self._snapshot_pendiente = None
        if snapshot.exists():
            temporal.unlink(
                missing_ok=True
            )  # mismo contenido por construcción: el nombre es su hash
            return
        os.replace(temporal, snapshot)

    def _descartar_snapshot(self) -> None:
        """Una puerta que no validó no deja su copia a medias en ``input/``."""
        if self._snapshot_pendiente is None:
            return
        _snapshot, temporal = self._snapshot_pendiente
        self._snapshot_pendiente = None
        temporal.unlink(missing_ok=True)
        for carpeta in (temporal.parent, self._project_dir):
            try:
                carpeta.rmdir()  # sólo si quedó vacía: nunca se borra evidencia ajena
            except OSError:
                break

    def _reservar_snapshot(self, contenido: bytes, sufijo: str) -> tuple[Path, Path, str]:
        """Escribe ``contenido`` en un temporal de ``input/``: (definitivo, temporal, huella).

        El nombre definitivo lleva la huella del contenido: otro archivo con el mismo ``name``
        deja un snapshot nuevo y no pisa el que referencia la evidencia de una corrida anterior.
        El temporal conserva la extensión para que el cargador infiera el formato.
        """
        digest = hashlib.sha256(contenido).hexdigest()
        snapshot = self._project_dir / _INPUT_SUBDIR / f"data-{digest[:16]}{sufijo}"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporal = snapshot.with_name(f".data-{digest[:16]}.{os.getpid()}.tmp{sufijo}")
        temporal.write_bytes(contenido)
        self._snapshot_pendiente = (snapshot, temporal)
        self._source_digest = (snapshot, digest)
        return snapshot, temporal, digest

    def _cargar(self, data: str | Path | pd.DataFrame) -> tuple[pd.DataFrame, str, str]:
        """Carga el archivo con el cargador del motor, o persiste el DataFrame como snapshot."""
        if isinstance(data, pd.DataFrame):
            if data.empty:
                raise self._InputError("data= es un DataFrame vacío.")
            # El snapshot es inmutable y se nombra por su contenido: otro DataFrame con el mismo
            # `name` deja un archivo nuevo y no pisa el que referencia la evidencia de una
            # corrida anterior. Se escribe en disco sólo después de validar toda la puerta
            # (`_publicar_snapshot`), no aquí (pasada 1 de Codex sobre la capa A).
            buffer = io.BytesIO()
            data.to_parquet(buffer)
            contenido = buffer.getvalue()
            snapshot, _temporal, _digest = self._reservar_snapshot(contenido, ".parquet")
            return (
                pd.read_parquet(io.BytesIO(contenido)),
                str(snapshot),
                f"DataFrame en memoria, guardado como {snapshot}",
            )
        ruta = Path(data).resolve()
        if not ruta.is_file():
            raise self._InputError(f"data= apunta a un archivo que no existe: {ruta}")
        from bayesrisk.data.config import LoadingConfig
        from bayesrisk.data.loading import DataLoader

        # Un archivo por ruta también se copia al proyecto: la inferencia y cada corrida leen
        # exactamente los MISMOS bytes (un archivo que un proceso externo reemplaza entre la
        # lectura y la corrida ya no puede entrenar otro modelo con inferencias viejas; pasada 2
        # de Codex sobre la capa B), y `config.yaml` + `input/` reproducen la corrida solos.
        contenido = ruta.read_bytes()
        snapshot, temporal, _digest = self._reservar_snapshot(contenido, ruta.suffix.lower())
        try:
            frame = DataLoader.from_config(LoadingConfig(source=str(temporal))).load()
        except BayesRiskError as exc:
            raise self._InputError(f"No se pudo leer {ruta}: {exc}") from exc
        if frame.empty:
            raise self._InputError(f"El archivo no trae filas: {ruta}")
        return frame, str(snapshot), f"{ruta} (copia en {snapshot})"

    def _verificar_fuente(self) -> None:
        """La corrida lee los mismos bytes sobre los que la puerta infirió, o no corre.

        El config referencia una ruta mutable y el motor la recarga en cada ``run()``; si el
        archivo cambió entre medio, las inferencias (esquema, columnas, muestras) describirían
        otros datos y la corrida calcularía en silencio otro resultado con el mismo config.
        Aplica también al snapshot de un ``DataFrame``: su nombre lleva la huella, pero un archivo
        editado en disco ya no es el que la puerta escribió.
        """
        if self._source_digest is None:
            return
        ruta, esperado = self._source_digest
        if not ruta.is_file():
            raise self._InputError(
                f"El archivo de datos ya no existe: {ruta}. Construye un {self._PUERTA} nuevo."
            )
        if _huella_del_archivo(ruta) != esperado:
            raise self._InputError(
                f"El archivo {ruta} cambió desde que se construyó el {self._PUERTA}: las "
                f"inferencias se hicieron sobre otro contenido. Construye un {self._PUERTA} nuevo "
                "sobre el archivo actual para volver a inferir y correr."
            )

    @classmethod
    def _resolver_id(
        cls, frame: pd.DataFrame, id_: str | None
    ) -> tuple[str | None, list[str] | None, str]:
        if id_ is None:
            return None, None, "sin identificador declarado: se usa el índice del archivo"
        if id_ in frame.columns:
            return None, [id_], f"{id_} (columna, llave de unicidad)"
        if frame.index.name == id_:
            return id_, None, f"{id_} (índice del archivo)"
        raise cls._InputError(
            f"id={id_!r} no es una columna ni el índice del archivo. Columnas disponibles: "
            f"{', '.join(str(c) for c in frame.columns)}."
        )

    @classmethod
    def _resolver_pipeline(cls, config: BayesRiskConfig) -> tuple[BayesRiskConfig, tuple[str, ...]]:
        """El config con sus secciones coaccionadas y los pasos en orden, comprobados sin correr.

        Un ``BayesRiskConfig`` recién validado lleva las secciones de dominio **opacas** (``dict``)
        si su capa no está importada; la comprobación del pipeline (D-PIPE-3) las coacciona a su
        clase real, y la puerta se queda con ESE config: es el que corre, el que exporta y el que
        las decisiones humanas editan campo a campo (medido fuera de pytest, donde nadie importa
        los dominios de antemano).
        """
        from bayesrisk.api import _audit_config, _governance_config, _tracking_config
        from bayesrisk.core.study import Study

        study = Study(config, apply_global_seed=False)
        try:
            pasos = study.check_pipeline()
        except ValidationError as exc:
            from bayesrisk.api import _mensaje_de_validacion

            raise cls._InputError(
                f"El config armado no es ejecutable: {_mensaje_de_validacion(exc)}"
            ) from exc
        except Exception as exc:
            raise cls._InputError(f"El config armado no es ejecutable: {exc}") from exc
        # Las secciones de infraestructura no son pasos y la comprobación del pipeline no las
        # toca: sin este paso quedan opacas en un intérprete que no importó su capa, y
        # `config.governance.purpose` dependería del orden de import.
        coaccionado = study.config
        tipadas = {
            "audit": _audit_config(coaccionado.audit),
            "governance": _governance_config(coaccionado.governance),
            "tracking": _tracking_config(coaccionado.tracking),
        }
        return coaccionado.model_copy(update=tipadas), tuple(pasos)

    def _validar_config(self, cfg: Mapping[str, Any]) -> BayesRiskConfig:
        """El config validado, con el mensaje de la puerta si un argumento no cabe."""
        try:
            return BayesRiskConfig.model_validate(cfg)
        except ValidationError as exc:
            from bayesrisk.api import _mensaje_de_validacion

            raise self._InputError(
                f"Un argumento no cumple las restricciones del motor: {_mensaje_de_validacion(exc)}"
            ) from exc

    # ── propiedades ─────────────────────────────────────────────────────────────────────

    @property
    def config(self) -> BayesRiskConfig:
        """El ``BayesRiskConfig`` completo que corre (la puerta completa lo ve todo)."""
        return self._config

    @property
    def config_hash(self) -> str:
        """La identidad de la corrida completa sobre el config vigente."""
        return config_hash(self._config)

    @property
    def study(self) -> Any:
        """El ``Study`` de la última corrida, o ``None`` si aún no corrió."""
        return self._study

    @property
    def steps(self) -> tuple[str, ...]:
        """Las etapas del pipeline en orden; los valores válidos de ``run(until=)``."""
        return self._steps

    @property
    def project_dir(self) -> Path:
        """``<run_dir>/<name>``: donde queda todo."""
        return self._project_dir

    @property
    def results(self) -> dict[str, pd.DataFrame]:
        """La tabla de decisión de cada etapa que ya corrió (con sus rótulos en español).

        Cada una es un ``DataFrame`` con los números intactos que se muestra como la lee una
        persona —coma decimal, miles, porcentajes—, con la misma regla del resumen de su etapa.
        """
        from bayesrisk.guided.summaries import TablaDeEtapa

        return {
            etapa: TablaDeEtapa.de(resumen.table, resumen.formats)
            for etapa, resumen in self._stage_summaries.items()
            if resumen.table is not None
        }

    @property
    def inferences(self) -> tuple[Inferencia, ...]:
        """Lo que la puerta infirió y declara al trail en cada corrida."""
        return self._inferences

    def to_yaml(self) -> str:
        """El config vigente en YAML, para la puerta completa o la pantalla."""
        return dump_config(self._config)

    # ── correr ──────────────────────────────────────────────────────────────────────────

    def run(self, until: str | None = None, *, raise_on_error: bool = False) -> Self:
        """Corre el pipeline completo —o hasta ``until`` inclusive— y cuenta cada etapa.

        ``until`` recorta ``run.steps`` al prefijo del pipeline: es una corrida parcial con su
        propio ``config_hash``. Ante un fallo de dominio la corrida devuelve el estado y el
        resumen final lo dice; con ``raise_on_error=True`` se levanta el error de corrida de la
        puerta con el mismo diagnóstico. La carpeta del proyecto admite una corrida a la vez: si
        otra la tiene, se levanta ese mismo error antes de mover nada.
        """
        if until is not None and until not in self._steps:
            raise self._InputError(
                f"until={until!r} no es una etapa de este pipeline. Etapas: "
                f"{', '.join(self._steps)}."
            )
        pasos = list(self._steps[: self._steps.index(until) + 1]) if until is not None else None
        config = self._config.model_copy(update={"run": RunConfig(steps=pasos)})
        self._verificar_fuente()
        # Un solo escritor por carpeta de proyecto: dos corridas a la vez sobre el mismo
        # `run_dir/name` —los defaults, en dos notebooks— mezclarían informe y evidencia (pasada
        # de cierre de Codex sobre la capa A). El candado lo suelta el sistema operativo si el
        # proceso muere, así que nunca queda uno huérfano.
        self._project_dir.mkdir(parents=True, exist_ok=True)
        try:
            candado = _bloquear_carpeta(self._project_dir / _LOCK_NAME)
        except OSError as exc:
            raise self._RunError(
                f"Otra corrida está en curso en la carpeta '{self._project_dir}' (candado "
                f"'{_LOCK_NAME}'). Espera a que termine, o usa otro name= o run_dir= para "
                "correr en paralelo."
            ) from exc
        try:
            return self._correr(config, until, raise_on_error=raise_on_error)
        finally:
            _liberar_carpeta(candado)

    def _correr(self, config: BayesRiskConfig, until: str | None, *, raise_on_error: bool) -> Self:
        """El intento, ya con el candado de la carpeta tomado."""
        import bayesrisk

        self._preparar_proyecto()
        self._until = until
        self._stage_summaries = {}
        self._final = None
        # El informe se asocia a su corrida por identidad de intento (pasadas de Codex sobre A2):
        # el `reports/` previo se aparta con el token de este intento y sólo vuelve a moverse al
        # hermano `.run.old.*` que ESTA consolidación cree; si el intento revienta, su propio
        # `reports/` va al `.run.failed.*` que ESTE intento deje, y el previo vuelve a su sitio.
        token = uuid.uuid4().hex[:8]
        previo = self._apartar_informe_previo(token)
        hermanos_antes = self._hermanos_de_corrida()
        try:
            self._study = bayesrisk.run(
                config,
                run_dir=self._run_dir,
                preamble=self._preamble(),
                on_step=self._contar_etapa,
            )
        except BaseException:
            self._asociar_informe_de_intento_fallido(hermanos_antes)
            self._restaurar_informe_previo(previo)
            raise
        self._archivar_informe_previo(previo, hermanos_antes)
        self._pending_decisions = False
        self._final = build_final_summary(
            self._study, tuple(self._stage_summaries.values()), self._context()
        )
        for linea in self._final.headline():
            self._echo(linea)
        if self._study.run_context.status != "done" and raise_on_error:
            raise self._RunError(self._final.execution)
        return self

    def resume(self) -> Self:
        """Corrida **nueva y completa** sobre el config vigente (D-SIM-6).

        Nada se reutiliza de la corrida anterior: ``run_id``, lineage y evidencia son propios, y
        la anterior queda como respaldo lateral (``.run.old.*``) con su informe.
        """
        return self.run(until=None)

    def summary(self, stage: str | None = None) -> FinalSummary | StageSummary:
        """El resumen final o el de una etapa que ya corrió."""
        if stage is None:
            if self._final is None:
                self._final = build_final_summary(
                    self._study, tuple(self._stage_summaries.values()), self._context()
                )
            return self._final
        rotulos = stage_labels(self._FAMILIA)
        if stage not in rotulos:
            raise self._InputError(
                f"summary({stage!r}): no existe esa etapa. Etapas: {', '.join(rotulos)}."
            )
        resumen = self._stage_summaries.get(stage)
        if resumen is None:
            raise self._InputError(
                f"La etapa «{rotulos[stage]}» no corrió todavía: llama a run() primero."
            )
        return resumen

    # ── decidir ─────────────────────────────────────────────────────────────────────────

    def _registrar_decision(
        self, accion: str, variables: Sequence[str], motivo: str, hojas: Mapping[str, Any]
    ) -> None:
        """Agrega la decisión al registro ``decisions`` del config (D-DEC-2): sólo agregar.

        Es la única fuente: viaja en ``to_yaml()``, cada corrida la declara al trail desde el
        config (``Study.run``) y una decisión posterior sobre la misma variable no borra la
        anterior —``exclude`` y después ``keep`` dejan los dos registros con sus motivos—.
        ``value`` es la huella de las hojas que la decisión dejó escritas, la misma que el evento
        lleva en ``valor``.
        """
        self._agregar_registro(self._nuevo_registro(accion, variables, motivo, hojas))

    def _nuevo_registro(
        self, accion: str, variables: Sequence[str], motivo: str, hojas: Mapping[str, Any]
    ) -> Any:
        """El ``DecisionEntry`` de una decisión, validado y **sin tocar el config**.

        Una puerta que arma el registro antes de mutar el config no puede quedar con el efecto
        escrito y sin su motivo si el registro no valida (pasada 1 de Codex sobre la capa A de
        IFRS 9: ``exclude(["x", "x"])``).
        """
        from bayesrisk.core.config.schema import DecisionEntry

        try:
            return DecisionEntry(
                action=accion,  # type: ignore[arg-type]  # una de las acciones de las puertas
                columns=tuple(variables),
                reason=motivo,
                author="usuario",
                value=deepcopy(dict(hojas)),
            )
        except ValidationError as exc:
            from bayesrisk.api import _mensaje_de_validacion

            raise self._InputError(
                f"{accion}(): la decisión no se puede registrar: {_mensaje_de_validacion(exc)}"
            ) from exc

    def _agregar_registro(self, registro: Any) -> None:
        """Agrega un registro ya validado al final de ``config.decisions`` (sólo agregar)."""
        self._config = self._config.model_copy(
            update={"decisions": (*self._config.decisions, registro)}
        )

    @property
    def _decisions(self) -> list[dict[str, Any]]:
        """Las decisiones registradas, como el payload de su evento (lo que leen los resúmenes)."""
        from bayesrisk.core.decisions import payload_de_decision

        return [payload_de_decision(registro) for registro in self._config.decisions]

    def _motivo(self, reason: str, accion: str) -> str:
        motivo = str(reason).strip() if reason is not None else ""
        if not motivo:
            raise self._InputError(
                f"{accion}() exige reason=: la decisión queda en el registro de auditoría con su "
                "motivo, y un motivo en blanco no le sirve a quien valide."
            )
        return motivo

    def _actualizar_seccion(self, seccion: str, campos: Mapping[str, Any]) -> None:
        """Reconstruye una sección del config con ``campos`` y la vuelve a validar entera."""
        actual = getattr(self._config, seccion)
        volcado = actual.model_dump(mode="python", by_alias=True)
        volcado.update(campos)
        try:
            nueva = type(actual).model_validate(volcado)
        except ValidationError as exc:
            from bayesrisk.api import _mensaje_de_validacion

            raise self._InputError(
                f"La decisión deja la sección «{seccion}» inválida: {_mensaje_de_validacion(exc)}"
            ) from exc
        self._config = self._config.model_copy(update={seccion: nueva})

    # ── exportar ────────────────────────────────────────────────────────────────────────

    def _exportar_excel(self) -> tuple[Path, ...]:
        """Los libros Excel de la familia de esta puerta, uno por etapa y el de decisiones.

        Bajo el candado y sobre la evidencia PROPIA: otra puerta con el mismo `run_dir/name` puede
        haber consolidado su corrida en `run/` —el trail que el libro de decisiones leería—, y este
        objeto escribiría sus tablas en memoria junto a decisiones ajenas (pasada 3 de Codex sobre
        la capa B del scorecard).
        """
        from bayesrisk.guided.export import EXCEL_SUBDIR, write_stage_workbooks

        candado = self._tomar_candado("exportar")
        try:
            self._exigir_evidencia_propia("export_excel")
            escritos = write_stage_workbooks(
                self._study,
                self._stage_summaries,
                directory=self._project_dir / EXCEL_SUBDIR,
                report_config=self._config.report,
                trail_path=self._context().trail_path,
                family=self._FAMILIA,
            )
        finally:
            _liberar_carpeta(candado)
        self._echo(
            f"Excel por etapa: {len(escritos)} "
            f"{_plural(len(escritos), 'libro', 'libros')} en {self._project_dir / EXCEL_SUBDIR}"
        )
        return escritos

    def export(self, destination: str | Path) -> Path:
        """Empaqueta la carpeta del proyecto en un ``.zip`` (hallazgo #8 de INTEGRACION-EXTERNA).

        Entran el config vigente, el snapshot de datos, la evidencia de la corrida (``run/``), el
        informe y el Excel si se exportó; quedan fuera el candado y los respaldos de corridas
        anteriores. Devuelve la ruta del archivo escrito.
        """
        from bayesrisk.guided.export import pack_project

        # Una corrida PROPIA, bajo el candado: la carpeta existe desde que un DataFrame publica
        # su snapshot, y un `name` repetido puede encontrar la corrida de otro objeto (pasadas 2
        # y 3 de Codex sobre B).
        candado = self._tomar_candado("empaquetar")
        try:
            self._exigir_evidencia_propia("export")
            ruta = pack_project(self._project_dir, Path(destination))
        except FileNotFoundError as exc:
            raise self._InputError(str(exc)) from exc
        finally:
            _liberar_carpeta(candado)
        self._echo(f"Paquete de la corrida: {ruta}")
        return ruta

    def _tomar_candado(self, accion: str) -> IO[bytes]:
        """El candado de la carpeta del proyecto, o el error de corrida si otro lo tiene."""
        self._project_dir.mkdir(parents=True, exist_ok=True)
        try:
            return _bloquear_carpeta(self._project_dir / _LOCK_NAME)
        except OSError as exc:
            raise self._RunError(
                f"Otra corrida está en curso en la carpeta '{self._project_dir}': espera a que "
                f"termine antes de {accion}."
            ) from exc

    def _exigir_evidencia_propia(self, accion: str) -> None:
        """La evidencia consolidada en ``run/`` es la de la corrida de ESTE objeto, o no se toca."""
        if self._study is None or self._study.run_context.run_id is None:
            raise self._InputError(
                f"{accion}() trabaja sobre la corrida de este {self._PUERTA}: llama a run() "
                "primero."
            )
        if _run_id_en_disco(self._run_dir) != self._study.run_context.run_id:
            raise self._InputError(
                f"La evidencia en {self._run_dir} no es la de la corrida de este {self._PUERTA} "
                "(otra corrida ocupó la carpeta): vuelve a correr antes de exportar."
            )

    def _repr_html_(self) -> str:
        if self._final is None:
            return (
                f'<div class="bayesrisk-summary"><b>{self._PUERTA} «{self._name}»</b>: listo '
                f"para correr ({len(self._steps)} etapas). Llama a <code>run()</code>.</div>"
            )
        return self._final._repr_html_()

    def __repr__(self) -> str:
        """Nombre, carpeta y estado de la última corrida."""
        estado = "sin correr" if self._study is None else str(self._study.run_context.status)
        return (
            f"{self._PUERTA}(name={self._name!r}, project_dir={str(self._project_dir)!r}, "
            f"estado={estado!r})"
        )

    # ── mecánica ────────────────────────────────────────────────────────────────────────

    def _preparar_proyecto(self) -> None:
        """Crea la carpeta del proyecto y escribe el config vigente."""
        self._project_dir.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(self.to_yaml(), encoding="utf-8")
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    # El informe se escribe fuera del `run_dir` (§3.1) y ``bayesrisk.run`` sustituye entero su
    # destino al consolidar; asociar cada informe a la evidencia de SU corrida —y sólo a ésa— es
    # lo que las cuatro funciones siguientes garantizan por identidad de intento, nunca por
    # heurísticas sobre qué hay en `run/` (pasadas de Codex sobre A2, A2-bis y A2-ter).

    def _hermanos_de_corrida(self) -> frozenset[str]:
        """Los `.run.old.*` y `.run.failed.*` que existen ahora.

        La diferencia con el censo posterior identifica los que este intento cree.
        """
        return frozenset(
            p.name
            for p in self._project_dir.iterdir()
            if p.is_dir()
            and (
                p.name.startswith(f".{_RUN_SUBDIR}.old.")
                or p.name.startswith(f".{_RUN_SUBDIR}.failed.")
            )
        )

    def _hermanos_nuevos(self, antes: frozenset[str], etiqueta: str) -> list[Path]:
        return sorted(
            p
            for p in self._project_dir.iterdir()
            if p.is_dir()
            and p.name.startswith(f".{_RUN_SUBDIR}.{etiqueta}.")
            and p.name not in antes
        )

    def _apartar_informe_previo(self, token: str) -> Path | None:
        """Aparta el `reports/` de la corrida previa a `.reports.prev.<token>` y deja uno limpio."""
        if not _tiene_archivos(self._reports_dir):
            return None
        apartado = self._project_dir / f".{_REPORTS_SUBDIR}.prev.{token}"
        shutil.move(str(self._reports_dir), str(apartado))
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        return apartado

    def _restaurar_informe_previo(self, previo: Path | None) -> None:
        """La corrida reventó sin consolidar: el informe previo vuelve a `reports/`."""
        if previo is None:
            return
        if _tiene_archivos(self._reports_dir):
            # El informe del intento fallido no encontró evidencia a la que ir (`_asociar_…`
            # lo deja en su sitio si no hay `.run.failed.*`): se conserva aparte, nunca se pisa.
            shutil.move(
                str(self._reports_dir),
                str(_ruta_libre(previo.with_name(f".{_REPORTS_SUBDIR}.old"))),
            )
        elif self._reports_dir.exists():
            shutil.rmtree(self._reports_dir)  # vacío: no es evidencia
        shutil.move(str(previo), str(self._reports_dir))

    def _asociar_informe_de_intento_fallido(self, hermanos_antes: frozenset[str]) -> None:
        """El `reports/` que ESTE intento escribió va con la evidencia `.run.failed.*` que dejó."""
        if not _tiene_archivos(self._reports_dir):
            return
        fallidas = self._hermanos_nuevos(hermanos_antes, "failed")
        if not fallidas:
            return  # sin evidencia fallida: `_restaurar_informe_previo` lo conserva aparte
        shutil.move(str(self._reports_dir), str(fallidas[-1] / _REPORTS_SUBDIR))
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def _archivar_informe_previo(self, previo: Path | None, hermanos_antes: frozenset[str]) -> None:
        """La corrida consolidó: el informe previo va al `.run.old.*` que ESTA consolidación creó.

        Sin `.run.old.*` nuevo (no había corrida previa consolidada) queda aparte, nunca se pisa.
        """
        if previo is None:
            return
        viejas = self._hermanos_nuevos(hermanos_antes, "old")
        destino = (
            viejas[-1] / _REPORTS_SUBDIR
            if viejas
            else _ruta_libre(previo.with_name(f".{_REPORTS_SUBDIR}.old"))
        )
        shutil.move(str(previo), str(destino))

    def _preamble(self) -> tuple[tuple[str, dict[str, Any]], ...]:
        """Lo que la corrida declara al trail antes del primer paso.

        La puerta y sus inferencias, en ese orden.
        """
        import bayesrisk

        entrada = {
            "regla": "puerta_de_entrada",
            "umbral": None,
            "valor": {"puerta": "guiada", "version": bayesrisk.__version__, "hasta": self._until},
            "accion": "declarar",
            "autor": AUTOR_PUERTA,
            "motivo": (
                f"la corrida entró por bayesrisk.{self._PUERTA}; el config completo es la verdad"
            ),
        }
        eventos: list[tuple[str, dict[str, Any]]] = [(self._GUIDED_STEP, entrada)]
        eventos.extend((self._GUIDED_STEP, inferencia.payload()) for inferencia in self._inferences)
        # D-DEC-2: las decisiones humanas no van aquí. Viven en `config.decisions` y las declara
        # `Study.run` después de este preámbulo, igual para esta puerta que para su YAML.
        return tuple(eventos)

    def _contar_etapa(self, stage: str, study: Any) -> None:
        """Arma y cuenta el resumen de la etapa recién terminada (gancho ``on_step``).

        Un resumen que no se puede armar es un fallo de ESTA corrida, no un detalle: se levanta
        como error de dominio para que el motor lo registre con su etapa y ``bayesrisk.run``
        devuelva la corrida fallida con el diagnóstico —los artefactos calculados quedan en la
        evidencia—, en vez de declarar «completada» una corrida sin resúmenes (pasada 1 de Codex
        sobre la capa A del scorecard).
        """
        try:
            resumen = build_stage_summary(stage, study, self._context())
        except Exception as exc:
            rotulo = stage_labels(self._FAMILIA).get(stage, stage)
            raise self._RunError(
                f"El resumen de la etapa «{rotulo}» no se pudo armar: {exc}"
            ) from exc
        self._stage_summaries[stage] = resumen
        self._echo(resumen.text(with_table=False))

    def _context(self) -> SummaryContext:
        trail: Path | None = None
        card: Path | None = None
        if self._config.audit is not None:
            trail = self._run_dir / self._config.audit.trail_filename
        if self._config.governance is not None:
            card = self._run_dir / _MODEL_CARD_NAME
        return SummaryContext(
            project_dir=self._project_dir,
            run_dir=self._run_dir,
            source_label=self._source_label,
            partition_label=self._partition_label,
            inference_lines=self._inference_lines,
            decision_lines=tuple(self._lineas_de_decision()),
            report_dir=self._reports_dir,
            trail_path=trail,
            card_path=card,
            config_path=self._config_path,
            until=self._until,
            family=self._FAMILIA,
        )

    def _lineas_de_decision(self) -> list[str]:
        lineas: list[str] = [decision_line(decision) for decision in self._decisions]
        if lineas and self._pending_decisions:
            lineas.append(
                "Hay decisiones posteriores a la última corrida: llama a resume() para aplicarlas."
            )
        return lineas


def _run_id_en_disco(run_dir: Path) -> str | None:
    """El ``run_id`` que la evidencia consolidada en ``run/`` declara, o ``None`` si no hay."""
    metadatos = run_dir / "study" / "run_metadata.json"
    if not metadatos.is_file():
        return None
    try:
        valor = json.loads(metadatos.read_text(encoding="utf-8")).get("run_id")
    except (OSError, ValueError):
        return None
    return str(valor) if valor else None


def _nombre_de_proyecto(name: object, error: type[ConfigError]) -> str:
    """``name`` como un único componente de carpeta, o ``error``.

    Compone ``<run_dir>/<name>``: con ``..``, un separador o una ruta absoluta la carpeta del
    proyecto salía de ``run_dir`` y las corridas escribían, movían y apartaban directorios ajenos
    (pasada 1 de Codex sobre la capa B). Un nombre reservado del sistema (``CON``, ``NUL``) lo
    rechaza el propio sistema operativo al crear la carpeta.
    """
    nombre = str(name).strip() if name is not None else ""
    if not nombre:
        raise error("name= no puede estar vacío: es el nombre de la versión.")
    if (
        nombre in {".", ".."}
        or "/" in nombre
        or "\\" in nombre
        or Path(nombre).is_absolute()
        or Path(nombre).name != nombre
    ):
        raise error(
            f"name={name!r} tiene que ser un nombre de carpeta simple, sin separadores, «..» ni "
            "unidad: compone <run_dir>/<name>. Para correr en otro sitio usa run_dir=."
        )
    return nombre


def _huella_del_archivo(ruta: Path) -> str:
    """SHA-256 de los bytes del archivo, por bloques (los archivos de cartera son grandes)."""
    resumen = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def _bloquear_carpeta(ruta: Path) -> IO[bytes]:
    """Candado exclusivo entre procesos sobre el archivo ``ruta`` (vacío, se crea si no existe).

    Levanta ``OSError`` si otro proceso —u otro descriptor— ya lo tiene. El sistema operativo lo
    suelta cuando el proceso termina, muera como muera: no hay candados huérfanos que limpiar.
    """
    handle = ruta.open("a+b")
    try:
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise
    return handle


def _liberar_carpeta(handle: IO[bytes]) -> None:
    """Suelta el candado tomado con :func:`_bloquear_carpeta` y cierra el archivo."""
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _tiene_archivos(ruta: Path) -> bool:
    """Si bajo ``ruta`` hay al menos un archivo (un directorio vacío no es evidencia)."""
    return ruta.is_dir() and any(p.is_file() for p in ruta.rglob("*"))


def _ruta_libre(ruta: Path) -> Path:
    """``ruta`` si no existe; si no, el primer hermano ``<nombre>.<n>`` libre."""
    if not ruta.exists():
        return ruta
    n = 1
    while (candidata := ruta.with_name(f"{ruta.name}.{n}")).exists():
        n += 1
    return candidata
