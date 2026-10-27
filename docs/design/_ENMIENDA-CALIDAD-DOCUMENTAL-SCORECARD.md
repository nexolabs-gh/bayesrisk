# Enmienda de calidad documental del scorecard

TL;DR: Una sola lectura respaldada por los artefactos de cada corrida, con estado contextual,
hallazgos, población y momento explícitos, y con evidencia localizable en todos los formatos.
Contenido y presentación se aceptan juntos. Cero nuevas perillas. **Diseño aprobado por Cami
el 2026-10-27. Implementación de A+B autorizada por Cami el mismo día; sin release ni recaptura.**

| Campo | Valor |
|---|---|
| Identidad | D-DOC-SC-1…12, revisión 1, 2026-10-27 |
| Fase / módulos | F1; report, guided, governance, UI y documentación de uso |
| Estado | Aprobada por Cami, 2026-10-27, mediante herramienta interactiva; diseño estático con APPROVE independiente |
| Base | Público 74e348cb25dd2cc3235d13bc5c1b10bfc6b88430 |
| Autor | Codex, único writer; 2026-10-27 |
| Contratos | SDD-26, SDD-31, D-FLU, D-PAN, D-CPY, D-GOB-17, D-SC-11…16, D-HLC y D-EST |
| Autoridad | Diseño aprobado el 2026-10-27; A+B autorizadas después por decisión interactiva. Promoción documental sin cambio de versión visual |
| Entregables de diseño | Maquetas HTML/PDF y Excel revisadas, preservadas como evidencia interna; matriz de aceptación en el anexo A de este documento |

## 1. Propósito y responsabilidad

Un modelador debe entender qué hizo la corrida, sobre quién, qué resultados obtuvo, qué no
acredita y qué decisión institucional falta. El informe, la ficha y el Excel deben permitir al
revisor localizar la evidencia sin reconstruir el pipeline. Se aborda el scorecard completo,
incluida su guía de uso y la explicación de ZIP y bundle. No se abre la implementación de otras
familias. Los patrones podrán reutilizarse después de medirlas y aprobar su alcance.

La evidencia de entrada son SC-01…15 y QD-02…07 pertinentes de
la revisión documental preservada internamente.
No hay censo exhaustivo de la librería ni prueba con lectores. Las maquetas son extractos de
diseño, no el informe completo ni nuevos resultados del modelo. El manifiesto de fuentes y sus
localizadores impide confundir el SHA del checkout con el SHA que generó la demo.

## 2. Contexto y arquitectura

**D-DOC-SC-1. Una interpretación común, sin otro motor.** Los consumidores leen una proyección
editorial determinista de los artefactos existentes. Se comparte la selección y redacción de
hechos entre resúmenes de etapa/final, informe, ficha visible y pantalla. Python decide significado;
el front consume la salida o sus rótulos espejados y gateados. Los renderers sólo presentan.

No se cambia el DAG ni se retrasa `report` al final por imposición. El informe identifica
«Estado al emitir el informe» y sus etapas pendientes. La ficha consolidada y el resumen final
identifican su propio momento. Si `report` precede a `validation`, dice «Validación pendiente de
ejecución al emitir este informe», sin incorporar resultados posteriores. Una corrida parcial o
fallida conserva su estado y la última evidencia disponible. No se construye una segunda ficha.

Se enmienda la presentación de SDD-26 §5 y D-FLU-4/C1: portada compacta más **una** entrada
ejecutiva, no dos resúmenes consecutivos. Se conservan los identificadores de sección/anclas
existentes mediante destinos compatibles, aunque dos bloques compartan una ubicación visual.
La modificación se limita a familia scorecard; un informe multipropósito conserva sus capítulos
de otros dominios y sus fronteras. El censo previo a código debe identificar esas intersecciones.

## 3. Conceptos y reglas editoriales

**D-DOC-SC-2. Momento del IV.** `model.iv_contribution_flags` se conserva sin modificar:
une flags del stepwise y contribuciones finales. Nunca se traduce directamente como presente.
La vista se deriva por variable de coeficientes finales, umbral efectivo y eventos estructurados:

