import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// @ts-expect-error El plugin Node es JavaScript ESM versionado fuera del proyecto TS del SPA.
import { frontendProvenancePlugin } from '../scripts/frontend_provenance_plugin.mjs'

const DEMO_ORIGIN = 'https://demo.bayesadvisory.cl'
const DEMO_TITLE = 'Demo de bayesrisk — modelos de riesgo de crédito'

// Estos metadatos y archivos pertenecen al sitio público, nunca al launcher local ni al wheel.
function demoSeoPlugin(): Plugin {
  return {
    name: 'bayesrisk-demo-seo',
    transformIndexHtml(html) {
      const titles = html.match(/<title>[^<]*<\/title>/g) ?? []
      if (titles.length !== 1) {
        throw new Error('La demo necesita exactamente un título HTML de origen')
      }
      return {
        html: html.replace(titles[0], `<title>${DEMO_TITLE}</title>`),
        tags: [
          { tag: 'link', attrs: { rel: 'canonical', href: `${DEMO_ORIGIN}/` }, injectTo: 'head' },
          { tag: 'meta', attrs: { name: 'robots', content: 'index, follow' }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:type', content: 'website' }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:site_name', content: 'bayesrisk' }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:title', content: DEMO_TITLE }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:url', content: `${DEMO_ORIGIN}/` }, injectTo: 'head' },
        ],
      }
    },
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'robots.txt',
        source: `User-agent: *\nAllow: /\n\nSitemap: ${DEMO_ORIGIN}/sitemap.xml\n`,
      })
      this.emitFile({
        type: 'asset',
        fileName: 'sitemap.xml',
        source: `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>${DEMO_ORIGIN}/</loc></url></urlset>\n`,
      })
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
