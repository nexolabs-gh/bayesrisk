# Enmienda H3 — PD, LGD y provisión interna con historia separada

**TL;DR:** completar el recorrido del modelador reutilizando el motor interno y F1. Añadir una
puerta guiada, resúmenes y entregables propios; ofrecer un ajuste LGD sobre historia declarada,
evaluarlo fuera del ajuste y aplicar un predictor congelado a una cartera sin LGD observada.
Conservar la aritmética grupal, las rutas actuales y sus advertencias. Esto no acredita una LGD
mejor ni resuelve recuperaciones incompletas.

| Campo | Valor |
|---|---|
| Estado | **Propuesta para revisión de Cami; no aprobada; no autoriza implementación** |
| Autor / fecha | Codex, 2026-10-20 (S61) |
| Base medida | `bce872f8b15d45fb676cc0d1388366b7221062de` |
| Hito | H3 del plan vigente; no amplía H10, H9R ni las campañas de calibración |
| Contratos | SDD-28, SDD-31, D-LGD, D-ART, D-ESC-7, D-FIR-9, D-HLC |
| Revisión independiente | **APPROVE del diseño en la segunda y última pasada (S61)**, gpt-6-astra/xhigh efectivos acreditados. No equivale a aprobación de Cami ni de implementación |

## 1. Propósito y responsabilidad

Un modelador debe poder llegar desde su PD y su severidad a una provisión interna explicable,
guardar lo utilizado y aplicar una LGD ajustada a operaciones cuyo resultado todavía no conoce.
La entrega propuesta tiene dos capas, ambas necesarias para declarar completado **este alcance H3**:

- **A — uso y entrega:** `Provision`, ruta autónoma y composición con `Scorecard`, esenciales,
  resumen, pantalla, informe y tablas descargables. Conserva las cinco formas LGD actuales y la
  tasa de pérdida directa por configuración completa. Corrige el copy tasa/monto (§1.1).
- **B — historia y aplicación:** `Lgd`, ajuste fraccional sobre incumplimientos con resultado
  completo declarado, evaluación separada y predictor reutilizable; rama interna `fitted`.
  Las tres puertas entregan lo mismo antes de declarar la capa terminada.

La aprobación del diseño no publica una release ni autoriza recapturar la demo o fixtures
existentes. La capa A sola sería un adelanto experimental, **no H3 terminado**.

Fuera: modelos nuevos de PD/EAD, entrenamiento ML, LGD macrocondicional/downturn, inferencia
causal, censura de recuperos, recuperos longitudinales con múltiples flujos, selección automática
de variables, tuning, imputación, WoE para LGD, cambios CMF/IFRS9, normativa local, cambios a HL o
un contraste sustituto. Tampoco se convierte `group_historical` en una tabla histórica separada:
su contrato actual sigue siendo la media simple dentro del grupo del frame recibido.

### 1.1 Brechas medidas, no porcentaje estimado

| ID | Medición en la base | Consecuencia / entrega propuesta |
|---|---|---|
| M1 | `guided/__init__.py` exporta Scorecard, Ecl, Monitor y Comparison; no H3 | Puerta `Provision` y composición explícita con F1 |
| M2 | `LgdEngine.estimate` ajusta y predice con el mismo `exog`; no conserva el ajuste | Separar ajuste/evaluación/aplicación mediante una capacidad aditiva |
| M3 | Sonda de 240 filas: quitar `lgd` produce `LgdError`; sustituirla por `1-lgd` cambia las predicciones hasta **0,5898266228** | La ruta vigente no sirve como predictor congelado de una cartera sin objetivo |
| M4 | Las regresiones consumen `1-recovery`, pero el schema dice «MONTO» y «No es una fracción» | Corregir descripción y ayuda de ambas regresiones; no cambiar cálculo |
| M5 | `provisioning_internal`: 44 nodos en el barrido del formulario, cero marcas esenciales y ninguna declaración de esenciales | Definir esenciales condicionales y plegar el resto |
| M6 | Mapas de etapas/resúmenes no incluyen provisión interna; `family_of` cae a scorecard | Una fuente común de resumen, tabla y advertencias para notebook, UI e informe |
| M7 | El paso publica detail/groups/summary/result/card, sin predictor ni diagnóstico LGD | Nuevos artefactos tipados para la capacidad de entrenamiento |
| M8 | Export de etapa usa el mapa de resúmenes; el inventario per-operation del informe no incluye el detail interno | Excel de etapa y export explícito del detalle interno, cotejados en el archivo final |
| M9 | F5 empaquetado: 6.000 filas, LGD provista; ejemplo público de 15 líneas | Reutilizar F5; crear un ejemplo adicional de historia separada sin recapturar F5 |
| M10 | Aceptación LGD existente usa PD inyectada; parametriza fractional/workout, no acredita cadena F1→LGD fuera del ajuste | Gates específicos de la cadena combinada y del predictor congelado |

La sonda tasa/complemento coincide hasta `1,11e-16`; un monto 100 veces mayor se rechaza por rango.
Un monto pequeño también puede pasar el rango: el motor no puede deducir las unidades de una cifra.
La corrección del texto se gatea además por rama y por cálculo, no sólo por una búsqueda de palabras.

