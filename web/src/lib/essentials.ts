/**
 * Esenciales abiertos y «Avanzado» plegado, por sección (SDD-31 D-SIM-4; enmienda
 * FLUJO-GUIADO-SCORECARD D-FLU-8).
 *
 * El motor marca cada campo esencial en el schema (`ui_essential: true`, metadato de
 * `json_schema_extra`) y cada sección que ya declaró los suyos (`ui_essentials_declared: true`,
 * `declara_esenciales` en el core). Con eso la pantalla divide el formulario de una sección en dos
 * vistas que editan **el mismo config por los mismos `path`**:
 *
 * - **esenciales**: los campos marcados, abiertos y planos (≤ 6 por sección, tope de Cami);
 * - **«Avanzado»**: todo lo demás, en UN bloque cerrado que dice cuántos de sus campos difieren
 *   del valor de fábrica. Dentro, los grupos (`ui_group`), la ayuda y la validación en vivo
 *   siguen exactamente como estaban.
 *
 * Una marca puede vivir DENTRO de un sub-modelo (`report.document.author`, `data.load.source`), así
 * que la división baja por los sub-modelos y los poda: la vista de esenciales recibe una copia del
 * sub-modelo con sólo sus hojas marcadas y la de «Avanzado» otra con el resto. Un sub-modelo que
 * queda entero en una de las dos vistas viaja **sin copiar** (conserva su `$ref`), que es lo que
 * mantiene intactos los defaults por `$defs` de las listas y las variantes. Una unión discriminada
 * (la estrategia de partición) y una lista son **atómicas**: van enteras a la vista de esenciales si
 * alguna de sus hojas está marcada —el selector de variante no se puede pintar dos veces— y enteras
 * a «Avanzado» si no.
 *
 * Una sección SIN la marca de sección —un módulo que todavía no pasó por su enmienda de
 * simplicidad— no se divide y se pinta entera, como siempre.
 *
 * Lógica PURA (sin React), testeable con vitest. `ESSENTIALS_BY_SECTION` es el espejo del golden de
 * Python (`tests/unit/test_esenciales_por_seccion.py::ESENCIALES_POR_SECCION`), atado en los dos
 * sentidos: el front lo compara con las marcas del fixture y la suite de Python lo compara con el
 * suyo.
 */

import {
  type DefaultsNode,
  type EffectiveDefaults,
  canonicalProjection,
  isDescriptor,
  nodeAtPath,
} from "@/lib/effective-defaults"
import {
  type Defs,
  type JsonSchema,
  groupedFields,
  isHiddenField,
  resolveRef,
  unwrapNullable,
} from "@/lib/form-engine"

/** La rama nula de una unión `X | None` (mismo criterio que `unwrapNullable`). */
function isNullSchema(schema: JsonSchema): boolean {
  return schema.type === "null"
}

/**
 * Los caminos esenciales por sección, tal como los declara la enmienda (§3.8) y los ancla el golden
 * de Python. Un camino que viva en varias ramas de una unión (`holdout_fraction`) se lista una vez.
 * `eda` declara sus esenciales y son cero: todo default, el resumen lo muestra.
 */
export const ESSENTIALS_BY_SECTION: Record<string, readonly string[]> = {
  data: [
    "data.load.source",
    "data.schema.unique_keys",
    "data.target.bad_rule",
    "data.partition.strategy.cohort_col",
    "data.partition.strategy.date_col",
    "data.partition.strategy.holdout_fraction",
    "data.partition.strategy.oot_cohorts",
    "data.partition.strategy.oot_from",
  ],
  eda: [],
  binning: [
    "binning.categorical_columns",
    "binning.feature_columns",
    "binning.max_n_bins",
    "binning.min_bin_size",
    "binning.monotonic_trend",
  ],
  selection: [
    "selection.correlation.threshold",
    "selection.min_iv",
    "selection.vif.threshold",
  ],
  model: [
    "model.sign_policy.action",
    "model.stepwise.enabled",
    "model.stepwise.entry_p_value",
    "model.stepwise.exit_p_value",
  ],
  scorecard: ["scorecard.pdo", "scorecard.target_odds", "scorecard.target_score"],
  calibration: ["calibration.anchor_source", "calibration.target_pd"],
  performance: ["performance.n_deciles"],
  stability: ["stability.psi_review_threshold", "stability.psi_stable_threshold"],
  validation: ["validation.families"],
  report: [
    "report.document.author",
    "report.document.entity",
    "report.document.model_name",
    "report.document.portfolio",
    "report.formats",
  ],
  governance: [
    "governance.author",
    "governance.purpose",
    "governance.review_period_months",
  ],
  // FLUJO-GUIADO-IFRS9 D-ECL-6: las columnas de la curva y de la provisión (la de IFRS 9 trae diez,
  // la única excepción al tope de seis, §8-4; de siete a diez por CASO-REAL-IFRS9 §8-3: las tres
  // del contrato, opcionales).
  survival: [
    "survival.input.covariate_cols",
    "survival.input.duration_col",
    "survival.input.event_col",
    "survival.time_grid.horizon_periods",
    "survival.time_grid.time_unit",
  ],
  provisioning_ifrs9: [
    "provisioning_ifrs9.as_of_date_col",
    "provisioning_ifrs9.ead.ead_col",
    "provisioning_ifrs9.ead.installment_col",
    "provisioning_ifrs9.ecl.eir_col",
    "provisioning_ifrs9.lgd.lgd_col",
    "provisioning_ifrs9.maturity_date_col",
    "provisioning_ifrs9.origination_date_col",
    "provisioning_ifrs9.portfolio_col",
    "provisioning_ifrs9.staging.days_past_due_col",
    "provisioning_ifrs9.staging.is_default_col",
  ],
}