| Evidencia disponible | Texto exigido |
|---|---|
| Evento con iteración y valor, final finito ≤ umbral | «Alerta durante la construcción: [valor] en la iteración [n]. Contribución final: [valor]; no supera el umbral [corte]» |
| Final finito > umbral | «Contribución final al IV superior al umbral», con valor/corte; historia aparte si existe |
| Flag sin momento verificable | «Alerta registrada; momento no identificado en la evidencia disponible»; mostrar final por separado si existe |
| Umbral ausente o final no finito | «Comparación final no disponible», con causa; nunca “resuelta” ni cero |
| Evento de variable que no quedó en el modelo | Historia de construcción; no se atribuye al modelo final |

El operador es **>** para concentración (results.py:317–337). No se confunde con IV sospechoso
**≥ 0,50** de IV-A1 ni se cambia ninguna bandera o selección. En la demo, el evento estructurado
registra ingreso_mensual, 1,0, iteración 2 y umbral 0,9; su contribución final es
0,5143031291926708. No significa que se haya reparado leakage ni que el IV valide el modelo.
El evento resumido sin iteración y el detallado se conservan en evidencia; la vista histórica
no inventa dos iteraciones ni transforma el primero en otra alerta final.

**D-DOC-SC-3. Magnitud y población.** La tendencia `monotonic_trend` describe el **event rate**
de tramos numéricos regulares. El texto dice «Tendencia de la tasa de malos en Desarrollo».
WoE se muestra como otra magnitud con su valor y convención existentes. No se invierte su signo.
Una categórica con tipo acreditado y sin orden numérico dice «No aplica el diagnóstico de
tendencia numérica»; un `None` aislado no permite inferir esa causa: dice «No disponible».
Missing/Special, vacíos y tramos bajo el mínimo conservan su tratamiento; no se inventa una
tendencia ni se convierte cero filas en tasa observada 0 %. Las inversiones HO/OOT siguen visibles.

Cada cifra de población lleva universo, partición, eje/periodo y denominador cuando aplica.
La demo distingue global 6.000/1.407 (23,45 %) de EDA en Desarrollo 3.961/924 (23,33 %),
cinco cohortes 2023Q1–2024Q1. La estabilidad declara seis cohortes: no se le atribuye la ventana
del EDA. OOT es 2024Q2, 1.008 filas/239 malos; Holdout 1.031/244, 20 % del resto según el
resumen preservado. Fuera del ajuste vacío se muestra como 0 filas y tasa no aplicable, aunque
la fuente histórica guarde 0. No se cambia ese dato fuente ni se calcula una tasa nueva.

**D-DOC-SC-4. Inferencias acotadas.** PSI se presenta con magnitud (puntaje o PD), comparación,
valor, cortes efectivos y banda existente. Ejemplo: «Peor PSI entre score y PD: 0,0132, PD,
Desarrollo frente a Holdout. Banda Estable con corte 0,10». No implica igualdad de distribuciones,
ausencia de todo desplazamiento, causa de una caída del AUC ni calibración aprobada.
Se conservan Estable/Revisar/Redesarrollar/No evaluable, sin nueva banda ni umbral.

En desempeño sin umbrales, el rótulo visible es «Sin umbrales de alerta configurados», neutral,
junto a las cifras. El `ok` fuente se conserva; no se le atribuye un aval. P-valores se describen
como resultados del contraste ejecutado, sin “confirmar” aporte o transportabilidad.

**D-DOC-SC-5. Conclusión y límites.** La entrada y el cierre comparten los mismos hechos:
estado contextual/causa; alertas de escala OOT/HO; inversiones de tasa fuera de Desarrollo;
desempeño y PSI; historia del IV. Orden de lectura fijo por esas familias, dentro de cada una por
partición y variable; no se inventa un ranking de materialidad por magnitud. Todos los hallazgos
se listan; si la entrada ocupa dos páginas, continúa sin “top N” que oculte casos.

En el ejemplo: «Revisar: calibración pendiente», 0 pruebas evaluables en el conteo contextual,
tramo 1 OOT rojo (PD 4,77 %, observada 11,85 %) y tramo 1 Holdout ámbar. Los tramos de escala
no son grupos HL; la señal de escala se muestra aparte, **sin recalcular el estado contextual**.
La concordancia de medias en Desarrollo es resultado del ajuste, no validación global.
Se conserva HL convencional y su estado histórico (3 pruebas, 1 rechazo) en el soporte.
Contexto de calibración no certifica independencia del pipeline; Brier es puntaje. Ninguna
frase convierte ejecución completada, aceptación funcional o una banda en aprobación humana.

