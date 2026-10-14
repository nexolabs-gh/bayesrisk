# Monitorear un modelo en uso

Una tarjeta en uso necesita, cada mes o trimestre, tres respuestas y una acción: **¿cambió la
cartera?**, **¿el modelo sigue ordenando?** y **¿cada tramo sigue acertando su PD?**; y, según eso,
**sin acción, vigilar, recalibrar o redesarrollar**. `bayesrisk.Monitor` las da por periodo, a
partir de la tarjeta guardada y de la cartera nueva, sin volver a correr el desarrollo ni conservar
sus datos.

!!! note "Estable desde la 2.14.0"
    El monitoreo salió en la 2.13.0 por la puerta guiada y el config completo, y desde la 2.14.0
    tiene sus tres puertas —también la pantalla, con el trabajo «Monitorear un modelo en uso»—,
    su capítulo en el informe y el libro `Monitoreo.xlsx`. Está bajo la garantía SemVer 2.x.

## La tarjeta que se monitorea

El monitoreo compara cada periodo contra la **referencia de Desarrollo** que la tarjeta congela al
guardarse: los cortes del puntaje y cuántas operaciones de Desarrollo caen entre ellos, la
participación de cada tramo de la escala maestra y el AUC inicial sobre esos tramos —el de
Holdout, la validación inicial fuera de la muestra de ajuste—. Son sólo agregados: la tarjeta sigue
sin guardar una fila de los datos. Por eso se monitorean las tarjetas guardadas desde la 2.13.0, con
su escala maestra; una guardada antes se sigue leyendo y aplicando igual, y el monitoreo la rechaza
diciendo cómo obtener una que sí: volver a correr el desarrollo con esta versión —mismo config,
mismo modelo— y guardar la tarjeta.

Aquí la tarjeta sale del scorecard de la cartera de consumo del paquete y se monitorea sobre otra
cartera del paquete, `consumo_drift`, cuya población se desplaza con las añadas:

<!-- monitoreo-tarjeta:start -->
```python
from pathlib import Path

from bayesrisk import FittedScorecardBundle, Scorecard
from bayesrisk.ui.datasets import materialize

runs = Path("bayesrisk-runs")
sc = Scorecard(
    data=materialize("consumo_comportamiento", workdir=runs),
    target="bad_flag",
    id="loan_id",
    cohort="cohorte",
    oot_cohorts=["2024Q2"],
    name="consumo_v01",
)
sc.run()
FittedScorecardBundle.from_study(sc.study).save("tarjeta")   # la tarjeta, con su escala maestra
cartera = materialize("consumo_drift", workdir=runs)          # la cartera nueva, por añada
```
<!-- monitoreo-tarjeta:end -->

## El monitoreo en tres líneas

<!-- monitoreo:start -->
```python
from bayesrisk import Monitor

mon = Monitor(bundle="tarjeta", data=cartera, period="cohorte", default="bad_flag")
mon.run()
```
<!-- monitoreo:end -->

`period` es la columna que dice a qué periodo pertenece cada operación —texto, número o fecha (una
fecha se agrupa por mes)— y `default`, el desenlace: 1 malo, 0 bueno y vacío si todavía no madura.
Sin `default` sólo se mide la población. Una misma operación puede estar en varios periodos: la
tarjeta se aplica periodo por periodo, con sólo sus variables y sus llaves.

Con la corrida de estos bloques, el resumen dice:

```text
── Monitoreo ──
Veredicto: Recalibrar en 2024Q2 — Recalibrar la PD de los tramos: el modelo sigue ordenando, pero su nivel ya no acierta.
Por qué: la tasa de malos de la cartera no acierta su PD (la PD subestima el riesgo).
```

La población se mueve desde 2023Q3 (el PSI del puntaje llega a 2,04) y mientras el modelo la sigue
el veredicto es **vigilar**; en 2024Q2 la tasa de malos de la cartera, 48,5 %, ya no cabe en su PD
esperada, 43,7 %, y el veredicto pasa a **recalibrar**. El orden se sostiene: el AUC sobre los
tramos, 0,664, no cae significativamente contra el inicial, 0,682.

## Qué se mide en cada periodo

