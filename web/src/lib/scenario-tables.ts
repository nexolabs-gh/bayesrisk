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
