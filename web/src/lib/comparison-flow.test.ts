import { describe, expect, it } from "vitest"
import { canRun } from "./validation"
import { jobSkeleton, sectionsOfJob, type Job } from "./jobs"
import jobs from "../fixtures/jobs.json"
import schema from "../fixtures/schema.json"
import type { EffectiveDefaults } from "./effective-defaults"

describe("comparación sin cartera", () => {
  it("permite comparar sin dataset y conserva la guarda de los otros trabajos", () => {
    const validation = { kind: "valid" as const, hash: "abc", pipeline: null, producedColumns: {} }
    expect(canRun(validation, null, false).ok).toBe(true)
    expect(canRun(validation, null).ok).toBe(false)
    expect(canRun({ kind: "checking" }, null, false).ok).toBe(false)
  })
  it("siembra sólo comparación, informe y gobernanza y apaga la cartera previa", () => {
    const job = jobs.jobs.find((j) => j.id === "comparar_modelos") as unknown as Job
    expect(sectionsOfJob(job).map((s) => s.key)).toEqual(["comparison", "report", "governance"])
    const config = jobSkeleton({ data: { load: { source: "anterior" } } }, job,
      schema.effective_defaults as unknown as EffectiveDefaults)
    expect(config.data).toBeNull()
    expect(config.comparison).not.toBeNull()
    expect(config.governance).toBeNull()
  })
})