Evidencia estática principal:
[`lgd.py`](../../src/bayesrisk/provisioning/lgd.py),
[`config interno`](../../src/bayesrisk/provisioning/internal/config.py),
[`paso interno`](../../src/bayesrisk/provisioning/internal/step.py),
[`resúmenes`](../../src/bayesrisk/guided/summaries.py),
[`export`](../../src/bayesrisk/guided/export.py),
[`jobs`](../../src/bayesrisk/ui/jobs.py),
[`tests LGD`](../../tests/unit/test_internal_provisioning_lgd_modelada.py).
Las sondas S61 son sintéticas y de contrato; **no** son validación estadística ni una cuarta
revisión de S60. La evidencia reproducible y los resultados completos se conservan en el cierre
operativo privado; este documento no publica datos institucionales.

## 2. Contexto y ubicación en la arquitectura

**D-H3-1 — una aritmética, tres puertas.** `Provision` reutiliza el paso
`provisioning_internal`, la API `run` y `Study`. `from_scorecard` compone el config de un
`Scorecard` con ese paso; no implementa otro scorecard ni toma como entradas los resultados
obsoletos de una corrida anterior. La ruta autónoma materializa la PD declarada como el artefacto
que ese paso ya consume. Se amplía el enlace interno de `_PuertaGuiada` con `artifacts=`, por
defecto vacío: el `run` público ya lo admite, la base guiada aún no lo pasa.

**D-H3-2 — dominio de entrenamiento separado.** La sección opt-in `lgd_training` y su paso
trabajan sobre una historia de recuperaciones, distinta de la cartera de provisión. Una corrida
de `Lgd` produce `lgd_training.fitted_model` y evaluación; la corrida de `Provision` consume ese
modelo mediante su tabla declarativa `lgd_training.model_table`, inyectada para la rama `fitted`.
No ejecuta el paso de entrenamiento sobre la cartera.
La composición PD+LGD es F1 sobre su población de PD más **aplicación** del predictor LGD previamente
ajustado. Entrenar LGD usa otro `Study`, otra identidad de datos y otra población.

`data.target` binario y las particiones F1 no se reutilizan como objetivo/partición de LGD.
En `Lgd`, `data` sólo carga y tipa la historia: sin target binario ni partición automática.
En `Provision` autónoma sucede lo mismo; `from_scorecard` conserva íntegros los contratos F1.

**Población de la composición.** `from_scorecard` usa una variante aditiva del paso interno,
`provisioning_internal.type="full_population"`; el default `standard` sigue intacto. Esta
variante une por índice `calibration.calibrated_pd_frame` con
`calibration.out_of_model_calibrated_pd_frame`, o `model.raw_pd_frame` con
`model.out_of_model_pd_frame`, según `pd_source`. Declara las dependencias del principal y las
opcionales del complementario en el DAG. No sobrescribe ningún artefacto F1; publica una copia
de la tabla consumida (`provisioning_internal.pd_input`) y conteos de procedencia
(`provisioning_internal.pd_coverage`) como artefactos adicionales de esta variante.
Índices duplicados dentro de una tabla o solapados entre ambas son error, incluso si coinciden
sus PD. La unión debe cubrir **todo `data.frame`**. Las filas adicionales se cuentan y no agregan
exposición. Si TTD está desactivada, falló o no cubre todas las operaciones, sólo puede calcularse
provisión si el principal ya cubre el frame completo; de otro modo se detiene esta etapa y
conserva los resultados F1, con conteo de operaciones/exposición sin PD. No puntúa de nuevo,
no sustituye PD por cero y no recorta silenciosamente la cartera. Para esas operaciones la persona
debe resolver la puntuación o traer una PD completa por la puerta autónoma.

La variante se selecciona en el nuevo recorrido H3 guiado de pantalla y en la composición por
código; no cambia el preset F5 ni la siembra de los trabajos antiguos. La puerta completa declara
el mismo `type` explícito. Ampliar el literal de un campo existente no añade una hoja de cálculo;
no se introduce una perilla de política de cobertura.

## 3. Conceptos y fundamentos

**D-H3-3 — preservar la provisión grupal.** Para cada grupo `g`, salvo la rama histórica que ya
tiene su agregación propia:

`E_g = Σ E_i`; `PD_g = Σ(E_i PD_i)/E_g`; `LGD_g = Σ(E_i LGD_i)/E_g`;
`P_g = redondeo(E_g · PD_g · LGD_g)`.

El detalle distribuye `P_g` según exposición, con el comportamiento de redondeo vigente. No se
presenta como `E_i PD_i LGD_i`. Caso de control: exposiciones `(100,100)`, PD `(0,1;0,9)` y LGD
`(0,2;0,8)` dan **50,00** por grupo; sumar productos individuales daría **74,00**. La sonda
exige rojo con 74 y vuelve a verde con 50. Exposición grupal cero, bandas, empates, piso/techo,
fuentes de PD, media simple histórica y tasa de pérdida directa conservan sus reglas actuales.

**D-H3-4 — mismo estimador fraccional, población distinta.** La capacidad nueva ajusta el GLM
binomial con enlace logit ya utilizado por `fractional_response`, sin ponderación por exposición:
`μ_i = logistic(β₀ + x_i'β)`, objetivo en `[0,1]`. Intercepto incluido, covariables numéricas
crudas y finitas; no selección ni transformaciones aprendidas. Una observación vale una operación,
no una unidad monetaria. La exposición pondera la provisión, no el ajuste. La nueva capacidad
fija este estimador; no incorpora un selector de algoritmos. Beta y workout siguen disponibles
por las rutas actuales. No se redefine ni sustituye `LgdEngine.estimate()`.

