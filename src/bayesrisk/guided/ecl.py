"""``bayesrisk.Ecl``: la puerta guiada de la provisión IFRS 9 (FLUJO-GUIADO-IFRS9 D-ECL-1…D-ECL-9).

Estable desde que cerraron sus tres puertas —código, config completo y pantalla— con la capa B de
la enmienda (D-ECL-9): su firma, sus métodos y la forma de sus resúmenes sólo crecen de forma
aditiva bajo SemVer 2.x. Sus **cifras** siguen la marca experimental de los motores que las
calculan, ``survival`` y ``provisioning`` (la lectura de D-EST-5: el sobre es estable, el contenido
sigue a quien lo calcula).

Se construye con lo que el área de riesgo ya tiene en su archivo de cartera —fecha de corte,
cartera, exposición, LGD, tasa efectiva anual, días de mora y, si la tiene, la marca de
incumplimiento— y con la historia de incumplimientos de esa misma cartera, que alimenta la curva de
PD: duración, evento, la unidad de esa duración y el horizonte de la curva. Infiere y **declara**
el resto —el horizonte de 12 meses desde la unidad, el esquema de las columnas declaradas, el
identificador, que es una corrida de cartera sin target ni partición y, si falta, que no hay
marca— y corre con :func:`bayesrisk.run`. **No es un segundo orquestador**: parte de las secciones
``survival`` y ``provisioning_ifrs9`` del preset F4, que corren, y escribe encima las columnas del
usuario (§3.5: constantes de la puerta, ningún default de fábrica nuevo). ``ecl.config`` es la
verdad y ``ecl.config_hash``, la identidad (D-SIM-1).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar, Final, Self

import pandas as pd

from bayesrisk.core.exceptions import BayesRiskError, ConfigError
from bayesrisk.core.time_units import year_fraction
from bayesrisk.guided._puerta import _PuertaGuiada
from bayesrisk.guided.inference import Inferencia, columnas_esquema
from bayesrisk.guided.summaries import time_unit_words
from bayesrisk.report.prose import _miles, _plural

__all__ = ["Ecl", "EclInputError", "EclRunError"]

#: Paso con que la puerta firma sus eventos en el trail (§3.2: el del scorecard es
#: ``scorecard_guided``).
GUIDED_STEP: Final = "ecl_guided"

#: IFRS9-FIRMABLE §3.11: en la puerta guiada la tasa de la historia va en la columna de nombre fijo
#: ``default_rate``; las demás columnas fijas y las reglas de las dos tablas viven en
#: :mod:`bayesrisk.guided.escenarios`, la fuente que comparte con la pantalla.
_HISTORIA_TASA: Final = "default_rate"

#: Las unidades que la puerta acepta, en palabras, para el mensaje de una unidad no reconocida. La
#: tabla de conversión es la de :mod:`bayesrisk.core.time_units`; aquí sólo se nombra.
_UNIDADES_ACEPTADAS: Final = (
    "año, semestre, trimestre, mes, semana o día, en español o en inglés y en singular o plural "
    '("year", "meses", "quarter"…)'
)


class EclInputError(ConfigError):
    """Lo que la puerta guiada de IFRS 9 rechaza **antes de correr**.

    Falta un dato institucional (el horizonte de la curva), la unidad no se reconoce o un
    argumento no casa con el archivo.
    """


class EclRunError(BayesRiskError):
    """La corrida terminó fallida y se pidió ``raise_on_error=True``.

    También cuando la corrida no pudo empezar porque otra tiene la carpeta del proyecto.
    """


class Ecl(_PuertaGuiada):
    """La provisión IFRS 9 de una cartera, de punta a punta, con la entrada mínima (D-ECL-1).

    La firma, los métodos y la forma de los resúmenes son estables (SemVer 2.x), también los
    escenarios y las dos PD del modelo desde que cerraron sus tres puertas (IFRS9-FIRMABLE capa C,
    D-SIM-1); las cifras siguen la marca experimental de ``survival``, ``forward`` y
    ``provisioning`` (D-ECL-9).

    Parameters
    ----------
    data
        Ruta a un CSV, Parquet o Excel, o un ``pandas.DataFrame``, con **una fila por operación a
        la fecha de corte**. Se copia al proyecto bajo ``<run_dir>/<name>/input/`` con su huella
        en el nombre, y el config referencia esa copia: la inferencia y cada corrida leen
        exactamente los mismos bytes.
    id
        Identificador de cada operación, opcional y recomendado: una columna o el nombre del
        índice del archivo. Sin él se usa el índice del archivo y se declara. Una columna se
        verifica única, y la curva, la provisión y el detalle por operación identifican cada
        operación por ella.
    as_of, portfolio, exposure, lgd, rate, days_past_due
        Las columnas de la provisión: fecha de corte (un solo valor), cartera, exposición al
        incumplimiento ya calculada, LGD, tasa efectiva **anual** de cada operación y días de mora.
    default
        La marca de incumplimiento (verdadero/falso), opcional: sin ella el Stage 3 lo asigna sólo
        la mora, y se declara.
    origination, maturity
        Las fechas de otorgamiento y de vencimiento contractual de cada operación, opcionales
        (fechas AAAA-MM-DD o columnas de tipo fecha; una fila vacía es «sin fecha»). Con ellas la
        curva de PD se lee desde la antigüedad de cada operación —sin redondear— y la vida termina
        en su vencimiento (IFRS 9 5.5.19); el Stage 1 suma 12 meses o la vida, si es menor. Una
        operación ya vencida con saldo se provisiona con un período. Más allá del último período de
        la curva con incumplimientos observados, el riesgo se extiende con la media de los tres
        últimos. Supone que ``duration`` cuenta desde el otorgamiento.
    installment
        La cuota mensual del contrato, opcional; exige ``maturity``. La exposición de cada período
        sigue la tabla de pagos de esa cuota hasta el vencimiento, con la tasa implícita en la
        cuota (no ``rate``). Si la cuota no alcanza a pagar el saldo en el plazo, la exposición
        queda constante y se cuenta en «Qué revisar».
    history, scenarios
        Los escenarios económicos de la institución (IFRS9-FIRMABLE; estables desde la capa
        C, con la pantalla y el informe), las dos juntas, como ruta (CSV, Parquet o Excel) o
        ``DataFrame``. ``history`` es la historia larga de una tasa de incumplimiento de
        referencia —columnas ``date``, ``default_rate`` como fracción (un 0,9 % va como
        0,009) y las variables macro—; ``scenarios``, las trayectorias de esas variables por
        escenario —``scenario``, ``weight``, ``date`` y las mismas variables—, al menos dos,
        con pesos mayores que cero que suman 1 y que cubran los 12 meses siguientes al
        corte. El motor estima cuánto se mueve la tasa con la macro y desplaza en logit el
        riesgo de cada tramo de la curva según su fecha de calendario; la ECL es la
        ponderada de los escenarios. Se copian al proyecto con su huella, como ``data``.
    pd, origination_pd
        La PD a 12 meses de **hoy** de cada operación, de tu scorecard o de tu modelo de rating
        (con ``bayesrisk``, el bundle del scorecard aplicado a la cartera con ``bayesrisk.apply``),
        y la del **otorgamiento** —tu score de admisión—, opcionales. Con ``pd`` la curva de cada
        operación se ancla a esa PD: conserva su forma por edad y su PD de los 12 meses siguientes
        al corte es la de tu modelo, también en la pérdida de por vida. Tiene que medir el mismo
        incumplimiento a 12 meses que la curva y ser a lo largo del ciclo: el resumen compara las
        dos medias y avisa si difieren en más de un 25 %. Con ``origination_pd`` (exige ``pd`` y
        ``origination``) el aumento significativo del riesgo compara, para los 12 meses
        siguientes al corte, la PD de hoy —ponderada por escenario, si los hay— con la que se
        esperaba al otorgar para ese mismo tramo de vida. Una fila vacía es «sin dato»; una PD de
        0, de 1 o fuera de ese rango se acota y se cuenta.
    duration, event
        La historia de incumplimientos que alimenta la curva de PD: cuánto tiempo se observó cada
        operación (entero ≥ 1, en la unidad de ``period``) y si incumplió (0/1).
    period
        La **unidad** de ``duration``: año, semestre, trimestre, mes, semana o día. No se puede
        inferir de un entero y declararla mal cambia la provisión; con ella se infiere el horizonte
        de 12 meses (un año son 1, 2, 4, 12, 52 o 365 períodos).
    horizon
        Hasta cuántos períodos se proyecta la curva. Es un dato de la institución: si falta, la
        puerta se detiene antes de correr con el máximo que observan tus datos y el valor que
        usaría.
    covariates
        Columnas numéricas con que la curva ordena el riesgo entre operaciones. Sin ellas, una
        sola curva para toda la cartera (se declara).
    name, run_dir
        Nombre de la versión y carpeta raíz: la evidencia queda en ``<run_dir>/<name>/``
        (``"ecl"`` y ``"bayesrisk-runs"`` de fábrica).
    purpose, owner, review_every, track, document, formats
        Como en ``bayesrisk.Scorecard``: gobernanza y ficha con ``purpose``; registro en MLflow con
        ``track``; portada y formatos del informe.
    """

    _PUERTA: ClassVar[str] = "Ecl"
    _GUIDED_STEP: ClassVar[str] = GUIDED_STEP
    _InputError: ClassVar[type[ConfigError]] = EclInputError
    _RunError: ClassVar[type[BayesRiskError]] = EclRunError
    _FAMILIA: ClassVar[str] = "cartera"

    def __init__(
        self,
        data: str | Path | pd.DataFrame,
        *,
        id: str | None = None,
        as_of: str,
        portfolio: str,
        exposure: str,
        lgd: str,
        rate: str,
        days_past_due: str,
        default: str | None = None,
        origination: str | None = None,
        maturity: str | None = None,
        installment: str | None = None,
        history: str | Path | pd.DataFrame | None = None,
        scenarios: str | Path | pd.DataFrame | None = None,
        pd: str | None = None,
        origination_pd: str | None = None,
        duration: str,
        event: str,
        period: str,
        horizon: int | None = None,
        covariates: Sequence[str] | None = None,
        name: str = "ecl",
        run_dir: str | Path = "bayesrisk-runs",
        purpose: str | None = None,
        owner: str | None = None,
        review_every: int = 12,
        track: str | Path | None = None,
        document: Mapping[str, str] | None = None,
        formats: Sequence[str] | None = None,
    ) -> None:
        self._iniciar(name, run_dir)
        self._tablas_pendientes: list[tuple[Path, bytes]] = []
        self._tablas_huellas: list[tuple[Path, str]] = []
        try:
            frame, source, source_label = self._cargar(data)
            self._construir(
                frame,
                source,
                source_label,
                columnas={
                    "as_of": as_of,
                    "portfolio": portfolio,
                    "exposure": exposure,
                    "lgd": lgd,
                    "rate": rate,
                    "days_past_due": days_past_due,
                    "duration": duration,
                    "event": event,
                },
                id=id,
                default=default,
                contrato={
                    "origination": origination,
                    "maturity": maturity,
                    "installment": installment,
                },
                escenarios=(history, scenarios),
                del_modelo={"pd": pd, "origination_pd": origination_pd},
                period=period,
                horizon=horizon,
                covariates=covariates,
                purpose=purpose,
                owner=owner,
                review_every=review_every,
                track=track,
                document=document,
                formats=formats,
            )
        except BaseException:
            self._descartar_snapshot()
            raise

    def _construir(
        self,
        frame: pd.DataFrame,
        source: str,
        source_label: str,
        *,
        columnas: Mapping[str, str],
        id: str | None,
        default: str | None,
        contrato: Mapping[str, str | None],
        escenarios: tuple[Any, Any] = (None, None),
        del_modelo: Mapping[str, str | None] | None = None,
        period: str,
        horizon: int | None,
        covariates: Sequence[str] | None,
        purpose: str | None,
        owner: str | None,
        review_every: int,
        track: str | Path | None,
        document: Mapping[str, str] | None,
        formats: Sequence[str] | None,
    ) -> None:
        """Infiere, arma el config y lo comprueba; el snapshot se publica al final."""
        inferencias: list[Inferencia] = []

        # ── unidad y horizonte de 12 meses ───────────────────────────────────────────────
        fraccion = year_fraction(period) if isinstance(period, str) else None
        if fraccion is None:
            raise EclInputError(
                f"period={period!r} no es una unidad que el motor sepa convertir a años, y sin "
                "ella no se puede saber cuántos períodos de la curva son 12 meses ni descontar "
                f"bien. Unidades aceptadas: {_UNIDADES_ACEPTADAS}."
            )
        horizonte_12m = round(1.0 / fraccion)
        unidad_12m = time_unit_words(period, horizonte_12m) or period
        inferencias.append(
            Inferencia(
                regla="inferencia_horizonte_12m",
                valor={"unidad": period, "periodos": horizonte_12m},
                motivo=(
                    f"un año son {horizonte_12m} {unidad_12m}: la pérdida esperada a 12 meses del "
                    "Stage 1 suma esos períodos de la curva"
                ),
            )
        )

        # ── columnas declaradas ──────────────────────────────────────────────────────────
        covariables = tuple(str(c) for c in covariates) if covariates is not None else ()
        if len(set(covariables)) != len(covariables):
            raise EclInputError(f"covariates= repite una columna: {list(covariables)}.")
        historia = {columnas["duration"], columnas["event"]}
        fugas = [c for c in covariables if c in historia]
        if fugas:
            raise EclInputError(
                f"covariates= incluye {', '.join(fugas)}, que es la historia de la curva "
                "(duration= o event=): entraría como predictora de sí misma."
            )
        if contrato["installment"] is not None and contrato["maturity"] is None:
            raise EclInputError(
                f"installment={contrato['installment']!r} necesita maturity=: la cuota arma la "
                "tabla de pagos hasta el vencimiento de cada operación, y sin vencimiento no hay "
                "plazo."
            )
        modelo = dict(del_modelo or {"pd": None, "origination_pd": None})
        if modelo["origination_pd"] is not None and modelo["pd"] is None:
            raise EclInputError(
                f"origination_pd={modelo['origination_pd']!r} necesita pd=: lo que se esperaba al "
                "otorgar se compara con la PD de hoy de los mismos 12 meses."
            )
        if modelo["origination_pd"] is not None and contrato["origination"] is None:
            raise EclInputError(
                f"origination_pd={modelo['origination_pd']!r} necesita origination=: lo que se "
                "esperaba al otorgar para los próximos 12 meses se lee desde la antigüedad de cada "
                "operación."
            )
        del_contrato = [c for c in contrato.values() if c is not None]
        declaradas = [
            *columnas.values(),
            *([default] if default is not None else []),
            *del_contrato,
            *(c for c in modelo.values() if c is not None),
            *covariables,
        ]
        faltan = [c for c in dict.fromkeys(declaradas) if c not in frame.columns]
        if faltan:
            raise EclInputError(
                f"El archivo no trae {_plural(len(faltan), 'la columna', 'las columnas')} "
                f"{', '.join(faltan)}. Columnas disponibles: "
                f"{', '.join(str(c) for c in frame.columns)}."
            )
        horizonte = self._resolver_horizonte(frame, columnas["duration"], period, horizon)
        if (
            modelo["pd"] is not None
            and contrato["origination"] is None
            and contrato["maturity"] is None
            and horizonte < horizonte_12m
        ):
            # IFRS9-FIRMABLE §3.7 (pasada 2 de Codex sobre el código): sin las fechas, la curva no
            # dice nada más allá de su horizonte; anclar ahí la PD de 12 meses la concentraría.
            raise EclInputError(
                f"pd={modelo['pd']!r} es la PD de los 12 meses siguientes al corte, y la curva "
                f"llega a horizon={horizonte} y 12 meses son {horizonte_12m} {unidad_12m}: amplía "
                "horizon= hasta cubrirlos, o declara origination= o maturity=, que extienden la "
                "curva con su cola."
            )
        ciclo = self._escenarios(frame, columnas["as_of"], *escenarios)

        # ── identificador ────────────────────────────────────────────────────────────────
        index_col, unique_keys, id_label = self._resolver_id(frame, id)
        if id is None:
            inferencias.append(
                Inferencia(
                    regla="inferencia_identificador",
                    valor="índice del archivo",
                    motivo="no se declaró id=: cada operación se identifica por su posición",
                )
            )
        elif unique_keys is not None:
            # Un archivo de banco trae el identificador como COLUMNA. Desde CASO-REAL-IFRS9
            # (D-CRE-6) la curva identifica por esa columna —`survival.input.id_col`— y la
            # provisión la lee con `row_id_col`: las dos hojas se escriben juntas, y el detalle
            # por operación sale con el identificador del banco. Hasta la 2.5.0 las tres etapas
            # identificaban por la posición de la fila, porque la curva sólo publicaba el índice.
            inferencias.append(
                Inferencia(
                    regla="inferencia_identificador",
                    valor={"columna": id},
                    motivo=(
                        f"id={id} es una columna del archivo: se verifica que sea única, y la "
                        "curva, la provisión y el detalle por operación identifican cada "
                        "operación por ella"
                    ),
                )
            )
        id_columna = id if unique_keys is not None else None
        if id_columna is not None:
            id_label = f"{id_label}; la curva y la provisión identifican cada operación por ella"

        # ── esquema de las columnas declaradas ───────────────────────────────────────────
        en_esquema = list(dict.fromkeys([*([id_columna] if id_columna else []), *declaradas]))
        esquema = columnas_esquema(frame[[c for c in frame.columns if c in en_esquema]])
        inferencias.append(
            Inferencia(
                regla="inferencia_esquema",
                valor={c["name"]: c["dtype"] for c in esquema},
                motivo=(
                    "tipos leídos de los datos para las columnas declaradas, todas obligatorias: "
                    "una que falte falla al cargar, con su nombre, y no a mitad del cálculo"
                ),
            )
        )
        inferencias.append(
            Inferencia(
                regla="inferencia_corrida_de_cartera",
                valor={"target": None, "partition": None},
                motivo=(
                    "la provisión no usa qué es un cliente malo ni cómo se separan muestras: la "
                    "corrida no los declara (no aplica) y no siembra ningún criterio"
                ),
            )
        )
        if default is None:
            inferencias.append(
                Inferencia(
                    regla="inferencia_sin_marca",
                    valor={"provisioning_ifrs9.staging.is_default_col": None},
                    motivo=(
                        "no se declaró default=: el staging no usa una marca de incumplimiento "
                        "para el Stage 3"
                    ),
                )
            )
        self._inferences: tuple[Inferencia, ...] = tuple(inferencias)
        self._partition_label = ""
        self._source_label = source_label
        self._inference_lines = self._lineas_de_inferencia(
            n_columnas=len(esquema),
            id_label=id_label,
            horizonte_12m=horizonte_12m,
            unidad_12m=unidad_12m,
            period=period,
            sin_marca=default is None,
            sin_covariables=not covariables,
        )
        if ciclo is not None:
            self._inferences = (*self._inferences, ciclo["inferencia"])
            self._inference_lines = (*self._inference_lines, ciclo["linea"])

        # ── el config ────────────────────────────────────────────────────────────────────
        cfg = _config_base()
        cfg["name"] = self._name
        cfg["data"] = {
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
                "index_col": index_col,
                "unique_keys": unique_keys,
            },
            "missing": {"special_values": [], "max_missing_rate": 0.99},
            # D-ECL-2: una corrida de cartera declara target y partición en null explícito.
            "target": None,
            "partition": None,
        }
        survival = cfg["survival"]
        survival["input"]["duration_col"] = columnas["duration"]
        survival["input"]["event_col"] = columnas["event"]
        survival["input"]["covariate_cols"] = list(covariables)
        # D-CRE-6: con id= columna, la curva y la provisión leen la misma columna; con id= índice
        # (o sin id=), las dos hojas vacías: identifican por el índice, como el preset F4.
        survival["input"]["id_col"] = id_columna
        survival["time_grid"]["time_unit"] = period
        survival["time_grid"]["horizon_periods"] = horizonte
        ifrs = cfg["provisioning_ifrs9"]
        ifrs["as_of_date_col"] = columnas["as_of"]
        ifrs["portfolio_col"] = columnas["portfolio"]
        ifrs["row_id_col"] = id_columna
        ifrs["pd"]["horizon_12m_periods"] = horizonte_12m
        ifrs["ead"]["ead_col"] = columnas["exposure"]
        ifrs["lgd"]["lgd_col"] = columnas["lgd"]
        ifrs["ecl"]["eir_col"] = columnas["rate"]
        ifrs["staging"]["days_past_due_col"] = columnas["days_past_due"]
        ifrs["staging"]["is_default_col"] = default
        # CASO-REAL-IFRS9 D-CRE-2 y D-CRE-3: las tres columnas del contrato, opcionales.
        ifrs["origination_date_col"] = contrato["origination"]
        ifrs["maturity_date_col"] = contrato["maturity"]
        ifrs["ead"]["installment_col"] = contrato["installment"]
        # IFRS9-FIRMABLE D-FIR-7 y D-FIR-8: las dos PD del modelo, opcionales.
        ifrs["pd"]["pd_12m_col"] = modelo["pd"]
        ifrs["staging"]["origination_pd_12m_col"] = modelo["origination_pd"]
        if ciclo is not None:
            # IFRS9-FIRMABLE D-FIR-1…4: la vía de los escenarios de la institución.
            cfg["forward"] = ciclo["forward"]
            ifrs["pd"]["pit_mode"] = "cycle"
            ifrs["scenarios"]["source"] = "forward"
        report = cfg["report"]
        report["output_dir"] = str(self._reports_dir)
        if document:
            report["document"] = {**report.get("document", {}), **dict(document)}
        if formats is not None:
            report["formats"] = list(formats)
        if purpose is not None:
            if not str(purpose).strip():
                raise EclInputError(
                    "purpose= está en blanco: la ficha exige un propósito escrito por la "
                    "institución. Omite el argumento si no quieres ficha."
                )
            cfg["governance"] = {
                "model_name": self._name,
                "purpose": str(purpose),
                "author": owner,
                "review_period_months": review_every,
            }
        if track is not None:
            cfg["tracking"] = {"enabled": True, "tracking_uri": str(track)}
        self._config = self._validar_config(cfg)
        self._config, self._steps = self._resolver_pipeline(self._config)
        self._publicar_snapshot()

    def _escenarios(
        self, frame: pd.DataFrame, as_of: str, history: Any, scenarios: Any
    ) -> dict[str, Any] | None:
        """Las dos tablas de escenarios, validadas antes de correr con las reglas del motor.

        Devuelve la sección ``forward`` que las lee, la inferencia (las variables macro y la
        frecuencia de cada tabla) y su línea; ``None`` sin escenarios. Las tablas se copian al
        proyecto con su huella al publicar, como los datos.
        """
        if history is None and scenarios is None:
            return None
        if history is None or scenarios is None:
            raise EclInputError(
                "history= y scenarios= van juntas: la historia de la tasa de referencia estima la "
                "sensibilidad y los escenarios la aplican. Pasa las dos, o ninguna."
            )
        from bayesrisk.guided.escenarios import (
            ScenarioTablesError,
            leer_tablas_de_escenarios,
            seccion_forward,
        )

        try:
            tablas = leer_tablas_de_escenarios(
                self._tabla(history, "history"),
                self._tabla(scenarios, "scenarios"),
                reference_rate_col=_HISTORIA_TASA,
                cortes=frame[as_of].dropna().astype(str).str.strip().unique().tolist(),
            )
        except ScenarioTablesError as exc:
            raise EclInputError(str(exc)) from exc
        historia_ruta = self._reservar_tabla(tablas.historia, "history")
        rutas = {
            nombre: str(self._reservar_tabla(tabla, f"scenario-{i + 1}"))
            for i, (nombre, tabla) in enumerate(tablas.por_escenario.items())
        }
        return {
            "forward": seccion_forward(tablas, ruta_historia=str(historia_ruta), rutas=rutas),
            "inferencia": Inferencia(
                regla="inferencia_escenarios",
                valor={
                    "variables": list(tablas.variables),
                    "frecuencia_historia": tablas.frecuencia_historia,
                    "frecuencia_escenarios": tablas.frecuencia_escenarios,
                    "escenarios": dict(tablas.pesos),
                },
                motivo=(
                    "las variables macro son las columnas comunes a las dos tablas y la frecuencia "
                    "de cada una se lee de sus fechas"
                ),
            ),
            "linea": tablas.linea,
        }

    def _tabla(self, tabla: Any, argumento: str) -> pd.DataFrame:
        """Una tabla de escenarios desde un ``DataFrame`` o una ruta, con el cargador del motor."""
        if isinstance(tabla, pd.DataFrame):
            if tabla.empty:
                raise EclInputError(f"{argumento}= es un DataFrame vacío.")
            return tabla.reset_index(drop=True)
        ruta = Path(tabla).resolve()
        if not ruta.is_file():
            raise EclInputError(f"{argumento}= apunta a un archivo que no existe: {ruta}")
        from bayesrisk.guided.escenarios import leer_tabla

        try:
            return leer_tabla(ruta)
        except BayesRiskError as exc:
            raise EclInputError(f"No se pudo leer {argumento}= ({ruta}): {exc}") from exc

    def _reservar_tabla(self, tabla: pd.DataFrame, prefijo: str) -> Path:
        """El snapshot de una tabla en ``input/``, con su huella; se escribe al publicar."""
        from bayesrisk.guided.escenarios import contenido_parquet

        contenido, digest = contenido_parquet(tabla)
        ruta = self._project_dir / "input" / f"{prefijo}-{digest[:16]}.parquet"
        self._tablas_pendientes.append((ruta, contenido))
        self._tablas_huellas.append((ruta, digest))
        return ruta

    def _publicar_snapshot(self) -> None:
        """Los datos y, con escenarios, las dos tablas: sólo después de validar toda la puerta."""
        super()._publicar_snapshot()
        pendientes, self._tablas_pendientes = self._tablas_pendientes, []
        for ruta, contenido in pendientes:
            if ruta.exists():
                continue  # mismo contenido por construcción: el nombre es su huella
            ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal = ruta.with_name(f".{ruta.stem}.{os.getpid()}.tmp{ruta.suffix}")
            temporal.write_bytes(contenido)
            os.replace(temporal, ruta)

    def _descartar_snapshot(self) -> None:
        super()._descartar_snapshot()
        self._tablas_pendientes = []

    def _verificar_fuente(self) -> None:
        """Los datos y las tablas de escenarios son los mismos bytes sobre los que se infirió."""
        super()._verificar_fuente()
        for ruta, esperado in getattr(self, "_tablas_huellas", ()):
            if not ruta.is_file() or hashlib.sha256(ruta.read_bytes()).hexdigest() != esperado:
                raise EclInputError(
                    f"La tabla de escenarios {ruta} ya no existe o cambió desde que se construyó "
                    "el Ecl: construye uno nuevo."
                )

    @staticmethod
    def _resolver_horizonte(
        frame: pd.DataFrame, duration: str, period: str, horizon: int | None
    ) -> int:
        """El horizonte declarado, o la parada antes de correr con el valor que se usaría."""
        observado = pd.to_numeric(frame[duration], errors="coerce").max()
        maximo = int(observado) if pd.notna(observado) and float(observado).is_integer() else None
        if horizon is None:
            if maximo is None or maximo < 1:
                raise EclInputError(
                    f"Falta el horizonte de la curva: horizon=. La columna {duration!r} no trae "
                    "duraciones enteras positivas con que sugerirlo; es una decisión de la "
                    "institución: pásalo explícito."
                )
            palabras = time_unit_words(period, maximo) or f"períodos de «{period}»"
            raise EclInputError(
                f"Falta el horizonte de la curva: horizon=. Tus datos observan hasta {maximo} "
                f"{palabras}: con horizon={maximo} la curva llega hasta ahí. Es una decisión de la "
                "institución: pásalo explícito."
            )
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
            raise EclInputError(
                f"horizon={horizon!r} tiene que ser un número entero de períodos, 1 o más."
            )
        return horizon

    @staticmethod
    def _lineas_de_inferencia(
        *,
        n_columnas: int,
        id_label: str,
        horizonte_12m: int,
        unidad_12m: str,
        period: str,
        sin_marca: bool,
        sin_covariables: bool,
    ) -> tuple[str, ...]:
        lineas = [
            (
                f"Se infirió: esquema de {_miles(n_columnas)} "
                f"{_plural(n_columnas, 'columna declarada', 'columnas declaradas')}; los 12 "
                f"meses del Stage 1 son {_miles(horizonte_12m)} {unidad_12m} de la curva "
                f"(unidad «{period}»)"
            ),
            f"Identificador: {id_label}",
            "Corrida de cartera: no declara cliente malo ni muestras, que la provisión no usa",
        ]
        if sin_marca:
            lineas.append("Sin marca de incumplimiento: el Stage 3 no la usa")
        if sin_covariables:
            lineas.append("Sin covariables: una sola curva de PD para toda la cartera")
        return tuple(lineas)

    # ── decidir (D-ECL-8) ───────────────────────────────────────────────────────────────

    def exclude(self, columns: str | Sequence[str], *, reason: str) -> Self:
        """Retira covariables de la curva de PD en la corrida siguiente, con motivo.

        Escribe ``survival.input.covariate_cols`` sin ellas y registra la decisión en
        ``config.decisions`` con la lista que queda como huella: viaja en ``to_yaml()`` y la
        corrida siguiente (``resume()``) la declara al trail con autor ``usuario`` y este motivo.
        """
        motivo = self._motivo(reason, "exclude")
        nombres = [columns] if isinstance(columns, str) else [str(c) for c in columns]
        if not nombres:
            raise EclInputError("exclude() necesita al menos una covariable.")
        if len(set(nombres)) != len(nombres):
            raise EclInputError(f"exclude() repite una covariable: {nombres}.")
        survival = self._config.survival
        if survival is None:  # inalcanzable: la puerta siempre arma la sección
            raise EclInputError("La corrida no tiene curva de PD (sección survival).")
        actuales = tuple(survival.input.covariate_cols)
        desconocidas = [c for c in nombres if c not in actuales]
        if desconocidas:
            raise EclInputError(
                f"exclude(): {', '.join(desconocidas)} no "
                f"{_plural(len(desconocidas), 'es una covariable', 'son covariables')} de la "
                f"curva de esta corrida ({', '.join(actuales) or 'no tiene ninguna'})."
            )
        restantes = [c for c in actuales if c not in nombres]
        # El registro se arma y valida ANTES de escribir el config: o quedan los dos, o ninguno.
        registro = self._nuevo_registro(
            "exclude", nombres, motivo, {"survival.input.covariate_cols": list(restantes)}
        )
        entrada = survival.input.model_dump(mode="python", by_alias=True)
        entrada["covariate_cols"] = tuple(restantes)
        self._actualizar_seccion("survival", {"input": entrada})
        self._agregar_registro(registro)
        return self._tras_decidir(f"exclude {', '.join(nombres)}", motivo)

    def rebut_backstops(
        self,
        *,
        stage2_days: int | None = None,
        stage3_days: int | None = None,
        reason: str,
    ) -> Self:
        """Rebate las presunciones de mora de IFRS 9 (30 y 90 días), con motivo.

        IFRS 9 presume un aumento significativo del riesgo con más de 30 días de mora (5.5.11) y
        el incumplimiento con 90 (B5.5.37), y admite rebatirlas sólo con información razonable y
        sustentable: por eso es una decisión con motivo y no una perilla suelta. Escribe
        ``provisioning_ifrs9.staging.dpd_sicr_backstop`` y/o ``dpd_default_backstop`` y registra
        en ``config.decisions`` los dos días que quedan como huella; el validador del staging
        rechaza un Stage 3 que empiece antes que el Stage 2.
        """
        motivo = self._motivo(reason, "rebut_backstops")
        if stage2_days is None and stage3_days is None:
            raise EclInputError(
                "rebut_backstops() necesita stage2_days=, stage3_days= o los dos: los días de "
                "mora desde los que la institución presume el Stage 2 y el Stage 3."
            )
        for nombre, valor in (("stage2_days", stage2_days), ("stage3_days", stage3_days)):
            if valor is not None and (
                isinstance(valor, bool) or not isinstance(valor, int) or valor < 0
            ):
                raise EclInputError(f"{nombre}={valor!r} tiene que ser un número entero de días.")
        ifrs = self._config.provisioning_ifrs9
        if ifrs is None:  # inalcanzable: la puerta siempre arma la sección
            raise EclInputError("La corrida no tiene provisión (sección provisioning_ifrs9).")
        staging = ifrs.staging.model_dump(mode="python", by_alias=True)
        if stage2_days is not None:
            staging["dpd_sicr_backstop"] = stage2_days
        if stage3_days is not None:
            staging["dpd_default_backstop"] = stage3_days
        if staging["dpd_default_backstop"] < staging["dpd_sicr_backstop"]:
            # El validador del staging lo rechaza también; aquí se dice en palabras de negocio.
            raise EclInputError(
                f"rebut_backstops(): el Stage 3 desde {staging['dpd_default_backstop']} días de "
                f"mora empezaría antes que el Stage 2 (desde {staging['dpd_sicr_backstop']}). "
                "Un incumplimiento presume antes un aumento significativo del riesgo: sube "
                "stage3_days o baja stage2_days."
            )
        # El registro se arma y valida ANTES de escribir el config: o quedan los dos, o ninguno.
        registro = self._nuevo_registro(
            "rebut_backstops",
            [ifrs.staging.days_past_due_col],
            motivo,
            {
                "provisioning_ifrs9.staging.dpd_sicr_backstop": staging["dpd_sicr_backstop"],
                "provisioning_ifrs9.staging.dpd_default_backstop": staging["dpd_default_backstop"],
            },
        )
        self._actualizar_seccion("provisioning_ifrs9", {"staging": staging})
        self._agregar_registro(registro)
        return self._tras_decidir(
            f"rebut_backstops: Stage 2 desde {staging['dpd_sicr_backstop']} días de mora y "
            f"Stage 3 desde {staging['dpd_default_backstop']}",
            motivo,
        )

    # ── exportar (D-ECL-10) ─────────────────────────────────────────────────────────────

    def export_excel(self) -> tuple[Path, ...]:
        """Un libro Excel por etapa, numerado, en ``<run_dir>/<name>/excel/`` (D-ECL-10).

        ``01 Cartera.xlsx``, ``02 Curva de PD.xlsx``, ``03 Escenarios.xlsx`` (con escenarios) y
        ``04 Provisión IFRS 9.xlsx`` para las etapas que corrieron —cada uno con el resumen, la
        tabla de decisión, las tablas adicionales de la etapa y las tablas completas que el informe
        publica para ese dominio, con la misma protección de celdas que los exports del informe—
        más ``05 Decisiones.xlsx`` con las decisiones del registro de auditoría (humanas, de la
        puerta y del motor). El número es la posición de la etapa y no se mueve en una corrida
        parcial ni sin escenarios. Opcional: nunca es la vía para
        ver un resultado. Exige el extra ``excel`` (``openpyxl``); sin él se detiene con el comando
        de instalación.
        """
        return self._exportar_excel()

    def _tras_decidir(self, que: str, motivo: str) -> Self:
        self._pending_decisions = True
        self._config, self._steps = self._resolver_pipeline(self._config)
        self._final = None
        self._echo(
            f"Decisión registrada: {que} — «{motivo}». Se aplica en la corrida siguiente: resume()."
        )
        return self


def _config_base() -> dict[str, Any]:
    """El preset F4 como punto de partida: sus secciones de cálculo corren (§3.5)."""
    from bayesrisk.ui.presets import ifrs9_preset

    return deepcopy(ifrs9_preset()["config"])
