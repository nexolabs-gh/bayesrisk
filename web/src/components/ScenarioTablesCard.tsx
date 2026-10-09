import { useRef, useState, type ChangeEvent, type Dispatch, type SetStateAction } from "react"
import { CircleAlert, CircleCheck, FileUp, Loader2, RefreshCw, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError, scenarioTables, uploadDataset } from "@/lib/api"
import { ALLOWED_DATA_EXTENSIONS, isAllowedDataFile } from "@/lib/datasets"
import {
  quitarLecturas,
  releerTablas,
  subirTabla,
  type PuertoDeLasTablas,
  type ScenarioTablesState,
  type TablaSubida,
  type TablasLeidas,
} from "@/lib/scenario-tables"
import { describeApiError } from "@/lib/validation"

type Tabla = "historia" | "escenarios"

interface ScenarioTablesCardProps {
  /** ¿La sección de escenarios está encendida? Entonces se ofrece quitarlos. */
  active: boolean
  /** La columna de la tasa de referencia que dice su esencial (con su default). */
  referenceRateCol: string
  /** El archivo de cartera y su columna de corte: con los dos, se comprueba la cobertura antes. */
  portfolioDatasetId: string | null
  asOfCol: string | null
  /** Lo leído de las dos tablas: el `ConfigTab` enciende la sección con ello. */
  onTablas: (leidas: TablasLeidas) => void
  onQuitar: () => void
  /** Las dos tablas subidas, del store: sobreviven a cambiar de sección. */
  tablas: ScenarioTablesState
  setTablas: Dispatch<SetStateAction<ScenarioTablesState>>
  /** El config vigente del store: una lectura sólo se aplica si no cambió mientras se esperaba. */
  getConfig: () => Record<string, unknown>
  /** Las tablas vigentes del store, para quien vuelve de una subida. */
  getTablas: () => ScenarioTablesState
}

/**
 * Las dos tablas de los escenarios de la institución (IFRS9-FIRMABLE capa C, D-FIR-11).
 *
 * Sube la historia de la tasa de referencia y la tabla de escenarios por `POST /api/upload`, como
 * cualquier archivo, y las hace leer al servidor (`POST /api/scenario-tables`) con **la misma
 * regla** que `bayesrisk.Ecl(history=, scenarios=)`: lo que la puerta guiada rechaza, la pantalla
 * también, con el mismo motivo. Lo que vuelve —rutas, variables macro, nombres y pesos— se escribe
 * en la sección al encenderla; aquí no se interpreta nada (SDD-23 §11). Sin efectos: todo ocurre
 * en los manejadores.
 */