## 4. API pública y recorrido

**D-DOC-SC-6. Sin nuevos puntos de entrada ni parámetros.** Permanecen `Scorecard`, `summary`, `export_excel`, `export`,
`BayesRiskConfig`, `run` y el bundle. La propuesta no amplía las claves aceptadas por HTTP,
no introduce carga Study/joblib, no firma joblibs individuales ni cambia config_hash.
Los libros siguen por etapa, con sus nombres/orden vigentes; el Excel único de esta revisión
es un muestrario de hojas, **no** una propuesta de consolidar los libros de producción.

**D-DOC-SC-7. Dos variantes del tutorial.** El recorrido canónico empieza por la puerta guiada:
primera corrida sin exclusión; decisión explícita de excluir mora_max_12m y nueva corrida completa
con `resume`. Separar dos bloques de resultados y sus identidades. La demo base preservada
tiene AUC OOT 0,6560957827097084; el notebook de la variante muestra 0,648 a su precisión
publicada. No se promete igualdad entre esas corridas ni con otro entorno.

La puerta completa explica el preset base sin llamar a la variante «la misma corrida». El ejemplo
de corte 512 y su justificación numérica actual no se arrastran sobre la variante sin acreditar
su fuente; se retiran de la lectura lineal y se explican como decisión ilustrativa del caso base,
con su propia evidencia. No recomendar ese corte para datos nuevos. Los bloques ejecutables no
se mezclan mediante un objeto `sc` que cambió de config sin avisar.

Para obtener ficha se enseña el argumento existente `purpose=` como declaración deliberada de
la institución. El ejemplo usa sólo el propósito sintético preservado. Sin propósito no se crea
una ficha vacía, no se inventa dueño ni aprobación. Se enlaza la guía de gobernanza para los
campos disponibles por config; no se inventa un argumento de responsable en Scorecard.
La corrección de Markdown del notebook se especifica; no se edita ni ejecuta el notebook aquí.

## 5. Configuración

**D-DOC-SC-8. Cero perillas.** No se añaden modos ejecutivo/técnico, plantillas a elegir, umbrales
editoriales, switches de incertidumbre, controles de fuente/tamaño ni niveles de detalle.
Se respetan las opciones actuales de formatos, políticas de ausencias y placeholders. Los
defaults computacionales, PD, F1, CMF y hashes con nikodym permanecen intactos.
La presentación mejora sin hacer obligatorio `purpose` ni pedir un nuevo dato para correr.

## 6. Contratos de entrada y salida

La proyección editorial interna declara por hecho: `id`, origen (dominio/clave/selector),
momento, población, valor original, unidad, estado disponible/no aplicable/no disponible,
causa y destinos. Son metadatos de presentación internos; no una nueva card pública del modelo.
No parsea prosa ni `detail` cuando existen valores estructurados. Para la historia del IV usa
stepwise_trace/eventos estructurados; si faltan, aplica el texto conservador de §3.

Los artefactos estables, nombres de columnas y payloads históricos no se reescriben. La adición
de salida que sigue forma parte del contrato aprobado. Si se
necesita transportar la proyección en `summaries`/`results.json`, sólo se añade bajo clave
opcional `documentary_reading` con versión 1, nunca cambia el tipo de una clave existente:

```text
documentary_reading: {schema_version: 1, emission_scope: stage|report|run_end,
                     pending_stages: [str], facts: [hecho], evidence_index: [destino]}
hecho: {id: str, source: {domain: str, key: str, selector: str}, moment: str,
        population: str|null, value: escalar|null, unit: str|null,
        availability: available|not_applicable|unavailable, reason: str|null}
destino: {fact_id: str, artifact_key: str, section_id: str|null, local_path: str|null}
```

Campos desconocidos de una versión posterior no se interpretan como v1. Ausencia de la clave
conserva la lectura histórica identificada; los consumidores pueden derivar sólo hechos que
sus fuentes existentes acrediten. El esquema v1 se limita a escalares/punteros; las tablas
siguen en sus artefactos, sin duplicar filas por observación. No es entrada HTTP ejecutable.

