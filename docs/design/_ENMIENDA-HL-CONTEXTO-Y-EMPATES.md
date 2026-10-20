# Enmienda aprobada — HL con contexto y diagnóstico que no divide empates

**TL;DR:** conservar el HL clásico como resultado convencional auditable, sin usarlo por sí
solo para aprobar o rechazar un modelo; añadir una lectura contextual y grupos descriptivos
que mantengan juntas las PD idénticas. La falta de inferencia validada se muestra como falta,
jamás como «Pasa». No se cambia el modelo, su calibrador, alfa, G ni las guardas históricas.

| Campo | Valor |
|---|---|
| Estado | **APROBADA por Cami el 2026-10-20**; implementación autorizada en S60 |
| Autor / fecha | Codex writer, 2026-10-20 |
| Decisiones aprobadas | D-HLC-1…8 |
| Contratos que enmienda | SDD-22 §§3.2/7/9, D-VAL-17 y D-HLG-2 en la interpretación; D-FLU/resúmenes e informe para consumirla |
| Contratos preservados | Fórmula/DTO/tablas/contadores históricos; F1 2.x; D-HLG-1; D-CMP formato 1; defaults y hashes nikodym |
| Estado de entrega | Implementación S60 y controles locales completos; pendiente revisión adversarial del código e integración con CI |
| Entrega autorizada | Una capa completa de interpretación y tablas aditivas por las tres puertas |

## 1. Propósito y responsabilidad

Responder «qué permite concluir este HL» sin confundir aritmética correcta con referencia
estadística apropiada. **D-HLC-1:** HL clásico pasa a ser evidencia diagnóstica en la lectura
contextual; no se le concede una excepción automática por llamarse la muestra Desarrollo.

