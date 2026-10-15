import { expect, test } from "@playwright/test"

/** Resúmenes sintéticos del formato público: el navegador sólo sube los archivos y el motor compara. */
function comparable(name: string) {
  return {
    schema_version: 1, bayesrisk: "2.15.0", family: "scorecard", name,
    created_at: "2026-10-15T12:00:00+00:00", config_hash: `config-${name}`,
    data_hash: "datos", portfolio_hash: "cartera", currency: null, missing: {},
    model_hash: `modelo-${name}`,
    psi_recipe: { bins: 10, smoothing: 0.000001, thresholds: [0.1, 0.25] },
    samples: [{ sample: "oot", n: 10, n_bad: 5, auc: 1, gini: 1, ks: 1, status: "ok" }],
    evaluation_sample: "oot",
    evaluation_scores: { order: "index", basis: "pd_calibrated", rows_hash: "filas",
      default_hash: "desenlace", risk: [0, 0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 1],
      default: [0, 0, 0, 0, 0, 1, 1, 1, 1, 1] },
    score_psi: [{ comparison: "dev_vs_oot", psi: 0.01, band: "stable" }],
    score_psi_common: { comparison: "dev_vs_oot", psi: 0.01, band: "stable" },
    grades: { k: 2, share_by_sample: { oot: [0.4, 0.6] } },
    variables: [{ feature: "ingreso", beta: -1, expected_sign: "negative", sign_ok: true,
      iv_development: 0.2, iv_by_sample: {}, csi: [] }],
    validation: { status: "pass", reason: null },
  }
}

test("compara dos corridas sin cargar datos y muestra las tablas, los gráficos y el informe", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: /^Comparar modelos/ }).click()
  const nav = page.locator('nav[aria-label="Secciones"]')
  await expect(nav.getByRole("button", { name: /Cargar datos/ })).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "Comparación", exact: true })).toBeVisible()
  for (const name of ["S51 base", "S51 alternativa"]) {
    const subida = page.waitForResponse((r) => r.url().endsWith("/api/comparables/upload"))
    await page.getByLabel("Subir resumen comparable").setInputFiles({
      name: "comparable.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(comparable(name))),
    })
    expect((await subida).status()).toBe(200)
    await page.getByRole("checkbox", { name: new RegExp(name) }).check()
  }
  const alternativa = page.getByRole("listitem").filter({ has: page.getByRole("checkbox", { name: /S51 alternativa/ }) })
  await alternativa.getByRole("button", { name: "Usar como referencia" }).click()
  await expect(alternativa.getByRole("button", { name: "Referencia", exact: true })).toBeDisabled()
  await nav.getByRole("button", { name: "Ejecutar", exact: true }).click()
  await expect(page.getByRole("button", { name: "Ejecutar corrida" })).toBeEnabled()
  const corrida = page.waitForResponse((r) => r.url().endsWith("/api/run"))
  await page.getByRole("button", { name: "Ejecutar corrida" }).click()
  const respuesta = await corrida
  expect(respuesta.status()).toBe(200)
  expect((await respuesta.json()).status).toBe("done")
  await nav.getByRole("button", { name: "Resultados", exact: true }).click()
  await expect(page.getByText("Elección:", { exact: true })).toBeVisible()
  await expect(page.getByRole("img", { name: /AUC frente a PSI/ })).toBeVisible()
  await expect(page.getByRole("img", { name: /Gini frente/ })).toBeVisible()
  await expect(page.getByRole("cell", { name: "ingreso", exact: true }).first()).toBeVisible()
  if (process.env.BAYESRISK_EVIDENCE_DIR) {
    await page.screenshot({ path: `${process.env.BAYESRISK_EVIDENCE_DIR}/comparacion.png`, fullPage: true })
  }
  await nav.getByRole("button", { name: "Reporte", exact: true }).click()
  await expect(page.locator("iframe")).toBeVisible()
})
