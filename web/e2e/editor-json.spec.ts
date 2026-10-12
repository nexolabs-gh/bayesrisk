import { readFile } from "node:fs/promises"

import { expect, test, type Page } from "@playwright/test"

/**
 * El editor JSON del formulario en un navegador real (pasadas 3 y 4 de Codex sobre la capa B del
 * SDD-32, S43–S44).
 *
 * Un campo JSON (los cortes de la escala maestra, los cortes fijados a mano de una variable) acepta
 * un texto que todavía no se puede leer mientras la persona escribe. La regla: **lo que se ve es lo
 * que corre**. Al salir del campo, un texto ilegible se descarta, el editor vuelve al último valor
 * válido del config y «Ejecutar» avisa qué se descartó; no queda ningún borrador guardado aparte que
 * pueda quedar viejo y detener la corrida —una sección apagada, una fila movida, un config
 * reemplazado—. `vitest` corre sin DOM y no puede salir de un campo ni desmontar un editor: estos
 * recorridos sí, sobre el bundle que sirve el wheel.
 */

const SECCIONES = 'nav[aria-label="Secciones"]'

async function cargarElEjemplo(page: Page): Promise<void> {
  await page.goto("/")
  // Dos botones con ese nombre: la ficha del trabajo y el ejemplo, que llega con `listPresets()`
  // (ver `clean-room.spec.ts`). Esperar a los dos cierra la carrera.
  const scorecard = page.getByRole("button", { name: /^Scorecard de comportamiento/ })
  await expect(scorecard).toHaveCount(2)
  await scorecard.last().click()
  await expect(page.getByRole("button", { name: "Ejecutar corrida" })).toBeEnabled()
}

async function irA(page: Page, seccion: RegExp): Promise<void> {
  await page.locator(SECCIONES).getByRole("button", { name: seccion }).click()
}

/**
 * El interruptor de una sección o de un campo. Por atributo y no por rol con nombre: el switch de
 * base-ui lleva `aria-labelledby` hacia su rótulo, que en el cálculo del nombre accesible gana a su
 * `aria-label`.
 */
function interruptorDeSeccion(page: Page, seccion: string) {
  return page.locator(`[role="switch"][aria-labelledby="section-toggle-${seccion}-label"]`)
}

function interruptorDeCampo(page: Page, ruta: string) {
  return page.locator(`[role="switch"][data-field-path="${ruta}"]`)
}

async function encender(interruptor: ReturnType<Page["locator"]>): Promise<void> {
  await expect(interruptor).toHaveAttribute("aria-checked", "false")
  await interruptor.click()
  await expect(interruptor).toHaveAttribute("aria-checked", "true")
}

function editor(page: Page, ruta: string) {
  return page.locator(`textarea[id="${ruta}"]`)
}

/** El aviso de «Ejecutar» sobre lo descartado, o nada si no hay. */
function avisoDeDescarte(page: Page) {
  return page.locator('[data-descartes-json="ejecutar"]')
}

