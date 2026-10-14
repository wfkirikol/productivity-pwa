import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'Ритм — задачи и финансы',
        short_name: 'Ритм',
        description: 'Задачи, финансы и личные заметки в одном месте.',
        theme_color: '#f3f5ef',
        background_color: '#f3f5ef',
        display: 'standalone',
        start_url: '/',
        icons: [{ src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' }],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
