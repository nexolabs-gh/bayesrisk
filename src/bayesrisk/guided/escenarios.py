"""Las dos tablas de los escenarios de la institución (IFRS9-FIRMABLE D-FIR-2…4, §3.11 y §4).

**Una sola fuente** para las dos puertas que las reciben como tablas: la guiada
(``bayesrisk.Ecl(history=, scenarios=)``) y la pantalla (``POST /api/scenario-tables``, capa C).
Las lee, las valida con las mismas funciones del motor —``build_cycle_model`` y la cobertura de 12
meses contra el corte, también antes de correr—, infiere y declara lo que se puede inferir (las
variables macro son las columnas comunes a las dos; la frecuencia de cada una, de sus fechas) y
arma la sección ``forward`` que las lee. Así una tabla que la puerta guiada rechaza, la pantalla
también, con el mismo motivo, y lo que las dos escriben es el mismo config.

- **Historia:** ``date``, la tasa de incumplimiento de referencia (``default_rate`` en la puerta
  guiada; en la pantalla, la columna que declare su esencial) y las variables macro.
- **Escenarios:** ``scenario``, ``weight``, ``date`` y las mismas variables. Cada escenario se
  separa en su propia tabla —``forward`` lee una trayectoria por escenario— y su peso va al config.

Dónde quedan los archivos lo decide cada puerta (la guiada, en ``input/`` del proyecto; la
pantalla, en su ``workdir``): su ubicación no entra al ``config_hash`` y su contenido lo ancla la
huella que publica ``forward`` (Cami, 2026-10-09).
"""

from __future__ import annotations

import hashlib
import io
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pandas as pd

from bayesrisk.core.exceptions import ConfigError

if TYPE_CHECKING:
    from bayesrisk.forward.cycle import ForwardCycleModel

__all__ = [
    "COLUMNA_ESCENARIO",
    "COLUMNA_FECHA",
    "COLUMNA_PESO",
    "COLUMNA_TASA",
    "PROVISION_CON_ESCENARIOS",
    "ScenarioTablesError",
    "TablasDeEscenarios",
    "contenido_parquet",
    "escribir_tabla",
    "leer_tabla",
    "leer_tablas_de_escenarios",
    "seccion_forward",
]

#: Las columnas de nombre fijo de las dos tablas (§3.11). Las variables macro son las restantes.
COLUMNA_FECHA: Final = "date"
COLUMNA_TASA: Final = "default_rate"
COLUMNA_ESCENARIO: Final = "scenario"
COLUMNA_PESO: Final = "weight"
#: La tolerancia con que los pesos de los escenarios suman 1 (la de `forward`).
TOL_PESOS: Final = 1e-9

_FRECUENCIAS: Final[dict[int, str]] = {1: "mensual", 3: "trimestral", 12: "anual"}

#: Lo que la provisión IFRS 9 necesita para consumir los escenarios de la institución (D-FIR-1):
#: el ajuste por ciclo y los escenarios de `forward`. Lo escribe `Ecl(history=, scenarios=)` y lo
#: devuelve `POST /api/scenario-tables` junto con la sección `forward`, también cuando la pantalla
#: no tiene un trabajo que lo siembre (pasada 2 de Codex sobre la capa C).
PROVISION_CON_ESCENARIOS: Final[dict[str, dict[str, str]]] = {
    "pd": {"pit_mode": "cycle"},
    "scenarios": {"source": "forward"},
}


class ScenarioTablesError(ConfigError):
    """Las dos tablas no cumplen las reglas de §3.4 y §4: la corrida se detiene antes de correr."""


