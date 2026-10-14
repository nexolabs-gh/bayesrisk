/**
 * `subirYElegir` (SDD-33 capa B; pasada 1 de Codex): una subida vieja no pisa la tarjeta elegida.
 *
 * Con promesas diferidas: la subida se resuelve cuando el test lo decide, después de que la persona
 * eligió otra tarjeta, escribió la ruta a mano o salió de la sección.
 */
import { describe, expect, it } from "vitest"

import type { MonitorableCard } from "@/lib/api"
import { subirYElegir, type PuertoDeLaTarjeta } from "@/lib/monitoring-card"

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
})