| Indicador | Qué compara | Semáforo |
|---|---|---|
| PSI del puntaje | La distribución del puntaje del periodo contra la de Desarrollo, con los cortes de la tarjeta | < 0,10 verde, < 0,25 ámbar, rojo desde 0,25 |
| PSI por tramo | La participación de cada tramo contra la de Desarrollo | Las mismas bandas |
| Calibración por tramo y de cartera | La tasa de malos contra la PD del tramo (Jeffreys), sobre las operaciones con desenlace, **en las dos direcciones**: una PD demasiado baja subestima el riesgo; una demasiado alta niega crédito a quien podía pagar | p < 0,05 ámbar, p < 0,01 rojo; un tramo con menos de 30 operaciones con desenlace no se evalúa |
| Discriminación | El AUC sobre los tramos contra el AUC inicial (la prueba del BCE) y la pendiente de calibración: si los tramos separan lo que el modelo promete | p < 0,05 ámbar, p < 0,01 rojo |

Los umbrales son fijos —los mismos que usan la estabilidad y la validación— y el resumen los
nombra. Un indicador que no se puede evaluar (pocos malos, todas las operaciones con desenlace en un
solo tramo) **no cuenta como verde**: el veredicto se calcula con lo evaluable y dice «evidencia
parcial» con la lista de lo que faltó.

## El veredicto

Las filas se leen en orden y gana la primera que se cumple:

1. **Redesarrollar** si las dos pruebas de discriminación están en rojo: los tramos separan menos
   de lo que el modelo promete y el AUC cayó contra la validación inicial. Recalibrar el nivel no
   devuelve el orden perdido.
2. **Recalibrar** si la calibración de la cartera está en rojo, si hay dos o más tramos en rojo, o
   si el mismo tramo está en rojo dos periodos seguidos: el orden sigue, el nivel no.
3. **Vigilar** si la población está en rojo, si un indicador de la cartera está en ámbar (los PSI,
   la calibración de cartera o una prueba de discriminación), si un tramo está en rojo aislado o si
   sólo una de las dos pruebas de discriminación está en rojo: cambió algo que todavía no es una
   falla del modelo.
4. **Sin acción** si todo lo evaluable está en verde.

Un tramo en ámbar solo no pide vigilar, y un tramo rojo aislado sólo pide eso: con cinco tramos y
seis periodos, un rojo por azar aparece en uno de cada cuatro monitoreos. La población sola nunca
pide redesarrollar: en `consumo_drift` con su propia tarjeta el PSI llega a 0,75 sin ningún tramo
en rojo. Un periodo **sin desenlace** todavía no se puede medir: con la población
en rojo o ámbar es «vigilar» y si no, «sin desenlace aún», nunca «sin acción». El veredicto de la
corrida es el del último periodo; si ese periodo no tiene desenlace, se informa además el del
último que sí lo tiene.

## Lo que queda en la evidencia

`mon.summary()` devuelve el resumen final y `mon.summary("monitoring")` el de la etapa, con la
tabla de periodos como tabla de decisión y cada tramo por periodo. La corrida publica sus tablas
bajo el dominio `monitoring` —`periods`, `grades_by_period` (con las dos direcciones de cada
tramo), `variables_by_period` (el CSI de cada variable, como diagnóstico) y `verdict`—; el
registro de auditoría lleva una entrada por cada indicador en rojo y el veredicto, y el lineage la
huella de la tarjeta (`bundle_hash`). La ruta de la tarjeta y la de la cartera no entran a la
identidad de la corrida: moverlas de carpeta no cambia el `config_hash`; cambiar su contenido
cambia su huella. Cada corrida recalcula la serie entera: monitorear más periodos es una corrida
nueva con todos ellos, y ninguna corrida anterior se toca.

La misma corrida por el config completo lleva sus secciones —`data` sin target ni partición,
`monitoring`, el informe y la auditoría— y `mon.to_yaml()` las muestra:

```yaml
monitoring:
  bundle: bayesrisk-runs/monitoreo/input/tarjeta-…
  period: cohorte
  default: bad_flag
```

## En la pantalla, el informe y el Excel

En la pantalla (`bayesrisk-ui`), el trabajo **«Monitorear un modelo en uso»** pide lo mismo: la
tarjeta —la de una corrida del scorecard hecha en esa pantalla, que se guarda sola con cada corrida
que se puede monitorear, o una tarjeta guardada que se sube como `.zip`—, la cartera y sus columnas
de periodo y de desenlace. Resultados muestra el veredicto, la serie por periodo, cada tramo y cada
variable por periodo, con las mismas frases y cifras que el resumen.

El informe de la corrida tiene su capítulo, «Monitoreo del modelo en uso», con el veredicto y la
serie, cada tramo y cada variable por periodo; y `mon.export_excel()` deja
`excel/Monitoreo.xlsx`, un libro único con el resumen, los periodos, los tramos y las variables.
Las tres puertas —esta guía, el config completo y la pantalla— dan, con el mismo config, el mismo
`config_hash` y las mismas tablas.