/** Rótulo del bloque plegado. Copy público: una palabra que el modelador entiende. */
export const AVANZADO = "Avanzado"

/** Vista a la que va un campo (o la parte de un sub-modelo) al dividir la sección. */
export type Vista = "essential" | "advanced"

/** ¿La sección ya declaró sus esenciales? Sólo entonces se divide (aunque declare cero). */
export function declaresEssentials(sectionSchema: JsonSchema): boolean {
  return sectionSchema.ui_essentials_declared === true
}

// ---------------------------------------------------------------------------
// Marcas: dónde hay un esencial
// ---------------------------------------------------------------------------

/** Ramas objeto no nulas de una unión, sin resolver. */
function branches(schema: JsonSchema): JsonSchema[] {
  const variants = schema.anyOf ?? schema.oneOf
  if (!variants) return []
  return variants.filter((v) => !isNullSchema(v))
}

/** Clave de `$ref` para cortar recursiones (reglas anidadas del target). */
function refKey(schema: JsonSchema): string | undefined {
  return typeof schema.$ref === "string" ? schema.$ref : undefined
}

/**
 * ¿Hay alguna marca `ui_essential` en este nodo o debajo (todas las ramas, los `items`)?
 * Mismo barrido que `_marcas` en el golden de Python.
 */
export function hasEssentialInside(
  schema: JsonSchema,
  defs: Defs,
  visited: readonly string[] = [],
): boolean {
  if (schema.ui_essential === true) return true
  const ref = refKey(schema)
  if (ref !== undefined && visited.includes(ref)) return false
  const seen = ref === undefined ? visited : [...visited, ref]
  const target = resolveRef(schema, defs)
  if (target !== schema && target.ui_essential === true) return true
  for (const branch of branches(target)) {
    if (hasEssentialInside(branch, defs, seen)) return true
  }
  for (const child of Object.values(target.properties ?? {})) {
    if (hasEssentialInside(child, defs, seen)) return true
  }
  return target.items !== undefined && hasEssentialInside(target.items, defs, seen)
}

/**
 * Todos los caminos marcados bajo `schema`, con el prefijo dado: por todas las ramas de una unión y
 * por los `items` de una lista, sin `[]`. Es el espejo de `_marcas` (golden de Python) y lo que el
 * test del front compara con `ESSENTIALS_BY_SECTION` sobre el fixture del schema.
 */
export function essentialPaths(
  schema: JsonSchema,
  defs: Defs,
  prefix: string,
  visited: readonly string[] = [],
): Set<string> {
  const out = new Set<string>()
  if (schema.ui_essential === true) out.add(prefix)
  const ref = refKey(schema)
  if (ref !== undefined && visited.includes(ref)) return out
  const seen = ref === undefined ? visited : [...visited, ref]
  const target = resolveRef(schema, defs)
  if (target !== schema && target.ui_essential === true) out.add(prefix)
  for (const branch of branches(target)) {
    for (const p of essentialPaths(branch, defs, prefix, seen)) out.add(p)
  }
  for (const [name, child] of Object.entries(target.properties ?? {})) {
    const path = prefix ? `${prefix}.${name}` : name
    for (const p of essentialPaths(child, defs, path, seen)) out.add(p)
  }
  if (target.items !== undefined) {
    for (const p of essentialPaths(target.items, defs, prefix, seen)) out.add(p)
  }
  return out
}

