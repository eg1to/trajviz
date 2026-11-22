import fs from 'node:fs'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'

// Capturas do pôster/README: 1600×1000, tema claro, escala 2×. As amostras vêm de e2e/showcase.json
// (geradas por `uv run python scripts/pick_showcase.py` no backend: escolhidas por loops, ciclos edit→test e gabarito).
const OUT = path.resolve(import.meta.dirname, '..', '..', 'results', 'screenshots')
const API = `http://localhost:${process.env.TRAJVIZ_API_PORT ?? '8011'}`
const showcase = JSON.parse(fs.readFileSync(path.join(import.meta.dirname, 'showcase.json'), 'utf8')) as Record<string, { id: string }>

test.use({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2, colorScheme: 'light' })
test.beforeAll(() => fs.mkdirSync(OUT, { recursive: true }))

async function light(page: Page) { await page.addInitScript(() => { try { localStorage.setItem('trajviz-theme', 'light') } catch { /* */ } }) }
async function shot(page: Page, name: string) { await page.waitForTimeout(700); await page.screenshot({ path: path.join(OUT, `${name}.png`) }) }

async function open(page: Page, sampleId: string) {
  const r = await page.request.post(`${API}/api/library/${sampleId}/open?use_llm=false`)
  expect(r.ok(), await r.text()).toBeTruthy()
  const { id } = await r.json()
  const m = await (await page.request.get(`${API}/api/trajectories/${id}/metrics`)).json()
  return { id, m }
}

async function graphAndDashboard(page: Page, key: string, name: string, pick: (m: any) => { step?: number; range?: [number, number] }) {
  const { id, m } = await open(page, showcase[key].id)
  const sel = pick(m)
  const q = new URLSearchParams()
  if (sel.step != null) q.set('step', String(sel.step))
  if (sel.range) q.set('range', sel.range.join('-'))
  await page.goto(`/t/${id}?${q}`)
  await page.waitForSelector('[data-testid=step-node]')
  await page.evaluate(() => document.querySelectorAll('[data-sonner-toast]').forEach((e) => e.remove()))
  await shot(page, `${name}-grafo`)
  q.set('view', 'dashboard')
  await page.goto(`/t/${id}?${q}`)
  await page.waitForSelector('[data-testid=dashboard-tab]')
  await page.evaluate(() => document.querySelectorAll('[data-sonner-toast]').forEach((e) => e.remove()))
  await shot(page, `${name}-dashboard`)
  const h = await page.evaluate(() => (document.querySelector('[data-testid=dashboard-tab]') as HTMLElement).scrollHeight)
  await page.setViewportSize({ width: 1600, height: Math.min(h + 300, 2600) })
  await shot(page, `${name}-dashboard-completo`)
  await page.setViewportSize({ width: 1600, height: 1000 })
}

test('biblioteca', async ({ page }) => {
  await light(page)
  await page.goto('/')
  await page.waitForSelector('[data-testid=lib-row]')
  await shot(page, '01-biblioteca')
})

test('SWE-rebench resolvida', async ({ page }) => {
  await light(page)
  await graphAndDashboard(page, 'swe_rebench_resolved', '02-swe-rebench-resolvida', (m) => ({ step: m.problems.error.idx?.[0] ?? m.dynamics.first_edit_idx ?? 0 }))
})

test('SWE-rebench não resolvida', async ({ page }) => {
  await light(page)
  await graphAndDashboard(page, 'swe_rebench_unresolved', '03-swe-rebench-nao-resolvida', (m) => {
    const lp = m.problems.loop_ranges?.[0]
    return lp ? { step: lp.range[0], range: [lp.range[0], lp.range[1]] } : { step: m.problems.error.idx?.[0] ?? 0 }
  })
})

test('SWE-smith', async ({ page }) => {
  await light(page)
  await graphAndDashboard(page, 'swe_smith', '04-swe-smith', (m) => ({ step: m.problems.test_fail.idx?.[0] ?? m.dynamics.first_edit_idx ?? 0 }))
})

test('CodeTraceBench com gabarito', async ({ page }) => {
  await light(page)
  await graphAndDashboard(page, 'ctb_gt', '05-ctb-gabarito', (m) => {
    const lp = m.problems.loop_ranges?.[0]
    return { step: m.ground_truth?.incorrect_idx?.[0] ?? 0, range: lp ? [lp.range[0], lp.range[1]] : undefined }
  })
})

test('Ark (trace real do orientador)', async ({ page }) => {
  await light(page)
  await graphAndDashboard(page, 'ark', '06-ark', (m) => ({ step: m.problems.error.idx?.[0] ?? m.problems.test_fail.idx?.[0] ?? 0 }))
})
