import path from 'node:path'
import { defineConfig } from '@playwright/test'

// Mesmas variáveis do app: VITE_PORT (front, padrão 5173) e VITE_API_URL (API; padrão :8011, pois a 8000 costuma estar ocupada).
const WEB_PORT = process.env.VITE_PORT ?? '5173'
const WEB_URL = `http://localhost:${WEB_PORT}`
const API_URL = process.env.VITE_API_URL ?? `http://localhost:${process.env.TRAJVIZ_API_PORT ?? '8011'}`
const API_PORT = new URL(API_URL).port || '80'
const iso = path.resolve(import.meta.dirname, 'test-results')

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: WEB_URL, viewport: { width: 1600, height: 1000 }, trace: 'retain-on-failure' },
  webServer: [
    { command: `uv run uvicorn app.main:app --port ${API_PORT}`, cwd: '../backend', url: `${API_URL}/api/health`, reuseExistingServer: false, timeout: 60_000,
      env: { CORS_ORIGINS: `${WEB_URL},http://127.0.0.1:${WEB_PORT}`, LABEL_LLM_ENABLED: '0', TRAJVIZ_CACHE_DIR: path.join(iso, 'e2e-cache'), TRAJVIZ_RESULTS_DIR: path.join(iso, 'e2e-results') } },
    { command: 'npm run dev', url: WEB_URL, reuseExistingServer: false, timeout: 60_000, env: { VITE_PORT: WEB_PORT, VITE_API_URL: API_URL } },
  ],
})
