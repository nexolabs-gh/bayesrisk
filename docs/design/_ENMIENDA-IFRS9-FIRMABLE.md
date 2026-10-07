# Enmienda SDD — IFRS 9 firmable: escenarios, la PD de tu modelo y el aumento significativo del riesgo

> **Estado: PROPUESTA** (S36, 2026-10-07). Diseño sin código: nada se programa hasta el OK de Cami
> a §8. Es el primer eslabón de la cadena del banco que Cami puso primero el 2026-10-07 («lo que un
> banco necesita de punta a punta»; después, H5 y H4; H2b al final).
>
> **Base medida:** `main` = `0e5e46f` (bayesrisk 2.7.0). Las cifras de la 2.7.0 se **reprodujeron
> al peso** con el script de S35 sobre las tres carteras (paquete 4.786.739; Lending Club 3.254.890 /
> 3.315.758 / 2.805.408; Freddie Mac 3.028.897 / 2.706.204 / 2.632.095). Las cifras «después» se
> midieron **fuera del motor** con las reglas exactas que propone esta enmienda, sobre la corrida de
> la 2.7.0 con las dos fechas y la cuota del contrato: la lectura de la curva por tramo se
> re-implementó y, con desplazamiento cero, reproduce la PD de cada tramo (error máximo 4·10⁻¹⁶) y la
> ECL del motor (error 0). Scripts y salidas, sólo agregados, en el repo privado
> `evidencia/s36/` (`ciclo_y_escenarios.py`, `pd_sicr_lgd.py`, `pd_scorecard_paquete.py`,
> `forward_sobre_la_curva.py`, `vasicek_marginal_vs_riesgo.py`, `satelite_sistema_rezagos.py`,
> `calendario.py` y `salidas/`). Datos externos fuera de los repos (`E:\Proyectos\datos-externos\`).
> Los párrafos de IFRS 9 se cotejaron contra el texto oficial adoptado por la UE —Reglamento (UE)
> 2023/1803, consolidado al 2026-03-08, idéntico en estos párrafos al 2016/2067— en español y en
> inglés; el texto del IASB en ifrs.org exige sesión y **no se cotejó**.
>
> **Enmienda a:** SDD-20 (`forward`: el satélite y la referencia del desplazamiento), SDD-16
> (`provisioning_ifrs9`: la vía PIT, la PD de entrada, el SICR), D-ECL-5 de
> [`_ENMIENDA-FLUJO-GUIADO-IFRS9.md`](_ENMIENDA-FLUJO-GUIADO-IFRS9.md) (la provisión deja de ser sólo
> TTC cuando hay escenarios), D-CRE-4 y §3.2-7 de
> [`_ENMIENDA-CASO-REAL-IFRS9.md`](_ENMIENDA-CASO-REAL-IFRS9.md) (la PD de origen y lo PIT con las
> fechas del contrato), [`31-simplicidad-y-flujo-guiado.md`](31-simplicidad-y-flujo-guiado.md) (la
> excepción al tope de esenciales, §8-5) y `docs_site/` (la guía de la provisión).
>
> **No toca:** la curva de supervivencia (su ajuste, coeficientes y cifras), la lectura por contrato
> sin escenarios, Stage 3 (PD = 1), la tabla de pagos, el descuento, el staging por mora y marca y
> sus presunciones, el scorecard, CMF, Markov, stress, el arnés H9R ni ninguna decisión de las
> familias D-SC/D-VAL/D-GOB. **No autoriza** bump, tag, PyPI ni recaptura.

| Campo | Valor |
|---|---|
| **Enmienda** | IFRS9-FIRMABLE (D-FIR-1…D-FIR-11) |
| **Módulos** | `forward` (`config.py`, `satellite.py`, `scenarios.py`, `step.py`, `results.py`); `provisioning/ifrs9` (`config.py`, `engine.py`, `contract.py`, `pd_pit.py`, `staging.py`, `ecl.py`, `results.py`); `guided/ecl.py` y `guided/summaries.py`; `ui/jobs.py` + `web/` (capa C); `report` (capítulo IFRS 9); `docs_site/` |
| **Fase** | F4 / F5 |
| **Depende de** | FLUJO-GUIADO-IFRS9 (D-ECL-0…15) y CASO-REAL-IFRS9 (D-CRE-1…8), implementadas y publicadas en 2.4.0–2.7.0; SDD-31; D-HOR; D-EST-5 |
| **Lo consumen** | La guía «La provisión IFRS 9 de punta a punta», el trabajo `provisiones_ifrs9` de la pantalla, el informe; H5 (escala maestra: la PD de 12 meses anclada), H4 (monitoreo), H2b (comparar provisiones por escenario) |
| **Release** | Capa A en un minor (2.8.0), B en el siguiente (2.9.0), C en el siguiente (2.10.0) — §3.11, §8-7 |

## Recomendación ejecutiva

Hoy la provisión es **a lo largo del ciclo y de un solo escenario**, y lo declara. Eso no se puede
firmar: IFRS 9 5.5.17 pide un importe ponderado por la probabilidad de varios escenarios y que use
las condiciones actuales y las previsiones; y 5.5.9 pide comparar el riesgo de hoy con el del
otorgamiento, que hoy sólo se aproxima por la mora (5.5.11 lo admite como presunción, «a más
tardar»). Lo que el motor ya trae para eso **no sirve medido**: `forward` ajusta su modelo satélite
contra la **forma de la curva por edad**, no contra el ciclo (en el paquete: coeficiente del
desempleo **negativo**, R² 0,002, sobre 30.000 «observaciones» que son 6.000 operaciones repetidas
cinco veces), deja el escenario base igual a la curva TTC, y con escenarios adversos **baja** la
provisión un 1,6 %; Vasicek transforma la PD marginal en vez del riesgo del período y, con un
factor adverso, deja 126 operaciones del paquete con PD de vida mayor que 1. Nadie los alcanza
desde las puertas, por suerte.

Se propone, en tres capas:

1. **Escenarios ponderados con un ajuste por ciclo** (D-FIR-1…6, capa A). La institución entrega
   dos tablas —la historia de una tasa de incumplimiento de referencia larga con sus variables
   macro, y sus escenarios con pesos— y el motor: estima cuánto se mueve esa tasa con la macro
   (`logit(tasa) = a + b·x`), desplaza en logit el riesgo de cada tramo posterior al corte según la
   **fecha de calendario** del tramo (la edad sigue decidiendo la forma de la curva: así se combina
   con la lectura por contrato), calcula la ECL de cada escenario y la pondera. Medido con los
   escenarios oficiales de la Reserva Federal publicados al corte y pesos ilustrativos: **Lending
   Club −0,6 %** (2019: desempleo de 3,6 %, bajo el de la historia de la curva) y **Freddie Mac
   +17,3 %** (2026, con un severo de 10 % de desempleo); por escenario, de −9,4 % a +25,8 % en
   consumo y de 0 % a +57,7 % en hipotecas.
2. **La PD de tu modelo y el aumento significativo del riesgo** (D-FIR-7…9, capa B). Dos columnas
   opcionales —la PD a 12 meses de hoy y la del otorgamiento— anclan la curva de cada operación a la
   PD de tu scorecard y comparan, para el mismo tramo de vida, el riesgo de hoy con el que se
   esperaba al otorgar. Medido: la PD del scorecard del paquete sube la ECL **+18,5 %** (y destapa
   que su incumplimiento no es el de la curva: lo dice «Qué revisar»); con la PD de hoy, Lending
   Club **+11,2 %** y Freddie Mac **−12,3 %**; el SICR relativo pasa **269 de 9.308** operaciones de
   Lending Club a Stage 2 (+12,1 % con la PD de hoy) y ninguna de Freddie Mac. La LGD sigue siendo
   una columna: una LGD modelada sobre 206.216 castigos de Lending Club mueve la ECL −0,03 %.
3. **Pantalla, informe y Excel** (capa C), con la curva consumida en Resultados.

Presupuesto: **tres hojas nuevas** y cuatro opciones nuevas en literales existentes; dos argumentos
nuevos de `Ecl` en la capa A y dos en la B. Sin escenarios ni columnas nuevas, todo queda **bit a
bit** como en la 2.7.0. Cami decide seis cosas (§8): la fuente de la sensibilidad, el ancla, el
SICR, los esenciales, los datos del ejemplo y las releases.

## 0. Qué corrige de lo ya escrito

1. **SDD-20 §3, «Δx respecto de una ruta base o una media histórica configurada».** Sólo existe la
   ruta base: el desplazamiento se mide contra el escenario de referencia (`satellite.py`
   `_macro_deltas`), así que el escenario base reproduce la curva TTC tal cual (medido: diferencia
   máxima 5,6·10⁻¹⁷) y las condiciones actuales no entran nunca. La media histórica se calcula
   (`reference_macro_`) y sólo centra el ajuste.
2. **SDD-20 §3, «Satellite model Wilson/CreditPortfolioView: `logit(h_{i,k,t})` como función de
   factores macro».** Sobre una curva de `survival`, el satélite regresiona el `logit(hazard)` de la
   curva por **edad** contra la macro alineada por el mismo entero `period`
   (`satellite.py:453-475`): la fila 1 de la serie macro con la edad 1, la 2 con la 2… Una serie
   fechada no casa (medido: `MacroProjectionError`). Ese ajuste no estima la sensibilidad al ciclo.
3. **SDD-16 §3, Vasicek sobre «la PD marginal (o el hazard)».** El motor lo aplica sobre la
   `pd_marginal` —una probabilidad incondicional— sin recomponer la supervivencia
   (`engine.py:1136-1153`); la transformación de Vasicek está definida para la probabilidad
   condicional del período.
4. **«Por código ya existen forward, markov, stress y Vasicek»** (prompt de S36). Existen, pero
   ninguno da una provisión firmable sobre la curva de la cartera: §1.1 y §1.2.
5. **El texto de ayuda de `pd.base_pd_source` en la pantalla** (`ui/jobs.py:2753-2756`) dice que la
   PD a 12 meses «decide en qué etapa queda cada operación». La PD calibrada sólo reemplaza la
   columna `pd_12m` del detalle: no mueve la ECL y sólo toca la etapa por el *backstop* PIT con una
   columna de nombre fijo. Se corrige el texto (§3.7).
6. **El «+2,2 %» de la PD del scorecard (D-ECL-3)** no tiene script ni test que lo reproduzca; era
   la PD como covariable de la curva. La regla que se propone es otra (§3.7) y se midió aquí.
7. **D-CRE-4 prometió** que la ayuda de `origination_pd_life_col` diría que, con las fechas, la PD
   actual es la de la vida remanente; el campo no tiene `ui_help`. Lo absorbe §3.8.

## 1. El estado, medido sobre `0e5e46f`

### 1.1 Qué hace hoy `forward` sobre la curva de supervivencia

Medido con el preset F4 sobre el paquete y la sección `forward` encendida en su forma mínima
(`forward_sobre_la_curva.py`): serie de desempleo, satélite ajustado, escenarios base/adverso/severo
con choques de +1,5 y +3,0 puntos, `pit_mode = consume_pit`.

| Lo que pasa | Medido | Por qué |
|---|---|---|
| Con la serie macro fechada (trimestres) | la corrida se detiene: «Tipo temporal macro no soportado» | el satélite alinea por el `period` de la curva, que es la edad |
| Con la serie numerada 1…24 (lo único que casa) | corre | — |
| Coeficiente del desempleo | **−0,057** (más desempleo, menos riesgo), R² 0,002 | regresiona la forma de la curva por edad contra los cinco primeros valores de la serie |
| Observaciones del ajuste | 30.000 | 6.000 operaciones × 5 períodos: la misma macro repetida por operación |
| Escenario base frente a la curva TTC | idéntico (5,6·10⁻¹⁷) | el desplazamiento se mide contra el escenario de referencia |
| ECL ponderada (60/30/10) frente a F4 | **4.708.176 (−1,6 %)** | el signo equivocado: los escenarios adversos bajan la provisión |

Además (lectura del código, `forward/macro.py:177-232`): sin ARIMAX, la proyección de los tres
escenarios es la misma serie con un choque constante; una trayectoria institucional por escenario
(`macro_path_path`) sólo la acepta ARIMAX como exógena. El default `term_structure_sources =
("survival", "markov")` no puede alimentar IFRS 9 (Markov publica `row_id = "state:X"`). Ningún
trabajo de la pantalla incluye `forward`, el informe no tiene capítulo y `Ecl` no tiene argumentos de
escenarios. No hay un solo test de punta a punta `forward → provisioning_ifrs9`.

### 1.2 Qué hace hoy Vasicek

`pit_mode = apply_vasicek` exige `rho` escalar y una columna `Z` por fila de la curva; nada en el
paquete la produce (hay un test canario que lo vigila), así que es **inalcanzable** desde las tres
puertas. Si se alcanzara (`vasicek_marginal_vs_riesgo.py`, curva de F4):

| ρ, Z | Sobre la PD marginal (hoy) | Sobre el riesgo del período | PD de vida > 1 con la marginal |
|---|---|---|---|
| 0,10, Z = −1 (adverso) | +30,8 % | +27,4 % | **126 operaciones** (la corrida se detendría en `marginal_to_horizon`) |
| 0,10, Z = 0 | −7,7 % | −7,1 % | 0 |
| 0,15, Z = −1 | +36,8 % | +32,5 % | 179 |

Z = 0 no es «neutral»: la PD TTC es el promedio de la PD condicional sobre Z, no su valor en Z = 0
(el propio `pd_pit.py` lo documenta). Y ρ no tiene fuente: las correlaciones de Basilea (hipotecas
0,15; revolventes 0,04; otro minorista entre 0,03 y 0,16 según la PD, CRE31.14–16) se calibraron
para capital, con efectos de plazo implícitos (nota explicativa del BCBS, 2005, pág. 15).

### 1.3 El ciclo dentro de la historia de las carteras

Con la fecha de otorgamiento, cada período de vida de la historia cae en un trimestre o año de
calendario. Por período de calendario se contaron los incumplimientos observados `O_c` y los que
espera la curva TTC (`E_c`, la suma del riesgo de cada operación a su edad), y se resolvió `δ_c`: el
desplazamiento en logit que el calendario agrega a la curva (`ciclo_y_escenarios.py`).

- **Lending Club (originaciones 2013–2016, corte 2019-03): no hay un ciclo adentro.** El desempleo
  bajó de 7,7 % a 3,6 % mientras la cartera maduraba; `δ_c` va de −0,57 (2013T4) a +0,18 (2016T4)
  y la regresión de `δ_c` sobre el desempleo da **b = −0,133** (error 0,061; R² 0,17; 25
  trimestres): con esa sensibilidad, el escenario adverso **baja** la ECL un 7,1 % y el severo un
  25,2 %. Es el problema de identificación edad-período-cohorte: en cuatro años de originaciones la
  maduración y el calendario se confunden.
- **Freddie Mac (originaciones 2016, corte 2026-03): no se puede identificar.** Una sola cohorte:
  la edad y el año de calendario son la misma variable, y la curva por edad ya absorbe el calendario
  (`|δ_c| ≤ 0,02` todos los años; 2020 —el pico de la curva en el año 4— da 916 observados frente a
  920 esperados). Ese pico es además la tolerancia por COVID: de los 1.453 incumplimientos fechados
  en 2020 (convención del mes del evento, `calendario.py`), 1.339 estaban en *forbearance*.
- **El paquete no tiene calendario**: su `duration` no cuenta desde el otorgamiento (CASO-REAL
  §1.4) y no trae fechas.

**Conclusión medida:** la sensibilidad al ciclo **no puede salir de la historia corta de la propia
cartera** en dos de las tres carteras (y en la tercera no hay con qué). Tiene que salir de una serie
larga que cruce al menos un ciclo.

### 1.4 Una serie larga y pública: la tasa del sistema

Logit de la tasa del sistema bancario de EE.UU. (Reserva Federal vía FRED) sobre el desempleo (BLS
vía FRED, `UNRATE`), mínimos cuadrados (`satelite_sistema_rezagos.py`):

| Serie de referencia | Ventana | b por punto de desempleo | R² | n |
|---|---|---|---|---|
| Morosidad de consumo (`DRCLACBS`) | 1987T1–2018T4 | 0,047 (error 0,012) | 0,10 | 128 trimestres |
| Castigos de consumo (`CORCACBS`) | 1985T1–2018T4 | 0,090 (0,020) | 0,13 | 136 |
| Morosidad hipotecaria (`DRSFRMACBS`) | 1991T1–2025T4 | 0,243 (0,023) | 0,46 | 140 |

**Rezagos:** con el desempleo rezagado 2, 4, 6 u 8 trimestres el ajuste empeora en las tres series
y, en las de consumo, el signo se invierte desde el rezago 4; el contemporáneo es el mejor en todas.
En consumo la relación es débil (R² 0,10–0,13): el motor tiene que decirlo (§3.2).

### 1.5 Datos macro públicos y reproducibles

Doble verificación trazada contra las fuentes oficiales el 2026-10-07 (detalle en
`evidencia/s36/fuentes/` y en el informe del agente de fuentes, anexado al HANDOFF):

| Fuente | Qué trae | Sin login | Licencia | Notebook | Empaquetar un extracto |
|---|---|---|---|---|---|
| BLS (`api.bls.gov/publicAPI/v1`), BEA (`NipaDataQ.txt`), FHFA (`hpi_at_us_and_census.csv`) | desempleo, PIB real, precios de vivienda de EE.UU. | sí (probado; v1 de BLS sin clave, 25 consultas al día) | dominio público, con cita | sí | sí, con cita |
| Reserva Federal: escenarios supervisores (CSV *Domestic*) y tasas de castigo y morosidad del sistema | trayectorias trimestrales de 13 trimestres (desempleo, PIB, vivienda…): 2019 base/adverso/severo, 2026 base/severo; morosidad y castigos por cartera | sí (probado; 2019 dentro de un ZIP) | dominio público salvo las variables de terceros (BBB, Dow Jones, VIX: excluir) | sí | sí, desempleo y PIB, con cita |
| FRED (`fredgraph.csv?id=…`) | las mismas series, reunidas | sí (probado) | licencia base personal y no comercial; excluye el uso «in connection with the development … of any software program»; cada serie con su rótulo | sólo como comodidad del usuario | **no**: se empaqueta desde la fuente primaria |
| BIS (`stats.bis.org/api`) | precios reales de vivienda y brecha crédito/PIB, también de Chile | sí (probado) | uso libre con cita, sin sugerir respaldo | sí | sí, con cita |
| CMF: cartera vencida e indicadores de provisiones del sistema por cartera (Excel mensual) | consumo, vivienda, comercial, **desde 2009** | sí (probado; las URL no siguen patrón); la API exige clave | CC BY 4.0 (reuso comercial con cita) | sí | sí, con cita |
| Banco Central de Chile, BDE | IMACEC, PIB, desocupación (replica INE), TPM, IPC, UF, vivienda, encuesta de expectativas; mora 90+ del sistema por cartera (`F022.IM1…4`, desde 2015) | la API exige cuenta y token; los cuadros se bajan sin login (no es una API documentada) | permite reproducir citando la fuente, pero el Banco puede revocarlo y sus condiciones generales prohíben distribuir sin autorización | frágil | **no** sin autorización escrita |
| INE, desocupación | trimestre móvil desde 2010 (`indicadores_principales.xlsx`) | sí (probado) | CC BY-SA 4.0 | sí | sí, como archivo aparte bajo CC BY-SA |
| FMI, WEO | proyecciones anuales por país, versionadas por edición | sí (probado) | atribución; el reuso comercial pide permiso | sí, con pocas llamadas | dudoso |
| IPoM e IEF del BCCh | rangos anuales de PIB e inflación (el IPoM no proyecta desempleo en tablas); escenarios de tensión | bloqueado (anti-bot) | — | **no verificado** | — |

Las cifras de §1.4 se midieron con FRED (sólo en la evidencia privada); la guía y cualquier extracto
usan la fuente primaria. Para una cartera chilena, la serie larga de referencia es la de la CMF por
cartera desde 2009 (una crisis leve, el ciclo de 2015–2016 y la pandemia); ojo: la «cartera vencida»
de la CMF (sólo las cuotas impagas) no es la «mora 90+» del BCCh (el crédito completo) y no se
mezclan en un mismo satélite. Nota de alcance: para la cartera de colocaciones de un banco, la CMF no aplica el
capítulo 5.5 de NIIF 9 (Compendio de Normas Contables, A-2 N° 5; rige B-1 a B-3, que además exige
metodologías a través del ciclo): esta enmienda sirve a quien sí lo aplica —una cooperativa, una
financiera, una filial que consolida en IFRS, otra jurisdicción—; la norma local sigue fuera del
alcance del paquete.

### 1.6 Lo que dice la norma

Cotejado contra el texto oficial (Reglamento (UE) 2023/1803 consolidado, ES y EN):

- **5.5.17** pide un importe «ponderado en función de la probabilidad y no sesgado», el valor
  temporal del dinero, e información sobre «sucesos pasados, condiciones actuales y previsiones de
  condiciones económicas futuras». **5.5.18**: no hace falta enumerar todos los escenarios.
- **B5.5.42**: puede bastar un modelo simple; si se especifican escenarios, al menos dos resultados
  (que haya pérdida y que no). **El número de escenarios y sus pesos no los fija ninguna fuente**
  (EBA 2021: «prescribes neither the range of economic scenarios … nor the probability weights»).
  Un solo escenario no basta si la pérdida no es lineal en la macro (ITG del IASB, 11-12-2015, §49;
  ejemplo §50–51: 30/70/170 con 20/50/30 dan 92 frente a 70 del central).
- **B5.5.50**: no hace falta pronosticar toda la vida; para períodos lejanos se puede extrapolar.
  **B5.5.52**: la información histórica es el ancla, ajustada a las condiciones actuales. La
  reversión gradual al largo plazo es lectura supervisora (ECB, carta del 01-04-2020; EBA 2021
  §115–116: lo habitual son tres años de pronóstico y luego reversión, sin armonizar), y el ECB
  (04-12-2020) advierte que no basta lo TTC.
- **5.5.9**: el SICR compara el riesgo de incumplimiento a lo largo de la vida esperada con el del
  reconocimiento inicial. **B5.5.13**: el cambio de la PD a 12 meses puede aproximarlo si los
  incumplimientos no se concentran en un momento de la vida; **B5.5.14** lista excepciones, entre
  ellas factores macro que la PD a 12 meses no recoge. **5.5.11 y B5.5.19–20**: la mora de 30 días
  es el punto más tardío, no un indicador suficiente si hay información prospectiva.
- **Pesos en la práctica** (EBA 2021, hogares, dic-2019): 19/59/23 alza/base/baja.

### 1.7 La PD del scorecard y la LGD hoy

- La PD calibrada entra por `base_pd_source = "calibration"`: **sólo reemplaza** la columna
  `pd_12m` del detalle (`engine.py:370-375`); la ECL sigue con la curva. Con las fechas del contrato
  se rechaza (CASO-REAL §3.2-7). Por la otra vía, la PD como covariable de la curva (D-ECL-3), la
  curva se ajusta sólo sobre Desarrollo y exige el score de las operaciones de la historia.
- La LGD de la provisión puede modelarse dentro de la corrida (beta, fraccional, *workout*), pero
  **se ajusta sobre la cartera viva** (las filas con EAD > 0): justo las que no tienen LGD
  realizada. En `Ecl`, la LGD es una columna; «Supuestos» sólo describe ese caso.
- `Ecl` no acepta ni PD del modelo, ni PD de origen, ni escenarios.

### 1.8 Lo que se midió con las reglas de esta enmienda

Escenarios: los de la Reserva Federal **publicados al corte** de cada cartera (2019 para Lending
Club, 2026 para Freddie Mac), desempleo trimestral. Pesos **ilustrativos** —no los publica nadie y
son decisión de la institución—: 60/30/10 base/adverso/severo en Lending Club y 70/30 base/severo en
Freddie Mac. Satélite del sistema de §1.4 (castigos de consumo en Lending Club; morosidad
hipotecaria anual 1991–2025 en Freddie Mac, b = 0,273). Ancla y reversión de §3.3.

| | Lending Club (2.805.408) | Freddie Mac (2.632.095) |
|---|---|---|
| Desempleo en la ventana de la historia de la curva | 4,77 % | 4,67 % |
| Desempleo medio de largo plazo (serie de referencia) | 5,96 % | 5,68 % |
| Base | 2.542.445 (**−9,4 %**) | 2.633.288 (0,0 %) |
| Adverso | 3.038.230 (+8,3 %) | — |
| Severo | 3.529.353 (**+25,8 %**) | 4.150.079 (**+57,7 %**) |
| **Ponderada** | **2.789.871 (−0,6 %)** | **3.088.325 (+17,3 %)** |
| Ponderada, con la curva tomada como de largo plazo (§3.3, alternativa) | 2.525.071 (−10,0 %) | 2.760.068 (+4,9 %) |
| Ponderada, con la morosidad de consumo en vez de los castigos | 2.792.451 (−0,5 %) | — |
| Ponderada, con la sensibilidad de la propia historia (§1.3) | 2.895.402 (+3,2 %; el severo **−28,2 %**) | 2.632.540 (0,0 %) |
| Un desplazamiento uniforme de +0,25 en logit | +25,8 % | +9,9 % |

En Lending Club, Stage 1 pesa casi toda la ECL y su ventana de 12 meses cae entera dentro del
escenario: la reversión no mueve nada. En Freddie Mac, la reversión lineal en dos años mueve +0,3
puntos, y revertir hacia el largo plazo en vez de hacia la ventana de la curva, +1,4 puntos más.

## 2. Lo que ya está construido y no hay que inventar

Conectar, no reimplementar (RUNBOOK §12.1-3): la validación de escenarios, sus pesos y la guarda
contra el «escenario medio» (`forward/config.py`, `provisioning_ifrs9/ecl.py`); la carga de la serie
macro (`forward/step.py`, por ruta o artefacto); los coeficientes fijos con signo documentado
(`satellite.mode = "fixed_coefficients"`); la mezcla en logit con la curva TTC
(`forward/scenarios.py`); la lectura de la curva por tramo desde la edad, que **ya arma una curva por
`(operación, escenario)`** (`contract.py:542-583`); la ponderación de la ECL por escenario
(`ecl.py:280-293`); el umbral de razón del SICR (`staging.sicr_pd_ratio_threshold`, 2,0); la tabla
de cuotas; `bayesrisk.apply` para puntuar la cartera con el bundle de un scorecard. Lo nuevo es el
satélite contra una tasa de referencia, el desplazamiento por tramo de calendario, el ancla, el
anclaje a la PD del modelo y la comparación del SICR por tramo: piezas de `forward` y del motor de
provisiones, no un segundo motor.

## 3. Las decisiones que se proponen

### 3.1 D-FIR-1 — Escenarios ponderados: un desplazamiento en logit por escenario y por tramo de calendario

**Contrato.** Cuando la corrida trae escenarios (§3.4), la PD de cada tramo posterior al corte se
calcula con el riesgo de la curva desplazado en logit:

`logit h_k(i, t) = logit h_TTC(i, edad del tramo) + δ_k(t)`, con `δ_k(t) = Σ_j b_j · (x_{k,j}(t) − x̄_j)`

—`b_j` la sensibilidad de §3.2, `x̄_j` el ancla de §3.3— y la ECL es `Σ_k w_k · ECL_k`, una por escenario (nunca la de un escenario «medio»: la pérdida no es
lineal en la macro, ITG §49).

**Qué factor corresponde a cada tramo** (el abierto de S35). El tramo `t` posterior al corte cubre
la ventana de calendario `(corte + (t−1)·u, corte + t·u]` —`u` los meses de un período de la
curva— y el tramo de vida `[A + t − 1, A + min(t, L)]` de CASO-REAL §3.2. **La edad decide el
riesgo base** (la forma de la curva, la cola, el vencimiento); **el calendario decide el
desplazamiento**: `x_k(t)` es el promedio de los valores del escenario cuyas fechas caen en esa
ventana, o el del período del escenario que la contiene si el escenario es más grueso que la curva.
Sin fechas del contrato, `A = 0` y la regla es la misma. Dentro del tramo, el riesgo desplazado se
aplica a los dos períodos de la curva que el tramo cruza (riesgo constante dentro del período, como
hoy). Así la lectura por contrato admite escenarios: el requisito de S35 (`ttc_only` con fechas) se
levanta **para esta vía** y se mantiene para Vasicek y para las curvas de `forward` por edad.

**Qué se desplaza y qué no.** Stage 1 y Stage 2 (y Stage 3 con `stage3_direct = False`); Stage 3
con PD = 1 no cambia. La **etapa no la decide el escenario**: la razón del SICR (§3.8) compara PD
sin el desplazamiento macro, que entra como ajuste del importe de la cartera y no de la operación
(IHN-001: la macro por cartera es un ajuste, no un sustituto de la PD individual); «Supuestos» lo
dice; vale para los dos gatillos por razón de PD (`origination_pd_life_col` y el de §3.8), que
hoy leen la PD ponderada por escenario. La LGD y la EAD son las mismas en todos los escenarios
(FALTA-DATO-IFRS-6 sigue declarando que la LGD de `forward` se descarta).

**Salidas (aditivas).** `ecl_term_structure` con una fila por escenario (como hoy con varias curvas)
y la columna `cycle_shift` (`δ_k(t)`); `detail.scenario_weights` con los pesos; la card de la
provisión gana `ecl_by_scenario` y `ecl_ttc` (la de `δ = 0`, para comparar); `("forward",
"cycle_model")` (§3.2) y `("provisioning_ifrs9", "cycle_by_period")`: escenario × tramo con
ventana de calendario, `x`, `δ` y el estado (`escenario`, `reversión`, `largo plazo`).

**Alternativas descartadas.** Promediar la macro y correr un escenario (prohibido: no linealidad).
Escalar la PD marginal (no preserva la supervivencia). Vasicek con ρ de Basilea (ρ no tiene fuente
contable; §1.2). Indexar el desplazamiento por la edad (lo de hoy: el tramo de una hipoteca de diez
años recibiría la macro del año 11 del escenario).

### 3.2 D-FIR-2 — La sensibilidad al ciclo sale de una tasa de referencia larga (§8-2)

**Contrato.** Un modo nuevo del satélite, `forward.satellite.mode = "reference_rate"`: el satélite
se ajusta sobre la **tabla de historia** que entrega la institución —una fecha, la tasa de
incumplimiento de referencia (hoja nueva `satellite.reference_rate_col`, default `"default_rate"`)
y las mismas variables macro de los escenarios— por mínimos cuadrados:
`logit(r_c) = a + Σ_j b_j · (x_{c,j} − x̄_j)`, con la macro **contemporánea** y en niveles. La tasa
de referencia la elige la institución: la del sistema por cartera (lo que se midió) o la propia, si
su historia cruza un ciclo. `x̄_j` es la media de la ventana de la tabla (el largo plazo).

**El motor dice lo que estimó** en el resumen de la etapa: `b_j` con su error, R², `n`, la ventana
y, en palabras, el sentido («con más desempleo, la tasa de referencia sube»). «Qué revisar» alerta
si la sensibilidad es incierta —`|b/se| < 2` o R² < 0,1 (constantes, con su razón)— o si la ventana
tiene menos de 20 períodos. La dirección económica la juzga quien firma: el motor no sabe qué
variable debe subir con el riesgo.

**Qué NO se configura:** el rezago (medido: el contemporáneo es el mejor en las tres series, y en
consumo los rezagos invierten el signo), la forma funcional (logit lineal), el estimador (MCO) y la
ventana (la tabla entera).

**Alternativas descartadas.** La historia de la propia cartera (§1.3: signo invertido en Lending
Club, no identificable en Freddie Mac; candidata con evidencia cuando una cartera con varias
cohortes y un ciclo dentro la sostenga). Selección de variables o de rezagos por el motor (búsqueda
múltiple con pocas observaciones: los p-valores tras la selección no significan lo que dicen). Un modelo binomial con
numerador y denominador (no hay denominador en una tasa publicada). La forma vieja de `fit` (§3.5).
Los coeficientes declarados por la institución siguen en la puerta completa
(`mode = "fixed_coefficients"`, con su signo documentado).

### 3.3 D-FIR-3 — El ancla: las condiciones que la curva lleva dentro (§8-3)

**Contrato.** La curva TTC no es «de largo plazo» por decreto: es el promedio de las condiciones de
la ventana de su historia. Con la fecha de otorgamiento (CASO-REAL D-CRE-2), el motor pone cada
período de vida de la historia de la curva en su período de calendario y calcula `x̄_W`, el promedio
de la macro de la tabla de historia ponderado por cuántos períodos-operación hubo en cada período de
calendario. Entonces:

- dentro del horizonte del escenario: `δ_k(t) = b · (x_k(t) − x̄_W)`;
- después: **reversión lineal en dos años** hacia `δ_LP = b · (x̄_LP − x̄_W)`, las condiciones de
  largo plazo de la tabla de historia (B5.5.50/52; ECB 2020; EBA 2021 §115–116).

**Sin fecha de otorgamiento** no hay calendario para la historia: la curva se toma como de largo
plazo (`x̄_W = x̄_LP`), la reversión va a `δ = 0` y «Qué revisar» lo dice («sin la fecha de
otorgamiento, la curva se supone estimada en condiciones de largo plazo»). Si la tabla de historia
no cubre la ventana de la curva, la corrida se detiene con los años que faltan (IHN-010: un ancla
material no se rellena con un neutro).

**Por qué importa** (§1.8): en Lending Club la curva se estimó con 4,77 % de desempleo, no con el
5,96 % de largo plazo; tomarla como de largo plazo resta 9,4 puntos a la ECL ponderada (−10,0 %
frente a −0,6 %). En Freddie Mac, 12,4 puntos (+4,9 % frente a +17,3 %).

**Qué NO se configura:** el ancla (la ventana de la curva si hay fechas; el largo plazo si no), el
largo de la reversión (dos años; medido: +0,3 puntos en Freddie Mac, nada en Lending Club) ni su
forma (lineal en logit, la de `forward/scenarios.py`).

### 3.4 D-FIR-4 — Los escenarios son de la institución

**Contrato.** Una **tabla de escenarios** con `scenario`, `weight`, `date` y las variables macro
(las mismas de la historia). Reglas: al menos **dos** escenarios (un rango, 5.5.17(a); un solo
escenario no basta si la pérdida no es lineal); pesos **mayores que cero que suman 1** (la provisión
ya rechaza el peso 0); nombres libres (no se exige base/adverse/severe:
`require_at_least_three = False` en esta vía); todos los escenarios con las mismas fechas; la
primera fecha a más tardar en el primer período posterior al corte, y la tabla cubre **al menos los
12 meses** posteriores al corte (la ventana de Stage 1; si no, la corrida se detiene antes de
correr). El horizonte del escenario es el de la tabla (B5.5.50: el de la institución).

**Sin modelo macro en esta vía.** Los escenarios **son** la previsión de la institución (B5.5.51):
`forward.macro.kind = "scenario_paths"` (opción nueva) toma las trayectorias tal cual; ARIMA, VAR y
los choques constantes siguen en la puerta completa para la vía anterior. Los pesos viven en el
config (`forward.scenarios.scenarios[*].weight`: entran al `config_hash`), y cada trayectoria en su
archivo (`macro_path_path`), con su huella en el lineage.

**Qué NO se configura:** ningún peso por defecto (D-OBL-5: el motor no siembra criterio
institucional; los 60/30/10 de `forward` siguen marcados «a confirmar» y esta vía no los usa), ni
el número de escenarios.

**El ejemplo de la guía** usa escenarios ilustrativos y lo dice; la guía enlaza las fuentes
oficiales de §1.5 y explica que los escenarios supervisores de estrés no son previsiones
ponderables por sí solos.

### 3.5 D-FIR-5 — `forward` deja de ajustar contra la edad

**Contrato.** `satellite.mode = "fit"` sobre una curva sin columna de calendario (la de
`survival` y la de `markov`) **se detiene antes de correr** con un mensaje que lleva a
`"reference_rate"`: hoy produce un coeficiente sin sentido sin avisar (§1.1). Es un cambio de una
superficie experimental, declarado en el CHANGELOG; una curva con columna de calendario
(`time_col`) sigue ajustando como hoy. La vía anterior de IFRS 9 (`pit_mode = "consume_pit"` con la
curva de `forward` por edad, sin lectura por contrato) no cambia y queda documentada como tal.

### 3.6 D-FIR-6 — Vasicek se aplica al riesgo del período

**Contrato.** `apply_vasicek` transforma el `hazard` de cada período y recompone supervivencia, PD
marginal y acumulada (como `forward` con el logit). Corrige la PD de vida mayor que 1 de §1.2. Sigue
exigiendo `rho` y `Z` por fila, sigue sin fechas del contrato (su `Z` es por fila de la curva, por
edad) y sigue en la puerta completa: con D-FIR-1 la vía guiada no lo necesita. **Cambia números**
sólo en corridas con `apply_vasicek` (inalcanzable desde las puertas sin una columna `Z` del
usuario).

### 3.7 D-FIR-7 — La PD de tu modelo ancla la curva (capa B)

**Contrato.** Hoja nueva `provisioning_ifrs9.pd.pd_12m_col` (default `None`): la **PD a 12 meses de
hoy** de cada operación, de tu scorecard o de tu modelo de rating (con `bayesrisk`, el bundle del
scorecard aplicado a la cartera con `bayesrisk.apply`). Con ella, para cada operación se resuelve un
desplazamiento `s_i` tal que la PD de los 12 meses posteriores al corte de **su** curva —desde su
edad, sin cortar por el vencimiento— sea esa PD, y todos sus tramos usan `logit h + s_i`: la curva
conserva su forma por edad y su nivel es el de tu modelo. La ECL de Stage 1 es entonces la de la PD
de tu modelo. Con escenarios, `δ_k(t)` se suma encima. Una operación sin PD usa la curva sin anclar
(contada en «Qué revisar»); una PD de 0 o 1 se acota a `[10⁻⁹, 1 − 10⁻⁹]` y se cuenta.

**Contrato del dato** (se dice en «Supuestos» y en la guía): la PD tiene que medir **el mismo
incumplimiento a 12 meses** que la curva y estar calibrada a lo largo del ciclo (si ya fuera PIT,
el escenario contaría el ciclo dos veces). El motor no puede verificarlo, pero **reconcilia**: el
resumen muestra la PD media ponderada por exposición de tu modelo y la de la curva, y «Qué revisar»
alerta si difieren en más de un 25 % relativo. Medido en el paquete: el scorecard que trae
(`bad_flag`) promedia 9,99 %; la curva, 6,31 %: el `bad_flag` sintético no es el `event` de la
curva (9,6 % frente a 6,2 % en el primer año, correlación 0,17) y la alerta saltaría.

**Cifras.** Paquete, con el scorecard del paquete aplicado a la cartera: **4.786.739 → 5.669.963
(+18,5 %)**, correlación de rangos 0,76 entre las dos PD. Lending Club con la PD de hoy (el FICO
actual, `last_fico_range_low`): **+11,2 %**; Freddie Mac (el LTV estimado actual, ELTV, cobertura
89 %): **−12,3 %**.

**Corrección de texto:** la ayuda de `base_pd_source` dice lo que hace (reemplaza la PD a 12 meses
del detalle y alimenta el *backstop* PIT; no la ECL). La opción no cambia.

**Alternativas descartadas.** La PD como covariable de la curva (D-ECL-3): exige el score de toda la
historia, acopla la corrida al scorecard (target y partición, D-ECL-2) y ajusta sólo sobre
Desarrollo; queda en la puerta completa. Reemplazar sólo la PD a 12 meses (lo de hoy): la ECL de
por vida quedaría con otro nivel que la de Stage 1. Un riesgo constante calibrado a la PD de 12
meses (pierde la forma de la curva).

### 3.8 D-FIR-8 — El aumento significativo del riesgo: lo que se esperaba al otorgar, para el mismo tramo (capa B; §8-4)

**Contrato.** Hoja nueva `provisioning_ifrs9.staging.origination_pd_12m_col` (default `None`): la
**PD a 12 meses al otorgar** (tu score de admisión). Exige `pd_12m_col` y la fecha de otorgamiento
(requisitos por contexto). Para cada operación en Stage 1:

- **lo que se esperaba al otorgar** para los próximos 12 meses de hoy: la curva anclada a la PD de
  origen **en la edad 0**, leída en el tramo `[A, A + 12 meses]`;
- **lo de hoy**: la curva anclada a la PD de hoy en la edad `A` (por construcción, la PD de hoy);
- si la razón es ≥ `sicr_pd_ratio_threshold` (2,0, la hoja que ya existe), pasa a Stage 2 con el
  gatillo nuevo `sicr_pd_origination_12m`.

Comparar el mismo tramo de vida es lo que pide 5.5.9 (B5.5.11: el riesgo esperado para esa vida); la
PD a 12 meses es el atajo de B5.5.13, que «Supuestos» declara (con la excepción de B5.5.14: el
desplazamiento macro no entra a la comparación, §3.1). La mora y la marca siguen como presunciones
(5.5.11, B5.5.19–20). La alerta «el aumento significativo del riesgo se detecta sólo por la mora y
la marca» deja de salir cuando hay PD de origen. **Resuelve D-CRE-4.** `origination_pd_life_col`
(la PD de por vida de origen frente a la actual) sigue en la puerta completa; su ayuda dice que, con
las fechas, la PD actual es la de la vida remanente y que esa comparación no es por tramo.

**Cifras** (Lending Club, reglas de la 2.7.0; las dos PD salen de la propia curva, con el FICO del
otorgamiento y con el actual, que es exactamente esta regla con las dos columnas llenas así):
**269 de 9.308** operaciones de Stage 1 pasan a Stage 2 (EAD 1.210.222); la ECL sube **+0,5 %**
sólo por la etapa y **+12,1 %** con la PD de hoy anclada; con umbral 3,0, 20 operaciones. Freddie
Mac: ninguna (las viviendas se valorizaron). S33 había medido 255 con las reglas anteriores.

**Alternativas descartadas.** Comparar la PD de 12 meses de origen con la de hoy sin el tramo (en
una hipoteca de diez años, la caída natural del riesgo con la edad escondería un deterioro).
Inferir la PD de origen evaluando la curva con las covariables del otorgamiento (S33: es una lectura
PIT por validar, y la PD de origen la tiene el banco). Incluir el escenario en la razón (pasaría
carteras enteras a Stage 2 por la macro: candidata si un caso real lo pide, B5.5.17(f)).

### 3.9 D-FIR-9 — La LGD es una columna; la LGD modelada dentro de la provisión se declara (capa B)

**Medido** (`pd_sicr_lgd.py`): una regresión fraccional sobre 206.216 castigos de Lending Club con
covariables crudas (FICO, DTI, tasa, plazo; nunca WoE, D-LGD-7) da para la cartera viva una LGD
ponderada de 0,8871 frente a 0,8860 de la media por plazo: la ECL se mueve **−0,03 %**. Freddie Mac
tiene 93 salidas con pérdida: no alcanza para un modelo. No hay evidencia de que una perilla nueva
cambie la cifra.

**Contrato.** La LGD entra como **columna** (la de tu modelo de LGD; con `bayesrisk`, la LGD
modelada del método interno, D-LGD). «Supuestos» dice el método de la LGD también cuando no es
`provided`, y con un método modelado dentro de la provisión, «Qué revisar» alerta que se ajustó
sobre la cartera viva, que no tiene LGD realizada. La LGD por escenario (FALTA-DATO-IFRS-6) sigue
declarada: candidata cuando una cartera hipotecaria con su índice de precios lo justifique.

### 3.10 D-FIR-10 — Los datos del ejemplo (§8-6)

El paquete no trae calendario (§1.3). **Propuesto:** como en S35, un bloque de la guía ejecutado en
CI que **genera en el propio bloque** una cartera sintética pequeña y determinista con fechas,
cuota, PD de hoy y de origen, y las dos tablas macro (historia de 20 años con un ciclo y tres
escenarios), con una sensibilidad conocida que el motor recupera (y un test lo verifica). Ningún
dato macro real entra al paquete. La guía enlaza las fuentes oficiales (§1.5) —para una cartera
chilena, la CMF por cartera y la desocupación del INE, las dos con licencia abierta— y publica,
como evidencia medida fuera de CI, las cifras de Lending Club y Freddie Mac con los escenarios de la
Reserva Federal. La alternativa (c) de §8-6 —un extracto real de la CMF (CC BY 4.0) y del INE (CC
BY-SA 4.0, en archivo aparte)— es viable; cuesta un archivo con licencia distinta dentro del
paquete y no trae una sensibilidad conocida para el test.

### 3.11 D-FIR-11 — Capas, releases, perillas y puertas

| Capa | Qué | Mueve | Gate de cierre |
|---|---|---|---|
| **A** | D-FIR-1…6: `forward` modo `reference_rate` y `scenario_paths`, `("forward", "cycle_model")`, `pit_mode = "cycle"`, el desplazamiento por tramo, el ancla, la reversión; `fit` contra la edad se detiene; Vasicek sobre el riesgo. `Ecl(..., scenarios=, history=)` **experimental** (D-SIM-1); resumen de la etapa «Escenarios»; «Supuestos» y «Qué revisar»; el bloque de la guía | sin escenarios, nada (bit a bit); el `config_hash` de toda corrida con `forward`, por la hoja nueva; **F4 no se mueve** (no trae `forward`); `HOJAS_DEL_FORMULARIO` y el ledger de opciones, medidos al implementar | las cifras de §1.8 **con el motor** (las de esta enmienda son el oráculo); la sensibilidad sintética recuperada; sin escenarios, bit a bit |
| **B** | D-FIR-7…9: las dos columnas de PD, el anclaje, el SICR por tramo, la reconciliación, la LGD en «Supuestos»; `Ecl(..., pd=, origination_pd=)`; esenciales de `provisioning_ifrs9` 10 → 12 | esenciales (golden y espejo), `HOJAS_DEL_FORMULARIO` (+2), textos de ayuda; **el `config_hash` de F4** por las dos claves nuevas vacías (como en S35): el gate de identidad de la demo obliga a recapturar con la 2.9.0 | las cifras de §3.7 y §3.8 con el motor; sin las columnas, bit a bit |
| **C** | la pantalla (`forward` en el trabajo `provisiones_ifrs9`, con sus esenciales y la carga de las dos tablas; las columnas de PD), el informe (sección «Escenarios y ajuste por ciclo»: satélite, ancla, escenarios con pesos, ECL por escenario), el Excel y Resultados (la ECL por escenario y el desplazamiento por tramo: la curva consumida, abierto desde S32); `Ecl` estable | cinco censos de la sección nueva del formulario; la demo IFRS 9 si se le agregan escenarios (recaptura con su OK) | las tres puertas con el mismo `config_hash` y resultados |

**Releases** (§8-7): A en la 2.8.0, B en la 2.9.0 (con recaptura de la demo: mueve el hash de F4),
C en la 2.10.0; cada una y cada recaptura con su OK aparte.

**Perillas: tres hojas nuevas**, cada una con su evidencia (D-SIM-3):

| Hoja | Default | Evidencia de que el default falla |
|---|---|---|
| `forward.satellite.reference_rate_col` | `"default_rate"` | sin una tasa de referencia larga, la sensibilidad sale de la historia corta: signo invertido en Lending Club, nula en Freddie Mac (§1.3) |
| `provisioning_ifrs9.pd.pd_12m_col` | `None` | sin ella la ECL no usa la PD del modelo del banco: paquete −15,6 % frente a la anclada (§3.7) |
| `provisioning_ifrs9.staging.origination_pd_12m_col` | `None` | sin ella el SICR es sólo la mora: 269 operaciones de Lending Club en Stage 1 con el riesgo duplicado (§3.8) |

**Opciones nuevas en literales existentes:** `satellite.mode = "reference_rate"`, `macro.kind =
"scenario_paths"` y `pd.pit_mode = "cycle"`; además, un gatillo nuevo en `sicr_triggers`
(`sicr_pd_origination_12m`). Mueven el ledger de opciones y el catálogo del abanico.

**Qué NO se configura:** el rezago, la forma y el estimador del satélite; el ancla y la reversión
(dos años, lineal en logit); el umbral de cobertura de 12 meses de la tabla de escenarios; la
regla del tramo de calendario; que la etapa no la decide el escenario; la cota de la PD anclada; el
umbral de la reconciliación (25 %) y los de «Qué revisar» del satélite. Constantes con su razón en
el código.

**Las puertas.** Guiada: `Ecl(..., scenarios=None, history=None)` en la capa A —dos tablas (un
`DataFrame` o una ruta) con columnas de nombre fijo, `date`, `default_rate`, `scenario`, `weight`, y
las variables macro, que son las columnas restantes y tienen que coincidir en las dos— y `Ecl(...,
pd=None, origination_pd=None)` en la B. Completa: el YAML con `forward` y las hojas nuevas. Pantalla:
capa C.

## 4. Contratos de datos (I/O)

- **Tabla de historia:** `date` (fechas legibles sin ambigüedad, una por período, regulares),
  `default_rate` (tasa en (0, 1) o en porcentaje (0, 100): se declara por la escala que traiga; una
  columna con valores > 1 se lee como porcentaje y se dice), y una o más variables macro numéricas
  finitas. Al menos 20 períodos para no alertar; al menos `variables + 2` para correr.
- **Tabla de escenarios:** `scenario`, `weight` (constante por escenario), `date` y las mismas
  variables; frecuencia igual o más gruesa que la de la historia.
- **Cartera:** lo de FLUJO-GUIADO-IFRS9 §4 y CASO-REAL §4 más, opcionales, `pd_12m` y
  `origination_pd_12m` en (0, 1) (capa B).
- **Salida:** las de §3.1, la etapa «Escenarios» del resumen, `detail` con `pd_12m_model` y el
  gatillo nuevo (capa B).
- **Invariantes.** Sin escenarios ni las columnas nuevas, la provisión es bit a bit la de la 2.7.0
  (sólo cambia el hash por las claves nuevas vacías). Con un solo escenario de peso 1 y `δ = 0` en
  todos los tramos, la ECL es la TTC (control). La suma de la ECL por operación es la total. La
  ECL ponderada está entre la mínima y la máxima de los escenarios. Sin desplazamiento ni anclaje,
  la PD de cada tramo es la de CASO-REAL.

## 5. Casos borde

Un escenario solo (se detiene: no es un rango); pesos que no suman 1 o un peso 0 (se detiene); un
escenario sin alguna fecha que otro tiene (se detiene); una tabla de escenarios que no cubre los 12
meses posteriores al corte (se detiene antes de correr); una variable de los escenarios que no está
en la historia o al revés (se detiene); una tasa de referencia en 0 o en 1 (logit no definido: se
detiene con la fila); una variable constante en la historia (se detiene, como hoy); menos de
`variables + 2` períodos (se detiene); sensibilidad incierta (alerta); la historia que no cubre la
ventana de la curva (se detiene con los años); sin fecha de otorgamiento (ancla de largo plazo,
alerta); un escenario más grueso que la curva (el valor del período que contiene el tramo); un
tramo que cae después del último escenario (reversión); `pit_mode = "cycle"` sin `forward` (requisito
por contexto); `forward` con `fit` sobre una curva sin calendario (se detiene, §3.5); una PD de
modelo fuera de (0, 1) (se acota y se cuenta) o vacía (curva sin anclar, contada); la PD de origen
sin la de hoy o sin fecha de otorgamiento (requisito por contexto); una operación vencida con saldo
(un período, como hoy; el anclaje usa la ventana de 12 meses sin cortar).

## 6. Gates y controles negativos de ESTA enmienda

Un control negativo por regla, en paralelo, cada uno en su copia del árbol (RUNBOOK §6):

1. **D-FIR-1, el tramo de calendario:** un caso a mano —curva de tres períodos, edad 1,5, dos
   escenarios con desplazamientos distintos por trimestre— con la PD de cada tramo calculada en el
   test. CN: indexar el desplazamiento por la edad → rojo.
2. **D-FIR-1, no linealidad:** la ECL ponderada ≠ la de la macro promediada (guarda). CN: promediar
   la macro → rojo.
3. **D-FIR-2:** el bloque sintético recupera la sensibilidad conocida dentro de su error. CN: ajustar
   contra la curva por edad → rojo.
4. **D-FIR-3:** con fechas, el ancla es la ventana de la curva; sin fechas, el largo plazo, y lo
   dice. CN: anclar siempre en el largo plazo → rojo con la cifra del caso sintético.
5. **D-FIR-4:** un escenario, peso 0, tabla corta: se detienen antes de correr. CN: aceptar un
   escenario → rojo.
6. **D-FIR-5:** `fit` sobre `survival` se detiene. CN: dejarlo correr → rojo.
7. **D-FIR-6:** Vasicek con Z adverso no deja PD de vida > 1 y casa con la fórmula sobre el riesgo.
   CN: volver a la marginal → rojo.
8. **D-FIR-7:** la PD de 12 meses anclada es la del modelo (al peso) y la reconciliación alerta. CN:
   anclar sin la edad → rojo.
9. **D-FIR-8:** un caso a mano con edad 4 años donde la PD de 12 meses baja con la edad: sin tramo
   detectaría mal. CN: comparar sin tramo → rojo.
10. **Sin escenarios ni columnas, bit a bit:** proyección canónica de F4 y de Lending Club iguales a
    las de la 2.7.0 salvo el hash. CN: desplazar con `δ` de un escenario vacío → rojo.
11. **Simplicidad y copy:** golden de esenciales, `HOJAS_DEL_FORMULARIO`, ledger de opciones, espejo
    del front, cinco cifras; copy gate y gate de códigos internos sobre los rótulos nuevos.

Codex sobre el código de cada capa, con tope de tres pasadas y criterio declarado.

## 7. Lo que esta enmienda NO hace

No estima la sensibilidad desde la historia de la propia cartera (§3.2, candidata); no elige
variables ni rezagos; no trae datos macro reales al paquete; no fija pesos ni escenarios; no
modela la LGD ni la EAD por escenario; no deja que la macro decida la etapa; no cambia la curva de
supervivencia, Stage 3, la tabla de pagos, el descuento ni la mora y la marca; no retira la vía
anterior de `forward` ni Vasicek; no implementa stress (IHN-002); no toca CMF; no programa nada.

## 8. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 8-1 | La enmienda en su conjunto (D-FIR-1…11) | (a) **aprobar y programar la capa A en la sesión siguiente**; (b) aprobar con cambios; (c) no aprobar | **(a)** |
| 8-2 | De dónde sale la sensibilidad al ciclo (D-FIR-2) | (a) **una tasa de referencia larga que entrega la institución** (sistema o propia); (b) la historia de la propia cartera; (c) un coeficiente que declara la institución | **(a)**: (b) falla medido en las dos carteras reales; (c) sigue disponible en la puerta completa |
| 8-3 | El ancla (D-FIR-3) | (a) **con fechas, las condiciones de la ventana de la curva y reversión al largo plazo; sin fechas, el largo plazo declarado**; (b) siempre el largo plazo | **(a)**: (b) resta 9–12 puntos en las dos carteras reales cuando la curva se estimó en años buenos |
| 8-4 | El SICR con PD de origen (D-FIR-8; resuelve D-CRE-4) | (a) **adoptarlo en la capa B**; (b) seguir difiriéndolo | **(a)**: es lo que pide 5.5.9 y el dato lo tiene el banco |
| 8-5 | Esenciales y argumentos | (a) **`provisioning_ifrs9` 10 → 12 (las dos PD) y `forward` con 3 en el trabajo de la pantalla; `Ecl` gana `scenarios`, `history`, `pd`, `origination_pd`**; (b) las dos PD sólo en «Avanzado» y en la puerta completa | **(a)**: sin ellas en la puerta, la PD del modelo y el SICR no llegan al usuario de `Ecl` |
| 8-6 | Los datos del ejemplo (D-FIR-10) | (a) **sintéticos generados en el bloque de la guía, con sensibilidad conocida**; (b) tablas sintéticas en el catálogo del paquete; (c) un extracto real de la CMF por cartera (CC BY 4.0) y de la desocupación del INE (CC BY-SA 4.0) | **(a)**: cero licencias, reproducible, y es el precedente de S35 |
| 8-7 | Releases (D-FIR-11) | (a) **A en 2.8.0, B en 2.9.0, C en 2.10.0**; (b) A + B en 2.8.0 y C en 2.9.0 | **(a)**: la capa A es la que falta para 5.5.17 y es la más grande |

## 13. Simplicidad (SDD-31)

- **Entrada mínima:** la de CASO-REAL más, opcionales, dos tablas (historia de la tasa de referencia
  con su macro; escenarios con pesos) y dos columnas de la cartera (PD a 12 meses de hoy y de
  origen). Se infieren y se declaran: las variables macro (las columnas comunes a las dos tablas),
  la escala de la tasa, la frecuencia de cada tabla, el tramo de calendario de cada período
  posterior al corte, el ancla, el horizonte del escenario y la reversión, y el desplazamiento de
  cada operación para anclarla a su PD.
- **Qué NO se configura (§3.11):** el rezago, la forma y el estimador del satélite; el ancla; el
  largo y la forma de la reversión; la cobertura mínima de los escenarios; la regla del tramo de
  calendario; que la etapa no la decide el escenario; la cota de la PD; los umbrales de «Qué
  revisar» y de la reconciliación; ningún peso por defecto.
- **Campos esenciales:** `survival` 5 (sin cambio); `provisioning_ifrs9` **12** en la capa B (la
  excepción al tope de 6 de SDD-31 §12.1 se amplía, §8-5); `forward` **3** en el trabajo de la
  pantalla (la tabla de historia, la columna de la tasa —con su default— y los escenarios), capa C;
  el resto en «Avanzado».
- **Presupuesto de perillas:** **tres** hojas (§3.11), cada una con su evidencia; cuatro opciones
  nuevas en literales existentes.
- **Resumen por etapa:** una etapa nueva, **«Escenarios»**, entre «Curva de PD» y «Provisión IFRS
  9»: qué tasa de referencia y qué ventana, la sensibilidad con su error y su sentido en palabras,
  el ancla (ventana de la curva o largo plazo) y la tabla de escenarios con sus pesos, el
  desplazamiento del primer año por escenario y la ECL por escenario frente a la TTC. «Provisión
  IFRS 9» dice la ponderada, la PD del modelo frente a la de la curva y cuántas operaciones movió el
  SICR por PD de origen. El resumen final lo lleva a «Supuestos» («La PD se ajusta a las condiciones
  actuales y a N escenarios ponderados…», reemplaza a la línea TTC cuando hay escenarios) y a «Qué
  revisar». Decisiones humanas: las de FLUJO-GUIADO-IFRS9, sin nuevas.
- **Notebook mínimo:** «Tu primera provisión IFRS 9» sigue en **21** líneas y sin escenarios (el
  paquete no trae calendario). La provisión firmable se muestra en un bloque de la guía ejecutado
  en CI, con los datos sintéticos de §3.10 (≈ 15 líneas para generarlos y 3 para la corrida).
- **Las cinco cifras** (golden `test_simplicidad_ifrs9.py`):

| Cifra | Hoy (`0e5e46f`) | Después |
|---|---|---|
| Líneas de usuario | 21 | 21 |
| Esenciales por sección | `survival` 5, `provisioning_ifrs9` 10 | 5, **12** y `forward` **3** (capa C) |
| Perillas de las secciones de cálculo del trabajo | 233 (158 + 24 + 51) | 233 en A (la hoja nueva vive en `forward`, fuera del trabajo); **235** en B (158 + 24 + 53); **280** en C, cuando `forward` entra al trabajo (44 + 1 hojas) |
| Segundos al primer resumen (paquete) | ~1 | ~1 (sin escenarios no hay cálculo nuevo) |
| Conceptos antes del primer resultado | 5 | 5 |
