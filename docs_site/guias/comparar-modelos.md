# Comparar modelos

Un banco entrena varias versiones de su modelo —con y sin una variable, con otros tramos, con otra
ventana— y tiene que decidir cuál usar. `bayesrisk.Comparison` pone lado a lado entre 2 y 10
corridas guardadas, sin volver a correrlas, y dice lo que una planilla no dice: **si se midieron
sobre las mismas operaciones**, **cuáles son el mismo modelo**, **qué diferencias de discriminación
son reales y cuáles ruido**, **quién reparte mejor sus tramos** y **qué modelos no quedan superados
por ningún otro**. La comparación no elige: la institución registra su elección con su motivo.

!!! note "Estable desde la 2.16.0"
    La comparación está disponible por código y en la pantalla, con su informe y su libro Excel.
    Su API pública está bajo la garantía SemVer 2.x.

## Desde la pantalla

Elige **Comparar modelos**. En **Comparación**, marca entre 2 y 10 corridas terminadas
o sube sus archivos `comparable.json`. Pulsa **Usar como referencia** en la corrida de partida.
Este trabajo empieza en Configuración: los resúmenes ya contienen las medidas necesarias.

Pulsa **Ejecutar**. Resultados muestra la lectura, las tablas y los dos gráficos del informe;
para provisiones IFRS 9 muestra la comparación por etapa. La pestaña Reporte abre el informe.
La elección registrada se presenta como **Elección**, sin escoger un modelo por la institución.

## Lo que deja cada corrida

Desde la 2.15.0, toda corrida terminada de un scorecard que midió su desempeño, y toda de IFRS 9 que
calculó su provisión, deja junto a su evidencia un **resumen comparable**, `comparable.json`: sólo
agregados —las cifras por muestra, el PSI, la participación de cada tramo, las variables, la
validación—, las huellas que dicen sobre qué cartera y qué modelo se midió, y el riesgo y el
desenlace de su muestra de evaluación en orden, **sin ningún identificador de operación**. La
comparación lee estos archivos y nada más: no abre el estudio de ninguna corrida ni deserializa
objetos. Una corrida guardada con una versión anterior no tiene resumen: se vuelve a correr con esta
versión —mismo config, mismos resultados— o se pasa el objeto vivo.

Aquí, dos versiones del scorecard de la cartera de consumo del paquete: la de fábrica y una con
hasta cuatro tramos por variable.

<!-- comparar-corridas:start -->
```python
from pathlib import Path

from bayesrisk import Scorecard
from bayesrisk.ui.datasets import materialize

datos = materialize("consumo_comportamiento", workdir=Path("bayesrisk-runs"))
base = dict(target="bad_flag", id="loan_id", cohort="cohorte", oot_cohorts=["2024Q2"])
v01 = Scorecard(data=datos, name="consumo_v01", **base)
v01.run()
v02 = Scorecard(data=datos, name="consumo_v02", max_bins=4, **base)
v02.run()
```
<!-- comparar-corridas:end -->

## La comparación en tres líneas

<!-- comparar:start -->
```python
from bayesrisk import Comparison

comp = Comparison(runs=[v01, "bayesrisk-runs/consumo_v02"])
comp.run()
```
<!-- comparar:end -->

`runs` acepta, mezclados, objetos ya corridos (un `Scorecard`, un `Ecl` o un `Study`), la carpeta de
una corrida —la del proyecto guiado, el `run_dir` de `bayesrisk.run` o la de la pantalla— o el
`comparable.json` mismo. El orden manda: **la primera es la referencia**, el modelo en uso. Cada
resumen se copia a la carpeta de la comparación con su huella en el nombre, así que la comparación
se reproduce desde ella.

Con la corrida de estos bloques, el resumen dice:

```text
── Comparación ──
Las dos corridas usan las mismas operaciones.
En discriminación empatan consumo_v01 y consumo_v02.
Todas son estables.
Reparte mejor sus tramos: consumo_v02 (índice 0,07 frente a 0,13).
Ninguna otra supera a consumo_v02 en discriminación y concentración.
Pasa la validación técnica consumo_v02; falla consumo_v01 (Hosmer-Lemeshow en Fuera de tiempo (OOT)).
Comparten cinco variables.
```

Las dos versiones discriminan igual: la diferencia de AUC en la OOT, 0,002, es ruido (la prueba
pareada da p = 0,66). Con la misma discriminación, `consumo_v02` reparte mucho mejor sus tramos y
pasa la validación técnica que la de fábrica falla, así que es la única que ninguna otra supera en
discriminación y concentración. Si la alternativa hubiera dado exactamente el mismo modelo con otro
config, la primera línea lo diría.

## Qué se compara

**La muestra de evaluación** de cada corrida es su fuera de tiempo (OOT); sin OOT, su Holdout; sin
ninguna de las dos, sus cifras de Desarrollo, que son optimistas y quedan fuera de los gráficos.

**La comparabilidad**, contra la referencia, en tres niveles: la **misma muestra evaluada** (las
mismas operaciones con el mismo desenlace: la comparación es directa), la **misma cartera con otra
muestra** (otra OOT, otro objetivo) y **otra cartera** (otros datos: la comparación es orientativa).
Nunca bloquea: comparar un modelo redesarrollado con datos nuevos contra el que está en uso es
legítimo, y la comparación lo dice en vez de impedirlo.

