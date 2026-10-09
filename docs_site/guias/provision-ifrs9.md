# La provisión IFRS 9 de punta a punta

Esta guía lleva una cartera desde el archivo hasta la provisión IFRS 9 firmable —la cifra, su
informe y su evidencia— por las tres puertas de bayesrisk: la **guiada** (`bayesrisk.Ecl`, unas
veinte líneas), la **completa** (el config entero, en YAML o por código) y la **pantalla**
(`bayesrisk-ui`). Las tres corren el mismo config y llegan a la misma cifra.

!!! note "Qué garantiza"
    La firma de `bayesrisk.Ecl`, sus métodos y la forma de sus resúmenes son estables (SemVer
    2.x). Las cifras siguen la marca experimental de los motores de supervivencia y de
    provisiones, que pueden cambiar dentro de la 2.x. Necesita el extra `scoring`, que trae el
    ajuste de la curva.

## Qué calcula

La pérdida crediticia esperada (ECL) de cada operación en tres etapas: Stage 1 provisiona la
pérdida de los próximos 12 meses; Stage 2, la de toda la vida de la operación (IFRS 9 5.5.3 y
5.5.5); y Stage 3, una operación que ya incumplió, la pérdida de ese incumplimiento: su LGD por
su exposición. La probabilidad de incumplimiento de cada período sale de una **curva de PD**
que se ajusta sobre la historia de incumplimientos de tu propia cartera —un modelo de riesgo en
tiempo discreto con tus covariables—; la LGD y la exposición (EAD) vienen de tu archivo; cada
pérdida se descuenta a la tasa efectiva anual de la operación; y la etapa la deciden la mora
(30 y 90 días, las presunciones de la norma) y la marca de incumplimiento.

## Qué necesita de tus datos

Un archivo (`.csv`, `.parquet` o `.xlsx`) con una fila por operación y estas columnas, con el
nombre que tengan en tu archivo:

| Para qué | Columnas |
|---|---|
| La provisión | fecha de corte (un solo valor), cartera, exposición ya calculada, LGD, tasa efectiva **anual**, días de mora y, si la tienes, la marca de incumplimiento |
| La curva de PD | cuánto tiempo se observó cada operación (entero ≥ 1) y si incumplió (0/1); la unidad de ese tiempo (`"month"`, `"quarter"`, `"year"`…) y hasta cuántos períodos se proyecta la curva |
| Opcional | el identificador de la operación y las covariables que ordenan el riesgo |
| Opcional, del contrato | la fecha de otorgamiento, la de vencimiento y la cuota mensual de cada operación (ver [Con las fechas y la cuota del contrato](#con-las-fechas-y-la-cuota-del-contrato)) |
| Opcional, escenarios | la historia de una tasa de incumplimiento de referencia con sus variables macroeconómicas y tus escenarios con sus pesos, en dos tablas aparte (ver [Con escenarios económicos](#con-escenarios-economicos)) |
| Opcional, la PD de tu modelo | la PD a 12 meses de hoy de cada operación y la del otorgamiento (ver [Con la PD de tu modelo](#con-la-pd-de-tu-modelo)) |

Dos cosas que conviene saber antes de armar el archivo con datos reales:

- **La historia vive en las mismas filas que la cartera.** Los incumplimientos de tu historia
  suelen estar en operaciones que ya se cerraron —castigadas o pagadas—. Inclúyelas con
  exposición 0: alimentan la curva y no son operaciones de la cartera. La provisión no las
  valida, no las estagea ni las cuenta, y «Cartera» dice cuántas filas son sólo historia.
- **El identificador puede ser una columna.** `id=` verifica que sea única, y la curva, la
  provisión y el detalle por operación identifican cada operación por ella.

## La puerta guiada

`bayesrisk.Ecl` arma el config desde tus columnas, infiere y declara lo que no preguntó —cuántos
períodos son 12 meses, el esquema de las columnas, que es una corrida de cartera— y cuenta cada
etapa al correr. Aquí con la cartera de ejemplo del paquete: 6.000 operaciones al 30 de junio de
2025.

<!-- provision-ifrs9-guiada:start -->
```python
from pathlib import Path

from bayesrisk import Ecl
from bayesrisk.ui.datasets import materialize

datos = materialize("ifrs9_retail_latam", workdir=Path("bayesrisk-runs"))

ecl = Ecl(
    data=datos,
    id="loan_id",
    as_of="as_of_date",
    portfolio="portfolio",
    exposure="ead",
    lgd="lgd",
    rate="eir",                     # la tasa efectiva ANUAL
    days_past_due="days_past_due",
    default="is_default",
    duration="duration", event="event", period="year", horizon=5,
    covariates=["days_past_due", "utilizacion_linea", "deuda_ingreso", "antiguedad_meses"],
    name="provision_2025_06",
)

# Primero, sólo hasta la curva: mirar sus coeficientes antes de decidir.
ecl.run(until="survival")
print(ecl.results["survival"])      # los coeficientes de la curva

# Una decisión humana, con su motivo: la covariable no vendrá en los próximos cierres.
ecl.exclude("antiguedad_meses", reason="no viene en el archivo de cartera de los próximos cierres")
ecl.resume()                        # una corrida nueva y completa con la decisión

print(ecl.summary())                # el resumen final, con sus supuestos
paquete = ecl.export("provision_2025_06.zip")
```
<!-- provision-ifrs9-guiada:end -->

Cada etapa habla en palabras de provisiones —«Cartera», «Curva de PD», «Provisión IFRS 9» e
«Informe y ficha»— y `ecl.summary("survival")` suma la PD acumulada por período y cartera. Las
decisiones viajan en el config (sección `decisions`), en el registro de auditoría y en el resumen
final; la otra que la puerta admite es `ecl.rebut_backstops(stage2_days=..., reason=...)`, que
rebate las presunciones de mora y que la norma admite sólo con información razonable y
sustentable.

## La puerta completa

Lo que la puerta guiada corrió es un `BayesRiskConfig` entero: `ecl.config`, y en disco
`bayesrisk-runs/provision_2025_06/config.yaml`. Ese YAML es la puerta completa: se versiona, se
edita —todo lo que el motor admite está ahí, incluido lo que la puerta guiada no pregunta— y se
corre con `bayesrisk.run`.

<!-- provision-ifrs9-completa:start -->
```python
from pathlib import Path

import bayesrisk
from bayesrisk.core.config import load_config

config = load_config(Path("bayesrisk-runs") / "provision_2025_06" / "config.yaml")
study = bayesrisk.run(config, run_dir=Path("bayesrisk-runs") / "provision_por_yaml")
assert study.run_context.status == "done", study.run_context.error

card = study.artifacts.get("provisioning_ifrs9", "card")
print(f"ECL total: {float(card.total_ecl_reported):,.0f}")  # la misma cifra que la puerta guiada
```
<!-- provision-ifrs9-completa:end -->

El mismo config da la misma cifra y el mismo `config_hash`: la identidad de la corrida no
depende de la puerta por la que entró.

## Con las fechas y la cuota del contrato

Sin más datos, la provisión lee la curva de cada operación desde su primer período y hasta el
horizonte de la curva, como si cada operación naciera hoy, y con la exposición constante. Si tu
archivo trae las fechas y la cuota del contrato, dáselas: la curva se lee desde la **antigüedad**
de cada operación —los meses desde el otorgamiento, sin redondear— y la vida termina en su
**vencimiento** (IFRS 9 5.5.19); el Stage 1 suma 12 meses o la vida, si es menor; y la exposición
de cada período sigue la **tabla de pagos** de la cuota, con la tasa implícita en la cuota —no la
tasa efectiva, que incluye comisiones—. Las tres columnas son opcionales e independientes, salvo
la cuota, que necesita el vencimiento. Aquí, con una cartera sintética de cuota fija generada en
el mismo bloque:

<!-- provision-ifrs9-contrato:start -->
```python
import numpy as np
import pandas as pd

from bayesrisk import Ecl

# 2.000 préstamos de cuota fija otorgados en los últimos cuatro años, a 24, 36 o 48 meses, con su
# historia hasta el corte: los cerrados (pagados o castigados) entran con exposición 0.
rng = np.random.default_rng(2025)
n = 2_000
corte = pd.Timestamp("2025-06-30")
antiguedad = rng.integers(1, 49, n)                 # meses desde el otorgamiento
plazo = rng.choice([24, 36, 48], n)                 # meses del contrato
puntaje = rng.normal(0.0, 1.0, n)                   # más alto, menos riesgo
tasa_mes = 0.015 + 0.004 * rng.random(n)            # la tasa mensual del contrato
monto = rng.integers(500, 5_000, n) * 1_000.0
cuota = monto * tasa_mes / (1 - (1 + tasa_mes) ** -plazo)
mes_incumple = rng.geometric(0.006 * np.exp(-0.6 * puntaje))
observado = np.minimum(antiguedad, plazo)
incumplio = mes_incumple <= observado
vivo = ~incumplio & (antiguedad < plazo)
saldo = monto * ((1 + tasa_mes) ** plazo - (1 + tasa_mes) ** observado) / (
    (1 + tasa_mes) ** plazo - 1
)
otorgamiento = [corte - pd.DateOffset(months=int(m)) for m in antiguedad]

cartera = pd.DataFrame({
    "loan_id": [f"P{i:05d}" for i in range(n)],
    "as_of_date": "2025-06-30",
    "portfolio": np.where(plazo == 48, "consumo largo", "consumo"),
    "ead": np.where(vivo, saldo.round(0), 0.0),
    "lgd": 0.65,
    "eir": (1 + tasa_mes) ** 12 - 1,                # la tasa efectiva ANUAL
    "days_past_due": np.where(vivo & (puntaje < -1.5), 45, 0),
    "is_default": False,
    "duration": np.ceil(np.where(incumplio, mes_incumple, observado) / 3).astype(int),
    "event": incumplio.astype(int),
    "puntaje": puntaje,
    "otorgamiento": otorgamiento,
    "vencimiento": [o + pd.DateOffset(months=int(p)) for o, p in zip(otorgamiento, plazo)],
    "cuota": cuota.round(0),
})

contrato = Ecl(
    data=cartera,
    id="loan_id",
    as_of="as_of_date",
    portfolio="portfolio",
    exposure="ead",
    lgd="lgd",
    rate="eir",
    days_past_due="days_past_due",
    default="is_default",
    origination="otorgamiento",                     # la curva, desde la antigüedad
    maturity="vencimiento",                         # la vida, hasta el vencimiento
    installment="cuota",                            # la exposición, por la tabla de pagos
    duration="duration", event="event", period="quarter", horizon=16,
    covariates=["puntaje"],
    name="provision_con_contrato",
)
contrato.run()
print(contrato.summary("provisioning_ifrs9"))       # dice cómo leyó la curva y la exposición
```
<!-- provision-ifrs9-contrato:end -->

Con las fechas, la curva de cada operación se lee **desde su edad**: la probabilidad de cada
período es la de incumplir en ese tramo de la curva dado que la operación sobrevivió hasta hoy,
con el riesgo constante dentro de cada período. Tres reglas fijas, sin perilla, que el resumen
declara:

- **La cola.** Una curva por períodos sólo estima riesgo donde hubo incumplimientos: más allá del
  último período con incumplimientos observados, el riesgo de cada operación se extiende con la
  media de sus tres últimos períodos con incumplimientos. «Qué revisar» dice qué parte de la
  exposición vive ahí —en esta cartera, la de los préstamos a 48 meses que pasan del período 14—.
- **Vencida con saldo.** Una operación con el vencimiento ya pasado y saldo vivo sigue expuesta:
  se provisiona con un período y «Qué revisar» la cuenta.
- **Una cuota que no alcanza.** Si la cuota no paga el saldo en el plazo —un pago final mayor,
  atrasos, intereses que se capitalizan—, la exposición queda constante hasta el vencimiento y
  «Qué revisar» la cuenta con su monto.

La lectura desde la edad supone que la duración de la historia de la curva cuenta desde el
otorgamiento —como en este archivo—, y exige la curva de supervivencia por períodos discretos, la
PD a 12 meses de esa misma curva y a lo largo del ciclo: con otra configuración, la verificación
previa lo avisa antes de correr. Una fila sin fecha o sin cuota se lee como sin ese dato; sin ninguna de las tres
columnas, la provisión es exactamente la de antes.

## Con escenarios económicos

IFRS 9 pide una pérdida ponderada por la probabilidad de varios escenarios, con las condiciones
actuales y las previsiones (5.5.17): la curva de PD sola es un promedio del ciclo. Con dos tablas
más, la provisión se ajusta al ciclo:

- **La historia** de una tasa de incumplimiento de referencia larga —que cruce al menos un ciclo—
  con sus variables macroeconómicas: columnas `date`, `default_rate` (como fracción: un 0,9 % va
  como 0,009) y las variables, con una fila por mes, trimestre o año, sin huecos. El motor estima
  cuánto se mueve esa tasa con la macro, `logit(tasa) = a + b · (x − x̄)`, y lo dice con su error.
- **Los escenarios** de la institución, con sus pesos: columnas `scenario`, `weight`, `date` y las
  mismas variables, al menos dos escenarios, pesos que suman 1, que cubran como mínimo los 12
  meses siguientes al corte.

Cada tramo de la curva posterior al corte se desplaza en logit según la macro de su **fecha de
calendario** —la edad sigue decidiendo la forma de la curva—, se calcula la ECL de cada escenario
y se pondera. Aquí, sobre la misma cartera de arriba, con una historia sintética de veinte años
cuya sensibilidad se conoce (el logit de la tasa sube 0,15 por punto de desempleo) y tres
escenarios ilustrativos:

<!-- provision-ifrs9-escenarios:start -->
```python
# Veinte años trimestrales de una tasa de referencia y el desempleo, con un ciclo adentro.
trimestres = pd.date_range("2005-01-01", "2025-04-01", freq="QS")
desempleo = 7.0 + 2.0 * np.sin(np.arange(len(trimestres)) / 6.0 + 1.5) + rng.normal(0, 0.3, len(trimestres))
logit = -4.0 + 0.15 * (desempleo - desempleo.mean()) + rng.normal(0, 0.05, len(trimestres))
historia = pd.DataFrame({"date": trimestres, "default_rate": 1 / (1 + np.exp(-logit)),
                         "desempleo": desempleo})

# Tres escenarios para los tres años siguientes al corte, con sus pesos (ilustrativos).
futuro = pd.date_range("2025-07-01", periods=12, freq="QS")
escenarios = pd.concat([
    pd.DataFrame({"scenario": nombre, "weight": peso, "date": futuro,
                  "desempleo": desempleo[-1] + np.linspace(0.0, alza, 12)})
    for nombre, peso, alza in (("base", 0.6, 0.0), ("adverso", 0.3, 2.0), ("severo", 0.1, 4.0))
])

con_escenarios = Ecl(
    data=cartera, id="loan_id", as_of="as_of_date", portfolio="portfolio", exposure="ead",
    lgd="lgd", rate="eir", days_past_due="days_past_due", default="is_default",
    origination="otorgamiento", maturity="vencimiento", installment="cuota",
    duration="duration", event="event", period="quarter", horizon=16, covariates=["puntaje"],
    history=historia, scenarios=escenarios,         # las dos tablas
    name="provision_con_escenarios",
)
con_escenarios.run()
print(con_escenarios.summary("forward"))            # la sensibilidad y los escenarios
print(con_escenarios.summary("provisioning_ifrs9")) # la ECL de cada escenario frente a la TTC
```
<!-- provision-ifrs9-escenarios:end -->

Lo que el motor decide solo, y declara en «Supuestos» y en «Qué revisar»:

- **La sensibilidad se transfiere uno a uno.** Se estima sobre la tasa de referencia y se aplica a
  la curva de tu cartera: si tu cartera es más o menos cíclica que la referencia, el ajuste queda
  sesgado en esa proporción. El motor no puede verificar qué mide una tasa externa; quien firma
  documenta que la referencia es de la misma cartera o producto, mide un evento cercano al de la
  curva (mora de 90 días o castigo, no de 30), es trimestral o más fina y cruza al menos un ciclo.
  Cuando ninguna serie pública cumple los cuatro, se usa la más cercana y se declara la excepción.
  «Qué revisar» alerta si la sensibilidad es incierta (`|b| < 2` errores estándar o R² < 0,1) o
  si la ventana tiene menos de 20 períodos.
- **El ancla.** La curva no es «de largo plazo» por decreto: es el promedio de las condiciones de
  su historia. Con la fecha de otorgamiento, el desplazamiento se mide contra la macro media de
  los períodos con que se ajustó la curva; sin ella, contra la media de la tabla de historia, y
  se dice.
- **Más allá de los escenarios**, el desplazamiento vuelve en 24 meses, en línea recta, hacia las
  condiciones de largo plazo de la tabla de historia (B5.5.50 y B5.5.52).
- **El calendario va por meses.** El primer mes futuro es el que contiene el día siguiente al
  corte; un valor de una tabla vale para todo su período, y el de cada tramo es el promedio de sus
  meses. La tasa de la historia puede faltar al principio o al final —el trimestre del corte
  todavía no la tiene—: esos períodos dan sólo su macro al ancla.

Los escenarios y sus pesos son de la institución: el motor no trae ninguno por defecto ni datos
macroeconómicos reales. Fuentes públicas con licencia abierta: para Chile, la cartera vencida por
cartera de la [CMF](https://www.cmfchile.cl) (desde 2009) y la desocupación del
[INE](https://www.ine.gob.cl); para Estados Unidos, el desempleo del
[BLS](https://www.bls.gov), el PIB del [BEA](https://www.bea.gov), los precios de vivienda de la
[FHFA](https://www.fhfa.gov) y las tasas de castigo y morosidad del sistema y los escenarios
supervisores de la [Reserva Federal](https://www.federalreserve.gov). Los escenarios de estrés de
un supervisor no son, por sí solos, previsiones ponderables: tómalos como insumo de los tuyos.

Medido con el motor sobre las dos carteras públicas de abajo, con los escenarios de la Reserva
Federal publicados al corte y pesos ilustrativos: la ECL ponderada de los créditos de consumo de
Lending Club (corte 2019, desempleo bajo el de la historia de su curva) baja un 1,8 % frente a la
curva sola, y la de las hipotecas de Freddie Mac (corte 2026, con un severo de 10 % de desempleo)
sube un 12,9 %.

## Con la PD de tu modelo

La curva de PD sale de la historia de incumplimientos de la cartera; tu scorecard o tu modelo de
rating ya dice cuánto riesgo tiene cada operación hoy. Con dos columnas más, la provisión los usa:

- **La PD a 12 meses de hoy** (`pd=`): la curva de cada operación se desplaza para que su PD de los
  12 meses siguientes al corte —leída desde su antigüedad— sea la de tu modelo. Conserva su forma
  por edad y toma el nivel de tu modelo, también en la pérdida de por vida; con escenarios, su
  desplazamiento va encima. Con `bayesrisk`, es la PD calibrada del scorecard aplicado a la cartera
  con `bayesrisk.apply`.
- **La PD a 12 meses al otorgar** (`origination_pd=`, que exige `pd=` y `origination=`): el
  aumento significativo del riesgo compara, para los 12 meses siguientes al corte, la PD de hoy
  —ponderada por los escenarios, si los hay— con la que se esperaba al otorgar para ese mismo tramo
  de vida (IFRS 9 5.5.9; la PD a 12 meses como aproximación de la de por vida, B5.5.13). Si llega al
  doble, la operación pasa a Stage 2. Comparar sin el tramo escondería un deterioro: en una
  hipoteca de diez años, el riesgo de hoy es más bajo que el del primer año aunque la operación
  haya empeorado.

Aquí, sobre la misma cartera, con una PD de origen y una de hoy sintéticas —la de hoy, peor en un
10 % de las operaciones—:

<!-- provision-ifrs9-pd:start -->
```python
# La PD a 12 meses al otorgar sale del puntaje con que se otorgó; la de hoy, de un puntaje que se
# movió desde entonces y, en un 10 % de la cartera, a peor.
deterioro = np.where(rng.random(n) < 0.10, -1.5, 0.0)
puntaje_hoy = puntaje + rng.normal(0.0, 0.3, n) + deterioro
cartera["pd_origen"] = 1 - (1 - 0.006 * np.exp(-0.6 * puntaje)) ** 12
cartera["pd_hoy"] = 1 - (1 - 0.006 * np.exp(-0.6 * puntaje_hoy)) ** 12

con_pd = Ecl(
    data=cartera, id="loan_id", as_of="as_of_date", portfolio="portfolio", exposure="ead",
    lgd="lgd", rate="eir", days_past_due="days_past_due", default="is_default",
    origination="otorgamiento", maturity="vencimiento", installment="cuota",
    duration="duration", event="event", period="quarter", horizon=16, covariates=["puntaje"],
    history=historia, scenarios=escenarios,
    pd="pd_hoy", origination_pd="pd_origen",         # las dos PD de tu modelo
    name="provision_con_pd",
)
con_pd.run()
print(con_pd.summary("provisioning_ifrs9"))         # tu PD frente a la curva y el SICR
```
<!-- provision-ifrs9-pd:end -->

Lo que el motor supone, y declara en «Supuestos» y en «Qué revisar»:

- **Tu PD mide el mismo incumplimiento a 12 meses que la curva y es a lo largo del ciclo** —si ya
  fuera de las condiciones actuales, los escenarios contarían el ciclo dos veces—. El motor no puede
  verificarlo: el resumen compara la PD media de tu modelo con la de la curva, ponderadas por la
  exposición, y avisa si difieren en más de un 25 %.
- **Una fila sin PD** usa la curva sin anclar, y sin PD de origen su aumento significativo del
  riesgo es sólo la mora y la marca; una PD de 0, de 1 o fuera de ese rango se acota. Las dos se
  cuentan.
- La mora y la marca siguen como presunciones (5.5.11, B5.5.19–20), y la comparación de la PD de
  por vida de origen con la de hoy sigue en la puerta completa: con las fechas del contrato, la de
  hoy es la de la vida que le queda, y esa comparación no es por tramo.

Medido con el motor: la PD del scorecard del paquete sube la provisión de la cartera de ejemplo un
18,5 % —y la alerta salta: su incumplimiento sintético no es el de la curva, 9,99 % frente a
6,31 %—; con la PD de hoy, la de los créditos de consumo de Lending Club sube un 11,2 % y la de las
hipotecas de Freddie Mac baja un 12,3 %.

## La pantalla

```bash
bayesrisk-ui
```

El trabajo «Provisiones IFRS 9 / ECL» pregunta lo mismo que la puerta guiada y nada más: no pide
qué es un cliente malo ni cómo separar muestras —los muestra como «No aplica en una corrida de
cartera»— y sí la duración, el evento, la unidad y el horizonte de la curva. Parte de las mismas
constantes que la puerta guiada, así que con las mismas columnas calcula la misma provisión. La
curva abre sus cinco campos esenciales y la provisión sus doce —las tres columnas opcionales del
contrato van juntas bajo «Si tienes las fechas y la cuota del contrato», y las dos PD de tu modelo
bajo «Si tienes la PD de tu modelo»—; el resto queda en «Avanzado». Los 12 meses del Stage 1 se
infieren de la unidad, como en la puerta guiada.

Los escenarios están en «Escenarios económicos», apagados hasta que subes tus dos tablas —la
historia y los escenarios, con las mismas columnas que arriba—: la pantalla las lee con la misma
regla que la puerta guiada —una tabla que ésta rechaza, la pantalla también, con el mismo motivo—,
enciende la sección con lo que leyó y pone la provisión en el ajuste por ciclo; «Quitar los
escenarios» la devuelve a lo largo del ciclo. La sección abre tres campos: la tabla de historia, la
columna de la tasa de referencia (`default_rate`, si la tuya se llama distinto) y los escenarios
con sus pesos. Resultados pinta el mismo resumen, con sus supuestos, la curva de PD por cartera
—con escenarios, la curva que consumió la provisión: la ECL de cada escenario frente a la de la
curva a lo largo del ciclo y el desplazamiento de cada tramo— y la ECL por cartera y etapa.

Las tres puertas corren el mismo config: el YAML de la puerta guiada, cargado en la pantalla, da el
mismo `config_hash` y la misma cifra. Armado en el formulario, la cifra es la misma y el
`config_hash` difiere sólo en lo que la puerta guiada declara además —el esquema de tus columnas,
los 12 meses que infirió y su semilla—. Dónde quedan tus dos tablas no cambia la identidad: el
`config_hash` mira su contenido, por su huella, no su ubicación.

## Lo que entrega

- **El informe** (HTML; Word, PDF y fuente editable si los pides): abre con la página «Resumen de
  la corrida» —ejecución, supuestos, las cinco cifras, qué revisar, decisiones y archivos— y su
  capítulo de provisiones publica la curva de PD por período y cartera, los coeficientes del
  ajuste y la ECL por cartera y etapa. Con escenarios, «Escenarios y ajuste por ciclo» dice la
  sensibilidad estimada, el ancla, tus escenarios con sus pesos y la huella de las dos tablas, la
  ECL de cada escenario frente a la de la curva a lo largo del ciclo y el desplazamiento de cada
  tramo; con las dos PD de tu modelo, «La PD de tu modelo y el aumento significativo del riesgo»
  dice tu PD frente a la de la curva y cuántas operaciones movió la comparación por tramo.
- **El Excel**, si lo pides con `ecl.export_excel()` (extra `excel`): un libro por etapa
  —`01 Cartera`, `02 Curva de PD`, `03 Escenarios` si los hay, `04 Provisión IFRS 9`— y
  `05 Decisiones`.
- **La evidencia**: el config, la copia de tus datos con su huella, el registro de auditoría y la
  ficha, en `bayesrisk-runs/<nombre>/`; `ecl.export()` la empaqueta.

## Lo que la cifra supone

El resumen final dice los supuestos de cada corrida. Estos son los que más mueven la cifra en una
cartera real, medidos al correr esta misma provisión sobre dos carteras públicas además de la del
paquete —créditos de consumo de Lending Club (2013–2016) e hipotecas de Freddie Mac (2016)—:

| Supuesto | Qué significa | Cuánto movió la ECL al cambiarlo |
|---|---|---|
| PD a lo largo del ciclo (TTC), escenario único | la curva resume la historia, sin condiciones actuales ni escenarios macroeconómicos | — (IFRS 9 5.5.17 pide considerarlos) |
| Stage 3 con su pérdida, LGD × EAD | una operación ya incumplida se provisiona con lo que se pierde, PD = 1 (el default); con la PD de la curva —la opción «Stage 3 como EAD·LGD directo» apagada, en «Avanzado»— se provisionaría como una sana | +40 % en la cartera del paquete y +98 % en las hipotecas frente a la PD de la curva |
| La curva parte de la originación | no se lee desde la antigüedad de cada operación | +14 % en consumo de tres años; −27 % en hipotecas de diez años |
| La vida es la de la curva | no se corta en el vencimiento de cada operación | −16 % en consumo (vence antes que la curva); +6 % en hipotecas (la vida se alarga) |
| Las dos juntas | la curva leída desde la edad de cada operación hasta su vencimiento | +2 % en consumo; −21 % en hipotecas |
| Exposición constante | la EAD no amortiza a lo largo de la vida | −25 % en consumo de cuota fija y −6 % en hipotecas, sobre la vida contractual |
| El aumento significativo del riesgo, sólo por mora y marca | sin la PD de origen (`origination_pd=`) no hay comparación con lo esperado al otorgar | con la PD de hoy y la de origen, 256 de las 9.308 operaciones en Stage 1 de Lending Club (2,8 %) pasan a Stage 2 y ninguna en hipotecas; la PD de hoy (`pd=`) mueve la ECL +11,2 % en consumo y −12,3 % en hipotecas |

Las cifras de consumo y de hipotecas leen la curva desde la edad de cada operación con riesgo
constante dentro de cada período y, más allá del último período con incumplimientos observados,
con la media de los tres últimos: en las hipotecas, el último año de la curva no tiene ninguno.
Stage 3 con su pérdida ya es el default de las tres puertas. La antigüedad, el vencimiento y la
cuota de cada operación se declaran con tres columnas opcionales del archivo de cartera (arriba);
medido con el motor, con las tres la ECL de consumo baja un 13,8 % y la de hipotecas un 13,1 %. Lo
demás se cambia en el config (la puerta completa) y queda con su `config_hash`, o está declarado
como límite conocido en el [changelog](../changelog.md).
