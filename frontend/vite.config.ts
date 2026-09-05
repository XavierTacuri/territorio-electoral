import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // The service worker only ever answers precached build assets and the
      // offline app shell fallback. It intentionally declares zero
      // runtimeCaching entries for /api/*: offline-safe GET data (assigned
      // territories, agenda) is cached explicitly by the app in IndexedDB
      // (see src/offline/), namespaced per user/campaign, and mutations are
      // never touched by the service worker at all.
      registerType: 'prompt',
      injectRegister: false,
      manifest: {
        name: 'Territorio Electoral',
        short_name: 'Territorio',
        description: 'Operación de campo territorial para coordinadores.',
        lang: 'es',
        display: 'standalone',
        start_url: '/app',
        scope: '/',
        theme_color: '#244b5a',
        background_color: '#f4f6f7',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icons/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        runtimeCaching: [],
      },
      devOptions: { enabled: false },
    }),
  ],
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: { mui: ['@mui/material'], react: ['react', 'react-dom', 'react-router-dom'] },
      },
    },
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    // Several MSW suites intentionally replace globalThis.fetch; parallel files
    // can otherwise cross-talk and make unrelated HTTP assertions flaky.
    fileParallelism: false,
    exclude: ['tests/e2e/**', 'tests/manual/**', 'node_modules/**'],
  },
});