**D-DOC-SC-9. Paridad y evidencia.** Para cada tabla agregada existente hay destino íntegro en
cuerpo o anexo. La tabla de lectura es una proyección con vínculo a la íntegra, nunca sustituto.
Los adjuntos por observación conservan su entrega completa bajo las opciones actuales. Si no
se solicitaron, se explica cómo obtenerlos; no se ofrece un archivo inexistente ni se lo genera
automáticamente. Cada destino incluye título/ID utilizable en papel, además del enlace digital.
ZIP sigue incluyendo config.yaml, input/, run/, reports/ y excel/ presentes, sin respaldos
laterales ni archivos arbitrarios. El bundle sirve para aplicar la tarjeta y no sustituye la
evaluación ni el archivo de corrida. Su contenido/esquema no cambia.

## 7. Composición y flujo

**D-DOC-SC-10. Informe.** Secuencia: identidad compacta y estado de borrador automático;
entrada ejecutiva (objetivo 1–2 páginas); mapa de lectura/índice; datos y método; desarrollo;
evaluación; conclusión y decisión pendiente; evidencia íntegra. Las rutas absolutas, versiones
de dependencias y hashes largos pasan al soporte, accesible desde la entrada. En la portada
no se repiten formularios vacíos. Los huecos institucionales se agrupan donde se toman decisiones,
respetando `placeholders`; la ausencia no se convierte en declaración automática.

Tablas de lectura de 4–7 columnas preferidas, números alineados, unidades en cabecera,
encabezados repetidos y ninguna reducción por debajo de 10 pt en PDF/Word. Texto 11 pt,
notas 9 pt, títulos 20–24 pt; Roboto existente. Tablas anchas se dividen por pregunta/partición
o continúan en paisaje, nunca omiten columnas del soporte. Cortes se mantienen exactos con
comparadores: si no caben, el cuerpo usa ID de tramo y remite al diccionario exacto local.
No se redondean límites para que quepan. Figuras con etiquetas humanas, unidades y leyenda
escrita; tasa de malos y WoE en paneles separados, sin doble eje engañoso. Valores exactos
siguen en la tabla fuente; reglas D-PAN intactas.

**D-DOC-SC-11. Ficha y formatos.** El capítulo institucional del informe se titula y explica
como declaraciones disponibles al emitir. La ficha de cierre mantiene métricas/decisiones/fechas
consolidadas; el texto dice «no forman parte de este capítulo», nunca «de este informe».
Fechas de emisión y revisión no se convierten en firma ni aprobación. Sin gobernanza, la
navegación informa ficha no solicitada sin crear `model_card`.

HTML: navegación por teclado, anclas de ida/vuelta, tabla desplazable sólo en soporte y lectura
principal sin overflow a 390/1280 px y 200 % de zoom. PDF: índice/enlaces reales y referencias
por título/ID; la cantidad de páginas no es objetivo de calidad. Word: estilos de párrafo,
encabezados repetidos, filas que continúan según contenido, índice/campos actualizables y
links internos; el criterio es semántico y de legibilidad, no igualdad de paginación con PDF.

El DOCX preservado declara Roboto y su render LibreOffice usa LiberationSerif. No se atribuye
la causa. La maqueta paginada de Word de este paquete es una **propuesta visual en HTML/PDF**,
no un DOCX ni una prueba del motor Word. La comprobación nativa Word y el diagnóstico de fuentes
quedan como gate de la futura implementación. No se cambia la familia tipográfica por conjetura.

Excel: conservar libros por etapa y hojas técnicas. Resumen/Decisión/Índice con rótulos humanos,
tipos numéricos y formatos (porcentaje, p-valor, conteo), columnas ajustadas, filtros en tablas
de registros, encabezados fijos en hojas largas y enlaces internos. No se añaden fórmulas de
riesgo: se exportan valores de la corrida. Los cortes numéricos exactos se acompañan de su
representación textual exacta cuando Excel no conserve todos los dígitos; jamás se usan como
reglas operativas desde una celda redondeada. `spreadsheet_safety` y dialecto CSV permanecen.

Flujo determinista: tomar snapshot → identificar disponibilidad/momento → enlazar hechos y
tablas → ordenar lectura → renderizar → verificar destinos/valores. No hay azar ni dependencia
de red. La lectura común no requiere recalcular métricas ni volver a ajustar el modelo.

## 8. Casos borde y errores

