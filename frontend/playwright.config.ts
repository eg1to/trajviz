import path from 'node:path'
import { defineConfig } from '@playwright/test'

const API_PORT = process.env.TRAJVIZ_API_PORT ?? '8011' // 8000 costuma estar ocupada; o front lê VITE_API_URL
const iso = path.resolve(import.meta.dirname, 'test-results')

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: 'http://localhost:5173', viewport: { width: 1600, height: 1000 }, trace: 'retain-on-failure' },
  webServer: [
    { command: `uv run uvicorn app.main:app --port ${API_PORT}`, cwd: '../backend', url: `http://localhost:${API_PORT}/api/health`, reuseExistingServer: false, timeout: 60_000,
      env: { LABEL_LLM_ENABLED: '0', TRAJVIZ_CACHE_DIR: path.join(iso, 'e2e-cache'), TRAJVIZ_RESULTS_DIR: path.join(iso, 'e2e-results') } },
    { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: false, timeout: 60_000, env: { VITE_API_URL: `http://localhost:${API_PORT}` } },
  ],
})
