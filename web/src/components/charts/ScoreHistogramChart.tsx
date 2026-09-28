import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import type { HistogramBin, ScoreHistogram } from "@/lib/results-format"

import {
  AXIS_LINE,
  AXIS_TICK,
  BAR_PRIMARY,
  BRAND,
  CURSOR_FILL,
  GRID_STROKE,
} from "./chart-theme"
import { conteo, entero, marca } from "@/lib/cifras"

/** Ítem que Recharts inyecta al tooltip (el datum del bin vive en `.payload`). */
interface HistTooltipProps {
  active?: boolean
  payload?: ReadonlyArray<{ payload?: HistogramBin }>
}

/** Entero con separador de miles es-CL, igual que el resto de la app (DatosTab, catálogo). */
function count(n: number): string {
  return conteo(n)
}

/** Tooltip dedicado: rango de score del bin + su frecuencia. */
function HistTooltip({ active, payload }: HistTooltipProps) {
  const d = active && payload && payload.length > 0 ? payload[0]?.payload : null
  if (!d) return null
  return (
    <div className="rounded-lg bg-secondary px-3 py-2 text-xs shadow-card ring-1 ring-foreground/10">
      <p className="mb-1 font-mono font-medium text-foreground">
        {entero(d.x0)} – {entero(d.x1)}
      </p>
      <p className="text-muted-foreground">
        Frecuencia{" "}
        <span className="ml-1 font-mono tabular-nums text-foreground">
          {count(d.count)}
        </span>
      </p>
    </div>
  )
}

/**
 * Histograma de distribución del score: frecuencia (Y) por bin de score (X). El binning es
 * PRESENTACIÓN pura (bins de ancho uniforme, ya resuelto por `scoreHistogram`), NO un corte
 * de dominio. Marca la media y la mediana de la muestra como referencias de lectura del
 * centro/asimetría. Sin gridlines pesadas; barras de una sola serie (mismo color que IV).
 */
export function ScoreHistogramChart({ histogram }: { histogram: ScoreHistogram }) {
  const { bins, min, max, mean, median } = histogram
  if (bins.length === 0) return null

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={bins}
          margin={{ top: 16, right: 12, bottom: 4, left: -6 }}
          barCategoryGap={0}
        >
          <CartesianGrid horizontal vertical={false} stroke={GRID_STROKE} />
          <XAxis
            type="number"
            dataKey="center"
            domain={[min, max]}
            tickFormatter={(v: number) => entero(v)}
            tickLine={false}
            axisLine={AXIS_LINE}
            tick={AXIS_TICK}
          />
          <YAxis
            tickFormatter={marca}
            tickLine={false}
            axisLine={false}
            tick={AXIS_TICK}
            width={44}
            allowDecimals={false}
          />
          <Tooltip cursor={CURSOR_FILL} content={<HistTooltip />} />
          <Bar
            dataKey="count"
            name="Frecuencia"
            fill={BAR_PRIMARY}
            radius={[2, 2, 0, 0]}
            isAnimationActive={false}
          />
          {/* Referencias de lectura (media/mediana de la muestra dibujada, no cortes de dominio). */}
          <ReferenceLine
            x={median}
            stroke={BRAND.placeholder}
            strokeDasharray="4 3"
            label={{
              value: `mediana ${entero(median)}`,
              position: "insideBottomRight",
              fill: AXIS_TICK.fill,
              fontSize: 9,
            }}
          />
          <ReferenceLine
            x={mean}
            stroke={BRAND.cyan}
            strokeDasharray="4 3"
            label={{
              value: `media ${entero(mean)}`,
              position: "insideTopLeft",
              fill: BRAND.cyan,
              fontSize: 9,
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