**El mismo modelo.** Dos corridas con otro config pueden dar exactamente el mismo modelo —una
selección paso a paso que no saca nada, un tope de correlación que ninguna variable alcanza—. La
comparación lo reconoce por la huella de lo que el modelo usa para puntuar (los tramos, los
coeficientes, la calibración, la escala), no por el config, y lo dice primero.

**La discriminación, con su ruido.** Dos AUC de la misma muestra se comparan con la **prueba de
DeLong pareada**, que usa que las dos corridas puntúan las mismas operaciones: una diferencia es
real si la prueba la rechaza con p < 0,05; si no, **empatan**. Sobre otras operaciones no hay prueba
y se comparan las cifras, declarado. Con N corridas son N(N−1)/2 pruebas, sin corrección por
multiplicidad.

**La estabilidad**, por banda del PSI del puntaje —estable, revisar, redesarrollar—, medido para
todas con la **misma receta**, la de fábrica (10 tramos por cuantiles de Desarrollo y los cortes
0,10 y 0,25): con la receta propia de cada corrida, el mismo puntaje podría dar un PSI distinto
según cuántos tramos se cuenten. Si una corrida usó otra receta, la tabla muestra también su PSI
propio.

**La concentración**, con el **índice del BCE** sobre la participación de cada tramo de la escala
maestra, `1 + ln(HHI)/ln(K)`: 0 si los tramos pesan igual, 1 si todo cae en uno, y —a diferencia del
HHI— sin depender del número de tramos. Sin escala maestra el índice queda «No evaluable». No hay
umbral: se publica y no se alerta.

**La frontera.** Un modelo queda superado si otro es al menos igual de bueno en las dos cifras de un
gráfico —discriminación y estabilidad, o discriminación y concentración— y estrictamente mejor en
una, con los empates de arriba; la frontera son los que no supera ningún modelo de la frontera.
Elegir dentro de ella es pesar una cifra contra la otra, y ese peso es de la institución.

## La elección de la institución

<!-- comparar-eleccion:start -->
```python
comp.choose("consumo_v02", reason="la misma discriminación, con los tramos mejor repartidos")
```
<!-- comparar-eleccion:end -->

La elección queda en el config de la comparación y en su registro de auditoría con el autor y el
motivo, y el resumen la dice. Se ata a la **huella del resumen elegido**, no al nombre ni a la
posición: reordenar las corridas no la mueve, y si esa corrida se reemplaza o su resumen cambia, la
elección queda sin efecto y el resumen lo avisa.

## Provisiones IFRS 9

Dos provisiones de la misma cartera se comparan igual, por etapa: operaciones, exposición, ECL y
cobertura, y contra la referencia, la diferencia de ECL y la etapa donde está. No hay gráficos ni
frontera —en provisiones, «más» no es «mejor»—. Los montos se restan sólo cuando la unidad es la
misma con certeza: la misma cartera con las mismas columnas de monto, o la misma moneda declarada en
las dos. Una moneda sin declarar no es «la misma»: si no, cada provisión se muestra por separado y
la cobertura se compara en puntos.

## El informe y el libro Excel

La comparación escribe su informe en `reports/` —HTML, Word y la fuente editable—: el **«Informe de
Comparación de Modelos»**, con una página ejecutiva que dice la lectura y la elección, y el capítulo
«Comparación de modelos»: las corridas y su comparabilidad; la discriminación y la estabilidad, con
el gráfico del AUC frente al PSI común y la tabla de pruebas pareadas; la concentración, con el
gráfico del Gini frente al índice del BCE; las variables de cada modelo —en IFRS 9, la provisión por
etapa—, y la elección. En cada gráfico los modelos de la frontera van rellenos y los superados,
huecos; los que no entran —sin OOT ni Holdout, sin escala maestra— se declaran bajo el eje. En el
notebook, `comp.summary("comparison")` muestra los mismos dos gráficos.

```python
comp.export_excel()
```

deja `excel/Comparación.xlsx`, un libro único: el resumen, los modelos, las pruebas pareadas, cada
modelo en cada muestra, las variables —o la provisión por etapa—, las corridas y un índice. Son las
tablas del mismo resumen que el notebook y el informe, celda a celda. Exige el extra `excel`.

## Lo que queda en la evidencia

`comp.summary()` devuelve el resumen final y `comp.summary("comparison")` el de la etapa, con la
tabla de modelos como tabla de decisión, las variables de cada modelo y las pruebas pareadas. La
corrida publica sus tablas bajo el dominio `comparison` —`runs`, `models`, `tests`, `samples`,
`variables`, `provision` y `reading`—, el registro de auditoría lleva cada corrida comparada con su
huella y los modelos repetidos, y el lineage la huella de cada resumen, en orden
(`comparison_hashes`). Las rutas de las corridas no entran a la identidad de la comparación: moverlas
de carpeta no cambia el `config_hash`; cambiar un resumen cambia su huella.

La misma comparación por el config completo es una sola sección, y `comp.to_yaml()` la muestra:

```yaml
comparison:
  runs:
    - bayesrisk-runs/comparacion/input/comparable-…json
    - bayesrisk-runs/comparacion/input/comparable-…json
```
