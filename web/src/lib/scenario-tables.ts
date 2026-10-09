/**
 * Las dos tablas de los escenarios de la institución que el usuario subió en la pantalla
 * (IFRS9-FIRMABLE capa C). Viven en el store de la app y no en la tarjeta que las sube: la tarjeta
 * se desmonta al cambiar de sección, y sin esto volver a «Escenarios económicos» la mostraba
 * vacía —con la sección todavía encendida— y no se podía cambiar sólo una de las dos tablas
 * (medido en vivo en S40).
 */

/** Una tabla ya subida por `POST /api/upload`. */
export interface TablaSubida {
  datasetId: string
  fileName: string
}

export interface ScenarioTablesState {
  historia: TablaSubida | null
  escenarios: TablaSubida | null
  /** Lo que el servidor leyó la última vez, en una línea; `null` si todavía no las leyó. */
  leido: string | null
  /**
   * La marca del último gesto sobre las tablas —subir una, volver a leerlas, quitarlas—: sólo su
   * continuación puede escribir aquí o en el config. Un gesto dura desde que empieza la subida hasta
   * que termina la lectura que la sigue; uno más nuevo deja sin efecto al anterior, en cualquier
   * orden en que respondan (pasadas 3 y 4 de Codex sobre la capa C).
   */
  gesto?: string
  /** Lo que el último gesto tiene que decir; vive aquí para que lo vea la tarjeta que esté montada. */
  aviso?: string | null
}

export const SIN_TABLAS: ScenarioTablesState = { historia: null, escenarios: null, leido: null }

/** Lo que devuelve el servidor al leer las dos tablas (`POST /api/scenario-tables`). */
export interface TablasLeidas {
  forward: Record<string, unknown>
  /** Lo que la provisión necesita para consumirlos (el ajuste por ciclo); ausente en un mock. */
  provisioning_ifrs9?: Record<string, unknown>
  summary: string
}

export type ResultadoDeLectura =
  | ({ kind: "aplicar" } & TablasLeidas)
  | { kind: "descartada"; mensaje: string }
  | { kind: "error"; mensaje: string }
  /** Un gesto más nuevo la dejó sin efecto: no se aplica ni se dice nada (el nuevo dirá lo suyo). */
  | { kind: "superada" }

/**
 * Lee las dos tablas y dice si lo leído todavía se puede aplicar (pasada 1 de Codex sobre la capa
 * C). La lectura tarda; mientras tanto el usuario puede apagar los escenarios, editar otro campo o
 * cargar otro config, y aplicar una respuesta vieja reencendería lo que decidió apagar. Por eso
 * sólo se aplica si el config es el mismo objeto que cuando se pidió —el store crea uno nuevo en
 * cada cambio—; si no, se descarta y se dice. Sin efectos ni React: lo prueba vitest.
 */
export async function leerTablasVigentes(args: {
  historia: TablaSubida
  escenarios: TablaSubida
  pedir: (historia: TablaSubida, escenarios: TablaSubida) => Promise<TablasLeidas>
  configAlPedir: unknown
  configActual: () => unknown
  /** ¿Sigue siendo el gesto vigente? Si no, la respuesta se ignora (pasada 4 de Codex). */
  vigente?: () => boolean
  describirError?: (err: unknown) => string
}): Promise<ResultadoDeLectura> {
  let leidas: TablasLeidas
  try {
    leidas = await args.pedir(args.historia, args.escenarios)
  } catch (err) {
    if (args.vigente && !args.vigente()) return { kind: "superada" }
    const mensaje = args.describirError
      ? args.describirError(err)
      : err instanceof Error
        ? err.message
        : String(err)
    return { kind: "error", mensaje }
  }
  if (args.vigente && !args.vigente()) return { kind: "superada" }
  if (args.configActual() !== args.configAlPedir) {
    return {
      kind: "descartada",
      mensaje:
        "Cambiaste la configuración mientras se leían las tablas, así que no se aplicaron: " +
        "vuelve a leerlas.",
    }
  }
  return { kind: "aplicar", ...leidas }
}

export type ResultadoDeSubida =
  | { kind: "descartar" }
  /** La primera de las dos: todavía no hay qué leer, así que se guarda tal cual. */
  | { kind: "guardar"; siguiente: ScenarioTablesState }
  /** Con las dos: se leen, y la nueva queda sólo si el servidor la lee. */
  | { kind: "leer"; historia: TablaSubida; escenarios: TablaSubida }

/**
 * Decide qué hacer con una tabla que terminó de subir. Se descarta si su gesto ya no es el vigente
 * —una subida vieja que vuelve tarde pisaba a una más nueva— o si el config cambió mientras subía.
 * Con las dos tablas no se guarda nada todavía: un archivo rechazado no reemplaza al último leído.
 * Pura (pasadas 3 y 4 de Codex sobre la capa C).
 */
export function resolverSubida(
  vigente: ScenarioTablesState,
  cual: "historia" | "escenarios",
  marca: string,
  subida: TablaSubida,
  configActual: unknown,
  configAlPedir: unknown,
): ResultadoDeSubida {
  if (vigente.gesto !== marca || configActual !== configAlPedir) return { kind: "descartar" }
  const historia = cual === "historia" ? subida : vigente.historia
  const escenarios = cual === "escenarios" ? subida : vigente.escenarios
  if (historia !== null && escenarios !== null) return { kind: "leer", historia, escenarios }
  return { kind: "guardar", siguiente: { ...vigente, [cual]: subida } }
}

