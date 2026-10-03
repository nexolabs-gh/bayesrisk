import { readFileSync } from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// @ts-expect-error El plugin Node es JavaScript ESM versionado fuera del proyecto TS del SPA.
import { frontendProvenancePlugin } from '../scripts/frontend_provenance_plugin.mjs'

// Origen de la demo publicada. Es el único sitio del repo donde vive: el `rel=canonical`, el
// `og:url`, el `Sitemap:` de `robots.txt` y el `<loc>` del sitemap tienen que apuntar todos al
// mismo host, y un literal repetido en cuatro archivos es como se llega a un canonical que
// contradice al sitemap.
const DEMO_ORIGEN = 'https://demo.bayesadvisory.cl'

// El título de la demo, distinto del que sirve `docs.bayesadvisory.cl` («bayesrisk — librería
// Python de riesgo de crédito»): los dos sitios son públicos y hasta ahora publicaban el MISMO
// título, así que ningún resultado de búsqueda decía cuál era cuál.
const DEMO_TITULO = 'Demo de bayesrisk — del dataset al informe en una corrida'

// Estáticos que sólo existen en la demo. NO pueden vivir en `public/`: ese directorio se copia a
// los dos bundles, y el del paquete viaja en el wheel bajo una allowlist cerrada
// (`scripts/distribution_contents_allowlist.json`) donde `*.xml` no está admitido y un `robots.txt`
// entraría sin que nada lo note, describiendo un sitio que el launcher local no es.
const DEMO_ESTATICOS = ['robots.txt', 'sitemap.xml'] as const

/**
 * SEO de la demo estática: título propio, URL canónica y los dos estáticos de rastreo.
 *
 * Vive sólo en `--mode demo`. La canónica no aplica al bundle del paquete —corre en `localhost`,
 * no se rastrea y apuntar su HTML a `demo.bayesadvisory.cl` sería falso—, y por eso no se pone en
 * `index.html`, que es compartido.
 */
function demoSeoPlugin(): Plugin {
  return {
    name: 'bayesrisk-demo-seo',
    transformIndexHtml(html) {
      // La descripción se LEE del HTML en vez de copiarse: es la misma que
      // `test_portada_sin_jurisdiccion.py` ata al hero de la landing, y un segundo literal aquí
      // es exactamente cómo las dos versiones se separan sin que ningún gate lo vea.
      const descripcion = /name="description"\s+content="([^"]*)"/.exec(html)?.[1]
      if (!descripcion) {
        throw new Error('web/index.html no declara una meta description que la demo pueda reusar')
      }
      const titulos = html.match(/<title>[^<]*<\/title>/g) ?? []
      if (titulos.length !== 1) {
        throw new Error(`web/index.html declara ${titulos.length} <title>; se esperaba exactamente 1`)
      }
      return {
        html: html.replace(titulos[0], `<title>${DEMO_TITULO}</title>`),
        tags: [
          { tag: 'link', attrs: { rel: 'canonical', href: `${DEMO_ORIGEN}/` }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:type', content: 'website' }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:site_name', content: 'bayesrisk' }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:title', content: DEMO_TITULO }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:description', content: descripcion }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:url', content: `${DEMO_ORIGEN}/` }, injectTo: 'head' },
        ],
      }
    },
    // `emitFile` y no una copia a mano: así los archivos pasan por el bundle —salen en `outDir`
    // sea cual sea `BAYESRISK_DEMO_OUT_DIR`— y `pnpm check:demo-bundle`, que camina el directorio
    // construido, los ve como a cualquier otro output.
    generateBundle() {
      for (const nombre of DEMO_ESTATICOS) {
        this.emitFile({
          type: 'asset',
          fileName: nombre,
          source: readFileSync(path.resolve(__dirname, './demo-public', nombre)),
        })
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const demo = mode === 'demo'
  const demoOutDir = process.env.BAYESRISK_DEMO_OUT_DIR
  return {
    plugins: [
      react(),
      tailwindcss(),
      ...(demo ? [demoSeoPlugin()] : [frontendProvenancePlugin()]),
    ],
    build: {
      modulePreload: { polyfill: false },
      outDir: demo
        ? path.resolve(demoOutDir ?? path.resolve(__dirname, './dist'))
        : path.resolve(__dirname, '../src/bayesrisk/ui/static'),
      emptyOutDir: true,
    },
    resolve: {
      alias: [
        {
          find: '@/lib/demo-runtime',
          replacement: path.resolve(
            __dirname,
            demo ? './src/lib/demo.ts' : './src/lib/demo-disabled.ts',
          ),
        },
        { find: '@', replacement: path.resolve(__dirname, './src') },
      ],
    },
  }
})