// ---------------------------------------------------------------------------
// Poda: la parte de un campo que va a cada vista
// ---------------------------------------------------------------------------

/** ¿El nodo (ya resuelto) se pinta como un sub-modelo con campos propios? */
function isSubmodel(target: JsonSchema): boolean {
  return (
    target.properties !== undefined &&
    branches(target).length === 0 &&
    target.items === undefined
  )
}

/**
 * ¿El esencial va en el bloque pedido? ``grupo`` sin declarar (``undefined``) es «todos»: la
 * poda de siempre. ``null`` es «los sin subtítulo»; un texto, los de ese subtítulo
 * (``ui_essential_group``, CASO-REAL-IFRS9 §13).
 */
function enGrupo(schema: JsonSchema, grupo: string | null | undefined): boolean {
  if (grupo === undefined) return true
  return (schema.ui_essential_group ?? null) === grupo
}

/** Las claves del campo declarado que viajan con él aunque se copie el sub-modelo. */
function outerKeys(schema: JsonSchema): JsonSchema {
  const rest: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(schema)) {
    if (key !== "$ref" && key !== "anyOf" && key !== "oneOf") rest[key] = value
  }
  return rest as JsonSchema
}

/**
 * La parte de `schema` (un campo, tal como lo declara su padre) que pertenece a `vista`, o `null`
 * si nada de él va ahí.
 *
 * - Un campo `hidden` no va a ninguna vista (los enumeradores del formulario ya lo omiten).
 * - Un campo marcado `ui_essential` es esencial ENTERO, sea hoja o sub-modelo (`data.target.bad_rule`).
 * - Una unión, una lista o una hoja son atómicas: esenciales si tienen alguna marca dentro.
 * - Un sub-modelo se divide campo a campo. Si todo él cae en la misma vista, se devuelve el schema
 *   ORIGINAL (con su `$ref`); si no, una copia inline con sólo los campos de esa vista y las claves
 *   del campo declarado (título, grupo, ayuda) encima, respetando la nulabilidad.
 */
export function pruneForView(
  schema: JsonSchema,
  defs: Defs,
  vista: Vista,
  visited: readonly string[] = [],
  grupo?: string | null,
): JsonSchema | null {
  if (isHiddenField(schema)) return null
  if (schema.ui_essential === true) {
    return vista === "essential" && enGrupo(schema, grupo) ? schema : null
  }
  const { schema: base, nullable } = unwrapNullable(schema)
  const ref = refKey(base)
  if (ref !== undefined && visited.includes(ref)) {
    return vista === "advanced" ? schema : null
  }
  const seen = ref === undefined ? visited : [...visited, ref]
  const target = resolveRef(base, defs)
  if (target.ui_essential === true) {
    return vista === "essential" && enGrupo(base, grupo) ? schema : null
  }
  if (!isSubmodel(target)) {
    const essential = hasEssentialInside(target, defs, seen)
    // Una unión o lista atómica con marcas dentro va con los esenciales sin subtítulo.
    const enSuGrupo = vista !== "essential" || grupo === undefined || grupo === null
    return (vista === "essential") === essential && enSuGrupo ? schema : null
  }
  const kept: Record<string, JsonSchema> = {}
  let intact = true
  const props = target.properties ?? {}
  for (const [name, child] of Object.entries(props)) {
    const part = pruneForView(child, defs, vista, seen, grupo)
    if (part === null) {
      // Un campo `hidden` no cuenta: la vista lo omite igual que el formulario entero.
      if (!isHiddenField(child)) intact = false
      continue
    }
    if (part !== child) intact = false
    kept[name] = part
  }
  if (Object.keys(kept).length === 0) return null
  if (intact) return schema
  const pruned: JsonSchema = {
    ...target,
    ...outerKeys(base),
    properties: kept,
    required: (target.required ?? []).filter((name) => name in kept),
  }
  if (!nullable) return pruned
  return { ...outerKeys(schema), anyOf: [pruned, { type: "null" }] }
}

/** Un campo de primer nivel de la sección ya podado para su vista. */
export type SectionField = [string, JsonSchema]

/**
 * El campo de primer nivel tal como se poda: un campo OBLIGATORIO que admite `null`
 * (`data.target`, `data.partition`, D-ECL-2) se poda como su rama no nula, porque el formulario no
 * lo pinta con interruptor (`FieldRenderer`): su `null` es una declaración de la corrida de
 * cartera, no un estado apagado. Sin esto, la vista lo envolvería en `anyOf: [T, null]` y cada una
 * de las dos vistas pintaría su propio interruptor sobre el mismo objeto.
 */
