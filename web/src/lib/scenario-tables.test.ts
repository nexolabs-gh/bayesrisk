import { describe, expect, it } from "vitest"

import { leerTablasVigentes, SIN_TABLAS } from "@/lib/scenario-tables"

/** Una promesa que el test resuelve cuando quiere: la respuesta «tardía» del servidor. */
function diferida<T>() {
  let resolver!: (valor: T) => void
  const promesa = new Promise<T>((r) => {
    resolver = r
  })
  return { promesa, resolver }
}

const HISTORIA = { datasetId: "uploaded_h", fileName: "historia.csv" }
const ESCENARIOS = { datasetId: "uploaded_e", fileName: "escenarios.csv" }

describe("la lectura de las dos tablas sólo se aplica si el config no cambió (pasada 1 de Codex)", () => {
  it("una respuesta que llega con el mismo config se aplica", async () => {
    const config = { forward: null }
    const respuesta = diferida<{ forward: Record<string, unknown>; summary: string }>()
    const lectura = leerTablasVigentes({
      historia: HISTORIA,
      escenarios: ESCENARIOS,
      pedir: () => respuesta.promesa,
      configAlPedir: config,
      configActual: () => config,
    })
    respuesta.resolver({ forward: { macro: { kind: "scenario_paths" } }, summary: "Escenarios: 2" })
    const resultado = await lectura
    expect(resultado.kind).toBe("aplicar")
  })

  it("si el usuario apagó los escenarios o cargó otro config mientras esperaba, se descarta", async () => {
    let config: Record<string, unknown> = { forward: null }
    const alPedir = config
    const respuesta = diferida<{ forward: Record<string, unknown>; summary: string }>()
    const lectura = leerTablasVigentes({
      historia: HISTORIA,
      escenarios: ESCENARIOS,
      pedir: () => respuesta.promesa,
      configAlPedir: alPedir,
      configActual: () => config,
    })
    config = { ...config, provisioning_ifrs9: { pd: { pit_mode: "ttc_only" } } }
    respuesta.resolver({ forward: { macro: { kind: "scenario_paths" } }, summary: "Escenarios: 2" })
    const resultado = await lectura
    expect(resultado.kind).toBe("descartada")
    if (resultado.kind === "descartada") expect(resultado.mensaje).toMatch(/vuelve a leerlas/)
  })

  it("un error del servidor se dice y no toca nada", async () => {
    const config = { forward: null }
    const resultado = await leerTablasVigentes({
      historia: HISTORIA,
      escenarios: ESCENARIOS,
      pedir: () => Promise.reject(new Error("Hacen falta al menos dos escenarios")),
      configAlPedir: config,
      configActual: () => config,
    })
    expect(resultado).toEqual({ kind: "error", mensaje: "Hacen falta al menos dos escenarios" })
    expect(SIN_TABLAS.leido).toBeNull()
  })
})