Sin umbrales no hay verde favorable; sin prueba evaluable no hay aprobación; sin metadatos no
hay independencia acreditada. Una corrida sin validation o con report temprano declara la
cobertura. Un PSI no evaluable expone causa; no se inventan bandas. Un resultado histórico sin
interpretación se rotula histórico; no se reserializa. Evento IV sin valor o iteración conserva
su evidencia y limita el texto. Categórica/tendencia desconocida no se adivina. Cero filas,
moneda no declarada, NaN y tablas truncadas se distinguen explícitamente.

La falta de un dato editorial no cambia las excepciones del motor. Se reutilizan las políticas
de ausencia y errores de SDD-26; un enlace roto, un hecho material sin fuente o un destino
omitido hacen fallar el gate de entrega, no se esconden detrás de “no disponible”.

## 9. Reproducibilidad y auditoría

Mismo config y snapshot producen el mismo contenido determinista. Cada maqueta preserva
run_id, config_hash, data_hash, SHA generador y fecha de la fuente; fecha del diseño separada.
El manifiesto enlaza bytes y localizadores de las fuentes utilizadas, no firma ni autentica
la institución. Los originales no se sobrescriben. La política HL histórica y contextual, el
bundle y `comparable.json` conservan su contrato. H3/Freddie sigue siendo aceptación funcional
por préstamo/proxy/corte, sin validación ni transportabilidad; no es parte de este piloto.

## 10. Dependencias

Reutilizar builder, document, prose, cifras, summaries, labels, spreadsheet_safety y motores
actuales HTML/PDF/Word/Excel. No se propone dependencia de producción, servicio IA, fuente
remota ni nuevo extra. Los guiones privados que dibujan las maquetas son herramientas de diseño,
no implementación del pipeline. La fuente Roboto existente conserva su licencia y procedencia.

## 11. Verificación y criterios de aceptación

**D-DOC-SC-12. Aceptación conjunta.** La matriz del anexo A ata cada SC a una decisión,
un criterio observable y un control negativo futuro. El censo de implementación tendrá dos
universos obtenidos independientemente: productores/cards/tablas/figuras/avisos, y consumidores
GUI/completa/pantalla/formatos/docs. Cada elemento debe tener destino o exención explícita,
y cada destino una fuente. Quitar una entrada y añadir una sin clasificar deben ponerlo rojo.
No se usa el propio manifiesto como único descubridor de lo que debe cubrir.

Contenido y presentación pesan 50/50 con cinco dimensiones por lado, 0–2 cada una.
Propuesta de aceptación: al menos 8/10 en cada lado, ninguna dimensión 0, y todos los gates
duros cumplidos. Los puntos no compensan cifras alteradas, inferencia falsa, evidencia perdida,
recorte material o decisión inventada. No se asigna nota al producto vigente ni se acredita
comprensión con esta revisión de diseño.

Prueba humana propuesta: un modelador y un revisor distintos del writer responden, en cinco
minutos cada uno, propósito/universo, resultado principal, límite principal, decisión pendiente
y ubicación de su evidencia. Cinco respuestas correctas y cero falsa aprobación/calibración;
si falla uno se revisa y se repite sólo lo afectado. Se registra tarea, respuesta, tiempo y error.
La rúbrica mide localización y comprensión del caso, no validez estadística ni representatividad.

Gates futuros: tests dirigidos de prosa/resúmenes/ficha/exports/UI; proyección canónica y hashes
F1; celdas/tipos de Excel; HTML/PDF/DOCX finales; build y recorrido del bundle UI; ejemplos desde
paquete instalado; CI del cambio job a job. Suite local completa sólo con una release autorizada.
Sin aprobar recaptura, la demo conserva bytes y se identifica como histórica cuando corresponda.

## 12. Decisiones humanas y plan de implementación propuesto

Cami aprobó el bloque D-DOC-SC-1…12 y las maquetas revisadas mediante herramienta interactiva
el 2026-10-27. La aprobación del diseño no autorizó por sí sola implementación, release, recaptura o campañas.
Cami autorizó posteriormente, el mismo 2026-10-27 y mediante herramienta interactiva, las
capas A+B: fidelidad en las tres puertas y formatos, más composición, tablas y navegación.
La capa C permanece fuera de este alcance. Release, recaptura y campañas requieren su OK propio.