function campoDeSeccion(sectionSchema: JsonSchema, name: string, schema: JsonSchema): JsonSchema {
  if (!(sectionSchema.required ?? []).includes(name)) return schema
  return unwrapNullable(schema).schema
}

/**
 * Los esenciales de la sección, planos y en el orden en que el formulario los pintaría (grupo de
 * declaración, luego `ui_order`), cada uno podado a sus hojas marcadas.
 */
export function essentialFields(
  sectionSchema: JsonSchema,
  defs: Defs,
  grupo?: string | null,
): SectionField[] {
  const out: SectionField[] = []
  for (const group of groupedFields(sectionSchema)) {
    for (const [name, schema] of group.fields) {
      const part = pruneForView(
        campoDeSeccion(sectionSchema, name, schema),
        defs,
        "essential",
        [],
        grupo,
      )
      if (part !== null) out.push([name, part])
    }
  }
  return out
}

/** Un bloque de esenciales opcionales que van juntos bajo su subtítulo (CASO-REAL-IFRS9 §13). */
export interface EssentialGroup {
  etiqueta: string
  campos: SectionField[]
}

/**
 * Los subtítulos (`ui_essential_group`) que declaran los esenciales de la sección, en el orden en
 * que aparecen, cada uno con sus campos podados a las hojas de ese subtítulo —también las que
 * cuelgan de un sub-modelo, como la cuota en `ead`—. Los esenciales sin subtítulo los da
 * `essentialFields(schema, defs, null)`.
 */
export function essentialGroups(sectionSchema: JsonSchema, defs: Defs): EssentialGroup[] {
  const etiquetas: string[] = []
  const recorrer = (schema: JsonSchema, visited: readonly string[]): void => {
    if (isHiddenField(schema)) return
    const { schema: base } = unwrapNullable(schema)
    const etiqueta = schema.ui_essential_group ?? base.ui_essential_group
    if ((schema.ui_essential === true || base.ui_essential === true) && etiqueta) {
      if (!etiquetas.includes(etiqueta)) etiquetas.push(etiqueta)
      return
    }
    const ref = refKey(base)
    if (ref !== undefined && visited.includes(ref)) return
    const target = resolveRef(base, defs)
    if (!isSubmodel(target)) return
    const seen = ref === undefined ? visited : [...visited, ref]
    for (const group of groupedFields(target)) {
      for (const [, child] of group.fields) recorrer(child, seen)
    }
  }
  for (const group of groupedFields(sectionSchema)) {
    for (const [, schema] of group.fields) recorrer(schema, [])
  }
  return etiquetas.map((etiqueta) => ({
    etiqueta,
    campos: essentialFields(sectionSchema, defs, etiqueta),
  }))
}

/**
 * La sección podada a lo que va a «Avanzado» (mismo objeto, sólo con esos campos), o `null` si
 * nada queda plegado. Se consume con `groupedFields` como la sección entera: los grupos no cambian.
 */
export function advancedSchema(sectionSchema: JsonSchema, defs: Defs): JsonSchema | null {
  const kept: Record<string, JsonSchema> = {}
  for (const [name, schema] of Object.entries(sectionSchema.properties ?? {})) {
    const part = pruneForView(campoDeSeccion(sectionSchema, name, schema), defs, "advanced")
    if (part !== null) kept[name] = part
  }
  if (Object.keys(kept).length === 0) return null
  return {
    ...sectionSchema,
    properties: kept,
    required: (sectionSchema.required ?? []).filter((name) => name in kept),
  }
}

// ---------------------------------------------------------------------------
// Hojas de «Avanzado»: contar cambios, anclar errores y foco
// ---------------------------------------------------------------------------

/** Una hoja de la vista «Avanzado»: su `path` y el nodo del catálogo que le corresponde. */
export interface AdvancedLeaf {
  path: string[]
  key: string
}

/**
 * Las hojas de un schema podado a «Avanzado»: cada campo atómico (hoja, lista o unión) con su
 * `path`. Un sub-modelo se recorre; una lista o una unión cuentan como UNA hoja, igual que en el
 * formulario, donde se editan con un solo control (o un selector de variante).
 */