@dataclass(frozen=True)
class TablasDeEscenarios:
    """Las dos tablas leídas y validadas, con lo que se infirió de ellas."""

    historia: pd.DataFrame
    #: Cada escenario en su tabla: la fecha y las variables, en el orden de la historia.
    por_escenario: dict[str, pd.DataFrame]
    #: El peso de cada escenario, en el orden de primera aparición.
    pesos: dict[str, float]
    variables: tuple[str, ...]
    reference_rate_col: str
    modelo: ForwardCycleModel

    @property
    def frecuencia_historia(self) -> str:
        """La frecuencia de la historia, inferida de sus fechas («trimestral»)."""
        return _FRECUENCIAS[self.modelo.history_frequency_months]

    @property
    def frecuencia_escenarios(self) -> str:
        """La frecuencia de los escenarios, inferida de sus fechas."""
        return _FRECUENCIAS[self.modelo.scenarios[0].frequency_months]

    @property
    def ventana(self) -> str:
        """La ventana de la historia con tasa, en palabras cortas («2005T1 a 2025T1»)."""
        from bayesrisk.forward.cycle import month_label

        meses = self.modelo.history_frequency_months
        return (
            f"{month_label(self.modelo.window_start_month, meses)} a "
            f"{month_label(self.modelo.window_end_month, meses)}"
        )

    @property
    def linea(self) -> str:
        """La línea que la puerta dice al construirse (y la pantalla, al leer las dos tablas)."""
        from bayesrisk.report.prose import _plural

        nombres = list(self.pesos)
        return (
            f"Escenarios: {len(nombres)} ({', '.join(nombres)}), {self.frecuencia_escenarios}es; "
            f"historia {self.frecuencia_historia} de la tasa de referencia, {self.ventana}; "
            f"{_plural(len(self.variables), 'variable', 'variables')} {', '.join(self.variables)}"
        )


def leer_tablas_de_escenarios(
    historia: pd.DataFrame,
    trayectorias: pd.DataFrame,
    *,
    reference_rate_col: str = COLUMNA_TASA,
    cortes: Sequence[str] = (),
    rotulos: tuple[str, str] = ("history=", "scenarios="),
) -> TablasDeEscenarios:
    """Valida las dos tablas con las reglas del motor e infiere sus variables.

    Parameters
    ----------
    historia, trayectorias : pandas.DataFrame
        La historia de la tasa de referencia y la tabla de escenarios, ya leídas.
    reference_rate_col : str
        La columna de la tasa en la historia (``default_rate`` en la puerta guiada).
    cortes : Sequence[str]
        Las fechas de corte de la cartera: con una sola, se comprueba que los escenarios cubran los
        12 meses siguientes (§3.4) antes de correr; sin ella, lo comprueba la corrida.
    rotulos : tuple[str, str]
        Cómo se nombra cada tabla en un mensaje: el argumento de la puerta guiada o la tabla de
        la pantalla.

    Raises
    ------
    ScenarioTablesError
        Con el motivo, si una regla no se cumple.
    """
    from bayesrisk.core.exceptions import BayesRiskError
    from bayesrisk.forward.cycle import build_cycle_model
    from bayesrisk.provisioning.ifrs9.cycle import check_scenario_coverage, first_future_month

    de_historia, de_escenarios = rotulos
    historia = historia.reset_index(drop=True)
    trayectorias = trayectorias.reset_index(drop=True)
    faltan = [c for c in (COLUMNA_FECHA, reference_rate_col) if c not in historia.columns]
    if faltan:
        raise ScenarioTablesError(
            f"{_mayuscula(de_historia)} no trae {', '.join(faltan)}: lleva {COLUMNA_FECHA}, "
            f"{reference_rate_col} (la tasa de referencia como fracción) y las variables macro."
        )
    faltan = [
        c for c in (COLUMNA_ESCENARIO, COLUMNA_PESO, COLUMNA_FECHA) if c not in trayectorias.columns
    ]
    if faltan:
        raise ScenarioTablesError(
            f"{_mayuscula(de_escenarios)} no trae {', '.join(faltan)}: lleva scenario, weight, "
            f"date y las mismas variables macro que {de_historia}."
        )
    variables = [c for c in historia.columns if c not in (COLUMNA_FECHA, reference_rate_col)]
    otras = [
        c for c in trayectorias.columns if c not in (COLUMNA_ESCENARIO, COLUMNA_PESO, COLUMNA_FECHA)
    ]
    if not variables or set(variables) != set(otras):
        raise ScenarioTablesError(
            "Las variables macro son las columnas restantes de las dos tablas y tienen que ser "
            f"las mismas: {de_historia} trae {variables or 'ninguna'} y {de_escenarios} trae "
            f"{otras or 'ninguna'}."
        )
    nombres = list(dict.fromkeys(str(n) for n in trayectorias[COLUMNA_ESCENARIO].tolist()))
    pesos: dict[str, float] = {}
    por_escenario: dict[str, pd.DataFrame] = {}
    for nombre in nombres:
        filas = trayectorias.loc[trayectorias[COLUMNA_ESCENARIO].astype(str) == nombre]
        valores = pd.to_numeric(filas[COLUMNA_PESO], errors="coerce").unique()
        if len(valores) != 1 or not pd.notna(valores[0]):
            raise ScenarioTablesError(
                f"El peso del escenario {nombre!r} tiene que ser un número, el mismo en todas "
                "sus filas."
            )
        pesos[nombre] = float(valores[0])
        por_escenario[nombre] = filas[[COLUMNA_FECHA, *variables]].reset_index(drop=True)
    total = sum(pesos.values())
    if abs(total - 1.0) > TOL_PESOS:
        raise ScenarioTablesError(
            f"Los pesos de los escenarios suman {total!r}: tienen que sumar 1 "
            f"({', '.join(f'{n} {w}' for n, w in pesos.items())})."
        )
    try:
        modelo = build_cycle_model(
            historia,
            por_escenario,
            pesos,
            time_col=COLUMNA_FECHA,
            reference_rate_col=reference_rate_col,
            factor_cols=variables,
        )
        unicos = list(dict.fromkeys(str(c).strip() for c in cortes))
        if len(unicos) == 1:
            check_scenario_coverage(modelo, first_month=first_future_month(unicos[0]))
    except BayesRiskError as exc:
        raise ScenarioTablesError(str(exc)) from exc
    return TablasDeEscenarios(
        historia=historia,
        por_escenario=por_escenario,
        pesos=pesos,
        variables=tuple(variables),
        reference_rate_col=reference_rate_col,
        modelo=modelo,
    )