test.describe("el editor JSON: lo que se ve es lo que corre", () => {
  let erroresDePagina: string[]

  test.beforeEach(({ page }) => {
    erroresDePagina = []
    page.on("pageerror", (error: Error) => erroresDePagina.push(error.message))
  })

  test.afterEach(() => {
    expect(erroresDePagina, "la página no debe lanzar errores").toEqual([])
  })

  test("un texto ilegible se descarta al salir y «Ejecutar» lo avisa sin detenerse", async ({
    page,
  }) => {
    await cargarElEjemplo(page)
    await irA(page, /Escala maestra/)
    await encender(interruptorDeSeccion(page, "master_scale"))
    await encender(interruptorDeCampo(page, "master_scale.grade_edges"))
    const cortes = editor(page, "master_scale.grade_edges")
    await cortes.fill("[500, 550")
    await expect(page.locator("main")).toContainText("JSON inválido")

    // Salir del campo sin navegar: el editor vuelve al valor del config (vacío) y lo dice ahí.
    await page.locator("main h1").click()
    await expect(cortes).toHaveValue("")
    await expect(page.locator("main")).not.toContainText("JSON inválido")
    await expect(page.locator("main")).toContainText("Se descartó «[500, 550»")

    await irA(page, /^Ejecutar/)
    // La corrida usa lo que el config trae —ningún corte: los tramos los forman los datos— y lo
    // dice antes de correr, con el texto descartado para que se pueda volver a escribir.
    await expect(page.getByRole("button", { name: "Ejecutar corrida" })).toBeEnabled()
    await expect(avisoDeDescarte(page)).toContainText("Cortes de los tramos")
    await expect(avisoDeDescarte(page)).toContainText("[500, 550")

    // De vuelta en Configuración se ve lo mismo que corre: el campo sin cortes.
    await irA(page, /Escala maestra/)
    await expect(interruptorDeCampo(page, "master_scale.grade_edges")).toHaveAttribute(
      "aria-checked",
      "false",
    )
    await expect(editor(page, "master_scale.grade_edges")).toHaveCount(0)

    // «Entendido» retira el aviso.
    await irA(page, /^Ejecutar/)
    await avisoDeDescarte(page).getByRole("button", { name: "Entendido" }).click()
    await expect(avisoDeDescarte(page)).toHaveCount(0)
  })

  test("apagar la sección con un texto ilegible no deja nada que detenga la corrida", async ({
    page,
  }) => {
    await cargarElEjemplo(page)
    await irA(page, /Escala maestra/)
    await encender(interruptorDeSeccion(page, "master_scale"))
    await encender(interruptorDeCampo(page, "master_scale.grade_edges"))
    await editor(page, "master_scale.grade_edges").fill("[500, 550")
    await interruptorDeSeccion(page, "master_scale").click()

    await irA(page, /^Ejecutar/)
    await expect(page.getByRole("button", { name: "Ejecutar corrida" })).toBeEnabled()
    await expect(page.locator("main")).not.toContainText("a medio escribir")
  })

  test("mover una fila lleva sus valores y su aviso con ella", async ({ page }) => {
    await cargarElEjemplo(page)
    await irA(page, /Optimal Binning/)
    await page.locator('[data-advanced="binning"]').click()
    const anadir = page.locator('[id="binning.variable_overrides"]')
    await anadir.click()
    await anadir.click()

    const filas = [
      { nombre: "antiguedad_meses", cortes: "[24, 60]" },
      { nombre: "ingreso_mensual", cortes: "[1000, 5000]" },
    ]
    for (const [indice, fila] of filas.entries()) {
      const base = `binning.variable_overrides.${indice}`
      await page.locator(`input[id="${base}.name"]`).fill(fila.nombre)
      await encender(interruptorDeCampo(page, `${base}.user_splits`))
      await editor(page, `${base}.user_splits`).fill(fila.cortes)
    }
    // La segunda fila queda a medio escribir y sube.
    await editor(page, "binning.variable_overrides.1.user_splits").fill("[2000, 5000")
    await page.getByRole("button", { name: "Subir ingreso_mensual" }).click()

    // Cada fila conserva sus cortes válidos, en su nueva posición.
    await expect(page.locator('input[id="binning.variable_overrides.0.name"]')).toHaveValue(
      "ingreso_mensual",
    )
    await expect
      .poll(async () =>
        JSON.parse(await editor(page, "binning.variable_overrides.0.user_splits").inputValue()),
      )
      .toEqual([1000, 5000])
    await expect
      .poll(async () =>
        JSON.parse(await editor(page, "binning.variable_overrides.1.user_splits").inputValue()),
      )
      .toEqual([24, 60])
    // Y el aviso del texto descartado va con su fila, no con la que quedó en su lugar.
    const fila = (indice: number) =>
      page.locator("li").filter({
        has: page.locator(`input[id="binning.variable_overrides.${indice}.name"]`),
      })
    await expect(fila(0)).toHaveCount(1)
    await expect(fila(0)).toContainText("Se descartó «[2000, 5000»")
    await expect(fila(1)).not.toContainText("Se descartó")

    await irA(page, /^Ejecutar/)
    await expect(avisoDeDescarte(page)).toContainText("[2000, 5000")
  })

  test("un editor que se desmonta sin perder el foco también avisa", async ({ page }) => {
    await cargarElEjemplo(page)
    await irA(page, /Escala maestra/)
    await encender(interruptorDeSeccion(page, "master_scale"))
    await encender(interruptorDeCampo(page, "master_scale.grade_edges"))
    const cortes = editor(page, "master_scale.grade_edges")
    await cortes.fill("[500, 550")
    await expect(cortes).toBeFocused()

    // Un clic por JS no mueve el foco: el editor se desmonta con el campo enfocado, sin `blur`.
    await page.evaluate((selector) => {
      const boton = [...document.querySelectorAll<HTMLButtonElement>(`${selector} button`)].find(
        (b) => b.innerText.trim().startsWith("Ejecutar"),
      )
      boton?.click()
    }, SECCIONES)

    await expect(page.getByRole("button", { name: "Ejecutar corrida" })).toBeEnabled()
    await expect(avisoDeDescarte(page)).toContainText("[500, 550")
  })

  test("reemplazar el config no revive un texto descartado", async ({ page }) => {
    await cargarElEjemplo(page)
    await irA(page, /Escala maestra/)
    await encender(interruptorDeSeccion(page, "master_scale"))
    await encender(interruptorDeCampo(page, "master_scale.grade_edges"))
    const cortes = editor(page, "master_scale.grade_edges")
    await cortes.fill("[500]")
    await cortes.fill("[500, 550")

    // El YAML del config tal como corre: con el corte 500.
    const [descarga] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Descargar YAML" }).click(),
    ])
    const ruta = await descarga.path()
    const yaml500 = await readFile(ruta, "utf-8")
    expect(yaml500).toMatch(/grade_edges:\s*\n\s*- 500(\.0)?\s*\n/)
    const yaml520 = yaml500.replace(/(grade_edges:\s*\n\s*- )500(\.0)?/, "$1520.0")

    const cargar = async (nombre: string, texto: string) => {
      await page
        .locator('input[type="file"][accept=".yaml,.yml"]')
        .setInputFiles({ name: nombre, mimeType: "text/yaml", buffer: Buffer.from(texto) })
    }

    // El mismo valor: el editor muestra el corte y no queda nada pendiente. Un YAML cargado retira
    // el rótulo del ejemplo: es la señal de que el config se reemplazó.
    await cargar("con-500.yaml", yaml500)
    await expect(page.locator("main")).not.toContainText("Cargado el ejemplo")
    await expect.poll(async () => JSON.parse(await cortes.inputValue())).toEqual([500])
    await expect(page.locator("main")).not.toContainText("JSON inválido")
    // El aviso bajo el campo hablaba del config anterior (pasada 5 de Codex).
    await expect(page.locator("main")).not.toContainText("Se descartó")

    // Otro valor y de vuelta al primero: nada revive.
    await cargar("con-520.yaml", yaml520)
    await expect.poll(async () => JSON.parse(await cortes.inputValue())).toEqual([520])
    await cargar("otra-vez-500.yaml", yaml500)
    await expect.poll(async () => JSON.parse(await cortes.inputValue())).toEqual([500])
    await expect(page.locator("main")).not.toContainText("JSON inválido")

    await irA(page, /^Ejecutar/)
    await expect(page.getByRole("button", { name: "Ejecutar corrida" })).toBeEnabled()
    // El aviso hablaba del config anterior: reemplazarlo lo retira.
    await expect(avisoDeDescarte(page)).toHaveCount(0)
  })

  /**
   * Pasada 5 de Codex: un texto válido que apaga el campo —`null`, o vaciarlo— desmonta el editor en
   * el mismo render; la red de seguridad del desmontaje no puede anunciar el texto ilegible que había
   * justo antes.
   */
  test("aceptar un JSON válido que apaga el campo no anuncia un descarte", async ({ page }) => {
    await cargarElEjemplo(page)
    await irA(page, /Optimal Binning/)
    await page.locator('[data-advanced="binning"]').click()
    await page.locator('[id="binning.variable_overrides"]').click()
    const base = "binning.variable_overrides.0"
    await page.locator(`input[id="${base}.name"]`).fill("ingreso_mensual")
    const interruptor = interruptorDeCampo(page, `${base}.user_splits`)
    const cortes = editor(page, `${base}.user_splits`)

    // «nul» no se lee; la «l» que falta da `null`, que apaga el campo.
    await encender(interruptor)
    await cortes.fill("nul")
    await cortes.pressSequentially("l")
    await expect(interruptor).toHaveAttribute("aria-checked", "false")
    await expect(cortes).toHaveCount(0)

    // Vaciar un texto ilegible también es un valor válido: el campo sin valor.
    await encender(interruptor)
    await cortes.fill("[1")
    await cortes.fill("")
    await expect(interruptor).toHaveAttribute("aria-checked", "false")

    await irA(page, /^Ejecutar/)
    await expect(page.getByRole("button", { name: "Ejecutar corrida" })).toBeEnabled()
    await expect(avisoDeDescarte(page)).toHaveCount(0)
  })

  /**
   * Pasada 5 de Codex: un YAML que llega mientras la persona escribe reemplaza el config entero,
   * también lo que estaba a medio escribir —como cualquier otro campo—, sin dejar un aviso del
   * config anterior ni el texto en el editor.
   */
  test("un YAML que llega mientras se escribe reemplaza también lo escrito", async ({ page }) => {
    await cargarElEjemplo(page)
    await irA(page, /Escala maestra/)
    const [descarga] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Descargar YAML" }).click(),
    ])
    const yamlSinEscala = await readFile(await descarga.path(), "utf-8")
    expect(yamlSinEscala).not.toContain("master_scale")

    await encender(interruptorDeSeccion(page, "master_scale"))
    await encender(interruptorDeCampo(page, "master_scale.grade_edges"))
    const cortes = editor(page, "master_scale.grade_edges")
    await cortes.fill("[500]")

    // La respuesta del backend se demora hasta que la persona deja un texto a medio escribir.
    const cargarDemorado = async (nombre: string, texto: string, escribir: () => Promise<void>) => {
      let soltar: () => void = () => undefined
      const demora = new Promise<void>((resolver) => {
        soltar = resolver
      })
      await page.route("**/api/config/from-yaml", async (ruta) => {
        await demora
        await ruta.continue()
      })
      const respuesta = page.waitForResponse("**/api/config/from-yaml")
      await page
        .locator('input[type="file"][accept=".yaml,.yml"]')
        .setInputFiles({ name: nombre, mimeType: "text/yaml", buffer: Buffer.from(texto) })
      await escribir()
      soltar()
      await respuesta
      await page.unroute("**/api/config/from-yaml")
    }

    // Con el mismo valor: el editor muestra el del YAML, sin el texto ni su error.
    const [descarga500] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Descargar YAML" }).click(),
    ])
    const yaml500 = await readFile(await descarga500.path(), "utf-8")
    await cargarDemorado("con-500.yaml", yaml500, () => cortes.fill("[500, 550"))
    await expect(page.locator("main")).not.toContainText("Cargado el ejemplo")
    await expect.poll(async () => JSON.parse(await cortes.inputValue())).toEqual([500])
    await expect(page.locator("main")).not.toContainText("JSON inválido")

    // Sin la sección: el YAML la apaga y el editor desmontado no deja aviso.
    await cargarDemorado("sin-escala.yaml", yamlSinEscala, () => cortes.fill("[500, 550"))
    await expect(interruptorDeSeccion(page, "master_scale")).toHaveAttribute("aria-checked", "false")

    await irA(page, /^Ejecutar/)
    await expect(page.getByRole("button", { name: "Ejecutar corrida" })).toBeEnabled()
    await expect(avisoDeDescarte(page)).toHaveCount(0)
  })
})