export function advancedLeaves(
  schema: JsonSchema | null,
  defs: Defs,
  base: readonly string[],
): AdvancedLeaf[] {
  if (schema === null) return []
  const out: AdvancedLeaf[] = []
  const walk = (node: JsonSchema, path: string[], visited: readonly string[]) => {
    if (isHiddenField(node)) return
    const { schema: unwrapped } = unwrapNullable(node)
    const ref = refKey(unwrapped)
    const target = resolveRef(unwrapped, defs)
    if (isSubmodel(target) && !(ref !== undefined && visited.includes(ref))) {
      const seen = ref === undefined ? visited : [...visited, ref]
      for (const [name, child] of Object.entries(target.properties ?? {})) {
        walk(child, [...path, name], seen)
      }
      return
    }
    out.push({ path, key: path.join(".") })
  }
  for (const [name, child] of Object.entries(schema.properties ?? {})) {
    walk(child, [...base, name], [])
  }
  return out
}

/** Igualdad estructural por JSON canónico (claves ordenadas): `[]`, `null` y `0` son valores. */
function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, v) => {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const obj = v as Record<string, unknown>
      return Object.fromEntries(Object.keys(obj).sort().map((k) => [k, obj[k]]))
    }
    return v
  })
}

/** Lo que el motor usaría en este nodo del catálogo, o `undefined` si no hay default que ofrecer. */
function defaultOf(node: DefaultsNode | undefined): { known: boolean; value?: unknown } {
  if (node === undefined) return { known: false }
  if (isDescriptor(node)) {
    if (node.has_default) return { known: true, value: node.value }
    if (node.children) return { known: true, value: canonicalProjection(node.children) }
    return { known: false }
  }
  return { known: true, value: canonicalProjection(node) }
}

/**
 * ¿La hoja difiere de su valor de fábrica? Sólo una clave PRESENTE en el config puede diferir
 * (D-FX-7: la ausencia es el default). Una hoja obligatoria sin default —el catálogo no ofrece
 * nada— cuenta como cambiada cuando el usuario la escribió: no hay fábrica con la que coincidir.
 * Sin catálogo no se afirma nada.
 */
export function differsFromDefault(stored: unknown, node: DefaultsNode | undefined): boolean {
  if (stored === undefined) return false
  if (node === undefined) return false
  const def = defaultOf(node)
  if (!def.known) return true
  return canonical(stored) !== canonical(def.value)
}

/** Baja por un objeto siguiendo `path`; `undefined` en cuanto falta un tramo. */
function valueAt(config: unknown, path: readonly string[]): unknown {
  let current: unknown = config
  for (const segment of path) {
    if (current === null || typeof current !== "object" || Array.isArray(current)) {
      return undefined
    }
    current = (current as Record<string, unknown>)[segment]
    if (current === undefined) return undefined
  }
  return current
}

/** Cuántas hojas de «Avanzado» difieren de su valor de fábrica (D-FLU-8). */
export function countChangedAdvanced(
  leaves: readonly AdvancedLeaf[],
  config: Record<string, unknown>,
  catalog: EffectiveDefaults | undefined,
): number {
  let changed = 0
  for (const leaf of leaves) {
    const node = nodeAtPath(catalog, leaf.path)
    if (differsFromDefault(valueAt(config, leaf.path), node)) changed += 1
  }
  return changed
}

/** ¿`key` (un `path` unido por puntos) es una hoja de «Avanzado» o vive dentro de una? */
export function insideAdvanced(leaves: readonly AdvancedLeaf[], key: string): boolean {
  const normalized = key.replace(/\[(\d+)\]/g, ".$1")
  return leaves.some((leaf) => normalized === leaf.key || normalized.startsWith(`${leaf.key}.`))
}

/** Cuántos errores de validación del backend caen en hojas de «Avanzado». */
export function errorsInsideAdvanced(
  leaves: readonly AdvancedLeaf[],
  errors: Map<string, string> | undefined,
): number {
  if (!errors) return 0
  let count = 0
  for (const key of errors.keys()) {
    if (insideAdvanced(leaves, key)) count += 1
  }
  return count
}

/**
 * Lo que dice el bloque plegado además de «Avanzado»: cuántos campos difieren de fábrica y, si los
 * hay, cuántos errores tiene dentro. Sin cambios lo dice; el número nunca se omite en silencio.
 */
export function advancedSummary(changed: number, errors: number): string {
  const partes: string[] = []
  if (changed === 0) partes.push("sin cambios")
  else partes.push(changed === 1 ? "1 campo cambiado" : `${changed} campos cambiados`)
  if (errors === 1) partes.push("1 error")
  else if (errors > 1) partes.push(`${errors} errores`)
  return partes.join(" · ")
}