def seccion_forward(
    tablas: TablasDeEscenarios, *, ruta_historia: str, rutas: Mapping[str, str]
) -> dict[str, Any]:
    """La sección ``forward`` que lee las dos tablas desde sus archivos (§3.11).

    Las hojas que no salen de las tablas —la vía del ciclo— son las que la pantalla escribe al
    encender la sección (``toggle_overrides`` del trabajo IFRS 9); un gate ata las dos.
    """
    return {
        "input": {
            "macro_source": {
                "type": "path",
                "path": ruta_historia,
                "time_col": COLUMNA_FECHA,
                "variable_cols": list(tablas.variables),
            },
            "term_structure_sources": ["survival"],
            # La curva de supervivencia es a lo largo del ciclo; en esta vía no se usa (el
            # satélite mira la tabla de historia), pero el sub-schema lo exige declarado.
            "pd_basis_assumption": "ttc",
        },
        "satellite": {
            "mode": "reference_rate",
            "factor_cols": list(tablas.variables),
            "reference_rate_col": tablas.reference_rate_col,
        },
        "macro": {"kind": "scenario_paths"},
        "scenarios": {
            "scenarios": [
                {"name": nombre, "weight": peso, "macro_path_path": rutas[nombre]}
                for nombre, peso in tablas.pesos.items()
            ]
        },
    }


def leer_tabla(ruta: Path) -> pd.DataFrame:
    """Una tabla desde un archivo, con el cargador del motor (el mismo que lee los datos)."""
    from bayesrisk.data.config import LoadingConfig
    from bayesrisk.data.loading import DataLoader

    return DataLoader.from_config(LoadingConfig(source=str(ruta))).load().reset_index(drop=True)


def contenido_parquet(tabla: pd.DataFrame) -> tuple[bytes, str]:
    """Los bytes con que se guarda una tabla y su huella SHA-256, que su nombre de archivo lleva."""
    buffer = io.BytesIO()
    tabla.to_parquet(buffer, index=False)
    contenido = buffer.getvalue()
    return contenido, hashlib.sha256(contenido).hexdigest()


def escribir_tabla(directorio: Path, prefijo: str, tabla: pd.DataFrame) -> Path:
    """Guarda una tabla como ``<prefijo>-<huella>.parquet``: el mismo contenido, el mismo archivo.

    La escritura es atómica (un temporal y ``os.replace``) y no reescribe lo que ya existe: el
    nombre es la huella.
    """
    contenido, digest = contenido_parquet(tabla)
    ruta = directorio / f"{prefijo}-{digest[:16]}.parquet"
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(f".{ruta.stem}.{os.getpid()}.tmp{ruta.suffix}")
        temporal.write_bytes(contenido)
        os.replace(temporal, ruta)
    return ruta


def _mayuscula(rotulo: str) -> str:
    """Un rótulo de la pantalla abre la frase con mayúscula; un argumento (``history=``), no."""
    return rotulo if rotulo.endswith("=") else rotulo[:1].upper() + rotulo[1:]
