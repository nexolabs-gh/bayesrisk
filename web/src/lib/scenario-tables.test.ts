import { describe, expect, it } from "vitest"

import tarjetaFuente from "@/components/ScenarioTablesCard.tsx?raw"
import { leerTablasVigentes, resolverSubida, SIN_TABLAS } from "@/lib/scenario-tables"

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

describe("la tarjeta compara contra el config del store (pasada 2 de Codex)", () => {
  it("no guarda su propia copia del config y lo captura antes de subir", () => {
    // Una copia local (`useRef(config)`) se queda vieja si la tarjeta se desmonta y otro YAML se
    // carga en otra sección: la lectura vieja se aplicaba sobre el config nuevo.
    expect(tarjetaFuente).not.toMatch(/useRef\(config\)/)
    expect(tarjetaFuente).toMatch(/configActual: getConfig/)
    // Y la referencia se toma al empezar la subida, no al volver de ella.
    const subir = tarjetaFuente.slice(tarjetaFuente.indexOf("async function subir"))
    expect(subir.indexOf("getConfig()")).toBeLessThan(subir.indexOf("await uploadDataset"))
  })

  it("decide cada subida con `resolverSubida` antes de guardarla (pasada 3 de Codex)", () => {
    // La primera tabla se guardaba sin guarda: una subida vieja pisaba a una más nueva.
    const subir = tarjetaFuente.slice(tarjetaFuente.indexOf("async function subir"))
    const tras = subir.slice(subir.indexOf("await uploadDataset"))
    expect(subir.indexOf("pendiente:")).toBeLessThan(subir.indexOf("await uploadDataset"))
    expect(tras.indexOf("resolverSubida(getTablas()")).toBeGreaterThan(-1)
    expect(tras.indexOf("resolverSubida(")).toBeLessThan(tras.indexOf("setTablas(siguiente)"))
  })
})

describe("una subida vieja no pisa a una más nueva (pasada 3 de Codex)", () => {
  const A = { datasetId: "uploaded_a", fileName: "historia-a.csv" }
  const B = { datasetId: "uploaded_b", fileName: "historia-b.csv" }

  it("la subida que vuelve después de otra más nueva de la misma tabla se descarta", () => {
    const config = { forward: null }
    // Se pidió A (marca 1), después B (marca 2); B ya se guardó y A vuelve tarde.
    const vigente = { ...SIN_TABLAS, historia: B, pendiente: {} }
    expect(resolverSubida(vigente, "historia", "1", A, config, config).kind).toBe("descartar")
  })

  it("si el config cambió mientras subía, se descarta", () => {
    const vigente = { ...SIN_TABLAS, pendiente: { historia: "1" } }
    const resultado = resolverSubida(vigente, "historia", "1", A, { otro: 1 }, { forward: null })
    expect(resultado.kind).toBe("descartar")
  })

  it("la subida vigente se guarda y libera su marca", () => {
    const config = { forward: null }
    const vigente = { ...SIN_TABLAS, escenarios: B, pendiente: { historia: "7" } }
    const resultado = resolverSubida(vigente, "historia", "7", A, config, config)
    expect(resultado.kind).toBe("guardar")
    if (resultado.kind === "guardar") {
      expect(resultado.siguiente.historia).toEqual(A)
      expect(resultado.siguiente.escenarios).toEqual(B)
      expect(resultado.siguiente.pendiente?.historia).toBeUndefined()
    }
  })
})