export function ScenarioTablesCard({
  active,
  referenceRateCol,
  portfolioDatasetId,
  asOfCol,
  onTablas,
  onQuitar,
  tablas,
  setTablas,
  getConfig,
  getTablas,
}: ScenarioTablesCardProps) {
  const { historia, escenarios } = tablas
  // Lo leído sólo se dice mientras la sección siga encendida: apagada, ya no describe la corrida.
  const leido = active ? tablas.leido : null
  const aviso = tablas.aviso ?? null
  const [ocupado, setOcupado] = useState<Tabla | "leer" | null>(null)
  const refs = {
    historia: useRef<HTMLInputElement | null>(null),
    escenarios: useRef<HTMLInputElement | null>(null),
  }

  // La secuencia subir → leer vive en `lib/scenario-tables` (un gesto vigente por vez, en el store):
  // la tarjeta sólo le presta el store, la API y la sección. Así una respuesta vieja no se aplica
  // aunque la tarjeta se haya desmontado y vuelto a montar entretanto (pasada 4 de Codex).
  const puerto: PuertoDeLasTablas = {
    getTablas,
    setTablas,
    getConfig,
    subir: async (archivo) => {
      const resp = await uploadDataset(archivo as File)
      return { datasetId: resp.dataset_id, fileName: archivo.name }
    },
    pedir: (h: TablaSubida, e: TablaSubida) =>
      scenarioTables({
        history_dataset_id: h.datasetId,
        scenarios_dataset_id: e.datasetId,
        reference_rate_col: referenceRateCol,
        portfolio_dataset_id: portfolioDatasetId,
        as_of_col: asOfCol,
      }),
    aplicar: onTablas,
    activa: () => {
      const forward = getConfig().forward
      return forward !== null && forward !== undefined
    },
    describirError: mensajeDeError,
    fase: setOcupado,
  }

  function subir(cual: Tabla, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = "" // permite volver a subir el mismo archivo
    if (!file) return
    if (!isAllowedDataFile(file.name)) {
      setTablas((actual) => ({
        ...actual,
        aviso: `Formato no soportado: usa ${ALLOWED_DATA_EXTENSIONS.join(", ")}.`,
      }))
      return
    }
    void subirTabla(puerto, cual, file)
  }

  const boton = (cual: Tabla, rotulo: string, tabla: TablaSubida | null) => (
    <div className="flex flex-wrap items-center gap-3">
      <input
        ref={refs[cual]}
        type="file"
        accept={ALLOWED_DATA_EXTENSIONS.join(",")}
        onChange={(event) => subir(cual, event)}
        className="hidden"
        aria-hidden="true"
        tabIndex={-1}
      />
      <Button
        type="button"
        variant="outline"
        disabled={ocupado !== null}
        onClick={() => refs[cual].current?.click()}
        data-testid={`subir-${cual}`}
      >
        {ocupado === cual ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        ) : (
          <FileUp className="size-3.5" aria-hidden="true" />
        )}
        {tabla === null ? `Subir ${rotulo}` : `Cambiar ${rotulo}`}
      </Button>
      {tabla !== null ? (
        <span className="text-xs text-muted-foreground">{tabla.fileName}</span>
      ) : null}
    </div>
  )

  return (
    <Card className="shadow-card" data-testid="tablas-de-escenarios">
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-eyebrow">
            Tus escenarios
          </p>
          <p className="text-sm font-medium text-foreground">
            Ajusta la provisión al ciclo con tus escenarios económicos
          </p>
          <p className="text-sm text-muted-foreground">
            Sube dos tablas. La <strong>historia</strong> de una tasa de incumplimiento de
            referencia larga, que cruce al menos un ciclo: columnas <code>date</code>, la tasa
            (<code>{referenceRateCol}</code>, como fracción: un 0,9 % va como 0,009) y tus
            variables macroeconómicas. Tus <strong>escenarios</strong> con sus pesos: columnas{" "}
            <code>scenario</code>, <code>weight</code>, <code>date</code> y las mismas variables,
            al menos dos escenarios y los 12 meses siguientes al corte. Sin ellas, la provisión es
            a lo largo del ciclo.
          </p>
        </div>

        {boton("historia", "historia", historia)}
        {boton("escenarios", "escenarios", escenarios)}

        {ocupado === "leer" ? (
          <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
            Leyendo las dos tablas…
          </p>
        ) : null}
        {leido !== null ? (
          <p
            className="flex items-start gap-1.5 text-xs text-foreground/90"
            data-testid="tablas-leidas"
          >
            <CircleCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>{leido}.</span>
          </p>
        ) : null}
        {aviso ? (
          <p
            className="flex items-start gap-1.5 text-xs text-amber-200/90"
            data-testid="tablas-error"
          >
            <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>{aviso}</span>
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {historia !== null && escenarios !== null ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={ocupado !== null}
              onClick={() => void releerTablas(puerto)}
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              Volver a leer las tablas
            </Button>
          ) : null}
          {active ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={ocupado !== null}
              onClick={() => {
                onQuitar()
                quitarLecturas(puerto)
              }}
              data-testid="quitar-escenarios"
            >
              <X className="size-3.5" aria-hidden="true" />
              Quitar los escenarios
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

function mensajeDeError(err: unknown): string {
  if (err instanceof ApiError) return describeApiError(err.body, err.message)
  return err instanceof Error ? err.message : String(err)
}
