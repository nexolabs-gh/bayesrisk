import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { ApiError, listComparables, uploadComparable, type ComparableRun } from "@/lib/api"
import { describeApiError } from "@/lib/validation"

/** Subir sólo amplía la lista: elegir siempre es un gesto explícito sobre el config vigente. */
export function ComparablePicker({ runs, activa, onChange }: {
  runs: string[]; activa: boolean; onChange: (runs: string[]) => void
}) {
  const [lista, setLista] = useState<ComparableRun[]>([])
  const [error, setError] = useState<string | null>(null)
  const [archivo, setArchivo] = useState<File | null>(null)
  const [revision, setRevision] = useState(0)
  const [subiendo, setSubiendo] = useState(false)
  useEffect(() => {
    let vigente = true
    setSubiendo(archivo !== null)
    const cargar = async () => {
      try {
        if (archivo) await uploadComparable(archivo)
        const { comparables } = await listComparables()
        if (vigente) { setLista(comparables); setError(null) }
      } catch (e) {
        if (vigente) setError(e instanceof ApiError ? describeApiError(e.body, e.message) : String(e))
      } finally {
        if (vigente) setSubiendo(false)
      }
    }
    void cargar()
    return () => { vigente = false }
  }, [archivo, revision])
  const conocidas = new Set(lista.map((r) => r.path))
  return <div className="space-y-3 rounded-lg border border-border p-4">
    <p>Elige entre 2 y 10 corridas guardadas desde la 2.15.0. La primera es la referencia.</p>
    <p className="text-sm text-muted-foreground">Puedes subir el archivo comparable.json de una corrida hecha por código.</p>
    <label className="block text-sm">Subir resumen comparable
      <input type="file" accept=".json" disabled={!activa || subiendo}
        onChange={(e) => { setArchivo(e.target.files?.[0] ?? null); e.target.value = "" }} />
    </label>
    <Button variant="outline" disabled={subiendo} onClick={() => { setArchivo(null); setRevision((n) => n + 1) }}>Actualizar lista</Button>
    {subiendo ? <p role="status">Validando resumen…</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    <ul aria-label="Corridas disponibles" className="space-y-2">
      {lista.map((r) => {
        const elegida = runs.includes(r.path)
        return <li key={r.path} className="flex flex-wrap items-center gap-3 rounded border border-border p-2">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={elegida} disabled={!activa || (!elegida && runs.length >= 10)}
              onChange={() => onChange(elegida ? runs.filter((p) => p !== r.path) : [...runs, r.path])} />
            {r.name} · {r.family === "ifrs9" ? "IFRS 9" : "Scorecard"}
            <span className="text-xs text-muted-foreground">{r.comparison_hash.slice(0, 12)}</span>
          </label>
          {elegida ? <Button size="sm" variant="outline" disabled={!activa || runs[0] === r.path}
            onClick={() => onChange([r.path, ...runs.filter((p) => p !== r.path)])}>
            {runs[0] === r.path ? "Referencia" : "Usar como referencia"}
          </Button> : null}
        </li>
      })}
    </ul>
    {!lista.length && !subiendo ? <p>Aún no hay corridas: sube un resumen o termina un scorecard o una provisión en esta pantalla.</p> : null}
    {runs.filter((p) => !conocidas.has(p)).map((p) => <p key={p} className="break-all text-xs">
      Corrida del archivo de configuración: {p} {runs[0] === p ? "(referencia)" : ""}
      <Button variant="outline" disabled={!activa} onClick={() => onChange(runs.filter((v) => v !== p))}>Quitar</Button>
    </p>)}
    <p role="status">{runs.length} corridas seleccionadas</p>
  </div>
}
