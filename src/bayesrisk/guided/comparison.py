"""``bayesrisk.Comparison``: la puerta guiada de la comparación de modelos (SDD-34 D-CMP-1…9).

**Experimental (fuera de la garantía SemVer 2.x).**
Sale en la 2.15.0 como adelanto declarado (capa A del SDD-34, D-CMP-9): estable cuando cierren sus
tres puertas —pantalla, informe y Excel— en la capa B.

Se construye con lo único que la institución tiene que decir: **qué corridas** comparar, en orden
—la primera es la referencia (el modelo en uso)—. Cada una puede ser un objeto vivo ya corrido (un
``Scorecard``, un ``Ecl`` o un ``Study``), la carpeta de una corrida (la del proyecto guiado, el
``run_dir`` de ``bayesrisk.run`` o ``runs/<id>/`` de la pantalla) o su ``comparable.json``. Infiere
y **declara** el resto —la referencia, la muestra de evaluación de cada una, la comparabilidad y
los modelos repetidos— y corre con :func:`bayesrisk.run`. **No es un segundo orquestador**: arma un
config con la sección ``comparison`` y lo corre; ``comp.config`` es la verdad y
``comp.config_hash``, la identidad (D-SIM-1). Cada resumen se copia a ``<run_dir>/<name>/input/``
con su huella en el nombre, así que la comparación se reproduce desde su carpeta.

La comparación **no elige**: ``choose(nombre, reason=…)`` registra la elección de la institución
con su motivo (D-CMP-6), atada a la huella del resumen elegido.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, Final, Self

from bayesrisk.core.exceptions import BayesRiskError, ConfigError
from bayesrisk.guided._puerta import _PuertaGuiada
from bayesrisk.guided.inference import Inferencia
from bayesrisk.report.prose import _enumerar, _miles

__all__ = ["Comparison", "ComparisonInputError", "ComparisonRunError"]

#: Paso con que la puerta firma sus eventos en el trail.
GUIDED_STEP: Final = "comparison_guided"
#: Cómo se nombra cada muestra de evaluación en las inferencias.
_MUESTRAS: Final[dict[str, str]] = {
    "oot": "OOT",
    "holdout": "Holdout",
    "desarrollo": "Desarrollo (sin OOT ni Holdout: cifras optimistas)",
}


class ComparisonInputError(ConfigError):
    """Lo que la puerta guiada de la comparación rechaza **antes de correr**.

    Una corrida sin resumen comparable, fuera de 2 a 10, de familias distintas o repetida, o una
    elección que no nombra a ninguna de las comparadas.
    """


class ComparisonRunError(BayesRiskError):
    """La corrida terminó fallida y se pidió ``raise_on_error=True``.

    También cuando la corrida no pudo empezar porque otra tiene la carpeta del proyecto.
    """


class Comparison(_PuertaGuiada):
    """La comparación de entre 2 y 10 corridas terminadas, con la entrada mínima (D-CMP-1).

    **Experimental (fuera de la garantía SemVer 2.x).**
    Sale en la 2.15.0 (capa A del SDD-34); su firma y sus resúmenes pueden crecer de forma aditiva
    hasta cerrar sus tres puertas.

    Parameters
    ----------
    runs
        Las corridas, en orden: la primera es la referencia. Cada una, un ``Scorecard``, un
        ``Ecl`` o un ``Study`` ya corridos; la carpeta de una corrida guardada; o su
        ``comparable.json``. Todas de la misma familia (scorecards o provisiones IFRS 9) y
        guardadas desde la 2.15.0.
    name, run_dir
        Nombre de la comparación y carpeta raíz: la evidencia queda en ``<run_dir>/<name>/``
        (``"comparacion"`` y ``"bayesrisk-runs"`` de fábrica).
    """

    _PUERTA: ClassVar[str] = "Comparison"
    _GUIDED_STEP: ClassVar[str] = GUIDED_STEP
    _InputError: ClassVar[type[ConfigError]] = ComparisonInputError
    _RunError: ClassVar[type[BayesRiskError]] = ComparisonRunError
    _FAMILIA: ClassVar[str] = "comparacion"

    def __init__(
        self,
        runs: Sequence[Any],
        *,
        name: str = "comparacion",
        run_dir: str | Path = "bayesrisk-runs",
    ) -> None:
        self._iniciar(name, run_dir)
        self._resumenes_pendientes: list[tuple[Path, bytes]] = []
        self._resumenes_huella: list[tuple[Path, str]] = []
        try:
            if isinstance(runs, str | Path) or not isinstance(runs, Sequence):
                raise ComparisonInputError(
                    "runs= es una lista de corridas (entre 2 y 10), la primera la referencia."
                )
            resumenes = [self._resumen(entrada, posicion) for posicion, entrada in enumerate(runs)]
            self._construir(resumenes)
        except BaseException:
            self._descartar_snapshot()
            raise

    # ── construir ───────────────────────────────────────────────────────────────────────

    def _resumen(self, entrada: Any, posicion: int) -> dict[str, Any]:
        """El resumen comparable de una entrada: un objeto vivo, una carpeta o el archivo."""
        from bayesrisk.comparison.comparable import leer, resumen_de
        from bayesrisk.comparison.exceptions import ComparisonDataError
        from bayesrisk.core.study import Study

        try:
            if isinstance(entrada, str | Path):
                return leer(Path(entrada).resolve())[0]
            if isinstance(entrada, Study):
                return resumen_de(entrada)
            study = getattr(entrada, "study", None)
            if study is None and hasattr(entrada, "study"):
                raise ComparisonInputError(
                    f"La corrida {posicion + 1} todavía no corrió: llama a run() antes de "
                    "compararla."
                )
            if isinstance(study, Study):
                return resumen_de(study)
        except ComparisonDataError as exc:
            raise ComparisonInputError(str(exc)) from exc
        raise ComparisonInputError(
            f"La corrida {posicion + 1} es un {type(entrada).__name__}: se compara un Scorecard, "
            "un Ecl o un Study ya corridos, la carpeta de una corrida o su comparable.json."
        )

    def _construir(self, resumenes: list[dict[str, Any]]) -> None:
        """Valida la comparación, declara lo inferido y arma el config.

        Los resúmenes se publican al final, con su huella en el nombre.
        """
        from bayesrisk.comparison.comparable import bytes_canonicos, huella
        from bayesrisk.comparison.exceptions import ComparisonDataError
        from bayesrisk.comparison.step import comparar
        from bayesrisk.comparison.textos import NIVELES

        try:
            vista = comparar(resumenes)
        except ComparisonDataError as exc:
            raise ComparisonInputError(str(exc)) from exc
        card = vista.card
        nombres = list(card.names)
        self._nombres: tuple[str, ...] = tuple(nombres)
        self._huellas: tuple[str, ...] = tuple(card.summary_hashes)
        muestras = {
            nombre: str(r.get("evaluation_sample"))
            for nombre, r in zip(nombres, resumenes, strict=True)
            if r["family"] == "scorecard"
        }
        niveles = dict(zip(nombres[1:], card.levels[1:], strict=True))
        inferencias: list[Inferencia] = [
            Inferencia(
                regla="inferencia_referencia",
                valor={"nombre": nombres[0], "huella": self._huellas[0]},
                motivo=(
                    "la primera corrida es la referencia —el modelo en uso—: contra ella se miden "
                    "la comparabilidad, las diferencias y la provisión"
                ),
            ),
            Inferencia(
                regla="inferencia_comparabilidad",
                valor={"niveles": niveles, "mismo_modelo": dict(card.same_as)},
                motivo=(
                    "las huellas de la cartera y de la muestra evaluada dicen si se midieron "
                    "sobre las mismas operaciones; la huella computacional, si son el mismo "
                    "modelo (SDD-34 §3.3)"
                ),
            ),
        ]
        if muestras:
            inferencias.append(
                Inferencia(
                    regla="inferencia_muestra_de_evaluacion",
                    valor=muestras,
                    motivo=(
                        "cada corrida se compara en su OOT; sin OOT, en su Holdout; sin ninguna, "
                        "con sus cifras de Desarrollo, optimistas y fuera de la frontera"
                    ),
                )
            )
        self._inferences: tuple[Inferencia, ...] = tuple(inferencias)
        self._partition_label = ""
        self._source_label = f"{_miles(len(nombres))} corridas guardadas: {_enumerar(nombres)}"
        lineas = [
            f"Referencia: {nombres[0]} (la primera)",
            "Comparabilidad: " + _enumerar([f"{n}, {NIVELES[v]}" for n, v in niveles.items()]),
        ]
        if muestras:
            distintas = sorted(set(muestras.values()))
            lineas.append(
                "Muestra de evaluación: "
                + (
                    f"{_MUESTRAS.get(distintas[0], distintas[0])} en todas"
                    if len(distintas) == 1
                    else _enumerar([f"{n}, {_MUESTRAS.get(m, m)}" for n, m in muestras.items()])
                )
            )
        if card.same_as:
            lineas.append(
                "El mismo modelo: " + _enumerar([f"{c} es {o}" for c, o in card.same_as.items()])
            )
        self._inference_lines = tuple(lineas)

        # ── cada resumen, copiado al proyecto con su huella ──────────────────────────────
        rutas: list[str] = []
        for resumen in resumenes:
            contenido = bytes_canonicos(resumen)
            valor = huella(resumen)
            destino = self._project_dir / "input" / f"comparable-{valor[:16]}.json"
            self._resumenes_pendientes.append((destino, contenido))
            self._resumenes_huella.append((destino, valor))
            rutas.append(str(destino))
        cfg: dict[str, Any] = {
            "schema_version": "1.0.0",
            "name": self._name,
            "repro": {"seed": 20240706, "strict_determinism": False},
            "run": {"steps": None, "fail_fast": True},
            "comparison": {"runs": rutas},
            # SDD-34 capa B: el informe con su capítulo (``report`` es INFRA, fuera del
            # `config_hash`): ninguna sección del scorecard se exige y el capítulo se activa por la
            # card de la comparación, como el del monitoreo.
            "report": {
                "output_dir": str(self._reports_dir),
                "basename": "comparison_report",
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
        """Los resúmenes: sólo después de validar toda la puerta, sin pisar uno existente."""
        import os

        super()._publicar_snapshot()
        pendientes, self._resumenes_pendientes = self._resumenes_pendientes, []
        for destino, contenido in pendientes:
            if destino.exists():
                continue  # mismo contenido por construcción: el nombre es su huella
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporal = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
            temporal.write_bytes(contenido)
            os.replace(temporal, destino)

    def _descartar_snapshot(self) -> None:
        self._resumenes_pendientes = []
        super()._descartar_snapshot()

    def _verificar_fuente(self) -> None:
        """Los resúmenes son los mismos sobre los que se construyó la comparación."""
        from bayesrisk.comparison.comparable import huella, leer
        from bayesrisk.comparison.exceptions import ComparisonDataError

        super()._verificar_fuente()
        for ruta, esperada in self._resumenes_huella:
            try:
                vigente = huella(leer(ruta)[0])
            except ComparisonDataError:
                vigente = None
            if vigente != esperada:
                raise ComparisonInputError(
                    f"El resumen {ruta} ya no existe o cambió desde que se construyó la "
                    "comparación: construye una nueva."
                )

    # ── decidir (D-CMP-6) ───────────────────────────────────────────────────────────────

    @property
    def names(self) -> tuple[str, ...]:
        """Los nombres de las corridas comparadas, en orden; uno repetido lleva su posición."""
        return self._nombres

    def choose(self, name: str, *, reason: str) -> Self:
        """Registra la corrida que eligió la institución, con su motivo, y vuelve a comparar.

        La comparación no elige (D-CMP-6): muestra la frontera y la institución decide. La
        decisión queda en la sección ``decisions`` y en el registro de auditoría con su autor y
        motivo, atada a la **huella** del resumen elegido —no al nombre ni a la posición—: si esa
        corrida se reemplaza o su resumen cambia, la elección queda sin efecto y el resumen lo
        avisa. Volver a comparar toma milisegundos, así que la corrida es inmediata.
        """
        motivo = self._motivo(reason, "choose")
        if name not in self._nombres:
            raise ComparisonInputError(
                f"choose({name!r}): no es una de las corridas comparadas. Corridas: "
                f"{', '.join(self._nombres)}."
            )
        valor = self._huellas[self._nombres.index(name)]
        registro = self._nuevo_registro("choose", [name], motivo, {"comparison.choice": valor})
        self._agregar_registro(registro)
        self._echo(f"Decisión registrada: choose → {name} — «{motivo}».")
        return self.run()

    # ── exportar (SDD-34 §6.3, capa B) ──────────────────────────────────────────────────

    def export_excel(self) -> tuple[Path, ...]:
        """``Comparación.xlsx`` en ``<run_dir>/<name>/excel/``: un libro único (SDD-34 §6.3).

        Sus hojas son el resumen (la lectura y qué revisar), los modelos (la tabla de decisión,
        con las dos fronteras), las pruebas de DeLong pareadas, cada modelo en cada muestra, las
        variables —o, en IFRS 9, la provisión por etapa—, las corridas con su comparabilidad y un
        índice: las tablas del mismo resumen «Comparación» que el notebook y el informe.
        Opcional: nunca es la vía para ver un resultado. Exige el extra ``excel`` (``openpyxl``);
        sin él se detiene con el comando de instalación.
        """
        return self._exportar_excel()