Plan por capas: (A) proyección editorial y fidelidad con las tres puertas y formatos; (B)
composición/tablas/navegación con evidencia íntegra; (C) documentación de uso y recorrido de
entrega. No publicar A parcialmente adaptada. Cada capa: censo focal antes de editar, tests nacidos
rojos, controles negativos, revisión independiente acotada e integración. Si C necesita modificar
notebook/salidas o demo, preparar el delta y pedir el OK específico; una guía lateral puede
explicar las variantes sin modificar los originales. No iniciar C/D de H10 ni otras familias.

Riesgos medidos: faltan Excel nativo y Word nativo, el censo exhaustivo y lectores. Este paquete
no los declara superados. La revisión independiente del diseño tiene tope de dos pasadas:
primera completa, segunda sobre correcciones; parar en APPROVE o elevar un residual contractual
con evidencia. No repetir revisiones verdes ni ampliar por iniciativa propia.

## 13. Simplicidad

Entrada mínima sin cambios: datos, target, id opcional, eje y frontera OOT declarada (o random
explícito). Propósito opcional para ficha; no se infiere. Perillas nuevas **0**, esenciales nuevos
**0**. Ni tono, detalle, formato editorial, tendencia, umbral interpretativo ni severidad nuevos.
Cada etapa conserva 3–8 líneas y su tabla de decisión; las referencias al soporte permiten leer
sin memorizar claves. Las decisiones humanas existentes conservan autor y motivo.

| Cifra | Base utilizada, sin nueva corrida | Objetivo |
|---|---|---|
| Líneas de usuario | Golden fuente 15; bloque canónico preservado | 15; ≤25, sin añadir setup editorial |
| Esenciales | Golden 37 visibles a la vez, máximo 6 por sección del scorecard; 39 paths por ramas | Sin cambios |
| Perillas | Golden 414 en las secciones del scorecard | 414, delta 0 |
| Primer resumen | Medición histórica 1,0 s (2026-09-19), gate ≤30 s; no remedido aquí | No añadir trabajo antes del primer resumen; gate existente al implementar |
| Conceptos | Golden 5: Scorecard, materialize, run, exclude, resume | 5 |

No se presenta una lectura de goldens como nueva medición de rendimiento. El notebook mínimo
se conserva en esta fase; el tutorial separa las variantes sin imponer más líneas para correr.

## Referencias locales consultadas

- [Plantilla](_PLANTILLA-SDD.md), [SDD-26](26-report.md), [SDD-31](31-simplicidad-y-flujo-guiado.md).
- [Flujo guiado](_ENMIENDA-FLUJO-GUIADO-SCORECARD.md), [cifras](_ENMIENDA-CIFRAS-EN-PANTALLA.md), [HL contextual](_ENMIENDA-HL-CONTEXTO-Y-EMPATES.md), [frontera IV](_ENMIENDA-AUDIT-IV-FRONTERA.md).
- [Registro vigente](DECISIONES-VIGENTES.md).

## Anexo A. Matriz de aceptación del diseño documental

TL;DR: Quince hallazgos tienen destino, criterio y control negativo. Esta matriz especifica la
aceptación futura; no demuestra que la implementación ni el censo completo estén hechos.

