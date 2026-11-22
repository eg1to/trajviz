import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// VITE_PORT (padrão 5173) e VITE_API_URL (padrão http://localhost:8000, ver src/api/client.ts) vêm do ambiente ou de frontend/.env
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, import.meta.dirname, 'VITE_')
  const port = Number(process.env.VITE_PORT ?? env.VITE_PORT ?? 5173)
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
    server: { port, strictPort: true },
    test: { environment: 'node', include: ['src/**/*.test.ts'] },
  }
})
