"""``bayesrisk.Monitor``: la puerta guiada del monitoreo de un modelo en uso (SDD-33 D-MNT-1…10).

Salió en la 2.13.0 como adelanto declarado (capa A del SDD-33, D-MNT-8) y es estable desde la
2.14.0, al cerrar sus tres puertas —pantalla, informe y Excel— en la capa B: su firma y sus
resúmenes sólo crecen de forma aditiva en 2.x.

Se construye con lo que sólo la institución tiene: la **tarjeta** guardada (una carpeta de
:class:`~bayesrisk.scorecard.bundle.FittedScorecardBundle` de esquema 4, o el objeto), la
**cartera** nueva con sus columnas de **periodo** y, si lo tiene, de **desenlace**. Infiere y
**declara** el resto —cómo se lee el periodo, que es una corrida de cartera sin target ni
partición, la referencia de Desarrollo que la tarjeta congeló— y corre con :func:`bayesrisk.run`.
**No es un segundo orquestador**: arma un config con las secciones ``data`` y ``monitoring`` y lo
corre (con su informe, que tiene capítulo propio); ``mon.config`` es la verdad y
``mon.config_hash``, la identidad (D-SIM-1). No tiene
decisiones humanas: no hay nada que decidir sobre un modelo que sólo se mide (§4.1).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final

import pandas as pd

from bayesrisk.core.exceptions import BayesRiskError, ConfigError
from bayesrisk.guided._puerta import _PuertaGuiada
from bayesrisk.guided.inference import Inferencia, columnas_esquema
from bayesrisk.report.prose import _miles, _plural

if TYPE_CHECKING:
    from bayesrisk.scorecard.bundle import FittedScorecardBundle

__all__ = ["Monitor", "MonitorInputError", "MonitorRunError"]

#: Paso con que la puerta firma sus eventos en el trail (el del scorecard es ``scorecard_guided``).
GUIDED_STEP: Final = "monitor_guided"

#: Cómo se lee la columna de periodo, en palabras (§7 paso 2).
_LECTURA_DEL_PERIODO: Final[dict[str, str]] = {
    "date_month": "fecha, agrupada por mes (AAAA-MM)",
    "number": "número, en orden numérico",
    "text": "texto, en orden alfabético",
}


class MonitorInputError(ConfigError):
    """Lo que la puerta guiada del monitoreo rechaza **antes de correr**.

    La tarjeta no se puede monitorear (esquema anterior al 4 o sin escala maestra), o un argumento
    no casa con la cartera.
    """


class MonitorRunError(BayesRiskError):
    """La corrida terminó fallida y se pidió ``raise_on_error=True``.

    También cuando la corrida no pudo empezar porque otra tiene la carpeta del proyecto.
    """


class Monitor(_PuertaGuiada):
    """El monitoreo de una tarjeta en uso, periodo a periodo, con la entrada mínima (D-MNT-1).

    Parameters
    ----------
    bundle
        La tarjeta: la carpeta donde se guardó (``FittedScorecardBundle.save``) o el objeto
        ``FittedScorecardBundle``. Tiene que ser de esquema 4 —guardada desde la 2.13.0— y traer
        su escala maestra: congela la referencia de Desarrollo contra la que se compara (los cortes
        del puntaje, la participación por tramo y el AUC inicial de Holdout). Se copia al proyecto
        bajo ``<run_dir>/<name>/input/`` con su huella en el nombre.
    data
        La cartera nueva: ruta a un CSV, Parquet o Excel, o un ``pandas.DataFrame``, con las
        variables que la tarjeta necesita, la columna de periodo y, si la hay, la de desenlace. Se
        copia al proyecto con su huella, como en ``bayesrisk.Scorecard``.
    period
        La columna de periodo de cada operación: texto (``"2024Q1"``), número o fecha (una fecha
        se agrupa por mes). Una misma operación puede estar en varios periodos.
    default
        La columna de desenlace, opcional: 1 malo, 0 bueno y vacío si todavía no madura. Sin ella
        sólo se mide la población.
    name, run_dir
        Nombre de la versión y carpeta raíz: la evidencia queda en ``<run_dir>/<name>/``
        (``"monitoreo"`` y ``"bayesrisk-runs"`` de fábrica).
    """

    _PUERTA: ClassVar[str] = "Monitor"
    _GUIDED_STEP: ClassVar[str] = GUIDED_STEP
    _InputError: ClassVar[type[ConfigError]] = MonitorInputError
    _RunError: ClassVar[type[BayesRiskError]] = MonitorRunError
    _FAMILIA: ClassVar[str] = "monitoreo"

    def __init__(
        self,
        bundle: str | Path | FittedScorecardBundle,
        data: str | Path | pd.DataFrame,
        *,
        period: str,
        default: str | None = None,
        name: str = "monitoreo",
        run_dir: str | Path = "bayesrisk-runs",
    ) -> None:
        self._iniciar(name, run_dir)
        self._tarjeta_pendiente: tuple[Path, Any] | None = None
        self._tarjeta_huella: tuple[Path, str] | None = None
        try:
            tarjeta = self._leer_tarjeta(bundle)
            frame, source, source_label = self._cargar_panel(data)
            self._construir(tarjeta, frame, source, source_label, period=period, default=default)
        except BaseException:
            self._descartar_snapshot()
            raise

    # ── construir ───────────────────────────────────────────────────────────────────────

    def _leer_tarjeta(self, bundle: Any) -> FittedScorecardBundle:
        """La tarjeta, exigida monitoreable antes de leer la cartera (D-MNT-2, §8)."""
        from bayesrisk.monitoring.exceptions import MonitoringInputError
        from bayesrisk.monitoring.step import (
            cargar_tarjeta_monitoreable,
            exigir_tarjeta_monitoreable,
        )
        from bayesrisk.scorecard.bundle import FittedScorecardBundle

        if isinstance(bundle, FittedScorecardBundle):
            # El objeto ya validó su manifiesto al construirse: se exige lo mismo que a una carpeta.
            try:
                return exigir_tarjeta_monitoreable(bundle)
            except MonitoringInputError as exc:
                raise MonitorInputError(str(exc)) from exc
        if not isinstance(bundle, str | Path):
            raise MonitorInputError(
                "bundle= es la carpeta de una tarjeta guardada o un FittedScorecardBundle; "
                f"llegó {type(bundle).__name__}."
            )
        try:
            return cargar_tarjeta_monitoreable(Path(bundle).resolve())
        except MonitoringInputError as exc:
            raise MonitorInputError(str(exc)) from exc

    def _cargar_panel(self, data: str | Path | pd.DataFrame) -> tuple[pd.DataFrame, str, str]:
        """La cartera, con un índice que se repite pasado a columna (§7-3, pasada 3 de Codex).

        En un panel la misma operación está en varios periodos: si su identidad viene en el índice,
        el índice se repite y el paso de datos —que exige un índice único en toda la cartera— la
        rechazaría antes del monitoreo, que comprueba la unicidad **dentro** de cada periodo. El
        índice pasa a la columna reservada :data:`~bayesrisk.monitoring.step.INDICE_DEL_PANEL`, con
        su dtype, y —si tiene nombre— también a una columna con ese nombre (la tarjeta que
        identifica por él la vuelve a usar como índice); el paso decide en cada periodo qué índice
        recibe la tarjeta. El snapshot se escribe desde ese frame.
        """
        frame, source, source_label = self._cargar(data)
        plano = aplanar_panel(frame)
        if plano is None:
            return frame, source, source_label
        import io

        nombre = frame.index.name
        self._descartar_snapshot()
        buffer = io.BytesIO()
        plano.to_parquet(buffer)
        contenido = buffer.getvalue()
        snapshot, _temporal, _huella = self._reservar_snapshot(contenido, ".parquet")
        detalle = (
            f"el índice {nombre} se repite entre periodos y pasa a columna"
            if nombre is not None
            else "el índice del archivo se repite entre periodos y pasa a columna"
        )
        return (
            pd.read_parquet(io.BytesIO(contenido)),
            str(snapshot),
            f"{source_label}; {detalle} (guardado como {snapshot})",
        )

    def _construir(
        self,
        tarjeta: FittedScorecardBundle,
        frame: pd.DataFrame,
        source: str,
        source_label: str,
        *,
        period: str,
        default: str | None,
    ) -> None:
        """Infiere, arma el config y lo comprueba; los snapshots se publican al final."""
        from bayesrisk.monitoring.exceptions import MonitoringInputError
        from bayesrisk.monitoring.step import _desenlace, _periodos, es_fecha

        for nombre, valor in (("period", period), ("default", default)):
            if valor is not None and (not isinstance(valor, str) or not valor.strip()):
                raise MonitorInputError(f"{nombre}= tiene que ser el nombre de una columna.")
        if default is not None and default == period:
            raise MonitorInputError(
                f"default= y period= son la misma columna ({period!r}): el desenlace no puede ser "
                "el periodo."
            )
        manifest = tarjeta.manifest
        identidad = manifest["row_identity"]
        declaradas = [period, *([default] if default is not None else [])]
        faltan = [c for c in declaradas if c not in frame.columns]
        if faltan:
            raise MonitorInputError(
                f"La cartera no trae {_plural(len(faltan), 'la columna', 'las columnas')} "
                f"{', '.join(faltan)}. Columnas disponibles: "
                f"{', '.join(str(c) for c in frame.columns)}."
            )
        de_la_tarjeta = [*manifest["model"]["features"], *identidad["unique_keys"]]
        faltan = [c for c in dict.fromkeys(de_la_tarjeta) if c not in frame.columns]
        if faltan:
            raise MonitorInputError(
                f"La tarjeta puntúa con {_plural(len(faltan), 'la columna', 'las columnas')} "
                f"{', '.join(faltan)}, que la cartera no trae."
            )
        try:
            etiquetas, tipo, orden = _periodos(frame[period], pd)
        except MonitoringInputError as exc:
            raise MonitorInputError(str(exc)) from exc
        if not orden:
            raise MonitorInputError(f"La columna {period!r} no trae ningún periodo.")
        if default is not None:
            try:
                _desenlace(frame[default], default, pd)
            except MonitoringInputError as exc:
                raise MonitorInputError(str(exc)) from exc

        referencia = manifest["monitoring_reference"]
        auc = referencia["auc_initial"]
        k = len(manifest["master_scale"]["grade_pd"])
        sin_periodo = int(etiquetas.isna().sum())
        inferencias: list[Inferencia] = [
            Inferencia(
                regla="inferencia_periodo",
                valor={
                    "columna": period,
                    "lectura": tipo,
                    "periodos": len(orden),
                    "primero": orden[0],
                    "ultimo": orden[-1],
                    "filas_sin_periodo": sin_periodo,
                },
                motivo=(
                    f"la columna {period} se lee como {_LECTURA_DEL_PERIODO[tipo]}; cada periodo "
                    "se compara con Desarrollo y la regla de dos periodos seguidos mira el "
                    "anterior presente en ese orden"
                ),
            ),
            Inferencia(
                regla="inferencia_referencia_de_la_tarjeta",
                valor={
                    "bundle_hash": tarjeta.bundle_hash,
                    "tramos": k,
                    "n_desarrollo": int(referencia["n_development"]),
                    "auc_inicial": auc["auc"],
                    "fuente_auc_inicial": auc["source"],
                },
                motivo=(
                    "la población, la calibración y la discriminación se comparan con la "
                    "referencia de Desarrollo que la tarjeta congeló al guardarse; el AUC inicial "
                    "es el de Holdout, la validación inicial fuera de la muestra de ajuste "
                    "(D-MNT-3)"
                ),
            ),
            Inferencia(
                regla="inferencia_corrida_de_cartera",
                valor={"target": None, "partition": None},
                motivo=(
                    "el monitoreo no ajusta nada: la corrida no declara qué es un cliente malo "
                    "para modelar ni cómo separar muestras, y no siembra ningún criterio"
                ),
            ),
        ]
        if default is None:
            inferencias.append(
                Inferencia(
                    regla="inferencia_sin_desenlace",
                    valor={"monitoring.default": None},
                    motivo=(
                        "no se declaró default=: sólo se mide la población, y ningún periodo puede "
                        "ser «sin acción» (su desempeño no se puede medir)"
                    ),
                )
            )
        self._inferences: tuple[Inferencia, ...] = tuple(inferencias)
        self._partition_label = ""
        self._source_label = source_label
        lineas = [
            (
                f"Periodos: {_miles(len(orden))} ({orden[0]} a {orden[-1]}), columna {period} "
                f"leída como {_LECTURA_DEL_PERIODO[tipo]}"
            ),
            (
                f"Tarjeta: {_miles(k)} tramos; referencia de Desarrollo con "
                f"{_miles(int(referencia['n_development']))} operaciones y AUC inicial de "
                f"{'Holdout' if auc['source'] == 'holdout' else 'Desarrollo (sin Holdout)'}"
            ),
            "Corrida de cartera: no ajusta nada ni declara muestras",
        ]
        if sin_periodo:
            lineas.append(
                f"{_miles(sin_periodo)} {_plural(sin_periodo, 'fila', 'filas')} sin periodo "
                "quedan fuera del monitoreo"
            )
        if default is None:
            lineas.append("Sin columna de desenlace: sólo se mide la población")
        self._inference_lines = tuple(lineas)

        # ── la tarjeta, copiada al proyecto con su huella ────────────────────────────────
        destino = self._project_dir / "input" / f"tarjeta-{tarjeta.bundle_hash[:16]}"
        self._tarjeta_pendiente = (destino, tarjeta)
        self._tarjeta_huella = (destino, tarjeta.bundle_hash)

        # Un periodo de fechas como objetos (CSV con fechas ISO) se declara fecha con coacción,
        # para que la validación del esquema no lo rechace como texto (pasada 2 de Codex).
        esquema = columnas_esquema(
            frame[declaradas], fechas=[period] if es_fecha(frame[period], pd) else ()
        )
        cfg: dict[str, Any] = {
            "schema_version": "1.0.0",
            "name": self._name,
            "repro": {"seed": 20240706, "strict_determinism": False},
            "run": {"steps": None, "fail_fast": True},
            "data": {
                "type": "standard",
                "load": {
                    "source": source,
                    "file_format": "auto",
                    "backend": "pandas",
                    "csv_options": {"sep": ",", "decimal": ".", "encoding": "utf-8"},
                },
                "schema": {
                    "columns": esquema,
                    "strict": False,
                    "ordered": False,
                    "index_col": None,
                    "unique_keys": None,
                },
                "missing": {"special_values": [], "max_missing_rate": 0.99},
                # D-ECL-2: una corrida de cartera declara target y partición en null explícito.
                "target": None,
                "partition": None,
            },
            "monitoring": {"bundle": str(destino), "period": period, "default": default},
            # SDD-33 capa B: el informe con su capítulo (fuera del `config_hash`, como toda la
            # sección): ninguna sección del scorecard se exige, y el capítulo se activa por la card
            # del monitoreo, como el de IFRS 9 en su preset.
            "report": {
                "output_dir": str(self._reports_dir),
                "basename": "monitoring_report",
                "formats": ["pdf", "md", "docx"],
                "pdf": {"enabled": True, "fail_if_unavailable": False},
                "sections": {"required_sections": []},
            },
            "audit": {"enabled": True},
        }
        self._config = self._validar_config(cfg)
        self._config, self._steps = self._resolver_pipeline(self._config)
        self._publicar_snapshot()

    # ── snapshots ───────────────────────────────────────────────────────────────────────

    def _publicar_snapshot(self) -> None:
        """Los datos y la tarjeta: sólo después de validar toda la puerta."""
        super()._publicar_snapshot()
        pendiente, self._tarjeta_pendiente = self._tarjeta_pendiente, None
        if pendiente is None:
            return
        destino, tarjeta = pendiente
        if destino.exists():
            return  # mismo contenido por construcción: el nombre es su huella
        tarjeta.save(destino)

    def _descartar_snapshot(self) -> None:
        self._tarjeta_pendiente = None
        super()._descartar_snapshot()

    def _verificar_fuente(self) -> None:
        """Los datos y la tarjeta son los mismos sobre los que se construyó el ``Monitor``."""
        super()._verificar_fuente()
        if self._tarjeta_huella is None:
            return
        from bayesrisk.scorecard.bundle import FittedScorecardBundle
        from bayesrisk.scorecard.exceptions import ScorecardBundleError

        ruta, esperada = self._tarjeta_huella
        try:
            vigente = FittedScorecardBundle.load(ruta).bundle_hash
        except ScorecardBundleError:
            vigente = None
        if vigente != esperada:
            raise MonitorInputError(
                f"La tarjeta {ruta} ya no existe o cambió desde que se construyó el Monitor: "
                "construye uno nuevo."
            )

    # ── exportar (SDD-33 §6.4, capa B) ──────────────────────────────────────────────────

    def export_excel(self) -> tuple[Path, ...]:
        """``Monitoreo.xlsx`` en ``<run_dir>/<name>/excel/``: un libro único (SDD-33 §6.4).

        Sus hojas son el resumen (el veredicto, su acción y qué revisar), los periodos (los cuatro
        indicadores y el veredicto de cada uno), cada tramo por periodo y el CSI de cada variable
        por periodo —las tablas del mismo resumen «Monitoreo» que el notebook, la pantalla y el
        informe—, más un índice. La corrida de monitoreo no tiene etapas previas que numerar.
        Opcional: nunca es la vía para ver un resultado. Exige el extra ``excel`` (``openpyxl``);
        sin él se detiene con el comando de instalación.
        """
        return self._exportar_excel()


# ── el panel, compartido por la puerta guiada y la pantalla ─────────────────────────────


def aplanar_panel(frame: pd.DataFrame) -> pd.DataFrame | None:
    """La cartera con su índice repetido pasado a columna, o ``None`` si el índice no se repite.

    Una sola regla para las dos entradas de la cartera —``Monitor`` y la pantalla (pasada 1 de Codex
    sobre la capa B: la pantalla mandaba el panel tal cual y el paso de datos lo rechazaba)—: el
    índice pasa a la columna reservada :data:`~bayesrisk.monitoring.step.INDICE_DEL_PANEL`, con su
    dtype, y —si tiene nombre— también a una columna con ese nombre. El nombre reservado se rechaza
    siempre, se repita o no el índice (pasada 5).

    Raises
    ------
    MonitorInputError
        Si la cartera trae una columna con el nombre reservado, o un índice que se repite y se
        llama como una columna.
    """
    from bayesrisk.monitoring.step import INDICE_DEL_PANEL

    if INDICE_DEL_PANEL in frame.columns:
        # El paso lee esa columna como el índice del panel: una del usuario con el mismo nombre se
        # tomaría por él (pasada 5 de Codex).
        raise MonitorInputError(
            f"La cartera trae una columna llamada «{INDICE_DEL_PANEL}», un nombre reservado: el "
            "monitoreo la usa para conservar el índice de una cartera con la misma operación en "
            "varios periodos. Renómbrala y vuelve a construir el monitoreo."
        )
    if not frame.index.has_duplicates:
        return None
    nombre = frame.index.name
    if nombre is not None and nombre in frame.columns:
        raise MonitorInputError(
            f"El índice de la cartera se repite entre periodos y se llama como una columna "
            f"({nombre!r}): no se puede pasar a columna sin pisarla. Renombra el índice o la "
            "columna y vuelve a construir el monitoreo."
        )
    # El índice también es identidad cuando no tiene nombre (una tarjeta con id=None identifica por
    # él): se conserva siempre, con su dtype (pasada 4 de Codex), en la columna reservada —la señal
    # de que se aplanó, para que el paso sepa que el índice que queda es de posición (pasada 6)— y,
    # con nombre, también en su columna.
    plano = frame.rename_axis(INDICE_DEL_PANEL).reset_index()
    if nombre is not None:
        plano.insert(1, nombre, plano[INDICE_DEL_PANEL])
    return plano


def preparar_panel(source: Path, directorio: Path) -> Path:
    """La cartera de la pantalla lista para el monitoreo: la misma, o su panel aplanado.

    Lee el parquet que materializó la pantalla y, si su índice se repite, escribe el panel aplanado
    con :func:`aplanar_panel` junto a él (con su huella en el nombre) y devuelve esa ruta: la misma
    tabla que guarda ``Monitor``, así que las dos puertas dan el mismo ``data_hash`` (D-SIM-1).

    Con el índice único la cartera se usa tal cual, como en la puerta completa: así corre también el
    snapshot que guardó ``Monitor`` para un panel —ya aplanado, con la columna reservada—, que
    ``mon.to_yaml()`` referencia (pasada 2 de Codex sobre la capa B). La columna reservada sólo se
    rechaza cuando hay que aplanar, porque aplanar la pisaría.

    Raises
    ------
    MonitorInputError
        Lo que :func:`aplanar_panel` rechaza al aplanar.
    """
    import hashlib
    import io

    frame = pd.read_parquet(source)
    if not frame.index.has_duplicates:
        return source
    plano = aplanar_panel(frame)
    if plano is None:
        return source
    buffer = io.BytesIO()
    plano.to_parquet(buffer)
    contenido = buffer.getvalue()
    directorio.mkdir(parents=True, exist_ok=True)
    destino = directorio / f"panel-{hashlib.sha256(contenido).hexdigest()[:16]}.parquet"
    if not destino.exists():
        temporal = destino.with_name(f".{destino.name}.tmp")
        temporal.write_bytes(contenido)
        temporal.replace(destino)
    return destino


# ── la tarjeta en la pantalla (SDD-33 §4.3, capa B) ─────────────────────────────────────


def tarjeta_de_la_corrida(study: Any) -> FittedScorecardBundle | None:
    """La tarjeta monitoreable de una corrida del scorecard, o ``None`` (SDD-33 §4.3).

    La pantalla la guarda con cada corrida del scorecard que se puede monitorear —terminada, con la
    tarjeta completa y su escala maestra, y por eso con la referencia de Desarrollo (D-MNT-2)—, para
    que el trabajo «Monitorear un modelo en uso» la ofrezca. Una corrida sin esa tarjeta (parcial,
    sin escala o de otra familia) no tiene qué monitorear: no es un error.
    """
    if (
        study.run_context.status != "done"
        or not study.artifacts.has("scorecard", "card")
        or not study.artifacts.has("master_scale", "card")
    ):
        return None
    from bayesrisk.scorecard.bundle import FittedScorecardBundle
    from bayesrisk.scorecard.exceptions import ScorecardBundleError

    try:
        tarjeta = FittedScorecardBundle.from_study(study)
    except ScorecardBundleError:
        return None
    return tarjeta if "monitoring_reference" in tarjeta.manifest else None


def leer_tarjeta_monitoreable(ruta: str | Path) -> FittedScorecardBundle:
    """La tarjeta guardada en ``ruta`` si se puede monitorear (D-MNT-2).

    Raises
    ------
    MonitorInputError
        Con el mismo motivo que daría :class:`Monitor`: no se lee, es de un esquema anterior al 4 o
        no trae escala maestra.
    """
    from bayesrisk.monitoring.exceptions import MonitoringInputError
    from bayesrisk.monitoring.step import cargar_tarjeta_monitoreable

    try:
        return cargar_tarjeta_monitoreable(Path(ruta))
    except MonitoringInputError as exc:
        raise MonitorInputError(str(exc)) from exc
