/**
 * Símbolo de marca bayesrisk: el monograma «B» de Bayes Advisory, que conserva el trazo y los
 * colores del símbolo anterior (trazo con nodos de entrada; los dos nodos de salida en el color de
 * acento). SVG inline, theme-aware: sobre navy el trazo es blanco y la salida cyan; sobre papel el
 * trazo es navy y la salida azul. Viaja con el bundle (sin request extra) y escala nítido. El
 * tamaño se controla por className.
 */
export function BayesRiskMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role="img"
      aria-label="bayesrisk"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Trazo de la B + nodos de entrada: navy sobre claro, blanco sobre oscuro */}
      <path
        d="M17 12V52H34C47 52 51 45 47 38C45 34 40 32 34 32H17M17 12H32C44 12 49 18 45 25C43 29 38 32 32 32"
        fill="none"
        strokeWidth="5.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-[#051528] dark:stroke-white"
      />
      <g className="fill-[#051528] dark:fill-white">
        <circle cx="17" cy="12" r="4" />
        <circle cx="17" cy="52" r="4" />
      </g>
      {/* Nodos de salida: azul sobre claro, cyan sobre oscuro */}
      <g className="fill-[#1A46B0] dark:fill-brand-cyan">
        <circle cx="46" cy="21" r="4" />
        <circle cx="49" cy="42" r="4" />
      </g>
    </svg>
  )
}
