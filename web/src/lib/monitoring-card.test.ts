/**
 * `subirYElegir` (SDD-33 capa B; pasada 1 de Codex): una subida vieja no pisa la tarjeta elegida.
 *
 * Con promesas diferidas: la subida se resuelve cuando el test lo decide, después de que la persona
 * eligió otra tarjeta, escribió la ruta a mano o salió de la sección.
 */
import { describe, expect, it } from "vitest"

import type { MonitorableCard } from "@/lib/api"
import { bundleDeLaSeccion, subirYElegir, type PuertoDeLaTarjeta } from "@/lib/monitoring-card"

const tarjeta = (path: string): MonitorableCard => ({
  origin: "upload",
  run_id: null,
  name: path,
  created_at: null,
  bundle_hash: "a".repeat(64),
  n_grades: 5,
  path,
})

function diferida() {
  let resolver: (t: MonitorableCard) => void = () => {}
  const promesa = new Promise<MonitorableCard>((r) => {
    resolver = r
  })
  return { promesa, resolver }
}

function puerto(inicial: string | null) {
  const estado = { bundle: inicial }
  const subida = diferida()
  const p: PuertoDeLaTarjeta = {
    getBundle: () => estado.bundle,
    setBundle: (ruta) => {
      estado.bundle = ruta
    },
    subir: () => subida.promesa,
  }
  return { p, estado, subida }
}

const archivo = new File(["zip"], "t.zip")

describe("subirYElegir", () => {
  it("sin cambios entre tanto, elige la tarjeta subida", async () => {
    const { p, estado, subida } = puerto(null)
    const vuelo = subirYElegir(p, archivo, () => true)
    subida.resolver(tarjeta("A"))
    expect(await vuelo).not.toBeNull()
    expect(estado.bundle).toBe("A")
  })

  it("otra elección mientras sube: la respuesta vieja no la pisa", async () => {
    const { p, estado, subida } = puerto(null)
    const vuelo = subirYElegir(p, archivo, () => true)
    estado.bundle = "B" // la lista, el campo de texto u otro montaje eligieron otra
    subida.resolver(tarjeta("A"))
    expect(await vuelo).toBeNull()
    expect(estado.bundle).toBe("B")
  })

  it("un gesto anulado (otro gesto o la sección desmontada) no escribe", async () => {
    const { p, estado, subida } = puerto("X")
    let vigente = true
    const vuelo = subirYElegir(p, archivo, () => vigente)
    vigente = false
    subida.resolver(tarjeta("A"))
    expect(await vuelo).toBeNull()
    expect(estado.bundle).toBe("X")
  })

  it("la sección apagada mientras sube no se reactiva con la respuesta (pasada 2)", async () => {
    const { p, estado, subida } = puerto(null)
    const apagable = {
      ...p,
      getBundle: () => (apagada ? undefined : estado.bundle),
    }
    let apagada = false
    const vuelo = subirYElegir(apagable, archivo, () => true)
    apagada = true // la persona apagó la sección: `monitoring` es null
    subida.resolver(tarjeta("A"))
    expect(await vuelo).toBeNull()
    expect(estado.bundle).toBeNull()
  })

  it("con la sección apagada desde el principio, la subida no la enciende", async () => {
    const { p, estado, subida } = puerto(null)
    const apagada = { ...p, getBundle: () => undefined }
    const vuelo = subirYElegir(apagada, archivo, () => true)
    subida.resolver(tarjeta("A"))
    expect(await vuelo).toBeNull()
    expect(estado.bundle).toBeNull()
  })
})

describe("bundleDeLaSeccion (lo que lee la guarda en el config de la pantalla)", () => {
  it("apagada es `undefined`, encendida sin tarjeta es `null`, y si no la ruta", () => {
    // Pasada 2 de Codex sobre la capa B: con `null` en los dos casos, apagar la sección mientras
    // subía no cambiaba lo que la guarda leía, y la respuesta la reactivaba.
    expect(bundleDeLaSeccion({ monitoring: null })).toBeUndefined()
    expect(bundleDeLaSeccion({})).toBeUndefined()
    expect(bundleDeLaSeccion(null)).toBeUndefined()
    expect(bundleDeLaSeccion({ monitoring: { period: "mes" } })).toBeNull()
    expect(bundleDeLaSeccion({ monitoring: { bundle: "  " } })).toBeNull()
    expect(bundleDeLaSeccion({ monitoring: { bundle: "C:/t" } })).toBe("C:/t")
  })
})