let ultimaMarca = 0

/** Una marca nueva por gesto (fuera de React: sobrevive a que la tarjeta se desmonte). */
function nuevaMarca(): string {
  ultimaMarca += 1
  return String(ultimaMarca)
}

/** Lo que la tarjeta le presta a la secuencia: el store, la API y la sección. */
export interface PuertoDeLasTablas {
  getTablas: () => ScenarioTablesState
  setTablas: (cambio: (actual: ScenarioTablesState) => ScenarioTablesState) => void
  getConfig: () => unknown
  subir: (archivo: { name: string }) => Promise<TablaSubida>
  pedir: (historia: TablaSubida, escenarios: TablaSubida) => Promise<TablasLeidas>
  /** Enciende la sección con lo leído (el `ConfigTab`). */
  aplicar: (leidas: TablasLeidas) => void
  /** ¿La sección de escenarios está encendida ahora? */
  activa: () => boolean
  describirError: (err: unknown) => string
  /** En qué está la tarjeta, para su indicador; `null` al terminar. */
  fase?: (fase: "historia" | "escenarios" | "leer" | null) => void
}

/** Empieza un gesto nuevo: deja sin efecto a los anteriores y borra lo que decían. */
function empezar(puerto: PuertoDeLasTablas, cambio?: Partial<ScenarioTablesState>): string {
  const marca = nuevaMarca()
  puerto.setTablas((actual) => ({ ...actual, ...cambio, gesto: marca, aviso: null }))
  return marca
}

/** Escribe un aviso sólo si su gesto sigue siendo el vigente. */
function avisar(puerto: PuertoDeLasTablas, marca: string, aviso: string) {
  puerto.setTablas((actual) => (actual.gesto === marca ? { ...actual, aviso } : actual))
}

/**
 * Sube una de las dos tablas y, si ya están las dos, las hace leer. Toda la secuencia es un solo
 * gesto: si mientras sube o se lee el usuario pide otra tabla, vuelve a leer o quita los escenarios
 * —también desde la tarjeta montada de nuevo al volver a la sección—, lo de este gesto se ignora,
 * responda antes o después (pasada 4 de Codex sobre la capa C). El config se toma antes de la
 * primera espera: si cambia mientras tanto (otro YAML, apagar la sección), tampoco se aplica.
 */
export async function subirTabla(
  puerto: PuertoDeLasTablas,
  cual: "historia" | "escenarios",
  archivo: { name: string },
): Promise<void> {
  const alPedir = puerto.getConfig()
  const marca = empezar(puerto)
  puerto.fase?.(cual)
  let subida: TablaSubida
  try {
    subida = await puerto.subir(archivo)
  } catch (err) {
    puerto.fase?.(null)
    avisar(puerto, marca, puerto.describirError(err))
    return
  }
  puerto.fase?.(null)
  const resultado = resolverSubida(
    puerto.getTablas(),
    cual,
    marca,
    subida,
    puerto.getConfig(),
    alPedir,
  )
  if (resultado.kind === "descartar") {
    avisar(
      puerto,
      marca,
      `«${archivo.name}» terminó de subir cuando ya había cambiado la configuración, así que no ` +
        "se usó. Vuelve a subirlo si es el que quieres.",
    )
    return
  }
  if (resultado.kind === "guardar") {
    puerto.setTablas(() => resultado.siguiente) // sin espera desde que se decidió: sigue vigente
    return
  }
  await leerEnElGesto(puerto, resultado.historia, resultado.escenarios, marca, alPedir, archivo.name)
}

/** Vuelve a leer las dos tablas guardadas, como un gesto nuevo. */
export async function releerTablas(puerto: PuertoDeLasTablas): Promise<void> {
  const { historia, escenarios } = puerto.getTablas()
  if (historia === null || escenarios === null) return
  const alPedir = puerto.getConfig()
  const marca = empezar(puerto)
  await leerEnElGesto(puerto, historia, escenarios, marca, alPedir)
}

/** Quita lo leído de la tarjeta y deja sin efecto cualquier gesto en curso (quitar los escenarios). */
export function quitarLecturas(puerto: PuertoDeLasTablas): void {
  empezar(puerto, { leido: null })
}

async function leerEnElGesto(
  puerto: PuertoDeLasTablas,
  historia: TablaSubida,
  escenarios: TablaSubida,
  marca: string,
  alPedir: unknown,
  nuevo?: string,
): Promise<void> {
  puerto.fase?.("leer")
  const resultado = await leerTablasVigentes({
    historia,
    escenarios,
    pedir: puerto.pedir,
    configAlPedir: alPedir,
    configActual: puerto.getConfig,
    vigente: () => puerto.getTablas().gesto === marca,
    describirError: puerto.describirError,
  })
  puerto.fase?.(null)
  if (resultado.kind === "superada") return
  if (resultado.kind === "aplicar") {
    puerto.aplicar(resultado)
    puerto.setTablas((actual) => ({ ...actual, historia, escenarios, leido: resultado.summary }))
    return
  }
  const siguen =
    puerto.activa() && puerto.getTablas().leido !== null
      ? " La sección sigue con las tablas que se leyeron antes."
      : ""
  const mensaje =
    resultado.kind === "error" && nuevo !== undefined
      ? `No se leyó «${nuevo}»: ${resultado.mensaje}`
      : resultado.mensaje
  avisar(puerto, marca, `${mensaje}${siguen}`)
}