| Hallazgo | Decisión | Criterio verificable | Control negativo futuro |
|---|---|---|---|
| SC-01 | 2 | 100 % histórico/iteración 2 y 51,43 % final separados; umbral >90 %; flags originales iguales | Narrar el histórico como actual; debe fallar el oráculo de significado y fuente |
| SC-02 | 3 | Event rate decreciente y WoE creciente identificados; categórica sin orden no pendiente | Renombrar event rate como WoE o convertir None en revisión sin causa |
| SC-03 | 3 | 6.000/1.407 global, 3.961/924 EDA, 5 cohortes EDA y 6 estabilidad delimitados | Quitar el universo de una tasa o usar denominador global en el EDA |
| SC-04 | 4 | PSI nombra magnitud/muestras/cortes; sin causalidad ni certificación; umbrales ausentes neutrales | Reponer “no hay desplazamiento” o un verde favorable sin umbral |
| SC-05 | 1,11 | Capítulo institucional y ficha de cierre identificados por momento; referencias consistentes | Afirmar que ninguna métrica aparece en el informe |
| SC-06 | 5 | Entrada/cierre incluyen calibración pendiente y escala OOT roja, sin cambiar estado contextual | Omitir calibración pendiente o tramo 1 OOT sólo del cierre |
| SC-07 | 7 | Corrida base y posterior a exclude tienen resultados/procedencia propios | Atribuir AUC 0,656 de la base a la variante que publica 0,648 |
| SC-08 | 7,9 | El lector llega a los hallazgos, sus límites y una decisión humana pendiente | Terminar en exportación sin lectura ni siguiente decisión |
| SC-09 | 7,11 | purpose deliberado y opcional; sin él no hay ficha inventada | Generar propósito o responsable desde nombre del dataset |
| SC-10 | 9 | ZIP declara allowlist real; bundle distingue aplicación y evaluación | Prometer toda la carpeta, incluir un respaldo o llamar bundle al archivo de corrida |
| SC-11 | 5,7 | Markdown describe salidas preservadas y versión, sin prometer “Pasa” | Sustituir Revisar por Pasa en el relato, manteniendo salidas |
| SC-12 | 9,10 | Tablas legibles y cortes exactos accesibles; figuras con magnitud/unidad | Alterar un límite sólo en la vista legible o perder una columna de soporte |
| SC-13 | 1,10 | Una entrada, sin rutas dominantes; estado/ausencias explícitos | Duplicar resumen o afirmar corrida final con etapas posteriores pendientes |
| SC-14 | 10,11 | HTML/PDF/Word: mismo significado, tipografía medida, sin recortes; motor de render registrado | Alterar una cifra sólo en Word o forzar fila/salto que corte contenido |
| SC-15 | 6,11 | Valores numéricos, formato útil, filtros/panes y links; protección de texto | Convertir proporción en cadena o dejar fórmula activa desde texto de entrada |

Los controles de distintas reglas se ejecutan sobre copias aisladas, rojo correcto → restauración
exacta → verde. No mutar la demo. Un censo tiene controles de omisión y alta sin clasificar.

### Matriz de paridad

| Superficie | Estado/población/momento | Tabla íntegra y procedencia | Recorrido |
|---|---|---|---|
| Guiada consola / notebook | Fuente común, etapa o cierre según llamada | summary y artefactos existentes | Informe / export opcional |
| Completa config / Study | Mismos hechos para mismo snapshot; sin resultados futuros | Artefactos estables + proyección opcional | Referencia de API y run_dir solicitado |
| Pantalla | Consumo del mismo significado; sin reglas nuevas TS | Detalle con rótulos y originales | Saltos a informe/ficha/descargas existentes |
| HTML | Estado al emitir, etapas pendientes | Tablas agregadas íntegras, anclas y assets locales | Índice y retorno, sin servidor necesario |
| PDF | Mismo contenido, referencias impresas | Mismas cifras/tablas, índice con enlaces | Título/ID además de link |
| Word | Mismo contenido, editable, estilos y campos | Soporte íntegro, sin números “reconstruidos” | Índice actualizado y navegación probada en Word |
| Ficha JSON/Markdown/pantalla | Cierre propio, declaraciones/fechas sin aprobación inventada | Payload estable; vista desde fuente común | Identidad compartida con informe |
| Excel / CSV | Valor tipado, unidad y muestra; ausencia distinta de cero | Todas las tablas existentes, seguridad preservada | Resumen/Decisión/Índice por etapa |
| ZIP / bundle | Roles distintos, mismas identidades correspondientes | Membresía/esquemas sin ampliar | Archivo de corrida / aplicación del modelo |
| Tutorial / Inicio / notebook | Variantes explícitas y cifras ligadas a su corrida | Salidas preservadas y enlaces | Interpretar → documentar pendiente → entregar |

La equivalencia exige mismo config y datos, salvo procedencia declarada, y mismo momento del
snapshot. No obliga al informe temprano a conocer la ficha emitida después. Datos no incluidos
en el artefacto histórico se declaran ausentes; no se reconstituyen por conveniencia.

### Rúbrica de aceptación

Cada dimensión puntúa 0 (falla), 1 (usable con dificultad documentada) o 2 (cumple sin ambigüedad).
Contenido: fidelidad; delimitación; interpretación; síntesis; decisión y evidencia.
Presentación: entrada; tablas; gráficos; navegación; paridad de formatos.
Aceptar con ≥8/10 en cada grupo, ninguna dimensión 0 y cero veto duro. No hay nota asignada
en este diseño. El umbral y la prueba de dos lectores forman parte del diseño aprobado por
Cami el 2026-10-27; su ejecución y resultado siguen pendientes.