El predictor guarda coeficientes y orden de columnas. `predict` sólo evalúa la media; no lee el
objetivo ni ajusta otra vez. La separación técnica está soportada por la API oficial de
[GLM.predict 0.14.6](https://www.statsmodels.org/v0.14.6/generated/statsmodels.genmod.generalized_linear_model.GLM.predict.html)
y contrastada con su
[código oficial](https://www.statsmodels.org/v0.14.6/_modules/statsmodels/genmod/generalized_linear_model.html).
Ambos aceptan una matriz de aplicación distinta y usan los parámetros ya ajustados.
Esto verifica la operación del software; no prueba transportabilidad económica de la LGD.

**D-H3-5 — evaluación descriptiva fuera del ajuste.** Publicar tamaño, media observada/predicha,
sesgo medio `mean(pred-observed)`, MAE y RMSE por muestra. Comparar con la constante igual a la
media de LGD de entrenamiento, calculada sólo allí. Sin p-valores, bandas verde/rojo, mínimo
arbitrario ni proclamación de validación. No elegir modelo, variable, corte ni clipping mirando
evaluación. Temporalidad y representatividad no quedan certificadas por separar filas.

## 4. API pública propuesta

Nombres nuevos experimentales; no existen todavía. Las firmas siguientes fijan el contrato de
dominio; `name`, `run_dir`, `document`, `formats` y tracking siguen el molde guiado actual.

```python
Provision(data, *, as_of: str, portfolio: str, exposure: str,
          pd: str, lgd: str | LgdModel, id: str | None = None,
          name="provision", run_dir="bayesrisk-runs")
Provision.from_scorecard(scorecard: Scorecard, *, as_of: str,
          portfolio: str, exposure: str, lgd: str | LgdModel,
          name="provision", run_dir="bayesrisk-runs") -> Provision
Lgd(history, *, target: str, features: Sequence[str], entity: str,
    sample: str, default: str, resolved: str,
    id: str | None = None, purpose: str | None = None,
    assumptions: Sequence[str] = (), limitations: Sequence[str] = (),
    name="lgd", run_dir="bayesrisk-runs")
Lgd.model_ -> LgdModel                    # sólo tras ajuste terminado
LgdModel.predict(frame: DataFrame) -> DataFrame  # columna lgd, índice preservado
LgdModel.to_frame() -> DataFrame          # tabla plana declarativa de §6
LgdModel.from_frame(table: DataFrame) -> LgdModel  # schema cerrado, sin pickle
```

Las puertas ofrecen `run(until=...)`, `resume`, `summary`, `results`, `config`, `config_hash`,
`to_yaml`, `export_excel`, `export` y `study`, con la semántica guiada existente. `run` devuelve
la puerta; los errores siguen `raise_on_error`. `Study` no adquiere métodos `summary/export`.
`study.save` y `Study.load(trust=...)` siguen su contrato; el predictor se recupera de
`artifacts.get("lgd_training", "fitted_model")` y se valida antes de usarlo.

En la puerta autónoma `pd` nombra una columna del frame de aplicación. Se crea la tabla PD
alineada por ID/índice y se inyecta en el dominio configurado; eso se declara como entrada externa.
No se confunde con una PD ajustada o calibrada en esa corrida. `lgd` string significa columna
provista; `LgdModel` significa la rama `fitted`. Los otros métodos se seleccionan con el config
completo o en pantalla: se conserva el acceso sin añadir seis constructores equivalentes.
`from_scorecard` hereda el snapshot, configuración, decisiones y directorio de proyecto del
scorecard como **nuevo proyecto** bajo el nombre/directorio de destino, con identidad propia;
nunca sobrescribe su evidencia. Un destino que colisiona con el proyecto de origen se rechaza.
El ID de operación de `Lgd` y `Provision` reutiliza el resolvedor guiado hacia
`data.schema.index_col`/`data.schema.unique_keys`. Sin `id`, sólo se verifica unicidad del índice
técnico y se advierte que no se verificó unicidad económica de operaciones. `entity` es distinto:
identifica la unidad de separación, puede repetirse dentro de una muestra y no sustituye ese ID.

Pseudocódigo del recorrido modelado (13 líneas de usuario; archivos preparados, no API existente):

```python
from bayesrisk import Lgd, Provision

lgd = Lgd("historia.parquet", target="lgd", features=["ltv", "plazo"],
          entity="deudor", sample="muestra", default="incumplio", resolved="completo")
lgd.run()
lgd.summary()
cartera = Provision("cartera.parquet", as_of="fecha", portfolio="cartera",
                    exposure="exposicion", pd="pd", lgd=lgd.model_)
cartera.run(until="provisioning_internal")
cartera.summary()
cartera.resume()
cartera.export_excel()
cartera.study.save("evidencia-provision")
cartera.export("provision.zip")
```

El notebook entregado también enseña la tabla de evaluación y la salvedad de población; el
ejemplo mínimo de provisión con LGD provista no necesita importar `Lgd` ni preparar historia.
El ejemplo modelado sin `id` ni declaraciones institucionales debe mostrar sus ausencias;
un ejemplo ampliado enseña `id`, `purpose`, `assumptions` y `limitations`. La tabla de coeficientes
se exporta con `model_.to_frame().to_csv(..., index=False)` o Parquet y se importa con pandas
y `LgdModel.from_frame`; no se requiere cargar un `Study` para aplicar un predictor.

## 5. Configuración y pantalla

**D-H3-6 — adiciones sin mover configuraciones antiguas.** `lgd_training` sólo se serializa si
está declarada, conforme D-ESC-7. Campos de dominio nuevos, todos esenciales y sin defaults:

| Campo | Tipo / validación | Propósito |
|---|---|---|
| `target_col` | str no vacía | LGD realizada, fracción `[0,1]` |
| `covariate_cols` | tuple[str,...] no vacía, única | Covariables numéricas crudas; excluye los otros cinco campos |
| `entity_col` | str no vacía | Unidad de separación declarada; debe identificar al deudor si hay varias operaciones |
| `sample_col` | str no vacía | Valores exactos `train`, `evaluation`, `excluded` |
| `default_col` | str no vacía | Booleano real o 0/1, sin nulos |
| `resolved_col` | str no vacía | Resultado completo según definición institucional, booleano real o 0/1 |

`schema_version`/`type` son constantes técnicas ocultas, no perillas. No hay semilla, proporción
de holdout, selector automático, pesos de exposición ni ajuste de enlaces. La metodología del
objetivo, fecha de observación, población y disponibilidad de covariables se documentan en la
ficha/proyecto; la herramienta no las infiere ni las certifica a partir de los nombres.

La unión LGD interna gana `method="fitted"` con `lgd_floor` y `lgd_cap` existentes; no exige
`lgd_col`, `recovery_col` ni covariables configuradas por duplicado. El artefacto tipado trae su
schema. La entrada al paso es siempre `lgd_training.model_table`; la guiada convierte a esa
tabla el `LgdModel` recibido. Una rama `fitted` sin tabla, o una tabla con otra rama, falla antes
del cálculo. La tabla se valida en el dominio y sólo entonces se construye el DTO fijo.
Las otras cinco ramas y el default `provided` mantienen su dump y hashes. No cambia el
`IfrsLgdConfig` ni el default de `lgd_modelada`.

Pantalla: el trabajo existente `lgd_modelada` conserva sus modos y agrega acceso explícito a
«Ajustar con historia separada»; este recorrido corre `data → lgd_training → report → governance`.
No se sustituye silenciosamente el trabajo antiguo. El recorrido nuevo PD+LGD H3 selecciona la
variante `full_population`; los trabajos anteriores siguen accesibles con su configuración.
La UI carga **sólo la tabla declarativa** mediante la puerta HTTP tabular existente; el catálogo
añade exclusivamente `lgd_training.model_table` a la allowlist de los trabajos consumidores.
Conserva formatos CSV/XLSX/Parquet, límites de carga, tokens, Origin, validación de ruta y errores
del transporte actual. **No carga Study, joblib ni objetos Python por HTTP**: D-PUE-1/2 permanecen
vigentes. `fitted_model` no se añade a la allowlist HTTP. No hay nuevo endpoint genérico ni
campo que permita elegir clases a construir. La ruta PD+LGD aplica la tabla validada, no entrena
con la cartera. YAML conserva round-trip
y el mismo config que las otras puertas; los datos/modelos externos se adjuntan por D-ART.

**Precisión propuesta de D-PUE-6-bis.** La tabla de coeficientes tiene semántica **global del
modelo**, no una fila por operación. La fija el catálogo para la clave exacta
`lgd_training.model_table`, no un campo elegible por el cliente. Para esa clave, materialización,
preflight y ejecución validan el schema del modelo sin emparejarlo con la cartera, normalizar su
índice contra ella ni exigir igual número de filas. `position` ordena los coeficientes. Declarar
llave o modo de emparejamiento para esa tabla es error. El formulario no ofrece ese selector ni
el aviso de alineación posicional; informa que es un modelo aplicable a toda la cartera.
Las tablas PD y restantes entradas por operación conservan íntegro D-PUE-6-bis: llave, conteo,
alineación y caveat. No puede eludirse el control enviando una marca «global» para otra clave.
Esta excepción contractual acotada requiere el mismo OK de Cami a H3; no está implementada.

**Declaraciones institucionales.** Reutilizar `governance.purpose`, `assumptions` y `limitations`;
la puerta `Lgd` expone esos mismos campos, y la pantalla los conserva en gobernanza. Si se aportan
supuestos/limitaciones debe aportarse propósito para construir la ficha, conforme al contrato
actual; no se inventa uno. Recomendar que los supuestos describan población/cohortes, definición
y fecha del resultado y disponibilidad temporal de las covariables. No analizar texto libre
para afirmar que es suficiente. Si no hay gobernanza o no se aportaron supuestos, el resumen,
card, informe y Excel dicen **«Declaración de población y objetivo no aportada»**; si existen,
dicen **«Declaración aportada; suficiencia y temporalidad no verificadas»** y muestran el texto.
La ausencia no bloquea el cálculo experimental ni la exportación; bloquea cualquier afirmación
de completitud institucional o validación. Los seis campos de entrenamiento son mapeos,
no declaraciones de hechos externos. Estas reglas valen también por API completa y pantalla.

## 6. Contratos de datos y artefactos

**D-H3-7 — población explícita y particiones sin aprendizaje.** Historia: una fila por operación
con LGD observada, ID de operación declarado mediante `data.schema.index_col`/`unique_keys`
o índice técnico único con la limitación anterior, entidad no nula,
sample válido y flags no nulos. Son elegibles sólo `default=True & resolved=True`.
Las demás filas se cuentan y excluyen; no reciben LGD cero ni se declaran recuperadas. `excluded`
siempre se excluye. Entrenamiento y evaluación deben quedar no vacíos; ninguna entidad puede
estar en ambas muestras elegibles. No se divide por fila a un mismo deudor, ni se inventa una
frontera temporal. Los nulos de objetivo/covariables en filas elegibles detienen; en excluidas
se cuentan sin ajustar. Duplicados del ID declarado (incluidas filas excluidas), del índice
técnico o de columnas detienen antes de filtrar. Un CSV con RangeIndex único no acredita ausencia
de operaciones económicas repetidas; sin ID declarado se mantiene la advertencia.

`resolved` declara disponibilidad de un resultado, **no ausencia de sesgo de selección**.
La declaración de §5 permite describir cómo se seleccionaron las cohortes; siempre se advierte sobre procesos
abiertos excluidos y sobre representatividad no demostrada. No admite afirmar «validado» por
terminar. No elige una cohorte por alcanzar 98 % de recuperación ni considera cero la pérdida
que aún no se observó. No ofrece corrección de censura dentro de este alcance.

Aplicación: no exige target/default/resolved/sample; sólo columnas del predictor, finitas,
índice único, y los insumos de provisión. Columnas adicionales no cambian la predicción. Reordena
las covariables por **nombre almacenado**, nunca por posición del archivo. Ninguna superposición
con entrenamiento convierte la aplicación en evaluación independiente; la procedencia lo dice.

Artefactos nuevos del entrenamiento:

| Clave de `lgd_training` | Contenido |
|---|---|
| `fitted_model` | DTO inmutable `LgdModel`: versión 1, estimador fijo, nombres/orden, intercepto y coeficientes finitos, versión del entorno, hash del config/datos de ajuste y referencia al estudio |
| `model_table` | Representación tabular cerrada del predictor para aplicación y transporte HTTP; no contiene objetos serializados |
| `predictions` | ID, muestra, LGD observada y predicha de filas elegibles; sin reclasificar muestras |
| `evaluation` | Tabla descriptiva de §3, separando train/evaluation y baseline |
| `population` | Conteos por muestra, flags y motivo de exclusión; solapamientos y límites de la declaración |
| `card` | Método, procedencia, convergencia, advertencias y referencia a las tablas anteriores |

La corrida interna mantiene sus cinco artefactos (la variante `full_population` agrega los dos
de §2). Su card/prosa añade procedencia sólo cuando
consume `fitted`, con referencia al estudio de origen; nunca dice que ajustó LGD en aplicación.
La tabla de detalle mantiene el prorrateo grupal. `model_` no existe tras fallo de ajuste.

**Tabla de modelo, formato 1.** Columnas exactas: `format_version` (entero 1), `method`
(`fractional_response`), `position` (entero contiguo desde 0), `term_kind` (`intercept`/`feature`),
`feature` (string), `coefficient` (float64 finito), `source_config_hash`, `source_data_hash`,
`source_run_id`, `fit_environment`, `declaration_status` y `declaration_text` (strings). Primera
fila: position 0, intercept y feature decodificada `__intercept__`; restantes: feature decodificada
no vacía, única y distinta de ese marcador reservado. Metadatos de
origen y declaración son idénticos en todas las filas. Se exige al menos una covariable. Sin
columnas extra, posiciones ausentes/repetidas, métodos desconocidos, NaN/inf, metadatos
inconsistentes ni objetos/callables. Hashes usan el formato vigente de sus identidades, sin
renombrarlas; referencia de origen no autentica contenido. `fit_environment` es texto informativo,
no se ejecuta ni importa. `declaration_status` es `not_provided` o `provided_unverified`; en el
primer caso el texto es el marcador literal `No aportada`, en el segundo es la declaración no
vacía de §5. Se construye **sólo** `LgdModel` desde números/nombres validados.

Representación única del transporte: **feature, source_run_id, fit_environment y declaration_text**
se codifican siempre como `text:` más base64url sin padding de sus bytes UTF-8. Esto incluye el
marcador del intercepto y `No aportada`. Decodificación UTF-8 estricta, alfabeto base64url estricto
y recodificación idéntica obligatoria; no se acepta mezcla con texto plano ni una codificación
alternativa. Las comprobaciones semánticas anteriores se hacen tras decodificar. Hashes conservan
su gramática hexadecimal vigente; method/term_kind/declaration_status son allowlists cerradas.
Así, nombres como `=ratio`, `+saldo`, `-margen`, `@grupo`, `NA` o `001` no se convierten en fórmulas
ni valores ausentes durante el transporte. `to_frame/from_frame` comparten ese codec; la
aplicación, resúmenes y pantalla usan nombres decodificados. Los informes/libros legibles aplican
después la neutralización de fórmulas existente, sin cambiarla ni reimportar esas tablas de
presentación como si fueran el transporte canónico del modelo.

El lector no evalúa expresiones, rutas ni nombres de clase del cliente. CSV usa representación de
float de round-trip y lector con precisión round-trip; las columnas nominales del schema se leen
como texto, sin inferir números, NA o fechas a partir del nombre de una variable o un ID. Esta
lectura tipada se aplica exclusivamente a `model_table`, con el mismo adaptador de dominio en las
tres puertas; los lectores de tablas restantes no cambian. Parquet conserva float64. Excel admite la
tolerancia numérica declarada y no se usa para exigir igualdad bit a bit. Las tres puertas sobre
la **misma tabla ya leída** deben dar resultados iguales. Falsos archivos tabulares que contienen
pickle o versiones futuras se rechazan; no existe fallback a deserialización de objetos.

## 7. Algoritmos y flujo

Entrenamiento: cargar → validar roles/flags/IDs → formar muestras declaradas y registrar
exclusiones → validar soporte y rango completo de la matriz de entrenamiento con intercepto →
ajustar **sólo train** → exigir convergencia y coeficientes finitos → congelar predictor → predecir
train/evaluation → calcular diagnóstico y baseline → publicar artefactos y resumen. Exigir más
filas de entrenamiento que columnas de la matriz; rango deficiente y warnings del ajuste son
errores, sin cambiar automáticamente algoritmo ni eliminar variables.

Aplicación: validar el modelo y sus columnas → calcular `logistic(Xβ)` con orden congelado →
validar finitud/rango → aplicar piso/techo internos vigentes → calcular grupos y provisión con
el motor actual. No fit, imputación, calibración ni selección durante esta etapa.

Alternativas descartadas: ajustar sobre cartera viva (exige una LGD que no se conoce), reutilizar
WoE de PD (supervisión de otro objetivo), cambiar a suma de productos individuales (otra
metodología), partir aleatoriamente en silencio (decisión institucional), y sustituir el motor
compartido (mueve IFRS9 y contratos antiguos). La nueva ruta es explícita; el ajuste in-sample
preexistente queda con su advertencia D-LGD-9.

Costo dominante del GLM: matriz `n×p` y solución iterativa; sin búsqueda combinatoria ni tuning.
La predicción cuesta `O(n p)`. No se promete un tiempo de ajuste universal.

## 8. Casos borde y errores

| Caso | Comportamiento |
|---|---|
| Falta LGD observada en aplicación con `fitted` | Permitido; no se consulta |
| Falta target en historia elegible, rango inválido, NaN/inf | Error legible con columna y muestra; nunca imputar |
| Objetivo con 0 y 1 | Admitido por fraccional; no extenderlo a beta antigua |
| Todo objetivo igual, separación perfecta o matriz singular | Error de ajuste identificable; no neutralizar con LGD media silenciosa |
| Entidad en train y evaluation | Error previo al fit con conteo y ejemplo de ID en evidencia local |
| Sólo filas excluidas o evaluación vacía | No se publica predictor como entrega H3; error con conteos |
| Columnas de flags o roles confundidas con covariables | Error de config; no dejarlas predecir el resultado |
| Categórica textual como covariable | Error accionable; no introducir codificación supervisada ni automática |
| Modelo de versión/tipo desconocido o coeficientes alterados no finitos | Error antes de aplicar; no fallback a `provided` |
| Artefacto PD desalineado o modelo LGD ausente | Mantener error del consumidor y explicar el insumo requerido |
| Estudio externo sin confianza explícita | Se mantiene rechazo de `Study.load`; no deserializar por otra puerta |
| Modelo por HTTP | Sólo tabla cerrada; Study/joblib siguen prohibidos, aunque se renombre el archivo |

Los errores usan excepciones de dominio y localización de campo bajo el molde existente. Los
códigos internos no se convierten en texto público. Los ejemplos de IDs se quedan en evidencia
de la persona y nunca se copian al repositorio público.

## 9. Reproducibilidad, identidad y auditoría

**D-H3-8 — identidad de config y evidencia externa separadas.** Igual config y entradas producen
los mismos resultados entre puertas, con procedencia de entrada declarada. La presencia de
artefactos externos sigue D-ART-7: no son reconstruibles desde config+datos y no entran al
`config_hash`. El modelo incorpora referencias a su estudio, config y datos de entrenamiento;
la provisión registra cuáles consumió. Una referencia o huella de contenido no autentica al autor.

`Study.save/load` conserva confianza explícita y verificación actual de `config_hash`; esta
enmienda **no** agrega firma, autenticación ni digest por archivo joblib. El proyecto exportado
incluye los estudios/entradas necesarios para reconstruir la ruta y sus advertencias. Un config
aislado no se promociona como evidencia autosuficiente. No guardar tablas privadas dentro de la
representación pública del predictor; guardar su referencia y la evidencia en el proyecto local.

Sin azar nuevo. Se registran versiones y diferencias numéricas del entorno; igualdad entre
guardar/cargar en el mismo entorno, tolerancia declarada contra statsmodels como oráculo externo
(`atol=1e-12`, `rtol=1e-10` para medias, no tolerancia monetaria). La provisión reconcilia al
decimal con las reglas existentes. `run(until)` conserva su hash de prefijo; `resume()` es una
**corrida nueva y completa**, no reutiliza artefactos de pasos previos. Un predictor externo
declarado sigue siendo una entrada explícita, no un cache de entrenamiento.

## 10. Dependencias

Reutiliza `data`, `provisioning`, `guided`, `report`, `governance`, `ui`, `Study` y la puerta D-ART.
No añade dependencia externa: pandas/numpy/scipy/statsmodels del extra `scoring` y los extras
actuales para UI/Excel/Word. El mínimo vigente de statsmodels es `>=0.14`; la sonda usó 0.14.6.
Imports perezosos y error que indique el extra requerido. Licencias y compatibilidad se verifican
con el inventario/gate vigente; no se presupone equivalencia numérica entre todas las versiones.

## 11. Estrategia de aceptación y censo bidireccional

**D-H3-9 — una capacidad termina cuando se consume.** Por cada artefacto/decisión, enumerar
productor y consumidores: puerta completa, guiada, UI, resumen text/HTML/JSON, panel, informe
HTML/PDF/Word, Excel, CSV, ZIP, documentación y ejemplo instalable. El conjunto de enlaces exigidos
menos implementados y el de implementados sin contrato deben quedar vacíos. No contar palabras ni
tests como sustituto. Informes y exports se cotejan contra los artefactos, incluyendo detalle
completo, método y advertencias de población; no basta un HTML intermedio.

Gates y controles negativos necesarios al implementar:

1. Oráculo grupal 50 frente a 74; provisión modelada frente a la misma LGD por columna, al decimal.
2. Aplicación sin target; cambiar cualquier target de aplicación no mueve un bit; instrumentar
   fit para que falle si se llama durante predict. Recuperar predictor desde Study sin reajuste.
3. Envenenar el objetivo de evaluación cambia sus métricas, no coeficientes/predicciones del modelo.
   Entidad solapada, estado desconocido, datos no finitos y matriz singular nacen rojos.
4. Recuperación tasa vs monto en las dos regresiones y workout; alterar la ayuda de una rama debe
   ser rechazado. Verificar soporte 0/1 sin trasladarlo a beta.
5. Igual config/hash/resultado entre puertas y paridad de inputs/lineage salvo procedencia.
   Probar PD externa autónoma y cadena combinada F1→aplicación LGD→provisión.
6. Conservar hashes/YAML de F1/F3/F4/F5, resultados F1 bit a bit y rutas IFRS9/LGD antiguas. No
   repetir campañas verdes: usar sus oráculos y sólo correr regresiones afectadas.
7. Todas las formas LGD antiguas, la nueva, tasa directa, dos fuentes PD y tres agrupaciones:
   inventario explícito de combinaciones válidas e inválidas; sin producto cartesiano ciego.
8. Resumen parcial, corrida fallida, libros por etapa, CSV detalle y ZIP: inspeccionar archivos
   finales. Los negativos quitan enlaces/artefactos exigidos y deben dar rojo, luego restaurar verde.
9. Wheel instalado fuera del checkout: imports, datasets, notebook y recorrido completo. Un módulo
   que sólo funciona desde tests no está entregado.
10. Transporte del predictor: round-trip CSV/Parquet/Excel, versiones/campos/dimensiones
    inválidas, valores no finitos, nombres nominales como `NA` o `001`, nombres de clase/pickle
    disfrazados y metadatos inconsistentes. Conservar el gate que prohíbe Study.load/joblib en UI.
    Codec estricto con `=`, `+`, `-`, `@`, comillas y CR/LF; texto plano, base64url/UTF-8 inválidos
    o representación no canónica ponen rojo. Un modelo de tres coeficientes aplica a una cartera
    de 6.000 filas por las tres puertas; una tabla PD de tres filas no puede eludir su control de
    cobertura/conteo. Preflight, catálogo, formulario y ejecución acuerdan la semántica global.
11. Composición: PD principal más fuera del ajuste con ambas fuentes, solapamiento, TTD apagada,
    fallo de TTD y cobertura incompleta. No cambia F1, no desaparece exposición ni se inventa PD.
12. ID de operación repetido con RangeIndex distinto, entidad repetida dentro de una muestra,
    entidad cruzada y ausencia de ID; cada caso conserva su error o advertencia correspondiente.
    Declaraciones ausentes/presentes en las tres puertas y todos los entregables, sin inventar ficha.

Datos para aceptación: F5 actual para PD+LGD provista; conjunto sintético nuevo de historia/cartera
separadas con oráculos y extremos para la ruta modelada; al menos un conjunto externo real con
procedencia y uso admisible para evaluar transportabilidad y límites. Hay antecedentes de análisis
LGD externo en D-FIR-9; no sustituyen esta aceptación ni acreditan automáticamente derechos para
redistribuir datos. **No se ha ejecutado ni acreditado esa aceptación real en S61.** Antes de
iniciar capa B, inventariar disponibilidad/licencia, definición de default, recuperaciones,
madurez, covariables disponibles y particiones; si no hay un conjunto admisible, no declarar H3
cerrado ni fabricar tres ejemplos sintéticos como si fueran evidencia real. Su selección debe
mantenerse en este alcance y no convertirse en campaña H10 C/D.

## 12. Decisiones de Cami y riesgos

**Recomendación:** aprobar, tras revisión independiente del diseño, **A+B con estos límites**.
Cerrar sólo interfaz dejaría sin resolver el uso de LGD en cartera viva. A+B reutiliza el
estimador y separa sus poblaciones; no abre una investigación de nuevos modelos ni recuperos
censurados. La aprobación de implementación debe constar expresamente después de esta revisión.

| Decisión | Propuesta concreta | Impacto |
|---|---|---|
| Alcance H3 | A+B, sin cambiar motores previos | Mayor trabajo que sólo interfaz; resuelve la aplicación sin objetivo |
| Nueva LGD ajustada | Fraccional fija, covariables numéricas, muestras declaradas | Sin selector nuevo ni garantía de superioridad; beta histórica sigue disponible |
| Evidencia de calidad | Evaluación descriptiva y cohortes declaradas, sin veredicto | No se atribuye independencia del pipeline completo ni valida selección/madurez |
| Término de H3 | Tres puertas, artefactos finales, corpus de aceptación y revisión | No llamar 100 % al diseño ni a CI verde |
| Esenciales workout | Excepción de nueve campos explícitos de §13 | Evita esconder cinco insumos necesarios de recuperos; no añade parámetros de cálculo |

Riesgos medidos: D-LGD-9 es un límite vigente que se amplía **sólo por una nueva ruta**, el motor
compartido protege IFRS9, y las tablas externas no son parte del hash de config. Riesgos pendientes
de medir al implementar: costo del nuevo recorrido, calidad sobre corpus real y cobertura final
de consumidores. Ninguno se resuelve cambiando silenciosamente un default o adjudicando un
APPROVE a la implementación inexistente.

## 13. Simplicidad (SDD-31)

**Entrada mínima.** Provisión: cartera, corte, cartera/taxonomía, exposición, PD y LGD provista o
modelo explícito; ID opcional siguiendo contrato actual. Entrenamiento: historia y los seis
mapeos de §5. No inferir entidad, resultado completo, población, frontera temporal ni target.
El usuario declara esas semánticas; se registran sin prometer verificar hechos externos.

**Esenciales.** `lgd_training`: seis campos, exactamente §5. `provisioning_internal`: `as_of_date_col`,
`portfolio_col`, `exposure_col`, selector `lgd.method` y las columnas activas de LGD en modo
provisto/modelado. Máximo **seis simultáneos** en provided/fitted/regresión (target y covariables
en regresión); agrupación, fuente PD alternativa, piso/techo y método directo van en Avanzado.
Para workout se propone una **excepción explícita de nueve esenciales**: corte, cartera,
exposición, selector LGD, monto recuperado, EAD al incumplir, costo, tiempo y tasa contractual.
Son nueve entradas activas, aun si EAD y exposición apuntan a la misma columna; no se identifican
automáticamente porque pueden pertenecer a fechas distintas. Se agrupan visualmente, **sin
esconderlas como opcionales**. Cami decide esta excepción junto con el alcance (§12).
Las otras secciones conservan los esenciales actuales. No se reduce un conteo quitando controles
que el cálculo necesita ni contando una estructura de seis mapeos como un solo campo.

**Presupuesto.** Capa A: cero hojas nuevas de cálculo; sólo metadata de presentación y conexión
de entradas existentes, y el valor aditivo `full_population` de `type`, sin cambiar su default.
ID y declaraciones reutilizan hojas de data/gobernanza: se cuentan en esas secciones, no se
ocultan como metadatos gratuitos ni se duplican en entrenamiento.
Capa B: seis hojas institucionales en `lgd_training` y nueva rama
`fitted` con método/piso/techo (hasta tres nodos adicionales del barrido); metadata técnica oculta
no se vuelve control. Cero perillas estadísticas nuevas. Justificación: M3 impide aplicar sin
objetivo; M2/M7 no conservan predictor ni muestra; D-FIR-9 documentó el caso real de cartera viva.
No se solicita aumentar defaults, tolerancias ni presupuesto por comodidad. El total exacto del
barrido debe enumerarse al materializar schema, con cada diferencia explicada y gate bidireccional.

**Cada etapa habla.** Historia: elegibles/excluidos y causas; ajuste: método, variables, muestra,
convergencia; evaluación: tabla de métricas/baseline y límites; aplicación LGD: método, origen,
cobertura y piso/techo; provisión: exposición, PD/LGD agregadas, número de grupos y total,
reconciliación y decisiones de agrupación. Tres a ocho líneas y tabla relevante; mismo objeto
de resumen en texto, HTML y JSON. Excel de etapa contiene tablas completas; informe explica que
el detalle prorratea grupos. No añadir una segunda aritmética a UI/informe.

Cinco cifras, con línea base medida y objetivo, **sin confundir objetivo con resultado**:

| Cifra | Base S61 | Objetivo de entrega |
|---|---|---|
| Líneas del ejemplo público | 15, no vacías/no comentarios; usa preset/config/artifacts | ≤25 por recorrido provisto y modelado; notebook ejecutado en CI |
| Esenciales internos | 0 marcas; sección completa expuesta | ≤6 simultáneos; excepción workout de 9 propuesta explícitamente |
| Nodos del barrido por trabajo | PD+LGD 458; interno/modelada 249; internos 44 | A no aumenta hojas de cálculo; B sólo el inventario anterior, sin controles nuevos de algoritmo |
| Segundos al primer resumen H3 | No medible: no existe resumen; `estimate` sintético 1,44 s no sustituye esta cifra | ≤30 s desde construcción+run hasta primer resumen, dataset del paquete, entorno contractual; medir aparte hasta primera provisión |
| Conceptos del ejemplo | 5 interfaces bayesrisk invocadas: preset, materialize, validar config, run, artifacts.get | ≤5 hasta primer resultado útil; no esconder preparación obligatoria |

Los 458/249 cuentan nodos de todas las ramas con `_campos_visibles`, como el gate, no controles
simultáneos. Sin report/governance son 411/202; rutas únicas 370/166 son otra métrica. El censo
incluye 158 nodos de data; no adjudicar esa complejidad íntegra a LGD. El notebook modelado
propuesto usa archivos ya preparados: documentación y datos de ejemplo deben incluir también el
contrato de preparación y la tabla de evaluación. Sin eso, cumplir 25 líneas sería cosmético.