S58 observó 10,0–17,85 % de rechazos con PD verdaderas conocidas en 18 escenarios, y sensibilidad
al orden en empates. En la logística simple ajustada sobre la misma muestra obtuvo 3,91–5,60 %:
eso no valida una scorecard con binning supervisado, selección y recalibración. F-nueva
22,35–31,45 % no es una tasa de falsas alarmas p=q. Fuentes primarias: [MathWorks](https://www.mathworks.com/help/risk/risk.validation.hosmerlemeshowtest.html), [Surjanovic, Lockhart y Loughin](https://link.springer.com/article/10.1007/s11749-023-00912-8) y [Van Calster et al.](https://link.springer.com/article/10.1186/s12916-019-1466-7). F1/F2/F3 designan estas fuentes en ese orden; la trazabilidad de la auditoría se conserva internamente.

La propuesta no afirma que todo rechazo sea falso. Tampoco que todas las PD estén bien.
En S55 hubo cinco HL de fábrica que pasan, cuatro que fallan y uno no evaluable; Brier no
rechaza. Un HL verde no será objetivo de selección de defaults. No se reabre S56.

No incluye un nuevo contraste, bootstrap, simulaciones, refits, curva suavizada, intervalos
de calibración, regla de materialidad económica, dependencia por cliente o cambio del modelo.
La ausencia de un contraste validado para cada contexto sigue siendo deuda explícita del motor.

## 2. Contexto y arquitectura

Lectura estática sobre público `10458ead187f512a04ff292966a6cd1b2113e541`:

| Evidencia actual | Consecuencia para el diseño |
|---|---|
| `validation/calibration_tests.py`: orden estable + `array_split`, H, χ²(G−2); kernel mínimo 1 | Mantener esa ruta para reproducir lo histórico; no llamarla universalmente válida |
| `validation/evaluator.py`: mínimo efectivo 30, mismo kernel por partición | 30 filas no garantiza suficientes eventos esperados ni tamaño nominal |
| `validation/results.py`: DTO cerrado, gl=G−2, cuatro causas; deriva conteos/estado | No insertar null/otra gl ni cambiar significado dentro del DTO existente |
| `validation/step.py`: consume PD y labels, sin procedencia de ajuste como entrada de validación | La etiqueta de partición no prueba independencia ni ausencia de reutilización |
| `calibration/results.py`: parameters/card declaran `fit_partition="desarrollo"` | Describe la calibración; no certifica todo el proceso ni independencia entre deudores |
| `binning/step.py`, `selection/selector.py`, `model/step.py`: ajuste en Desarrollo | El flujo estándar separa muestras por construcción; no prueba que el usuario no eligió modelos mirando Holdout |
| `guided/summaries.py`, `report/prose.py`, `ui/serializers.py`, ResultsTab | Hoy propagan el estado consolidado y HL decisivo; deben distinguir la nueva lectura |
| `comparison/comparable.py::_validacion`, `_schema.py` | Formato estable 1 sólo guarda status/reason; no contiene suficiente evidencia para reinterpretar HL |

**D-HLC-2:** una sola función pura construye la interpretación nueva. La invocan el Step y
la API completa; guiada, pantalla, informe y Excel consumen su artefacto, no recalculan reglas.
No se crea un segundo evaluador de HL. El cálculo numérico histórico sigue siendo el existente.

El censo de diseño se verificó por lectura; la cobertura requerida figura en §9. La entrega exige además las pruebas de §11.

## 3. Conceptos y fundamentos

El resultado histórico conserva:

`H = Σ (O_g − n_g·p̄_g)² / [n_g·p̄_g·(1−p̄_g)]`,
`p_clásico = χ².sf(H, G−2)`, rechazo estricto cuando `p_clásico < alfa`.

Fórmula/convención cotejadas por F1/F2. G−2 es una aproximación asociada al ajuste, no una
identidad aplicable a cualquier vector de PD. No reemplazar automáticamente por G, K−2 o
G−número de variables. S58 mostró que G tampoco resuelve universalmente los eventos raros.
F3 respalda acompañar la interpretación con magnitud; no fija una banda de aceptación.

Tres planos separados: resultado convencional de HL; desviación observada descriptiva; decisión
humana de uso del modelo. Ninguno equivale por sí solo a los otros.

### Contexto que se publica, sin inventar procedencia

**D-HLC-3:** el DTO contextual registra por partición:

| `context` | Condición y texto |
|---|---|
| `same_calibration_sample` | Hay metadato de calibración coherente y la partición coincide con su fit_partition: «Misma muestra que declara el ajuste de calibración» |
| `other_calibration_sample` | Metadato coherente, partición distinta: «Muestra distinta de la declarada para calibrar; independencia y ausencia de reutilización no certificadas» |
| `unknown` | No hay metadato suficiente o no es coherente: «Procedencia de ajuste no acreditada» |

`context_source` es `artifact_metadata` o `none`. `context_scope` es siempre `calibration_only`;
`full_pipeline_independence_verified` es siempre `false` en esta enmienda.
El metadato es una declaración de su productor, incluso si fue inyectado; nunca se rotula
«verificado» por su mera presencia. La fuente y las claves se publican.

Coherencia mínima: parameters y card de calibración presentes, mismo método y fit_partition,
n_fit igual entre ambos, y el fit_partition aparece en el frame de calibración con n_fit filas
de target válido; si falla, `unknown` y razón. No inferir contexto sólo de los nombres
desarrollo/holdout/oot, de `model_ref`, del nombre de archivo ni de un run_id.
La falta de metadatos en un frame externo no impide el diagnóstico.

Esta distinción cambia explicación, no habilita una referencia inferencial: **ningún contexto
de esta enmienda acredita el p-valor clásico como control general de falsas alarmas**.
En muestras nuevas la desviación puede contener error real de PD y de estimación.
En la misma muestra hay reutilización del target; igualdad de medias puede ser consecuencia del ajuste.
Dependencia entre personas o reutilización externa siguen sin poder inferirse de estas columnas.

## 4. API pública, compatibilidad y adopción

**D-HLC-4:** extensión aditiva, con política identificada `hl_context_v1`:

```text
interpret_validation(
    result: ValidationResult,
    *,
    calibrated_pd: DataFrame | None,
    calibration_parameters: CalibrationParameters | None = None,
    calibration_card: CalibrationCardSection | None = None,
    calibration_config: CalibrationValidationConfig
) -> ValidationInterpretation
```

Firma ilustrativa del contrato, no implementación. Produce metadatos/contexto y tabla
descriptiva, sin llamar otra vez al kernel HL. El Step publica dos claves nuevas:
`("validation", "interpretation")` y `("validation", "calibration_tie_groups")`.
Metadatos de calibración en `optional_requires` cuando HL está activo; PD/labels conservan
sus `requires`. El constructor standalone admite metadatos ausentes.

**Se conservan exactamente** `hosmer_lemeshow`, su firma y resultados,
`CalibrationTestRecord`, `ValidationResult`, `validation.card/calibration/result`,
`hosmer_lemeshow_groups`, sus conteos y regla histórica de consolidación.
Las funciones antiguas siguen devolviendo lo que devolvían. Documentación API las identifica
como resultado convencional; usar la interpretación nueva para la lectura contextual.

La salida visible nueva distingue:

- **«Evaluación contextual»**, fuente nueva y estado definido en §7.
- Detalle auditable **«Resultado convencional de HL y estado histórico»**, con los números,
  conteos y decisiones originales, sin presentarlos como aprobación actual del modelo.

Es un cambio de interpretación explícito que requiere OK, no un parche aritmético ni una
promesa de igualdad del texto del informe. Proyección numérica histórica, config_hash,
predicciones y bundles deben quedar iguales; las claves y textos nuevos son la diferencia declarada.
La versión de política se registra fuera del config_hash, con la versión de la librería.

**Corridas anteriores:** no se reescriben. Si tienen PD/labels y sus resultados, una petición
explícita por código puede crear la interpretación en memoria con esta API; no persiste sobre
la evidencia vieja. Si sólo hay agregados, se muestra «Lectura histórica; contexto no disponible»;
no se fabrican grupos nuevos ni un estado contextual.

**Comparación estable:** `comparable.json` esquema 1, su status/reason y sus hashes se conservan.
Todos sus consumidores rotulan ese campo **«Validación histórica»** y añaden
«El resumen guardado no permite aplicar la lectura contextual de HL».
No mezclan esa cifra con el estado nuevo ni afirman haber recalculado corridas.
No se altera frontera, elección, DeLong ni formato de intercambio. Trasladar el nuevo estado
a un formato comparable futuro no está entregado por esta enmienda y exigiría otro diseño.

## 5. Configuración

Cero hojas, switches o parámetros nuevos; no se retira ninguno.
`hosmer_lemeshow=True`, `hl_n_groups=10`, alfa 0,05 y mínimo efectivo 30 se conservan.
Apagar HL omite también sus diagnósticos nuevos; no se lo ejecuta por detrás.
Los grupos descriptivos usan el G solicitado existente como **objetivo**, publicando K efectivo.
No se configura redondeo de PD, desempate, tolerancia económica ni un método sustituto.

La función pura recibe el config efectivo y exige concordancia de G/alfa/mínimo con el resultado.
Una contradicción de entradas es error de integridad, no un contexto desconocido.
Para Brier se mantiene puntaje, sin p, sin rechazo ni semáforo.
Las otras familias de validación mantienen sus contratos; no reciben un aval adicional por esta enmienda.

## 6. Contratos de datos

`ValidationInterpretation`, frozen/extra=forbid, esquema 1:

| Campo | Contrato |
|---|---|
| `policy_id` | Literal `hl_context_v1` |
| `overall_status` | Las cuatro palabras existentes; regla §7, fuente nueva explícita |
| `n_tests`, `n_failed` | Conteos de grado/backtesting evaluables; HL clásico y Brier no cuentan aquí |
| `legacy_status`, `legacy_n_tests`, `legacy_n_failed` | Copia exacta de la card vieja, claramente separada |
| `hl` | Una entrada por partición HL, mismo conjunto que los records históricos |
| `coverage_gap` | True si calibración está entre las familias ejecutadas y HL está solicitado en su config, incluso sin filas evaluables; no existe contraste contextual sustituto validado |
| `warning_codes` | Si coverage_gap: la nueva deuda estructural definida abajo; sin códigos visibles en copy |

Cada entrada `hl` contiene partition, contexto y fuente de §3, `context_reason` nullable,
`legacy_statistic/p_value/alpha/decision/not_evaluable_reason` copiados, n, G solicitado,
K descriptivo, `legacy_boundary_splits_tie` booleano,
`diagnostic_status="available"`, `formal_inference="not_established"`.
No se usa el viejo `not_evaluable_reason` para una causa metodológica nueva.
Si existen records HL, la API exige el frame analítico no vacío que los originó, con sus
particiones concordantes. No fabrica entradas para particiones ausentes. Sin records HL,
la lista y tabla están vacías, sin un record artificial n=0/K=0.

Tabla aditiva por partición × grupo: `partition, group, pd_min, pd_max, n,
observed_defaults, expected_defaults, observed_dr, mean_pd, gap_pp, oe_ratio, oe_ratio_reason,
expected_non_defaults, below_legacy_min_rows`.
No lleva H, contribuciones, p-valor, gl ni decisión. No se identifica como la tabla del HL.
Orden canónico de particiones y PD ascendente; límites precisos, sin redondear para agrupar.

N = suma n; eventos = suma O; esperados = suma PD. No se descartan filas válidas ni se
añaden registros. `gap_pp = 100*(O/n − E/n)`; `oe_ratio = O/E` sólo cuando E>0 y el cociente
es finito y representable en float64. `oe_ratio_reason` es null si se publica el número;
`non_representable_ratio` si E>0 pero el cociente desborda, con copy
«No representable: razón observado/esperado demasiado grande»; y `zero_expected` si E=0,
con copy «No definido: cero incumplimientos esperados». En ambos casos `oe_ratio` es null
y se conservan O, E, tasas y brecha, sin clipping, epsilon ni inf en JSON.
La rama E=0 es una defensa de serialización: no amplía el dominio público estricto (0,1).
`expected_non_defaults=n−E`. No se crean umbrales de significancia para esos conteos.

La limitación inferencial es deuda del motor, no falta de datos de Cami. Código
interno nuevo **`FALTA-DATO-VAL-HL-CONTEXTO`**, sin reutilizar VAL-1/2/3 retirados.
Se declara **estructural para la interpretación HL**: ningún input de esta enmienda habilita
la inferencia, por lo que `fail_on_falta_dato` no debe abortar por ella. Se registra mediante
el mecanismo `is_declared_warning`/`governable_warnings`, no filtros nuevos de literales.
No se añade al DTO/card históricos: pertenece al artefacto nuevo y a su evento de auditoría.
Texto público: «La librería aún no dispone de un contraste de calibración validado para este contexto».

## 7. Algoritmos y flujo

### 7.1 Grupos descriptivos sin dividir empates — D-HLC-5

1. Validar exactamente los pares analíticos de la partición: target binario, PD finita en (0,1),
   sin truncar ni imputar. Usar el mismo frame analítico que alimentó HL.
   La ruta pública con calibración activa conserva el rechazo de frame vacío y PD 0/1.
   El helper descriptivo de esta enmienda conserva ese dominio: no existe una segunda
   puerta que acepte esos bordes sin `ValidationResult`.
2. Ordenar por PD. Empate = igualdad exacta de float64. Sin jitter,
   redondeo, orden por Y, ID o semilla. Los ID no intervienen.
3. Para n>0 y G solicitado, q,r=divmod(n,G); cortes nominales
   b_j=j*q+min(j,r), j=1…G−1. A cada corte interior llevarlo al último registro del
   bloque con la misma PD que la observación b_j (posición 1-based).
   Quitar cortes 0/n y duplicados. Conservar los demás en orden.
4. Los intervalos resultantes contienen bloques de PD completos. K está entre 1 y min(n,G).
   No crear grupos vacíos ni reagrupar mirando Y. No fusionar por mínimos de eventos observados.
5. Agregar O como entero y E sumando PD en orden canónico por valores y frecuencias, con
   `math.fsum` o equivalente que cumpla el golden de permutación bit a bit.
   Publicar las columnas §6. No calcular un nuevo p sobre estos grupos.
6. `legacy_boundary_splits_tie` indica que algún corte nominal interior separa PD iguales.
   Advierte dependencia potencial del agrupamiento; **no afirma que el veredicto de esta muestra cambió**.

Ejemplos especificados a mano, no simulados:

- n=10,G=5, PD=(0,1 × 3; 0,2 × 1; 0,3 × 4; 0,4 × 2):
  cortes 2/4/6/8 → 3/4/8/8 → 3/4/8, tamaños 3/1/4/2.
- Todas las PD iguales: K=1, diagnóstico agregado; sin p ni grados de libertad.
- Sin empates en cortes: mismos tamaños nominales del HL, sin promesa de referencia válida.

Los grupos chicos se conservan con su n y señal de comparación al mínimo histórico.
Esa señal no es una garantía de precisión. No hay IC ni error estándar inventado.
Costo O(n log n), memoria O(n); no multiplica muestras, no ajusta modelos y no consume RNG.

### 7.2 Estado contextual — D-HLC-6

Copiar el resultado histórico. Derivar una consolidación nueva excluyendo sólo HL de la
evidencia decisoria. Conservar discriminación informativa, Brier informativo, semáforo,
backtesting y estabilidad tal como están contratados. Prioridad exacta:

1. `fail` si otra prueba evaluable falla, un grado es rojo o PSI falla.
2. `warn` si un grado es ámbar o PSI está en revisión.
3. `not_evaluable` si no hay ninguna otra prueba evaluable ni decisión de estabilidad.
4. `warn` si hay otra evidencia evaluable y coverage_gap por HL.
5. `pass` en otro caso, limitado a las familias efectivamente ejecutadas.

El estado contextual no equivale a una aprobación institucional. Si sólo había HL y Brier,
se obtiene **«No evaluable: falta un contraste de calibración validado»**, tanto si HL pasó
como si falló. Si PSI está verde y HL existe, **«Revisar: calibración pendiente»**.
Un rojo de otra familia permanece rojo. Desactivar HL no se recomienda para lograr un verde:
se enumera siempre la cobertura efectivamente solicitada y la ausencia de contraste global
de calibración; el rótulo Pasa sólo se refiere a la evidencia ejecutada.

No se modifican ni se mezclan los contadores antiguos y nuevos. La matriz de casos §11
incluye invariancia del estado contextual ante cambiar sólo pass/fail/p de HL.

## 8. Casos borde y errores

**D-HLC-7:** una limitación numérica y una metodológica no son la misma cosa.

- HL histórico sin veredicto conserva su causa, H/p null y todos sus invariantes.
  Con pares válidos sí se puede mostrar la tabla descriptiva nueva, incluso con n<30.
- Frame de calibración vacío o PD exactamente 0/1: el evaluador sigue rechazándolos antes
  de producir ValidationResult. La API contextual conserva ese dominio; no fabrica records
  ni salidas de diagnóstico para rescatar una corrida rechazada. Esto no altera el kernel
  HL suelto, cuyo dominio es más amplio y se conserva como está.
- Una clase observada con PD interiores no destruye el diagnóstico ni certifica potencia.
- PD positivas extremadamente pequeñas: si O/E desborda, sólo esa razón queda null con
  `non_representable_ratio`; el resto del diagnóstico y la causa histórica de HL se conservan.
- Sin HL solicitado/ejecutado no hay entradas HL ni grupos descriptivos. Esa tabla vacía
  es ausencia de la familia, no un resultado para un frame de calibración n=0.
- Metadatos ausentes/incoherentes: contexto unknown; no bloquea ni certifica independencia.
- Pares inválidos, filas perdidas, G/alfa/mínimo contradictorios o desajuste con los records:
  error explícito de integridad. No publicar un artefacto contextual aparentemente válido.
- Un consumidor no sabe leer policy_id: muestra política no soportada y el resultado histórico
  identificado; nunca cae silenciosamente a un «Pasa» contextual.
- Si no corrió validación o no se pidió HL: se informa esa cobertura sin inventar filas HL.
  La nueva interpretación puede consolidar las otras familias con la misma regla histórica.

## 9. Reproducibilidad, auditoría y superficies — D-HLC-8

Sin azar. Registrar `policy_id`, fuente/contexto, claves de entrada, conteos, K, cortes por valor
de PD, presencia de cortes históricos que dividen empates y motivo de la nueva conclusión.
Un evento separado por partición, sin repetir ni sobrescribir las decisiones históricas.
Mantener data_hash/config_hash/model_hash/bundle_hash y todos los prefijos nikodym.
Firmar los nuevos artefactos mediante el mecanismo de persistencia existente.

Cobertura requerida para la implementación eventual:

| Puerta/superficie | Lectura obligatoria |
|---|---|
| Guiada texto/HTML, etapa y resumen final | Estado contextual primero, causa y magnitudes; enlace/detalle histórico |
| API completa y `Study` | Artefactos nuevos tipados; documentación de qué versión interpreta cada estado |
| Pantalla y `results.json` | Campos aditivos, rótulos espejo de Python; ninguna regla inferida en TypeScript |
| Informe HTML/PDF/Word y página ejecutiva | Misma conclusión, tabla nueva claramente descriptiva y tabla HL antigua identificada |
| Excel/CSV/ZIP | Hojas nuevas y rótulos; datos antiguos íntegros; protección de fórmulas existente |
| Comparación esquema 1: panel, prosa, resumen y Excel | Estado etiquetado histórico, aviso de información insuficiente; no recalcular ni reserializar archivos |
| Ficha/limitaciones | Si recoge el resumen, adopta la misma interpretación; no fabricar decisión humana |
| Docs, tooltip, catálogo y notebook | Explicar qué significa cada salida; retirar la promesa de que HL «comprueba» por sí solo calibración |

Los artefactos históricos publicados de la demo conservan bytes y resultado histórico,
con el aviso de lectura histórica cuando se muestren desde el consumidor nuevo.
No se recapturan en esta capa sin OK propio. No publicar producción parcialmente adaptada:
las tres puertas y todas las superficies de la matriz deben cerrar juntas.

## 10. Dependencias

Se reutilizan numpy/pandas y las utilidades de validación, persistencia, rótulos y export.
La interpretación no añade dependencias ni requiere scipy para calcular p nuevos.
El HL histórico conserva su import perezoso de scipy y extra `scoring`.
No se requieren cambios del lock ni de versiones de entorno.

## 11. Estrategia de verificación

El diseño se verificó con lectura de fuentes/código y control negativo documental. Los casos de esta tabla son los criterios de implementación autorizados; no constituyen una nueva campaña de simulación.

| ID | Decisiones | Oráculo futuro, nacido rojo antes del cambio |
|---|---|---|
| T01 | D-HLC-1, D-HLC-6 | HL fail↔pass con otras filas iguales no mueve el estado contextual; sí permanece el histórico |
| T02 | D-HLC-2, D-HLC-4 | Misma función/artefacto en tres puertas; proyección histórica exactamente igual |
| T03 | D-HLC-3 | Cambiar sólo nombres de partición sin metadato no fabrica procedencia; card aislada/discordante → unknown |
| T04 | D-HLC-3 | Ficha coherente da mismo/otro respecto de calibración, siempre alcance parcial y no independencia certificada |
| T05 | D-HLC-5 | Golden 3/1/4/2; constantes K=1; sin empates en cortes; permutaciones finitas de filas no cambian grupos |
| T06 | D-HLC-5, D-HLC-7 | Conservación n/O/E, una clase y n<G; ruta pública rechaza vacío/PD 0/1 como antes; PD interior diminuta con O/E no representable → sólo razón null con causa, JSON estricto y demás cifras intactas |
| T07 | D-HLC-6 | Sólo HL/Brier → not_evaluable; PSI verde+HL → warn; PSI rojo/otro fail → fail; sin HL conserva otras familias |
| T08 | D-HLC-4, D-HLC-8 | Carga histórica sin artefacto nuevo: rótulo histórico; comparable formato 1 byte/huella idénticos |
| T09 | D-HLC-7 | Inputs/records contradictorios dan error; policy desconocida no produce verde contextual |
| T10 | D-HLC-8 | Trail adicional, no reemplazo; marca estructural no detiene y copy público no filtra código interno |
| T11 | D-HLC-2, D-HLC-8 | Mismos valores/rótulos en HTML/PDF/Word, pantalla viva, resumen y Excel; grupos nuevos jamás titulados HL |
| T12 | D-HLC-4, D-HLC-8 | Presets/config_hash/predicciones/bundle/proyección histórica sin cambios; demo no recapturada |

Gates proporcionales futuros: tests dirigidos de validación, resúmenes, report/export/UI,
comparación sólo consumidores históricos, vocabulario/avisos; ruff/mypy, frontend build,
docs strict y CI job a job conforme RUNBOOK. Al menos un negativo por regla nueva.
La suite completa local sólo en la release específica autorizada, no ahora.
No medir «menos HL rojos» como éxito: éxito es coherencia, conservación y ausencia de
afirmaciones inferenciales sin respaldo. Un futuro test sustituto necesita otro alcance
con hipótesis, dependencia, estimación, potencia, tamaño y protocolo aprobados antes de ejecutarse.

## 12. Decisión humana, alternativas y riesgos

**Aprobada por Cami el 2026-10-20:** esta enmienda conservadora y su implementación
completa. Cierra el uso injustificado de HL como decisión automática, sin inventar un reemplazo.
Impacto visible: la scorecard puede pasar de un estado histórico Falla/Pasa a una lectura
contextual No evaluable/Revisar; sus PD y su evidencia no mejoraron por ese cambio de lectura.

Alternativas examinadas:

- Mantener sólo advertencia junto al veredicto actual: menor cambio, pero deja a HL decidiendo
  por sí solo y no resuelve la contradicción medida; no recomendada.
- Sustituir la referencia por G o un nuevo contraste: puede ser un alcance futuro, pero S58
  no valida una solución universal. No se implementa ni se simula por iniciativa del writer.

Riesgos residuales declarados: falta de contraste formal contextual; contexto sólo documentado
para calibración; límites de datos dependientes y reutilización externa; pérdida de detalle
local al juntar empates; grupos dispares y sin intervalos; coexistencia de API histórica y
lectura nueva; comparación guardada no contiene la nueva interpretación. Se mitigan con
causas visibles, nombres distintos y conservación de evidencia, no se declaran resueltos.

Cami aprobó D-HLC-1…8 e implementar API, pantalla, informes y exports con pruebas y revisión, conservando defaults y evidencia, sin nuevas campañas, release ni recaptura. La evidencia de diseño y auditoría se conserva internamente.

## 13. Simplicidad

Entrada mínima: la de la scorecard actual. No pedir al usuario G, gl, tipo de contexto o
desempate para corregir una limitación del motor. Metadato insuficiente queda desconocido.
Presupuesto: **cero hojas nuevas**, cero esenciales nuevos, cero conceptos Python obligatorios.
El contenido avanzado existente conserva sus valores.

Resumen propuesto de 4–6 líneas: conclusión contextual; cobertura de pruebas; contexto de
calibración con su límite; PD media/tasa/brecha y tabla descriptiva; advertencia sobre empates
cuando aplica; acceso al resultado convencional. Sin nuevo botón «aprobar modelo».

Notebook mínimo: el vigente, sin líneas adicionales para obtener la interpretación en
`summary()`. Leer directamente la nueva clave es opcional para auditoría por código.

Cinco cifras: la línea base está en `tests/unit/test_simplicidad_scorecard.py` y
`test_esenciales_por_seccion.py`; se cotejó por lectura durante el diseño.
Objetivo posterior: mismos conteos de líneas/esenciales/perillas/conceptos y tiempo al primer
resumen dentro del tope vigente. **No se vuelve a correr una scorecard en S59** para medir
segundos; el incremento real de tiempo se medirá una vez al implementar, dentro de sus gates.
No declarar «sin costo» por inspección estática ni usar esa falta para ampliar esta sesión.
