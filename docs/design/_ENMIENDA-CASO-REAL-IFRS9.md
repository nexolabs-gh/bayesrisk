# Enmienda SDD — El caso real de IFRS 9: lo que midieron las carteras reales (hito H2)

> **Estado: PROPUESTA (S33, 2026-10-05).** Diseño sin código, pendiente de la revisión adversarial
> (tope de tres pasadas) y de la aprobación de Cami, punto por punto en §8. Aprobarla **no programa
> nada por sí sola**: la capa A entra en la sesión siguiente, con tests nacidos rojos, controles
> negativos y revisión del código; la B después. Cada release y cada recaptura piden su OK aparte.
> **Corregida tras la pasada 1 de Codex** (tres high y un medium, los cuatro reales y ninguno
> contractual): la lectura condicionada se limita a curvas de supervivencia, de las que se conoce la
> historia (§3.2-7); la EAD amortiza con la **cuota del contrato** y no con una tabla deducida de la
> EIR activada por el vencimiento (§3.3); las filas sin exposición se separan justo después de
> calcular la EAD (§3.5); y la edad es **fraccionaria**, con riesgo constante dentro de cada período
> de la curva (§3.2-1/2). Las cifras se volvieron a medir con esas reglas.
>
> **Base medida:** `main` = `629e422` (bayesrisk 2.5.0). Las cifras de S32 (enmienda
> FLUJO-GUIADO-IFRS9 §12) se **reprodujeron** con sus propios scripts sobre este HEAD y casan al
> peso; las «después» se midieron con las reglas exactas que esta enmienda propone. Scripts y
> salidas, sólo agregados, en el repo privado: `evidencia/s32/` (preparación de Lending Club y
> Freddie Mac, corrida de `Ecl`, primera medición) y `evidencia/s33/` (`medir_candidatas_v2.py`,
> `confirmar_stage3.py`, `hash_f4_stage3.py`, `inspeccionar_curvas.py`, y `salidas/`). Los datos
> externos viven fuera de los repos (`E:\Proyectos\datos-externos\ifrs9\`, con `LEEME.md` y
> `SHA256SUMS`). Los párrafos de IFRS 9 que se citan se cotejaron contra el texto oficial adoptado
> por la UE (Reglamento (UE) 2016/2067, EUR-Lex, versión EN); la segunda fuente, el texto del IASB
> en ifrs.org, exige sesión y **no se cotejó**.
> **Enmienda a:** SDD-16 (`provisioning_ifrs9`: Stage 3, vida contractual, antigüedad, perfil de
> la EAD, filas sin exposición), SDD-18 (`survival`: identificador por columna),
> [`_ENMIENDA-FLUJO-GUIADO-IFRS9.md`](_ENMIENDA-FLUJO-GUIADO-IFRS9.md) (D-ECL-4 si Cami elige la
> opción (b) de §8-2; D-ECL-6, esenciales de `provisioning_ifrs9`; D-ECL-13, candidatas de su
> §3.14), [`31-simplicidad-y-flujo-guiado.md`](31-simplicidad-y-flujo-guiado.md) (la excepción al
> tope de esenciales, §8-3) y `docs_site/` (guía de la provisión y el ejemplo de «Empezar»).
>
> **No toca:** la fórmula de la PD marginal de la curva, del staging por mora y marca, de la LGD ni
> del descuento; la curva de supervivencia (su ajuste, sus coeficientes y sus cifras); forward,
> Markov, stress, CMF, el arnés H9R, el scorecard ni ninguna decisión de las familias
> D-SC/D-VAL/D-HOR/D-GOB. **No autoriza** bump, tag, PyPI ni recaptura.

| Campo | Valor |
|---|---|
| **Enmienda** | CASO-REAL-IFRS9 (D-CRE-1…D-CRE-8) |
| **Módulos** | `provisioning/ifrs9` (`config.py`, `engine.py`, `ecl.py`, `ead.py`, `staging.py`, `results.py`); `survival` (`discrete_hazard.py`, `step.py`: el identificador); `guided/ecl.py` y `guided/summaries.py` (argumentos, constantes, «Supuestos», «Qué revisar», conteos); `ui/presets.py` (F4) y `ui/jobs.py` + `web/` (esenciales); `report` (prosa del capítulo IFRS 9); `docs_site/` |
| **Fase** | F4 |
| **Depende de** | FLUJO-GUIADO-IFRS9 (D-ECL-0…15, implementada y publicada en 2.4.0–2.5.0); SDD-31; D-HOR (unidad de la curva); D-EST-5 (el sobre estable, las cifras siguen a su motor) |
| **Lo consumen** | La guía «La provisión IFRS 9 de punta a punta», el ejemplo «Tu primera provisión IFRS 9», la demo IFRS 9, el trabajo `provisiones_ifrs9` de la pantalla; H2b (compara también provisiones), H3 (PD + LGD) y H7 (forward, PIT y la candidata diferida de §3.4) |
| **Release** | Capa A en un minor (2.6.0); capa B en el siguiente (2.7.0) — §3.7, §8-4 |

## Recomendación ejecutiva

En las dos carteras reales, cuatro supuestos del motor mueven la ECL decenas de puntos y dos
defectos de forma confunden a quien la lee. Esta enmienda corrige en el motor y en la puerta tres de
esos supuestos, que tienen una regla defendible; difiere el cuarto, que no la tiene, y arregla los
dos defectos de forma:

1. **Stage 3 con PD = 1** (D-CRE-1): una operación ya incumplida hoy se provisiona con la PD de la
   curva, como si siguiera sana. Con LGD × EAD —la ruta `stage3_direct` que el motor ya tiene— la
   ECL del paquete pasa de **3.423.116 a 4.786.739 (+39,8 %)** y la de Freddie Mac de **1.530.096 a
   3.028.897 (+98,0 %)**, medido con el propio motor; Lending Club no tiene operaciones vivas en
   Stage 3. Es la de mayor efecto y la más simple, y mueve la cifra y el `config_hash` de F4.
2. **Vida contractual y antigüedad** (D-CRE-2) y **EAD que amortiza con su cuota** (D-CRE-3): con
   tres columnas opcionales del archivo de cartera —fecha de otorgamiento, fecha de vencimiento y
   cuota— la curva se lee desde la edad de cada operación, la vida se corta en su vencimiento (IFRS 9
   5.5.19) y la exposición sigue su tabla de pagos. Juntas: Lending Club **−14,8 %**, Freddie Mac
   **−25,9 %**. Sin esas columnas, nada cambia.
3. **Las filas sin exposición no son operaciones** (D-CRE-5): Lending Club dice hoy «60.000
   operaciones, Stage 3: 10.191» de una cartera de 9.593 préstamos vivos sin ninguno en Stage 3.
4. **La curva identifica por la columna del identificador** (D-CRE-6): el detalle por operación
   sale con `loan_id` y no con la posición de la fila.
5. **La PD de origen para el SICR no se adopta** (D-CRE-4): se difiere a H7 con su evidencia. Lo
   medido muestra que el problema de fondo no es la PD de origen sino evaluar la curva con las
   covariables del otorgamiento —con las actuales, la ECL se mueve +13,3 % en Lending Club y −30,2 %
   en Freddie Mac, más que el propio SICR—, y eso es una metodología PIT por validar.

Presupuesto: **tres hojas nuevas** (las dos fechas y la cuota), cada una con su evidencia; los
esenciales de `provisioning_ifrs9` pasan de 7 a 10. Una regla con efecto material queda a decisión
de Cami: cómo se extiende la curva más allá de la historia observada (§8-6; en Freddie Mac, −21 %
o −37 %). Capa A (D-CRE-1, 5 y 6) en la 2.6.0 y capa B (D-CRE-2 y 3) en la 2.7.0.

## 0. Qué corrige de lo ya escrito

1. **«Curva desde la originación: −47,3 % en Freddie Mac»** (FLUJO-GUIADO-IFRS9 §12 y la guía
   `docs_site/guias/provision-ifrs9.md`, «Lo que la cifra supone») **es en buena parte un
   artefacto.** El último período de la curva de Freddie Mac (año 11) no tiene incumplimientos
   observados —su coeficiente es −19,75 con error estándar 12.644, y su hazard, 3·10⁻¹²— y la
   medición de S32 extendía ese hazard nulo como «riesgo constante» hasta el vencimiento: medía
   «ningún riesgo más allá del año 10» para hipotecas con veinte años por delante. Con las reglas de
   esta enmienda la cifra es **−21,1 %** (la cola con la media de los tres últimos períodos con
   incumplimientos, la recomendada) o −37,1 % (con el último), y va hasta −62,2 % sin proyectar más
   allá de lo observado (§1.3).
2. **«+6 % en consumo»** (Lending Club) redondeaba la edad a períodos completos y contaba completo
   el último período de vida aunque quedara un mes; con la edad fraccionaria y el período parcial,
   **+1,9 %**.
3. **«EAD constante: −37,5 % en Lending Club, −3,8 % en Freddie Mac»** incluía el corte en el
   vencimiento. Separados: la vida contractual sola mueve **−15,5 %** en Lending Club (los
   préstamos vencen antes del horizonte de la curva) y **+5,5 %** en Freddie Mac (la vida se
   **alarga**: 243 meses remanentes frente a 132 de la curva); la amortización encima, **−26,4 %** y
   **−6,3 %**.
4. **«Sin PD de origen: 255 de 9.308 operaciones de Stage 1»** se sostiene con la ventana de 12
   meses condicionada a la antigüedad; con la de vida remanente son 240, y con la PD de por vida
   desde la originación —la que el motor compara hoy— 85. Y no dice lo principal: la covariable
   actual mueve la ECL de todas las operaciones (§3.4).
5. **D-ECL-13** dejó la EAD constante «en H2» con la amortización como candidata CT-3 a la espera
   de un dataset de cuotas: Lending Club es ese dataset (§3.3).

## 1. El estado, medido sobre `629e422`

### 1.1 La reproducción

Los scripts de S32 (`lc_perfil.py`, `lc_preparar.py`, `fm_preparar.py`, `ecl_externo.py`,
`medir_externo.py`) corridos sobre este HEAD dan **las mismas cifras al peso**: Lending Club
3.254.890 en 115,9 s y Freddie Mac 1.530.096 en 60,0 s, con las mismas variantes de S32. La ECL del
motor se reconstruye fuera de él (PD marginal × LGD × EAD × DF por período) y casa exacto en Stage
1 y 2; el descuento del motor es `DF(t) = (1 + EIR)^(-t·u/12)` con `u` meses por período
(verificado sobre 2.000 filas), y el hazard de cada operación se reconstruye de los coeficientes del
ajuste (`logit⁻¹(α_t + β·x)`, sin constante) y casa con la curva publicada. La supervivencia por
tramos de §3.2 reproduce también la cifra del motor cuando la edad es cero y la vida es la de la
curva. Sobre esa reconstrucción se midieron todas las variantes (`medir_candidatas_v2.py`). Stage 3
con PD = 1 se midió además **con el motor** (`confirmar_stage3.py`: la misma corrida de `Ecl` con
`stage3_direct=True`).

### 1.2 Las tres carteras

| | Paquete (`ifrs9_retail_latam`) | Lending Club (2013–2016) | Freddie Mac SFLLD (2016) |
|---|---|---|---|
| Filas / vivas con EAD > 0 | 6.000 / 6.000 | 60.000 / 9.593 | 50.000 / 14.038 |
| Etapas hoy (todas las filas) | 5.235 · 477 · 288 | 49.522 · 287 · 10.191 | 48.523 · 155 · 1.322 |
| Etapas de las vivas | 5.235 · 477 · 288 | 9.308 · 285 · 0 | 13.828 · 155 · 55 |
| Curva: unidad, horizonte | año, 5 | trimestre, 20 (60 meses) | año, 11 (132 meses) |
| Incumplimientos por período | 374 · 339 · 286 · 270 · 233 | de 274 a 1.202 y baja a 7 en el 20 | 155 · 252 · 143 · 923 · 666 · 75 · 50 · 43 · 41 · 19 · **0** |
| Antigüedad de las vivas (mediana) | no medible (§1.4) | 34 meses (p10 28, p90 47) | 115 meses (p10 110, p90 120) |
| Plazo remanente (mediana) | sin vencimiento en el archivo | 9 meses (p10 2, p90 29) | 243 meses (p10 64, p90 249) |
| Cuota del contrato | — | en el archivo (`installment`), 9.593 de 9.593 | no publicada (se dedujo de saldo, tasa y plazo para medir) |
| ECL del motor | 3.423.116 | 3.254.890 | 1.530.096 |

### 1.3 La cola de la curva

Una curva con interceptos por período sólo estima riesgo donde hubo incumplimientos. En Freddie Mac
el período 11 tiene **cero** y su hazard sale ≈ 0 sin aviso; en Lending Club los períodos 21–23
tampoco tienen (−18,99 con error 17.730), pero quedan fuera del horizonte declarado (20). Hoy, con
la curva desde la originación, el período nulo de Freddie Mac apenas pesa (es el último de once);
**en cuanto la curva se lee desde la edad de cada operación, la cola lo es todo**: el 100 % de la
exposición viva de Freddie Mac tiene vida más allá del último período con incumplimientos (edad
~9,6 años, vencimiento a ~20 más). Medido sobre las reglas de D-CRE-2:

| Regla para la cola (más allá del último período con incumplimientos) | Lending Club | Freddie Mac |
|---|---|---|
| **La media de los tres últimos períodos con incumplimientos, constante (recomendada, §8-6)** | **+1,9 %** | **−21,1 %** |
| El hazard del último período con incumplimientos, constante | +1,9 % | −37,1 % |
| El hazard del último período de la curva (S32: en Freddie Mac, el nulo) | +1,9 % | −62,2 % |
| Ninguna proyección (riesgo cero más allá) | +1,9 % | −62,2 % |

En Lending Club la regla no importa (10 operaciones, 0,0 % de la EAD pasan la cola); en Freddie Mac
decide dieciséis puntos entre las dos reglas razonables. El último período con incumplimientos suele
estar observado sólo en parte —una operación que lleva siete meses del año 10 cuenta como expuesta
el año entero, porque la duración de una operación sin incumplir se redondea hacia arriba—, así que
su hazard queda bajo: en Freddie Mac hay 19 incumplimientos en el año 10 frente a 41–50 en los años
7–9, y el hazard medio del año 10 (0,15 %) es la mitad del de los años 6–9 (0,29–0,38 %). La media de
tres períodos amortigua ese sesgo y es la prudente (más ECL). Ninguna regla sustituye historia que no
existe: por eso la regla se declara con la parte de la exposición a la que se aplica (§3.2).

### 1.4 El paquete

`ifrs9_retail_latam` no trae fecha de otorgamiento, de vencimiento ni cuota, y su `duration` **no
cuenta desde el otorgamiento**: va de 1 a 5 años mientras `antiguedad_meses` va de 1 a 120 meses, con
correlación 0,09. La antigüedad no puede inferirse de la duración —en el paquete daría una edad
falsa y movería la cifra de F4 en silencio—: tiene que ser una columna declarada (§3.2). Las 6.000
filas tienen EAD > 0. En el paquete sólo aplica D-CRE-1.

### 1.5 Lo que el motor ya tiene

| Pieza | Dónde | Estado |
|---|---|---|
| Stage 3 como `EAD · LGD · DF(0)` | `IfrsEclConfig.stage3_direct` (D-IFRS-14), `ecl.py:_direct_lifetime` | implementado; F4 y la puerta lo fijan en `False`, el default de fábrica es `False` |
| PD de origen para el SICR | `IfrsStagingConfig.origination_pd_life_col` | implementado; compara la PD de por vida actual con la de origen (razón ≥ 2,0) |
| Tope global de vida | `IfrsPdConfig.max_lifetime_periods` | implementado; uno para toda la cartera, no por operación |
| Perfil EAD(t) | `IfrsEadConfig.exposure_profile_col` | **reservado** (CT-3): informarlo detiene la corrida |
| Identificador de la curva | `SurvivalInputConfig.id_col` | sólo se exige como columna; la curva publica `row_id` = el índice |
| Incumplimientos por período | `survival` → `person_period.events_by_period` | publicado en el resultado del ajuste de `discrete_hazard` |
| Identificador de la provisión | `IfrsProvisioningConfig.row_id_col` | implementado (columna o índice) |
| Cobertura de la curva | `engine.py`: `_check_row_coverage` | exige que la curva cubra todas las filas del archivo de la provisión |

## 2. Lo que ya está construido y no hay que inventar

Conectar, no reimplementar (RUNBOOK §12.1-3): D-CRE-1 es **una constante** sobre una ruta que ya
existe y tiene sus tests (`test_ifrs9_ecl.py`); D-CRE-6 reutiliza `survival.input.id_col` y
`provisioning_ifrs9.row_id_col`; la regla de la cola de D-CRE-2 lee `events_by_period`, que la
curva ya publica; la conversión de fechas a meses y a períodos usa `bayesrisk.core.time_units` (la
misma tabla que la unidad de la curva, D-HOR); el descuento, la ponderación por escenario y el
staging por mora y marca no cambian. Lo nuevo es la lectura de la curva desde la edad de cada
operación, el corte por operación y la tabla de pagos: tres piezas del motor de provisiones, no un
segundo motor.

## 3. Las decisiones que se proponen

### 3.1 D-CRE-1 — Stage 3 con PD = 1: la pérdida del incumplimiento ya ocurrido

**Contrato.** La ECL de una operación en Stage 3 es **LGD × EAD** (PD = 1, sin descontar: la LGD
ya es la pérdida en valor presente del incumplimiento que ocurrió) —la ruta `stage3_direct=True`
del motor, sin cambiar su fórmula—. Una operación en Stage 3 ya incumplió (IFRS 9, Apéndice A,
«activo con deterioro crediticio»; 5.5.3): su pérdida esperada no depende de la probabilidad de que
incumpla, sino de cuánto se pierde (B5.5.33: el valor en libros menos el valor presente de los
flujos que se espera recuperar). Hoy se provisiona con la PD de por vida de la curva, es decir, como
una operación sana: en el paquete, las 288 operaciones de Stage 3 tienen una ECL de 870.989, el
39 % de su LGD × EAD (2.234.612).

**Dónde cambia** (§8-2, decisión de Cami). Dos opciones con la misma cifra para la puerta, F4, la
pantalla y la demo:

- **(a) Constante de la puerta y del preset F4.** `Ecl` escribe `stage3_direct=True`;
  `_IFRS9_PROVISIONING_SECTION` también. El default de fábrica sigue en `False` (D-ECL-4 intacta):
  un YAML escrito a mano que omita la hoja conserva su cifra y su `config_hash`, y su resumen lo
  declara (abajo).
- **(b) Además, el default de fábrica pasa a `True`.** Un default que produce una cifra
  indefendible en un caso real es exactamente lo que D-SIM-3 manda corregir; el costo es que todo
  YAML con `provisioning_ifrs9` que omita la hoja cambia su `config_hash` y, si tiene operaciones en
  Stage 3, su cifra (el motor es experimental, fuera de SemVer 2.x; el CHANGELOG lo dice). Reabre
  D-ECL-4 sólo para esta hoja. **Medido** con el default invertido en una copia de `src/`: de los
  **1.892** tests que tocan IFRS 9 (71 archivos), **2** se ponen rojos —el golden de defaults de
  `IfrsProvisioningConfig`, que lo documenta, y `test_golden_staging_stage3_dpd` del motor, que
  fija la ECL de Stage 3 con la curva—; ningún `config_hash` fijado se mueve por el default (F4
  escribe la hoja explícita y el golden del config por defecto no trae la sección).

**Recomendación: (b).** Es la causa raíz: con (a), el próximo YAML escrito a mano vuelve a
provisionar como sanas las operaciones incumplidas, y el costo medido en el repo son dos goldens. El
`config_hash` que se mueve en los YAML de los usuarios es la señal honesta de que su cifra cambia.

**Cómo se declara.** «Supuestos» del resumen de la provisión, del resumen final, de la página
ejecutiva y de Resultados dice «Stage 3: la pérdida del incumplimiento ya ocurrido, LGD × EAD (PD =
1)». Con `stage3_direct=False` y alguna operación en Stage 3, en su lugar: «Stage 3 con la PD de la
curva: una operación ya incumplida se provisiona como una sana» y una alerta en «Qué revisar» con
la exposición en Stage 3. La LGD de Stage 3 es la misma columna del archivo; si la institución tiene
una LGD en incumplimiento distinta (*best estimate* de la pérdida ya incurrida), va en esa columna
para esas operaciones —la guía lo dice—. El CHANGELOG lo publica en «Cambiado» con las tres cifras.

**Qué NO se configura en la puerta:** la fórmula de Stage 3 ni su descuento.

**Cifras** (medidas con el motor; Lending Club no tiene vivas en Stage 3):

| | Antes | Después | |
|---|---|---|---|
| Paquete (F4) | 3.423.116 | **4.786.739** | +39,8 % |
| Lending Club | 3.254.890 | 3.254.890 | 0 |
| Freddie Mac | 1.530.096 | **3.028.897** | +98,0 % |

**Qué mueve.** El `config_hash` de F4: `013e69dc…` → **`a3b7cf9b…`** (medido con el preset
cambiado; la capa B lo vuelve a mover, §3.7) y su ECL. Fijados hoy: `test_ui_presets.py`
(`_EXPECTED_F4_CONFIG_HASH`), `test_corrida_de_cartera.py` (`_HASH_F4`),
`test_columna_cartera_ambigua.py`, `test_jobs_abanico.py`; `test_docs_quickstart.py` (`_ECL_F4`),
`test_guided_ecl.py`, `test_guided_summaries_cartera.py`, `test_report_renderer.py`,
`test_ui_serializers.py`; en `web/`, `ResultsTab.test.ts`, `demo.test.ts`,
`results-format.test.ts` y los fixtures `results-ifrs9.json`, `preset-ifrs9.json`,
`toyaml-ifrs9.json` con sus firmas (`scripts/frontend_demo_fixture_signatures.json`); los scripts
`capture_demo_fixtures_ifrs9.py` y `derive_ifrs9_preset.py`; las cifras de «Tu primera provisión
IFRS 9» (`getting-started.md`) y de la guía. La demo IFRS 9 exige **recaptura** (OK aparte).

### 3.2 D-CRE-2 — La vida contractual y la antigüedad de cada operación

**Contrato.** Dos hojas nuevas de `provisioning_ifrs9`, opcionales y por fila:
`origination_date_col` (fecha de otorgamiento) y `maturity_date_col` (fecha de vencimiento
contractual). En la puerta, `Ecl(..., origination=None, maturity=None)`. Con ellas:

1. **Antigüedad fraccionaria.** `A` = meses entre el otorgamiento y la fecha de corte, divididos
   por los meses de un período de la curva (la tabla de `core.time_units`), **sin redondear**.
   Exige que la duración de la historia cuente **desde el otorgamiento** —la puerta no puede
   verificarlo y lo declara en «Supuestos»—.
2. **Supervivencia por tramos.** Dentro de cada período de la curva el riesgo es constante:
   `S(x) = Π_{k ≤ ⌊x⌋} (1 − h_k) · (1 − h_{⌊x⌋+1})^(x − ⌊x⌋)`. La PD del período `t` posterior al
   corte —el tramo `[A + t − 1, A + min(t, L)]` de la curva— es
   `[S(A + t − 1) − S(A + min(t, L))] / S(A)`: la probabilidad de incumplir en ese tramo dado que la
   operación sobrevivió hasta hoy. Cada período posterior al corte cruza los períodos de la curva que
   le tocan; con `A = 0` y la vida de la curva reproduce la cifra de hoy.
3. **Vida contractual** (IFRS 9 5.5.19: el período máximo es el contractual). `L` = meses entre el
   corte y el vencimiento, en períodos de la curva y también fraccionaria. Stage 1 suma el tramo
   `min(12 meses, L)` (B5.5.43: si la vida es menor que 12 meses, el período más corto); Stage 2
   —y Stage 3 con `stage3_direct=False`—, el tramo `L`. Con `max_lifetime_periods`, el menor de los
   dos. El descuento de cada período no cambia (el tramo parcial se descuenta al final del período);
   la EAD tampoco, salvo con D-CRE-3.
4. **Vencida con saldo.** Una operación con el vencimiento ya pasado y saldo vivo tiene **un
   período** de vida (no cero: sigue expuesta); se cuenta en «Qué revisar». Lending Club: 221
   operaciones, EAD 100.128.
5. **La cola** (§8-6). Más allá del último período de la curva con incumplimientos observados
   (`H_ev`, leído de `events_by_period`), el hazard de cada operación se extiende constante en **la
   media de sus hazards de los tres últimos períodos con incumplimientos** (de los que haya, si son
   menos de tres); los períodos finales sin incumplimientos dentro del horizonte se reemplazan igual.
   Sólo con alguna de las dos hojas declarada: la curva publicada no cambia. «Supuestos» dice desde
   qué período se extiende y «Qué revisar», qué parte de la exposición tiene vida más allá de lo
   observado (Freddie Mac: 100 %).
6. **Sin las fechas, por fila.** Sin vencimiento —una línea rotativa, cuya vida es el período en
   que la institución está expuesta y su gestión no mitigaría las pérdidas (5.5.20, B5.5.39–40)—,
   la vida son los `H` períodos del horizonte declarado contados desde el corte, con la curva leída
   desde la edad (hoy, desde el período 1). Sin otorgamiento, `A = 0`: la curva se lee desde el
   período 1 y sólo se corta en el vencimiento. Sin ninguna de las dos hojas, la provisión es **bit
   a bit la de hoy**.
7. **Sólo curvas de supervivencia** (pasada 1 de Codex). Aplica con
   `pd.term_structure_source = "survival"`, la única fuente de la que se conocen el origen de la
   curva y sus incumplimientos por período; con `forward` o `markov` —esta última ya parte del
   estado actual, y `forward` puede venir de ella— la corrida se detiene antes de correr con un
   requisito por contexto. Extenderlo a `forward` es de H7, junto con lo PIT.
8. **Lo que se lee aguas abajo.** La verificación de D-ECL-0 (`FALTA-DATO-IFRS-8`: que los 12
   meses del Stage 1 tengan la duración de un año) sigue midiendo la curva publicada, antes del
   corte por operación: una operación con menos de 12 meses de vida no la dispara (B5.5.43). Las PD a
   12 meses y de por vida que publica la provisión —las del resumen y las que compara el SICR cuando
   hay PD de origen— son las condicionadas. La regla del informe y de la pantalla que atribuye la
   curva a la provisión «sólo si la consumió tal cual» (FLUJO-GUIADO-IFRS9 §12) trata la lectura
   condicionada como no tal cual, y la prosa dice que la provisión leyó la curva desde la edad de
   cada operación.

**Salidas (aditivas).** `ecl_term_structure` gana `curve_start` y `curve_end` (el tramo de la curva,
`A + t − 1` y `A + min(t, L)`); su `period` se cuenta desde el corte (hoy coinciden). `detail` gana
`age_periods` y `life_periods`; la card, `n_matured_with_balance`, `tail_from_period` y
`ead_beyond_observed_curve`.

**Qué NO se configura:** la regla de la cola (una vez decidida en §8-6), el riesgo constante dentro
del período, la vida de la operación vencida, el momento del descuento y qué fuente de curva admite
la lectura condicionada. Constantes con su razón en el código.

**Cifras** (fuera del motor, reglas exactas de arriba con la cola recomendada; Stage 3 sin cambiar):

| | Antes | Antigüedad sola | Vida contractual sola | **D-CRE-2** |
|---|---|---|---|---|
| Lending Club | 3.254.890 | 3.699.595 (+13,7 %) | 2.748.843 (−15,5 %) | **3.315.758 (+1,9 %)** |
| Freddie Mac | 1.530.096 | 1.123.776 (−26,6 %) | 1.615.007 (+5,5 %) | **1.207.403 (−21,1 %)** |
| Paquete | 3.423.116 | — | — | sin fechas: igual |

En Lending Club la antigüedad sube el riesgo (préstamos de ~3 años, en el pico de su curva) y el
vencimiento lo corta (quedan ~9 meses); en Freddie Mac la antigüedad lo baja (hipotecas de ~10 años
han pasado su pico) y el vencimiento lo alarga. Con la cola del último período con incumplimientos,
Freddie Mac −37,1 %; con la edad redondeada a períodos completos (la primera versión), Lending Club
+4,5 % y Freddie Mac −35,8 %.

**Alternativas descartadas.** Inferir la antigüedad de `duration` (el paquete muestra que la
duración no siempre cuenta desde el otorgamiento: §1.4). Redondear la edad a períodos completos
(pasada 1 de Codex: el primer período después del corte cruza dos períodos de la curva). La cola
desde el último período de la curva (S32: en Freddie Mac, riesgo cero 20 años). Detener la corrida
cuando la vida pasa la curva (el 100 % de Freddie Mac: la puerta no correría hipotecas). Agrupar en
la curva los períodos con pocos incumplimientos (cambio del ajuste de supervivencia;
`min_events_per_period` hoy sólo rechaza): candidata si la regla de la cola falla en un caso real.
Pedir los meses de antigüedad y de plazo remanente como columnas en la unidad de la curva (la fecha
es lo que trae un archivo de banco y no tiene unidad que declarar mal).

### 3.3 D-CRE-3 — La exposición amortiza con la cuota del contrato

**Contrato.** Una hoja nueva, `provisioning_ifrs9.ead.installment_col` (la **cuota mensual** del
contrato), default `None` (EAD constante, lo de hoy). Con ella, la EAD de cada período de una
operación con vencimiento es **el saldo al inicio del período** que deja pagar esa cuota:
`B_k = B(1 + i)^k − c((1 + i)^k − 1)/i` tras `k` meses, con piso cero y hasta el vencimiento, donde
`i` es la tasa mensual efectiva equivalente a la EIR anual, `(1 + EIR)^(1/12) − 1`. La cuota es un
dato del contrato y fija el ritmo de pago; la tasa sólo reparte cada cuota entre interés y capital:
con la EIR tres puntos más alta, Lending Club se mueve un punto (−36,8 % frente a −37,8 %). Una
cuota que no cubre el interés del mes **no amortiza** (un *bullet*, o sólo intereses): la EAD queda
constante hasta el vencimiento. Una cuota que no alcanza a pagar el saldo al vencimiento (atrasos,
pago final mayor) deja ese saldo expuesto hasta el vencimiento: Lending Club, 1.055 de 9.593. Sin
cuota en una fila, EAD constante. `FALTA-DATO-IFRS-4` («EAD constante») sigue declarándose cuando
alguna operación conserva la EAD constante, y deja de hacerlo cuando ninguna.

Exige `maturity_date_col` y `ead.method = "provided"` (requisitos por contexto: sin vencimiento no
hay plazo, y la tabla parte de un saldo entregado, no de un dispuesto más CCF). En la puerta,
`Ecl(..., installment=None)`: **la amortización la activa la cuota, no el vencimiento** (pasada 1 de
Codex). `exposure_profile_col` (el panel EAD(t) entregado por la institución) sigue reservado: es
CT-3 completo, sin evidencia todavía de que la cuota falle.

**Qué NO se configura:** la frecuencia de la cuota (mensual), la tasa con que se reparte (la EIR),
la EAD del período (saldo al inicio) ni el tratamiento de una cuota que no amortiza.

**Cifras** (sobre la vida contractual de D-CRE-2, que la tabla necesita; Freddie Mac no publica la
cuota y se midió con la que se deduce de saldo, tasa y plazo remanente):

| | Vida contractual sola | + cuota | Frente al motor |
|---|---|---|---|
| Lending Club | 2.748.843 | 2.024.464 (−26,4 %) | **−37,8 %** |
| Freddie Mac | 1.615.007 | 1.513.043 (−6,3 %) | **−1,1 %** |

**D-CRE-2 + D-CRE-3:** Lending Club 2.771.978 (**−14,8 %**), Freddie Mac 1.133.294 (**−25,9 %**);
con D-CRE-1, Freddie Mac 2.632.095 (**+72,0 %**) y Lending Club igual.

**Alternativas descartadas.** Una tabla de cuota fija recalculada desde la EIR y activada por el
vencimiento (la primera versión: −38,0 % en Lending Club; pasada 1 de Codex: la EIR incluye
comisiones y no es la tasa contractual, y un *bullet* con vencimiento quedaba amortizado sin que
nada lo detectara). Una columna de tasa contractual (no detecta el *bullet* y la cuota la hace
innecesaria). Pedir el panel EAD(t) (CT-3: ningún archivo de los tres lo trae).

### 3.4 D-CRE-4 — La PD de origen para el SICR: no se adopta; se difiere a H7

**Medido.** Con la PD de origen inferida de la misma curva —las covariables del otorgamiento frente
a las actuales: FICO en Lending Club, ELTV en Freddie Mac—, en Lending Club cruzan el umbral de 2,0
**255 de 9.308** operaciones de Stage 1 con la ventana de 12 meses condicionada a la antigüedad, 240
con la de vida remanente y 85 con la PD de por vida desde la originación (la semántica del motor
hoy); pasarlas a Stage 2 suma +5,5 %. En Freddie Mac, 0. Pero evaluar la curva con la covariable
actual mueve **la ECL de todas las operaciones**: **+13,3 %** en Lending Club (el FICO empeoró) y
**−30,2 %** en Freddie Mac (las viviendas se valorizaron).

**Por qué no ahora.** (1) Una columna de PD de origen —la hoja que ya existe— no es comparable con
la PD de vida remanente condicionada de D-CRE-2: IFRS 9 compara el riesgo de la vida que queda con
el que se esperaba **para ese mismo tramo** al otorgar (5.5.9, B5.5.11; la de 12 meses es un atajo
opcional que sólo vale si los incumplimientos no se concentran en un punto del plazo, B5.5.13–14),
y eso no cabe en un número por operación. (2) Inferirla exige evaluar una curva estimada con las
covariables del otorgamiento con valores actuales: es una lectura *point-in-time* que hay que
validar, y D-ECL-5 ya llevó lo PIT a H7. (3) Su efecto sobre la cifra pasa por la curva, no por el
SICR. **Mientras tanto:** la alerta «el aumento significativo del riesgo se detecta sólo por la
mora y la marca» sigue en «Qué revisar»; la puerta completa conserva `origination_pd_life_col`, y su
semántica con D-CRE-2 se dice en la ayuda del campo (la PD actual es la de la vida remanente). Lo
medido entra a la enmienda de H7 como evidencia.

### 3.5 D-CRE-5 — Una fila sin exposición no es una operación de la cartera

**Contrato.** La provisión estagea, cuenta y publica sólo las operaciones con **EAD > 0**; las
filas con EAD = 0 sólo alimentan la curva (la historia vive en el mismo archivo,
FLUJO-GUIADO-IFRS9 §12). **Dónde se separan** (pasada 1 de Codex): justo después de calcular la EAD
—entregada o por CCF, sobre todas las filas—, y antes de validar y leer cualquier otro insumo de la
provisión (LGD, EIR, mora, marca, fechas, cuota), de buscar la PD de cada operación y de estagear.
La curva se ajusta con el archivo completo, como hoy; la cobertura de la curva
(`_check_row_coverage`) y la malla de componentes de la ECL se comprueban y se arman contra las
operaciones activas; sin ninguna operación activa, la corrida se detiene con su mensaje. Así, un dato
inválido en una fila de historia (una LGD fuera de rango en un préstamo cerrado) ya no aborta la
provisión, y no entra a sus avisos. `staging`, `detail`, `ecl_term_structure`, `summary` y la card
las excluyen (`n_rows` = operaciones con exposición); la card gana `n_rows_without_exposure`
(aditivo). La ECL no cambia: esas filas aportaban cero. El resumen de «Cartera» lo dice: «60.000
filas: 9.593 operaciones con exposición al corte; 50.407 sin exposición sólo aportan historia a la
curva».

**Cifras** (conteos; la ECL, igual):

| | Operaciones | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|---|
| Lending Club | 60.000 → **9.593** | 49.522 → 9.308 | 287 → 285 | 10.191 → **0** |
| Freddie Mac | 50.000 → **14.038** | 48.523 → 13.828 | 155 → 155 | 1.322 → **55** |
| Paquete | 6.000 → 6.000 | igual | igual | igual |

**Alternativas descartadas.** Un archivo de historia aparte (`Ecl(data=, history=)`): exige dos
fuentes en el config (`data`, SDD-05) y no hay evidencia de que la regla de arriba falle; queda como
candidata. Corregir sólo los resúmenes: la pantalla, el informe y el Excel leen los artefactos, y
quedarían contradiciéndose. Excluir al publicar: las filas de historia seguirían validándose y
pudiendo abortar la provisión.

**Qué NO se configura:** el umbral (cero exacto) ni qué cuenta como «sin exposición».

### 3.6 D-CRE-6 — La curva identifica por la columna del identificador

**Contrato.** Con `survival.input.id_col` declarado, la curva identifica cada operación por **el
valor de esa columna** —verificado único, con un error que nombra los repetidos— en todos sus
artefactos por operación (`term_structure` y los demás por fila, en todos los métodos), en vez del
índice del archivo. La provisión lee la misma columna con `row_id_col`; si una declara y la otra no,
o declaran columnas distintas, la corrida se detiene antes de correr con un requisito por contexto
(la curva y la provisión no se encontrarían). La puerta con `id=` columna escribe las dos hojas y
abandona la identificación por posición de S32; con `id=` índice (F4), nada cambia. `forward`
hereda el `row_id` de la curva.

**Cifras:** la ECL es la misma (Lending Club 3.254.890, Freddie Mac 1.530.096); el detalle por
operación sale con `loan_id`. Cambia el `config_hash` de una corrida de `Ecl` con id columna (dos
hojas escritas); el de F4, no. Ningún test ni preset declara hoy `survival.input.id_col` (censo: las
únicas `id_col` declaradas son de Markov); el test de S32
`test_un_id_como_columna_corre_de_punta_a_punta_con_la_cifra_de_f4` cambia su oráculo (hoy exige
`id_col` y `row_id_col` vacíos y «posición» en el motivo de la inferencia).

**Qué NO se configura:** nada nuevo; la hoja existe.

### 3.7 D-CRE-7 — Capas y releases

| Capa | Qué | Mueve | Gate de cierre |
|---|---|---|---|
| **A** | D-CRE-1 (con la opción de §8-2), D-CRE-5, D-CRE-6; «Supuestos», «Qué revisar», conteos y la tabla de la guía corregida (§0) | F4: `config_hash` y ECL; demo (recaptura); ejemplo de «Empezar» | las tres cifras de §3.1 con el motor; F4 = `Ecl` sobre el paquete; conteos de §3.5; detalle con `loan_id` |
| **B** | D-CRE-2 y D-CRE-3: tres hojas, tres argumentos de la puerta, tres esenciales, las salidas aditivas, la prosa del informe y un bloque de la guía ejecutado en CI con fechas y cuota | `config_hash` de toda corrida con `provisioning_ifrs9` (F4 incluida, sin cambiar su cifra: claves nuevas en el `model_dump`); `HOJAS_DEL_FORMULARIO` (574, +3 esperadas; se mide al implementar); el golden de esenciales (`EXCEPCION_AL_TOPE` 7 → 10, 51 → 54 marcas) y su espejo del front; el ledger de opciones y `schema.json` | las cifras de §3.2 y §3.3 **con el motor** (las de esta enmienda son de fuera del motor y son el oráculo); sin las tres columnas, bit a bit |

**Releases** (§8-4): A en la **2.6.0** —es la de mayor efecto y la más chica— y B en la **2.7.0**.
Juntarlas en una (2.6.0) mueve F4 una sola vez y recaptura una vez, pero retrasa el arreglo de
Stage 3 al menos una sesión.

### 3.8 D-CRE-8 — Presupuesto de perillas: tres. Qué NO se configura

**Tres hojas nuevas**, todas en `provisioning_ifrs9` y cada una con su evidencia de que el default
falla en un caso real (D-SIM-3):

| Hoja | Default | Evidencia |
|---|---|---|
| `origination_date_col` | `None` | sin ella, Freddie Mac −26,6 % y Lending Club +13,7 % por la antigüedad sola (§3.2) |
| `maturity_date_col` | `None` | sin ella, la vida es la de la curva: Lending Club −15,5 %, Freddie Mac +5,5 % (§3.2) |
| `ead.installment_col` | `None` | con la EAD constante, Lending Club −26,4 % sobre la vida contractual (§3.3) |

`stage3_direct`, `id_col` y `row_id_col` ya existen. **Esenciales:** `provisioning_ifrs9` pasa de
7 a **10** (las tres columnas, opcionales); es ampliar la única excepción al tope de 6 de SDD-31
§12.1 (§8-3). La alternativa —que sean argumentos de la puerta sin ser esenciales— rompe D-SIM-4 (la
puerta sólo expone esenciales); dejarlas sólo en «Avanzado» deja la vida contractual fuera del
alcance del usuario de `Ecl`.

**No se configura en la puerta:** la fórmula de Stage 3; la regla de la cola, el riesgo constante
dentro del período y la vida de la operación vencida; la frecuencia de la cuota y la tasa con que se
reparte; qué es una fila sin exposición; la identificación por la columna. Todo lo que el motor
admite sigue en «Avanzado» y en `ecl.config`.

## 4. Contratos de datos (I/O)

- **Entrada.** Lo de FLUJO-GUIADO-IFRS9 §4 más, opcionales, dos columnas de fecha (las acepta
  `pandas.to_datetime` sin ambigüedad: ISO o tipo fecha) y una de cuota (numérica, ≥ 0, en la moneda
  de la exposición). Por fila: otorgamiento ≤ corte; un vencimiento anterior al corte es una
  operación vencida (§3.2-4), no un error; un vencimiento anterior al otorgamiento sí lo es, con la
  fila nombrada. Un valor vacío en una fila es «sin fecha» o «sin cuota» para esa fila (§3.2-6,
  §3.3). Todo esto se valida sólo en las operaciones con exposición (§3.5).
- **Salida.** Las columnas y campos aditivos de §3.2 y §3.5; el `detail` con el identificador del
  usuario (§3.6).
- **Invariantes.** Sin las tres columnas, D-CRE-2 y D-CRE-3 dejan la ECL bit a bit como la deja la
  capa A (sólo cambia el hash, por las claves nuevas); la ECL de `Ecl` sobre el paquete es la de F4
  (ahora 4.786.739); la suma de la ECL por operación es la total; `n_stage1 + n_stage2 + n_stage3 =
  n_rows` con `n_rows` las operaciones con exposición; la curva de supervivencia publicada no cambia
  con esta enmienda.

## 5. Casos borde

Una fecha que no se puede leer (error con la columna y la primera fila); otorgamiento posterior al
corte (error); vencimiento anterior al otorgamiento (error); vencimiento ya pasado con saldo (un
período, contado); vida que pasa la curva (la cola, declarada con su exposición); una curva sin
ningún período con incumplimientos (`DATO-INSTITUCIONAL-SUR-2`, ya declarado: no hay cola que
extender); menos de tres períodos con incumplimientos (la media de los que haya); antigüedad mayor
que el horizonte de la curva (toda la vida en la cola, declarada); las fechas con
`term_structure_source` `forward` o `markov` (requisito por contexto); todas las filas con EAD = 0
(error: no hay cartera que provisionar); un dato inválido en una fila con EAD = 0 (no se valida:
§3.5); la cuota sin `maturity_date_col` o con `ead.method = "ccf"` (requisitos por contexto); una
cuota que no cubre el interés (no amortiza); una cuota que no paga el saldo al vencimiento (saldo
expuesto hasta el vencimiento); EIR cero (la tabla resta la cuota sin interés); un identificador
repetido (error con los repetidos); `survival.input.id_col` y `row_id_col` distintos (requisito por
contexto); `stage3_direct=False` con operaciones en Stage 3 (declarado, §3.1).

## 6. Gates y controles negativos de ESTA enmienda

Un control negativo por regla, en paralelo, cada uno en su copia del árbol (RUNBOOK §6):

1. **D-CRE-1:** el golden de la ECL de F4 y de `Ecl` sobre el paquete en 4.786.739; Freddie Mac en
   3.028.897 por el motor (fuera de CI: script de evidencia). CN: devolver la constante a `False` →
   rojo con 3.423.116.
2. **D-CRE-1, declaración:** con `stage3_direct=False` y Stage 3 > 0, «Supuestos» y «Qué revisar» lo
   dicen. CN: retirar la línea → rojo.
3. **D-CRE-2:** un caso a mano —curva de tres períodos con hazards distintos, edad 1,5, vida 1,25
   períodos— con la PD de cada tramo calculada en el test; y las cifras de §3.2 con el motor sobre una
   muestra reproducible. CN: redondear la edad hacia abajo → rojo.
4. **D-CRE-2, la cola:** una curva con su último período sin incumplimientos extiende con la regla
   de §8-6. CN: extender el último período → rojo.
5. **D-CRE-2/3, sin columnas:** proyección canónica de F4 y de una corrida de Lending Club bit a bit
   iguales a las de la capa A salvo el hash. CN: amortizar sin cuota → rojo.
6. **D-CRE-3:** la tabla contra la fórmula cerrada del saldo; una cuota de sólo intereses deja la EAD
   constante. CN: amortizar la cuota que no cubre el interés → rojo.
7. **D-CRE-5:** conteos de §3.5 sobre una cartera con filas de EAD 0, una de ellas con una LGD
   inválida; la ECL igual y la corrida `done`. CN: separar las filas al publicar en vez de tras la
   EAD → rojo.
8. **D-CRE-6:** el detalle sale con el identificador; un repetido falla con su nombre; columnas
   distintas en curva y provisión se detienen antes de correr. CN: volver a publicar el índice →
   rojo.
9. **Simplicidad:** golden de esenciales (`provisioning_ifrs9` 10), `HOJAS_DEL_FORMULARIO`, el
   ledger de opciones, el espejo del front y las cinco cifras (§13). CN: un esencial de más → rojo.
10. **Copy:** los rótulos nuevos por el copy gate y el gate de códigos internos (ningún
    `FALTA-DATO`/`curve_start` en el copy público).

Codex sobre el código de cada capa, con tope de tres pasadas y criterio declarado.

## 7. Lo que esta enmienda NO hace

No cambia la curva de supervivencia (ajuste, coeficientes, períodos); no agrupa períodos con pocos
incumplimientos; no adopta la PD de origen ni las covariables actuales (§3.4, H7); no lee
condicionadas las curvas de `forward` ni de `markov` (§3.2-7, H7); no separa la historia en otro
archivo (§3.5); no implementa el panel EAD(t) (CT-3 sigue reservado); no toca LGD ni CCF (H3); no
decide PIT (H7); no cambia el staging por mora y marca ni sus presunciones; no regenera el dataset
del paquete; no programa nada.

## 8. Lo que Cami decide

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| 8-1 | La enmienda en su conjunto (D-CRE-1…8) | (a) **aprobar y programar la capa A en la sesión siguiente**; (b) aprobar con cambios; (c) no aprobar | **(a)** |
| 8-2 | Dónde cambia Stage 3 a PD = 1 (D-CRE-1) | (a) puerta y preset F4, default de fábrica intacto; (b) **además el default de fábrica** (reabre D-ECL-4 sólo para `stage3_direct`) | **(b)**: causa raíz; cuesta dos goldens en el repo (§3.1) |
| 8-3 | Esenciales de `provisioning_ifrs9` 7 → 10 (D-CRE-8) | (a) **ampliar la excepción a 10**; (b) las tres columnas sólo en «Avanzado» y en la puerta completa | **(a)**: sin ellas en la puerta, la vida contractual y la cuota no llegan al usuario de `Ecl` |
| 8-4 | Releases (D-CRE-7) | (a) **A en 2.6.0 y B en 2.7.0**; (b) A + B en 2.6.0 | **(a)**: Stage 3 es el mayor efecto y el cambio más chico |
| 8-5 | La PD de origen (D-CRE-4) | (a) **diferir a H7 con la evidencia**; (b) conectar ya la columna de PD de origen en la puerta; (c) inferirla ya (capa C) | **(a)** |
| 8-6 | La cola de la curva (D-CRE-2) | (a) **la media de los tres últimos períodos con incumplimientos** (Freddie Mac −21,1 %); (b) el último período con incumplimientos (−37,1 %) | **(a)**: el último período suele estar observado sólo en parte y su hazard sale bajo (§1.3); la media es la prudente |

## 13. Simplicidad (SDD-31)

- **Entrada mínima:** la de FLUJO-GUIADO-IFRS9 más tres columnas **opcionales** (otorgamiento,
  vencimiento y cuota). Se infieren y se declaran: la antigüedad y la vida en períodos de la curva,
  la tabla de pagos cuando hay cuota, desde qué período se extiende la cola y la exclusión de las
  filas sin exposición.
- **Qué NO se configura (§3.8):** la fórmula de Stage 3, la regla de la cola, el riesgo constante
  dentro del período, la vida de la operación vencida, la frecuencia y la tasa de la tabla de pagos,
  qué es una fila sin exposición y la identificación por columna.
- **Campos esenciales:** `survival` 5 (sin cambio); `provisioning_ifrs9` **10** (§8-3); el resto en
  «Avanzado».
- **Presupuesto de perillas:** **tres** hojas (§3.8), cada una con su evidencia.
- **Resumen por etapa:** «Cartera» cuenta operaciones con exposición y filas de historia; «Curva de
  PD» no cambia; «Provisión IFRS 9» dice la regla de Stage 3, la antigüedad, la vida contractual, la
  cola con su exposición, las operaciones vencidas y la tabla de pagos; el resumen final lo lleva a
  «Supuestos» y «Qué revisar». Decisiones humanas: las de FLUJO-GUIADO-IFRS9, sin nuevas.
- **Notebook mínimo:** «Tu primera provisión IFRS 9» sigue en **21** líneas (el paquete no trae
  fechas ni cuota); cambia su cifra (4.786.739). Las tres columnas se muestran en un bloque de la
  guía ejecutado en CI sobre un archivo sintético pequeño y determinista, generado en el propio
  bloque.
- **Las cinco cifras** (golden `test_simplicidad_ifrs9.py`):

| Cifra | Hoy (`629e422`) | Después |
|---|---|---|
| Líneas de usuario | 21 | 21 |
| Esenciales por sección | `survival` 5, `provisioning_ifrs9` 7 | 5 y **10** |
| Perillas de las tres secciones de cálculo | 230 (158 + 24 + 48) | **233** (158 + 24 + 51) |
| Segundos al primer resumen (paquete) | 6,5 | ~6,5 (sin las columnas no hay cálculo nuevo) |
| Conceptos antes del primer resultado | 5 (`Ecl`, `materialize`, `run`, `exclude`, `resume`) | 5 |
