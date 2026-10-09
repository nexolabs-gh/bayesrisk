import { describe, expect, it } from "vitest"

import tarjetaFuente from "@/components/ScenarioTablesCard.tsx?raw"
import {
  leerTablasVigentes,
  releerTablas,
  resolverSubida,
  SIN_TABLAS,
  subirTabla,
  type PuertoDeLasTablas,
  type ScenarioTablesState,
  type TablaSubida,
  type TablasLeidas,
} from "@/lib/scenario-tables"

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

describe("la tarjeta delega en el módulo y compara contra el store (pasadas 2 a 4 de Codex)", () => {
  it("no guarda su propia copia del config y orquesta con subirTabla/releerTablas", () => {
    // Una copia local (`useRef(config)`) se queda vieja si la tarjeta se desmonta y otro YAML se
    // carga en otra sección: la lectura vieja se aplicaba sobre el config nuevo.
    expect(tarjetaFuente).not.toMatch(/useRef\(config\)/)
    expect(tarjetaFuente).toMatch(/getConfig/)
    // La secuencia subir → leer vive en el módulo, que es lo que estos tests ejercitan.
    expect(tarjetaFuente).toMatch(/subirTabla\(/)
    expect(tarjetaFuente).toMatch(/releerTablas\(/)
    // Y no decide nada por su cuenta: ni qué subida vale ni qué lectura se aplica.
    expect(tarjetaFuente).not.toMatch(/resolverSubida|leerTablasVigentes/)
  })
})

/**
 * Un store y un config de mentira, con las subidas y las lecturas como promesas que el test resuelve
 * cuando quiere: la secuencia completa de la tarjeta, sin React. Que la tarjeta se desmonte y se
 * vuelva a montar entre dos gestos no cambia nada aquí: el estado vive en el store, no en ella.
 */
function banco(inicial: Partial<ScenarioTablesState> = {}) {
  let tablas: ScenarioTablesState = { ...SIN_TABLAS, ...inicial }
  let config: Record<string, unknown> = { forward: { tablas: "las de antes" } }
  const subidas = new Map<string, ReturnType<typeof diferida<TablaSubida>>>()
  const lecturas = new Map<string, ReturnType<typeof diferida<TablasLeidas>>>()
  const aplicadas: string[] = []
  const puerto: PuertoDeLasTablas = {
    getTablas: () => tablas,
    setTablas: (cambio) => {
      tablas = cambio(tablas)
    },
    getConfig: () => config,
    subir: (archivo) => {
      const d = diferida<TablaSubida>()
      subidas.set(archivo.name, d)
      return d.promesa
    },
    pedir: (historia) => {
      const d = diferida<TablasLeidas>()
      lecturas.set(historia.datasetId, d)
      return d.promesa
    },
    aplicar: (leidas) => {
      aplicadas.push(leidas.summary)
      config = { ...config, forward: { tablas: leidas.summary } } // el store crea otro objeto
    },
    activa: () => config.forward !== null,
    describirError: (err) => (err instanceof Error ? err.message : String(err)),
  }
  const tabla = (nombre: string) => ({ datasetId: `id_${nombre}`, fileName: `${nombre}.csv` })
  const leida = (nombre: string) => ({ forward: {}, summary: `leída ${nombre}` })
  return {
    puerto,
    aplicadas,
    tablas: () => tablas,
    cambiarConfig: () => {
      config = { ...config, otro: 1 }
    },
    async subida(nombre: string) {
      subidas.get(`${nombre}.csv`)!.resolver(tabla(nombre))
      await vaciar()
    },
    async lectura(nombre: string) {
      lecturas.get(`id_${nombre}`)!.resolver(leida(nombre))
      await vaciar()
    },
    tabla,
  }
}

/** Deja correr las continuaciones pendientes (varias vueltas de microtareas). */
async function vaciar() {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
}

describe("con las dos tablas, la última que se pidió gana hasta que termina su lectura (pasada 4 de Codex)", () => {
  const conLasDos = () =>
    banco({
      historia: { datasetId: "id_h0", fileName: "h0.csv" },
      escenarios: { datasetId: "id_e0", fileName: "e0.csv" },
      leido: "leída h0",
    })

  it("la lectura de A responde antes que la de B: sólo B se aplica", async () => {
    const b = conLasDos()
    void subirTabla(b.puerto, "historia", { name: "A.csv" })
    await b.subida("A") // A sube y su lectura queda en curso
    void subirTabla(b.puerto, "historia", { name: "B.csv" }) // remonta y pide B
    await b.subida("B")
    await b.lectura("A") // la vieja responde primero
    await b.lectura("B")
    expect(b.aplicadas).toEqual(["leída B"])
    expect(b.tablas().historia?.datasetId).toBe("id_B")
    expect(b.tablas().leido).toBe("leída B")
  })

  it("la lectura de B responde antes que la de A: sólo B se aplica", async () => {
    const b = conLasDos()
    void subirTabla(b.puerto, "historia", { name: "A.csv" })
    await b.subida("A")
    void subirTabla(b.puerto, "historia", { name: "B.csv" })
    await b.subida("B")
    await b.lectura("B")
    await b.lectura("A")
    expect(b.aplicadas).toEqual(["leída B"])
    expect(b.tablas().historia?.datasetId).toBe("id_B")
  })

  it("la lectura de A responde mientras B todavía sube: A no se aplica y B sí", async () => {
    const b = conLasDos()
    void subirTabla(b.puerto, "historia", { name: "A.csv" })
    await b.subida("A")
    void subirTabla(b.puerto, "historia", { name: "B.csv" })
    await b.lectura("A")
    await b.subida("B")
    await b.lectura("B")
    expect(b.aplicadas).toEqual(["leída B"])
    expect(b.tablas().historia?.datasetId).toBe("id_B")
  })

  it("subir la otra tabla también deja sin efecto la lectura en curso", async () => {
    const b = conLasDos()
    void subirTabla(b.puerto, "historia", { name: "A.csv" })
    await b.subida("A")
    void subirTabla(b.puerto, "escenarios", { name: "E1.csv" })
    await b.lectura("A")
    await b.subida("E1")
    // La lectura nueva lee la historia guardada (h0) con los escenarios nuevos.
    await b.lectura("h0")
    expect(b.aplicadas).toEqual(["leída h0"])
    expect(b.tablas().escenarios?.datasetId).toBe("id_E1")
  })

  it("volver a leer deja sin efecto una lectura anterior todavía en curso", async () => {
    const b = conLasDos()
    void subirTabla(b.puerto, "historia", { name: "A.csv" })
    await b.subida("A")
    void releerTablas(b.puerto) // vuelve a leer h0 + e0
    await b.lectura("A")
    await b.lectura("h0")
    expect(b.aplicadas).toEqual(["leída h0"])
    expect(b.tablas().historia?.datasetId).toBe("id_h0")
  })
})

describe("una subida vieja no pisa a una más nueva (pasadas 3 y 4 de Codex)", () => {
  it("la primera tabla que vuelve después de otra más nueva se descarta", async () => {
    const b = banco()
    void subirTabla(b.puerto, "historia", { name: "A.csv" })
    void subirTabla(b.puerto, "historia", { name: "B.csv" })
    await b.subida("B")
    await b.subida("A")
    expect(b.tablas().historia?.datasetId).toBe("id_B")
    expect(b.aplicadas).toEqual([])
  })

  it("si el config cambió mientras subía, no se guarda y se avisa", async () => {
    const b = banco()
    void subirTabla(b.puerto, "historia", { name: "A.csv" })
    b.cambiarConfig()
    await b.subida("A")
    expect(b.tablas().historia).toBeNull()
    expect(b.tablas().aviso).toMatch(/A\.csv.*no se usó/)
  })

  it("resolverSubida: con una sola tabla la guarda; con las dos pide leerlas sin guardar nada", () => {
    const config = {}
    const A = { datasetId: "id_A", fileName: "A.csv" }
    const sola = resolverSubida({ ...SIN_TABLAS, gesto: "1" }, "historia", "1", A, config, config)
    expect(sola.kind).toBe("guardar")
    if (sola.kind === "guardar") expect(sola.siguiente.historia).toEqual(A)
    const E = { datasetId: "id_E", fileName: "E.csv" }
    const vigente = { ...SIN_TABLAS, escenarios: E, gesto: "2" }
    const dos = resolverSubida(vigente, "historia", "2", A, config, config)
    expect(dos).toEqual({ kind: "leer", historia: A, escenarios: E })
    expect(resolverSubida(vigente, "historia", "1", A, config, config).kind).toBe("descartar")
  })

  it("una lectura rechazada no reemplaza a la última leída y se dice", async () => {
    const b = banco({
      historia: { datasetId: "id_h0", fileName: "h0.csv" },
      escenarios: { datasetId: "id_e0", fileName: "e0.csv" },
      leido: "leída h0",
    })
    const pedir = b.puerto.pedir
    b.puerto.pedir = (h, e) =>
      h.datasetId === "id_A" ? Promise.reject(new Error("Hacen falta dos escenarios")) : pedir(h, e)
    void subirTabla(b.puerto, "historia", { name: "A.csv" })
    await b.subida("A")
    expect(b.tablas().historia?.datasetId).toBe("id_h0")
    expect(b.tablas().aviso).toMatch(/No se leyó «A\.csv»: Hacen falta dos escenarios/)
    expect(b.tablas().aviso).toMatch(/sigue con las tablas que se leyeron antes/)
  })
})
