"""Puerta guiada del scorecard (SDD-31, enmienda FLUJO-GUIADO-SCORECARD; D-FLU-1…D-FLU-12).

:class:`~bayesrisk.guided.scorecard.Scorecard` se construye con lo que sólo la institución sabe
—los datos, qué es «malo», el identificador, el eje temporal con su frontera fuera de tiempo o una
partición aleatoria explícita—, infiere y **declara** el resto en el trail, corre el pipeline F1
completo con :func:`bayesrisk.run` y cuenta cada etapa con un resumen en español. Es un **cliente**
de ``bayesrisk.run``/``Study``: construye el ``BayesRiskConfig``, lo ejecuta y lee sus artefactos.
El config sigue siendo la verdad y el ``config_hash``, la identidad de la corrida (D-SIM-1).

**Estable (SemVer 2.x).** Salió en la 1.17.0 como adelanto declarado (D-SIM-1) y sus tres
puertas —código, config completo y pantalla— cerraron con la capa B de la enmienda (S18,
2026-09-21): la firma de :class:`Scorecard`, el contenido de los resúmenes y sus decisiones sólo
crecen de forma aditiva.

:class:`~bayesrisk.guided.ecl.Ecl`, la puerta guiada de la provisión IFRS 9 (enmienda
FLUJO-GUIADO-IFRS9), salió en la 2.4.0 como excepción experimental por símbolo y es estable desde
la capa B de su enmienda (D-ECL-9): su firma, sus métodos y la forma de sus resúmenes; sus cifras
siguen la marca experimental de ``survival``, ``forward`` y ``provisioning``. Los escenarios de la
institución y las dos PD del modelo (``history=``, ``scenarios=``, ``pd=``, ``origination_pd=``)
salieron experimentales en la 2.8.0 y la 2.9.0 y son estables desde que cerraron sus tres puertas
(IFRS9-FIRMABLE capa C, 2.10.0).
"""

from bayesrisk.guided.ecl import Ecl, EclInputError, EclRunError
from bayesrisk.guided.scorecard import Scorecard, ScorecardInputError, ScorecardRunError
from bayesrisk.guided.summaries import (
    STAGE_LABELS,
    STAGE_LABELS_CARTERA,
    FinalSummary,
    StageSummary,
)

__all__ = [
    "STAGE_LABELS",
    "STAGE_LABELS_CARTERA",
    "Ecl",
    "EclInputError",
    "EclRunError",
    "FinalSummary",
    "Scorecard",
    "ScorecardInputError",
    "ScorecardRunError",
    "StageSummary",
]
