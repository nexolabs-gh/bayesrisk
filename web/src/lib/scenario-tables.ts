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
}

export const SIN_TABLAS: ScenarioTablesState = { historia: null, escenarios: null, leido: null }

/** Lo que devuelve el servidor al leer las dos tablas (`POST /api/scenario-tables`). */
export interface TablasLeidas {
  forward: Record<string, unknown>
  summary: string
}

export type ResultadoDeLectura =
  | ({ kind: "aplicar" } & TablasLeidas)
  | { kind: "descartada"; mensaje: string }
  | { kind: "error"; mensaje: string }

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
  describirError?: (err: unknown) => string
}): Promise<ResultadoDeLectura> {
  let leidas: TablasLeidas
  try {
    leidas = await args.pedir(args.historia, args.escenarios)
  } catch (err) {
    const mensaje = args.describirError
      ? args.describirError(err)
      : err instanceof Error
        ? err.message
        : String(err)
    return { kind: "error", mensaje }
  }
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
